"""Pure axis-endpoint vision/path preview. No transport, motor or gripper IO."""
import math
from .six_item_catalog import PICK_ITEMS

COLORS = ('red', 'yellow', 'green')
NAMES = {'red': '红色', 'yellow': '黄色', 'green': '绿色'}
SOURCE_SIZE = (480, 270)
DETECTION_SIZE = (1920, 1080)
APPROACH_Y_MM = 220.0
TARGET_Y_MM = 330.0
PICK_X_COMPENSATION_MM = 60.0  # Image-left is increasing base X in this calibration.
PICK_Z_COMPENSATION_MM = 0.0
# Provisional calibration requested on 2026-10-30: full image covers 520x270
# mm at the object plane, 370 mm from the base. Gripping depth is already
# correct, so the shaft target remains Y330. Treat the measured far-left
# point as u=0 and correct its 60 mm image-right error toward image-left.
# The initial trial used base X150 and centre Z235. Field feedback then
# requested 30 mm image-right and 20 mm upward, then another 7 mm right:
# decrease X by 37 and increase Z by 20, retaining the separate X+60.
IMAGE_WIDTH_MM = 520.0
IMAGE_HEIGHT_MM = 270.0
IMAGE_LEFT_X_MM = 113.0
IMAGE_CENTER_Z_MM = 255.0
RELEASE_RULE = dict(reference='gripper_tip', above_box_rim_mm=10.0,
                    axis_endpoint_conversion_confirmed=False, enabled=False)
TEMPORARY_OFFSET_LIMIT_MM = 100.0


def checked_pick_offset(values=None):
    """Immutable image-right/image-up offsets, additional to calibration."""
    if values is None:
        return (0.0, 0.0)
    if (not isinstance(values, (list, tuple)) or len(values) != 2 or any(
            type(v) not in (int, float) or not math.isfinite(v)
            or abs(v) > TEMPORARY_OFFSET_LIMIT_MM for v in values)):
        raise ValueError('临时偏置须为左右、上下两个数值，各在±100mm内')
    return tuple(float(v) for v in values)


def offset_targets(groups, values):
    right, up = checked_pick_offset(values)
    # Source pixels and calibrated endpoints remain unchanged so target
    # freshness/identity and consumed-target matching use the same evidence.
    return {color: [dict(target, endpoint_xyz_mm=[target['endpoint_xyz_mm'][0]-right,
                    target['endpoint_xyz_mm'][1], target['endpoint_xyz_mm'][2]+up],
                    temporary_pick_offset_mm=[right, up]) for target in targets]
            for color, targets in groups.items()}


def quantities(values):
    if not isinstance(values, dict) or set(values) not in (set(COLORS), set(PICK_ITEMS)):
        raise ValueError('请选择三色积木或完整六类物品及各自数量')
    if any(type(value) is not int or not 0 <= value <= 99 for value in values.values()):
        raise ValueError('每种物品数量须为0～99的整数')
    if not any(values.values()):
        raise ValueError('请至少选择一个物品')
    keys = COLORS if set(values) == set(COLORS) else PICK_ITEMS
    return {item: values[item] for item in keys}


def endpoint_from_pixel(uv, source_size=SOURCE_SIZE):
    if tuple(source_size) != SOURCE_SIZE:
        raise ValueError('源图尺寸与480×270标定不符，请重新核对映射')
    if not isinstance(uv, (list, tuple)) or len(uv) != 2:
        raise ValueError('目标像素中心无效')
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in uv):
        raise ValueError('目标像素中心须为有限数值')
    u, v = uv
    if not (0 <= u <= 479 and 0 <= v <= 269):
        raise ValueError('目标不在已标定的源图范围内')
    # User confirmed these are model/J6 output-shaft endpoint coordinates.
    # Do not apply the historical 100 mm / 10 mm gripper installation offset.
    return (IMAGE_LEFT_X_MM - IMAGE_WIDTH_MM*u/479.0, TARGET_Y_MM,
            IMAGE_CENTER_Z_MM + IMAGE_HEIGHT_MM*(0.5-v/269.0))


def axis_route(endpoint):
    if not isinstance(endpoint, (list, tuple)) or len(endpoint) != 3:
        raise ValueError('轴端目标须有XYZ三个坐标')
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in endpoint):
        raise ValueError('轴端目标须为有限数值')
    x, y, z = endpoint
    if abs(y - TARGET_Y_MM) > 1e-6:
        raise ValueError('本次目标平面固定为Y330，不能外推深度')
    return [dict(phase='approach', label='预备点', xyz_mm=[x, APPROACH_Y_MM, z]),
            dict(phase='target', label='前伸定位点', xyz_mm=[x, TARGET_Y_MM, z]),
            dict(phase='retract', label='缩回点', xyz_mm=[x, APPROACH_Y_MM, z])]


def fresh_targets(telemetry, now, expected_session_id=None, pick_offset_mm=None):
    offset = checked_pick_offset(pick_offset_mm)
    if expected_session_id is not None:
        from .coco_grasp_targets import targets_from_coco
        return offset_targets(targets_from_coco(telemetry, expected_session_id, now), offset)
    if isinstance(telemetry, dict) and 'detections' in telemetry:
        raise ValueError('AI抓取结果必须绑定当前识别会话')
    if not isinstance(telemetry, dict) or telemetry.get('state') != 'running':
        raise ValueError('请先开始识别')
    stamp = telemetry.get('timestamp')
    if type(stamp) not in (int, float) or not math.isfinite(stamp) or not 0 <= now-stamp <= 1.2 or not telemetry.get('fresh'):
        raise ValueError('等待新鲜且稳定的识别结果')
    if tuple(telemetry.get('preview_source_size', ())) != SOURCE_SIZE:
        raise ValueError('源图尺寸与480×270标定不符，请重新核对映射')
    groups = {color: [] for color in COLORS}
    seen = set()
    targets = telemetry.get('targets', [])
    if not isinstance(targets, list) or len(targets) > 64:
        raise ValueError('目标列表无效')
    for row in targets:
        if not isinstance(row, dict) or row.get('color') not in COLORS:
            continue
        uv = row.get('center')
        # feature_regions.process reports compact centroids scaled by 4.
        # Undo that producer transform before applying the calibrated map.
        if not isinstance(uv, (list, tuple)) or len(uv) != 2 or any(
                type(v) not in (int, float) or not math.isfinite(v) for v in uv):
            raise ValueError('目标像素中心无效')
        source_uv = [uv[i] * SOURCE_SIZE[i] / DETECTION_SIZE[i] for i in range(2)]
        calibrated_xyz = endpoint_from_pixel(source_uv)
        xyz = [calibrated_xyz[0] + PICK_X_COMPENSATION_MM, calibrated_xyz[1],
               calibrated_xyz[2] + PICK_Z_COMPENSATION_MM]
        track = row.get('track_id')
        if track is not None and type(track) not in (int, str):
            raise ValueError('目标编号无效')
        identity = (row['color'], ('track', track) if track is not None else ('pixel', *uv))
        if identity in seen:
            continue
        seen.add(identity)
        groups[row['color']].append(dict(color=row['color'], track_id=track,
                                        pixel_uv=list(uv), source_pixel_uv=source_uv, calibrated_endpoint_xyz_mm=list(calibrated_xyz),
                                        pick_x_compensation_mm=PICK_X_COMPENSATION_MM,
                                        pick_z_compensation_mm=PICK_Z_COMPENSATION_MM, endpoint_xyz_mm=list(xyz)))
    for values in groups.values():
        values.sort(key=lambda target: tuple(target['pixel_uv']))
    return offset_targets(groups, offset)


def preview_plan(telemetry, requested, now, expected_session_id=None, pick_offset_mm=None):
    requested = quantities(requested)
    groups = fresh_targets(telemetry, now, expected_session_id, pick_offset_mm)
    if set(requested) - set(groups):
        raise ValueError('六类物品任务需要先开启AI识别')
    selected, missing = [], {}
    for color in requested:
        candidates = groups[color][:requested[color]]
        for number, target in enumerate(candidates, 1):
            selected.append(dict(target, same_color_order=number,
                                 route=axis_route(target['endpoint_xyz_mm'])))
        if len(candidates) < requested[color]:
            missing[color] = requested[color] - len(candidates)
    if not selected:
        raise ValueError('所选物品尚无目标，请调整画面或等待识别')
    return dict(schema=1, mode='axis_endpoint_preview', requested=requested, targets=selected,
                missing=missing, temporary_pick_offset_mm=list(checked_pick_offset(pick_offset_mm)),
                source_image_size_px=list(SOURCE_SIZE), detection_coordinate_size_px=list(DETECTION_SIZE),
                snapshot_timestamp=telemetry['captured_at'] if expected_session_id is not None else telemetry['timestamp'], target_frame='model_endpoint',
                tool_offset_applied=False, pick_x_compensation_mm=PICK_X_COMPENSATION_MM,
                pick_z_compensation_mm=PICK_Z_COMPENSATION_MM, orientation_policy='hold_current_orientation',
                approach_y_mm=APPROACH_Y_MM, target_y_mm=TARGET_Y_MM,
                release_rule=dict(RELEASE_RULE),
                deferred_steps=['夹爪开合', '移到指定投放盒', '松开'],
                trajectory_ik_checked=False, allowed_for_motor_motion=False,
                note='Axis-endpoint waypoint preview only; not a collision-checked or executable trajectory.')
