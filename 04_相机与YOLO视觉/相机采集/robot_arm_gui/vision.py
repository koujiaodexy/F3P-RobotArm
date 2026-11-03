"""Shared static-image contour processing; optional dependencies are loaded lazily."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from functools import lru_cache
from typing import Any, List, Optional


@dataclass(frozen=True)
class VisionParameters:
    include_internal: bool = False
    automatic: bool = True
    threshold: int = 128
    blur: int = 3
    min_area: int = 200
    epsilon: float = 2.0


@lru_cache(maxsize=1)
def dependencies():
    import sys
    bundle = Path(__file__).resolve().parent.parent / "vision-deps"
    if bundle.is_dir() and str(bundle) not in sys.path:
        sys.path.insert(0, str(bundle))
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "图像处理需要 OpenCV 和 NumPy。请先安装图像依赖，电机控制仍可正常使用。"
        ) from exc
    return cv2, np


def load_image(filename: str):
    cv2, np = dependencies()
    path = Path(filename)
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("图片文件超过 32 MB，请缩小后重试。")
    image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("图片无法解码，请选择 PNG、JPEG、BMP 或 WebP。")
    height, width = image.shape[:2]
    if width * height > 40_000_000:
        raise ValueError("图片超过 4000 万像素，请缩小后重试。")
    scale = min(1.0, 1600.0 / max(width, height))
    if scale < 1:
        image = cv2.resize(image, (round(width * scale), round(height * scale)),
                           interpolation=cv2.INTER_AREA)
    return {"filename": str(path), "width": width, "height": height, "image": image}


def extract(source: dict, parameters: VisionParameters):
    cv2, np = dependencies()
    if parameters.blur not in (0, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21):
        raise ValueError("去噪强度应为0或1～21的奇数。")
    if not 0 <= parameters.threshold <= 255 or parameters.min_area < 1 or parameters.epsilon <= 0:
        raise ValueError("图像处理参数超出范围。")
    image = source["image"]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if parameters.blur > 0:
        kernel = parameters.blur
        gray = cv2.GaussianBlur(gray, (kernel, kernel), 0)
    flags = cv2.THRESH_BINARY | (cv2.THRESH_OTSU if parameters.automatic else 0)
    threshold, binary = cv2.threshold(gray, parameters.threshold, 255, flags)
    # Choose the object polarity from the perimeter rather than whole-image area.
    border = np.concatenate((binary[0, :], binary[-1, :], binary[1:-1, 0], binary[1:-1, -1]))
    if np.count_nonzero(border) > border.size / 2:
        binary = cv2.bitwise_not(binary)
    retrieval = cv2.RETR_TREE if parameters.include_internal else cv2.RETR_EXTERNAL
    found = cv2.findContours(binary, retrieval, cv2.CHAIN_APPROX_SIMPLE)
    contours, hierarchy = found[-2:]
    working_height, working_width = binary.shape
    sx, sy = source["width"] / working_width, source["height"] / working_height
    paths = []
    kept = {}
    for index, contour in enumerate(contours):
        area = abs(cv2.contourArea(contour)) * sx * sy
        if area < parameters.min_area:
            continue
        full = contour.astype(np.float32)
        full[:, :, 0] *= sx
        full[:, :, 1] *= sy
        simple = cv2.approxPolyDP(full, parameters.epsilon, True).reshape(-1, 2)
        if len(simple) < 3:
            continue
        path_id = len(paths) + 1
        kept[index] = path_id
        paths.append({"id": path_id, "parent_id": None, "closed": True,
                      "area_px2": round(area, 2),
                      "points": [[round(float(x), 3), round(float(y), 3)] for x, y in simple],
                      "_index": index})
        if len(paths) > 1000:
            raise ValueError("轮廓超过 1000 条，请提高最小面积或加强去噪后重试。")
    for path in paths:
        index = path.pop("_index")
        ancestor = int(hierarchy[0][index][3]) if hierarchy is not None else -1
        while ancestor >= 0 and ancestor not in kept:
            ancestor = int(hierarchy[0][ancestor][3])
        path["parent_id"] = kept.get(ancestor)
    return {"source": source, "parameters": asdict(parameters),
            "threshold_used": float(threshold), "binary": binary, "paths": paths,
            "working_size": [working_width, working_height]}


def preview_png(source: dict, result: Optional[dict] = None, mode: str = "original",
                selected: Optional[List[int]] = None) -> bytes:
    cv2, np = dependencies()
    image = source["image"]
    if result is None or mode == "original":
        canvas = image.copy()
    elif mode == "binary":
        canvas = cv2.cvtColor(result["binary"], cv2.COLOR_GRAY2BGR)
    else:
        canvas = image.copy() if mode == "overlay" else np.full_like(image, (32, 18, 11))
        sx = image.shape[1] / source["width"]
        sy = image.shape[0] / source["height"]
        for path in result["paths"]:
            if selected is not None and path["id"] not in selected:
                continue
            points = np.array([[x * sx, y * sy] for x, y in path["points"]], dtype=np.int32)
            cv2.polylines(canvas, [points], True, (255, 211, 89), 2, cv2.LINE_AA)
            cv2.circle(canvas, tuple(points[0]), 4, (161, 225, 112), -1)
    factor = min(1.0, 900 / canvas.shape[1], 460 / canvas.shape[0])
    if factor < 1:
        canvas = cv2.resize(canvas, (max(1, round(canvas.shape[1] * factor)),
                                     max(1, round(canvas.shape[0] * factor))))
    ok, encoded = cv2.imencode(".png", canvas)
    if not ok:
        raise ValueError("预览图生成失败。")
    return encoded.tobytes()


def export_paths(result: dict, selected: List[int], filename: str, format: str) -> None:
    source = result["source"]
    paths = [p for p in result["paths"] if p["id"] in selected]
    if not paths:
        raise ValueError("请至少选择一条轮廓。")
    if format == "json":
        payload = {"version": 1, "unit": "px", "origin": "top-left", "x_axis": "right",
                   "y_axis": "down", "width": source["width"], "height": source["height"],
                   "source_file": Path(source["filename"]).name,
                   "working_size": result["working_size"],
                   "parameters": result["parameters"], "threshold_used": result["threshold_used"],
                   "paths": paths}
        content = json.dumps(payload, ensure_ascii=False, indent=2)
    elif format == "svg":
        elements = []
        for path in paths:
            pairs = [f"{x},{y}" for x, y in path["points"]]
            elements.append(f'<path id="contour-{path["id"]}" d="M {pairs[0]} L '
                            + " L ".join(pairs[1:]) + ' Z"/>')
        content = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {source["width"]} '
                   f'{source["height"]}" fill="none" stroke="black" stroke-width="1">\n'
                   + "\n".join(elements) + "\n</svg>\n")
    else:
        raise ValueError("不支持的导出格式。")
    Path(filename).write_text(content, encoding="utf-8")


class VisionSession:
    """UI-thread state with worker results accepted only at the matching revision."""

    def __init__(self, deliver):
        self.deliver = deliver
        self.source = None
        self.result = None
        self.revision = 0
        self.busy = False
        self.closed = False

    def invalidate(self):
        self.revision += 1
        self.result = None

    def start(self, filename=None, parameters=None, frame=None):
        import threading
        if self.busy:
            return
        self.invalidate()
        self.busy = True
        revision = self.revision
        source = self.source
        loaded = filename is not None or frame is not None

        def work():
            try:
                if frame is not None:
                    value = {'filename': 'camera-snapshot', 'width': frame.shape[1],
                             'height': frame.shape[0], 'image': frame}
                else:
                    value = load_image(filename) if filename else extract(source, parameters)
                png = preview_png(value if loaded else source, None if loaded else value,
                                  "original" if loaded else "overlay")
                if not self.closed:
                    self.deliver((revision, loaded, value, png, None))
            except Exception as exc:
                if not self.closed:
                    self.deliver((revision, loaded, None, None, str(exc)))
        threading.Thread(target=work, daemon=True, name="f3p-vision").start()

    def accept(self, completion):
        revision, loaded, value, png, error = completion
        self.busy = False
        if self.closed or revision != self.revision:
            return "stale"
        if error:
            return error
        if loaded:
            self.source = value
        else:
            self.result = value
        return None
