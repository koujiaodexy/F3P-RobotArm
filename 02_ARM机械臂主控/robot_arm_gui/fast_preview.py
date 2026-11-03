"""Requested geometry is displayed separately from validated rolling frames."""
from . import kinematics as k
from .collision import check_target

def attach_geometry(report,start,goal,via):
    from .fast_trajectory import _path_geometry
    origin=k.forward(start)['position_mm']
    point,length,_=_path_geometry(origin,goal['position_mm'],'line' if report['mode']=='L' else 'arc',via if report['mode']=='C' else None)
    if report['mode']=='C':
        from .cartesian_planner import circle
        check_target([0.,0.,circle(origin,via,goal['position_mm'])['minimum_z_mm']])
    points=[point(i/64) for i in range(65)]
    for xyz in points:check_target(xyz)
    report['requested_path_xyz_mm']=points
    report['preview_scope']='validated_start_and_brake_with_background_path'
    report['warning']='起步轨迹和备用制动段已校验；整段由后台继续规划。蓝线为请求路径，不代表整段已通过；后续失败时沿已校验备用段停车。'
    if report['native_report'].get('complete_before_start'):
        report['preview_scope']='complete_path_validated'
        report['warning']='整段路径、量化指令和前视插值已校验；执行时保持起点朝向。'
