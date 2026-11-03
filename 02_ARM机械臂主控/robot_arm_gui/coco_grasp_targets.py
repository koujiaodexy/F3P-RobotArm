"""Validate six-class NPU reports and reuse the established pick-plane map.

This is a stateless target adapter, not a motion command or a multi-frame
confirmation tracker. Call it only when a stopped robot is ready to pick.
"""
import math

from .coco_objects import checked_report
from .six_item_catalog import CLASS_ID_TO_ITEM, MODEL_CLASS_IDS, MODEL_NAMES, PICK_ITEMS

CONFIDENCE_THRESHOLD = .30
MAX_CAPTURE_AGE_SECONDS = 1.2


class CocoFrameNotReady(ValueError):
    """A structurally valid capture is too old to select for a new pick."""


def targets_from_coco(report, expected_session_id, now):
    """Return the original grasp-target shape grouped by six task item keys.

    COCO boxes already use the calibrated 480x270 image coordinates. Only the
    compatibility ``pixel_uv`` field is multiplied by four, preserving the
    existing 20-pixel refresh/consumed-target tolerance; mapping never divides
    the COCO centre a second time. No persistent track ID is fabricated.
    """
    from .grasp_preview import (DETECTION_SIZE, SOURCE_SIZE, endpoint_from_pixel,
                                PICK_X_COMPENSATION_MM, PICK_Z_COMPENSATION_MM)
    if not isinstance(expected_session_id, str) or not expected_session_id:
        raise ValueError('本次AI识别会话无效')
    if not isinstance(report, dict) or report.get('session_id') != expected_session_id:
        raise ValueError('AI识别结果不属于本次会话')
    if type(now) not in (int, float) or not math.isfinite(now):
        raise ValueError('抓取检查时间无效')
    captured = report.get('captured_at')
    if (type(captured) not in (int, float) or not math.isfinite(captured)
            or now-captured < 0):
        raise ValueError('AI图像采集时间无效')
    size = report.get('source_size')
    if not isinstance(size, (list, tuple)) or tuple(size) != SOURCE_SIZE:
        raise ValueError('AI源图尺寸与480×270标定不符')
    selection = report.get('class_selection')
    if (not isinstance(selection, dict) or selection.get('class_count') != 6
            or selection.get('class_ids') != list(MODEL_CLASS_IDS)
            or selection.get('names') != list(MODEL_NAMES)):
        raise ValueError('全自动夹取需要当前六类AI模型')
    evidence = report.get('npu')
    if (report.get('backend') not in ('Alnpu', 'Alnpu+CpuRef')
            or report.get('motion_enabled') is not False
            or not isinstance(evidence, dict)
            or type(evidence.get('hard_irq')) is not int or evidence['hard_irq'] <= 0
            or type(evidence.get('hard_workloads')) is not int or evidence['hard_workloads'] <= 0):
        raise ValueError('缺少本帧硬NPU识别证据')
    raw = report.get('detections')
    if not isinstance(raw, list) or any(not isinstance(row, dict)
            or type(row.get('class_id')) is not int
            or row['class_id'] not in CLASS_ID_TO_ITEM for row in raw):
        raise ValueError('AI结果含本次六类以外的目标')
    # Validate the full report before treating an old capture as a normal wait.
    # A bad session/NPU result must not be silently hidden behind its age.
    completed = report.get('completed_at', captured)
    if (type(completed) not in (int, float) or not math.isfinite(completed)
            or not 0 <= completed-captured <= 20. or completed > now):
        raise ValueError('AI图像完成时间无效')
    rows = checked_report(report, expected_session_id, completed,
                          maximum_age=MAX_CAPTURE_AGE_SECONDS)
    if now-captured > MAX_CAPTURE_AGE_SECONDS:
        raise CocoFrameNotReady('等待1.2秒内的新AI图像；未使用旧图抓取')
    groups = {item: [] for item in PICK_ITEMS}
    seen = set()
    for row in rows:
        if row['confidence'] < CONFIDENCE_THRESHOLD:
            continue
        item = CLASS_ID_TO_ITEM[row['class_id']]
        source_uv = list(row['center'])
        identity = (item, *source_uv)
        if identity in seen:
            continue
        seen.add(identity)
        calibrated = endpoint_from_pixel(source_uv, source_size=report['source_size'])
        endpoint = [calibrated[0] + PICK_X_COMPENSATION_MM, calibrated[1],
                    calibrated[2] + PICK_Z_COMPENSATION_MM]
        pixel_uv = [source_uv[i] * DETECTION_SIZE[i] / SOURCE_SIZE[i] for i in range(2)]
        groups[item].append(dict(color=item, class_id=row['class_id'], track_id=None,
                                 confidence=row['confidence'], bbox_xyxy=list(row['bbox_xyxy']),
                                 pixel_uv=pixel_uv, source_pixel_uv=source_uv,
                                 calibrated_endpoint_xyz_mm=list(calibrated),
                                 endpoint_xyz_mm=endpoint,
                                 pick_x_compensation_mm=PICK_X_COMPENSATION_MM,
                                 pick_z_compensation_mm=PICK_Z_COMPENSATION_MM,
                                 source='coco_npu', source_frame_id=report['frame_id'],
                                 captured_at=captured, session_id=expected_session_id))
    for targets in groups.values():
        targets.sort(key=lambda target: tuple(target['pixel_uv']))
    return groups
