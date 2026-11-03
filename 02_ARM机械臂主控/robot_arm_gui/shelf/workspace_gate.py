"""Bind targets to the frozen arm reference without planning on camera frames.

The existing grasp executor is the sole full-path preflight. A camera candidate
only allows stopping and requesting that executor, never bypassing its checks.
"""
import copy
import hashlib
import json


class GraspWorkspace:
    def __init__(self,start_model,bounds,pick_rotation,reference_id,check=lambda:None):
        if not isinstance(reference_id,str) or not reference_id:
            raise ValueError('Require versioned live arm zero/calibration reference ID')
        self.start=copy.deepcopy(start_model);self.bounds=copy.deepcopy(bounds)
        self.rotation=copy.deepcopy(pick_rotation);self.check=check
        from robot_arm_gui.kinematics import GEOMETRY_VERSION
        payload=dict(start=self.start,bounds=self.bounds,conditional_rule=getattr(bounds,'rule',None),
                     rotation=self.rotation,reference_id=reference_id,geometry=GEOMETRY_VERSION)
        self.context_id=hashlib.sha256(json.dumps(payload,sort_keys=True,allow_nan=False).encode()).hexdigest()

    def __call__(self,target):
        self.check()
        return dict(target_candidate=True,workspace_context=self.context_id,
                    workspace_check='reference_bound_only_path_checked_by_existing_grasp')
