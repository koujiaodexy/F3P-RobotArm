"""Standard-library FK/IK for an explicitly defined reference six-axis model.

Craig modified DH, column vectors: Rx(alpha) Tx(a) Rz(theta) Tz(d),
theta = model_joint + offset_sign * geometry_offset. Reference offset_sign=-1.
Original pyd strings identify alpha/a with i-1, but its executable algorithm was
not recovered or run. URDF zero-axis orientation supports this convention;
its differing geometry is deliberately NOT mixed with the user-selected lengths.

Model joint angle, current-zero motor angle, geometric offset and physical TCP
are separate quantities. The reference profile permits preview only. A solver
success proves an endpoint pose, not collision-free or constant-TCP travel.
Compatible with Python 3.8; no numpy, binary SDK, hardware or background thread.
"""
import copy
import hashlib
import json
import math
import sys
from pathlib import Path


class KinematicsError(ValueError):
    pass


class CalibrationError(KinematicsError):
    pass


class UnreachableTarget(KinematicsError):
    """No valid solution found within the configured bounded numerical search."""
    pass


def _vector(values, count, name):
    if not isinstance(values, (list, tuple)) or len(values) != count:
        raise KinematicsError('%s must contain %d numbers' % (name, count))
    result=[]
    for value in values:
        kind=type(value)
        # Most FK inputs are plain floats. Keep subclass acceptance and bool
        # rejection identical while validating/converting in a single pass.
        if ((kind is not float and kind is not int and
             (isinstance(value,bool) or not isinstance(value,(int,float)))) or
                not math.isfinite(value)):
            raise KinematicsError('%s must contain finite numbers' % name)
        result.append(float(value))
    return result


def _identity():
    return [[float(i == j) for j in range(4)] for i in range(4)]


def _multiply(a, b):
    if len(a)==3 and len(b)==3 and len(b[0])==3:
        # Rotation products dominate pose verification; retain the generic
        # branch for homogeneous and other matrix dimensions.
        b00,b01,b02=b[0][:3];b10,b11,b12=b[1][:3];b20,b21,b22=b[2][:3]
        result=[]
        for row in a:
            a0,a1,a2=row[:3]
            result.append([a0*b00+a1*b10+a2*b20,
                           a0*b01+a1*b11+a2*b21,
                           a0*b02+a1*b12+a2*b22])
        return result
    return [[sum(a[i][k]*b[k][j] for k in range(len(b))) for j in range(len(b[0]))] for i in range(len(a))]


def _transpose(a):
    return [list(row) for row in zip(*a)]


def _cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def _norm(v):
    return math.sqrt(sum(x*x for x in v))


def _rotation(t):
    return [row[:3] for row in t[:3]]


def _validate_transform(value, name='transform'):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise KinematicsError('%s must be 4x4' % name)
    t = [_vector(row, 4, name) for row in value]
    if max(abs(t[3][i]-[0,0,0,1][i]) for i in range(4)) > 1e-9:
        raise KinematicsError('%s has an invalid homogeneous last row' % name)
    r00,r01,r02=t[0][:3];r10,r11,r12=t[1][:3];r20,r21,r22=t[2][:3]
    # R^T R is symmetric: these are all six independent entries, not a
    # reduced validity criterion. Each input row was fully validated above.
    orthogonal_error=max(abs(r00*r00+r10*r10+r20*r20-1),
                         abs(r01*r01+r11*r11+r21*r21-1),
                         abs(r02*r02+r12*r12+r22*r22-1),
                         abs(r00*r01+r10*r11+r20*r21),
                         abs(r00*r02+r10*r12+r20*r22),
                         abs(r01*r02+r11*r12+r21*r22))
    determinant=(r00*(r11*r22-r12*r21)+r01*(r12*r20-r10*r22)+
                 r02*(r10*r21-r11*r20))
    if orthogonal_error > 1e-6 or abs(determinant-1) > 1e-6:
        raise KinematicsError('%s rotation must be in SO(3)' % name)
    return t


def rpy_to_matrix(rpy_deg):
    """Return Rz(yaw) Ry(pitch) Rx(roll); input order is roll,pitch,yaw."""
    roll, pitch, yaw = [math.radians(v % 360.0) for v in _vector(rpy_deg,3,'rpy_deg')]
    cr,sr,cp,sp,cy,sy = math.cos(roll),math.sin(roll),math.cos(pitch),math.sin(pitch),math.cos(yaw),math.sin(yaw)
    return [[cy*cp,cy*sp*sr-sy*cr,cy*sp*cr+sy*sr],
            [sy*cp,sy*sp*sr+cy*cr,sy*sp*cr-cy*sr],[-sp,cp*sr,cp*cr]]


def matrix_to_rpy(matrix):
    """Return one RzRyRx representation; at gimbal lock choose roll=0.

    Euler components are for display/input, never used as IK residuals.
    """
    if len(matrix) == 4:
        r = _rotation(_validate_transform(matrix))
    else:
        t = _identity()
        if len(matrix) != 3:
            raise KinematicsError('rotation must be 3x3 or transform 4x4')
        for i in range(3):
            t[i][:3] = _vector(matrix[i],3,'rotation')
        r = _rotation(_validate_transform(t))
    pitch = math.atan2(-r[2][0], math.hypot(r[0][0],r[1][0]))
    if abs(math.cos(pitch)) > 1e-8:
        roll, yaw = math.atan2(r[2][1],r[2][2]), math.atan2(r[1][0],r[0][0])
    else:
        roll, yaw = 0.0, math.atan2(-r[0][1],r[1][1])
    return [math.degrees(v) for v in (roll,pitch,yaw)]


def _rotation_log(r):
    """SO(3) logarithm via a normalized quaternion, robust at 180 degrees."""
    trace = sum(r[i][i] for i in range(3))
    if trace > 0:
        s = 2*math.sqrt(max(0.0, trace+1))
        w,x,y,z = s/4,(r[2][1]-r[1][2])/s,(r[0][2]-r[2][0])/s,(r[1][0]-r[0][1])/s
    else:
        i = max(range(3),key=lambda k:r[k][k]); j=(i+1)%3; k=(i+2)%3
        s = 2*math.sqrt(max(1e-30,1+r[i][i]-r[j][j]-r[k][k]))
        v = [0.0]*3;v[i]=s/4;v[j]=(r[i][j]+r[j][i])/s;v[k]=(r[i][k]+r[k][i])/s
        w=(r[k][j]-r[j][k])/s;x,y,z=v
    length = math.sqrt(w*w+x*x+y*y+z*z)
    w,x,y,z = [v/length for v in (w,x,y,z)]
    if w < 0:
        w,x,y,z = -w,-x,-y,-z
    n = math.sqrt(x*x+y*y+z*z)
    if n < 1e-12:
        return [2*x,2*y,2*z]
    scale = 2*math.atan2(n,max(0.0,w))/n
    return [scale*x,scale*y,scale*z]


def pose_error(current, target):
    """Return (translation mm, base-frame SO(3) rotation-vector radians)."""
    current, target = _validate_transform(current), _validate_transform(target)
    return ([target[i][3]-current[i][3] for i in range(3)],
            _rotation_log(_multiply(_rotation(target),_transpose(_rotation(current)))))


def _solve_linear(a, b):
    """Small pivoted Gaussian solve; damping makes the normal matrix positive."""
    size=len(b); rows=[list(a[i])+[b[i]] for i in range(size)]
    for i in range(size):
        pivot=max(range(i,size),key=lambda j:abs(rows[j][i]))
        if abs(rows[pivot][i]) < 1e-16:
            raise ArithmeticError('singular damped normal matrix')
        rows[i],rows[pivot]=rows[pivot],rows[i]
        divisor=rows[i][i]
        for k in range(i,size+1):rows[i][k]/=divisor
        for j in range(size):
            if j == i:continue
            factor=rows[j][i]
            for k in range(i,size+1):rows[j][k]-=factor*rows[i][k]
    return [rows[i][-1] for i in range(size)]


def _continuous_joints(value):
    if not isinstance(value,(list,tuple)) or any(type(n) is not int or not 1<=n<=6 for n in value):
        raise KinematicsError('continuous_joints must contain joint numbers 1 through 6')
    if len(set(value))!=len(value):
        raise KinematicsError('continuous_joints must not contain duplicates')
    return tuple(sorted(value))


def _limits(value, continuous_joints=()):
    if isinstance(value,dict):
        try:value=[value[n] if n in value else value[str(n)] for n in range(1,7)]
        except KeyError:raise KinematicsError('limits must explicitly include all six joints')
    if not isinstance(value,(list,tuple)) or len(value)!=6:
        raise KinematicsError('limits must contain six intervals or explicitly continuous null entries')
    result=[]
    for node,row in enumerate(value,1):
        if row is None:
            if node not in continuous_joints:
                raise KinematicsError('joint %d has null limits without an explicit continuous declaration' % node)
            result.append(None)
        else:
            low,high=_vector(row,2,'joint limit')
            if low>=high or high-low>7200:
                raise KinematicsError('joint limits must be ordered finite intervals at most 7200 degrees wide')
            result.append([low,high])
    return result


def _nearest_equivalent(angle, low, high, reference):
    first=math.ceil((low-angle)/360.0-1e-12);last=math.floor((high-angle)/360.0+1e-12)
    if first<=last:
        k=max(first,min(last,round((reference-angle)/360.0)))
        return max(low,min(high,angle+360*k))
    return max(low,min(high,angle))


def _halton(index, base):
    result=0.0;fraction=1.0
    while index:
        fraction/=base;result+=fraction*(index%base);index//=base
    return result


class ArmModel:
    def __init__(self, profile=None):
        if profile is None:profile=Path(__file__).with_name('reference_arm.json')
        if isinstance(profile,(str,Path)):
            try:profile=json.loads(Path(profile).read_text(encoding='utf-8'))
            except (ValueError,OSError) as exc:raise KinematicsError('cannot load arm profile: %s' % exc)
        if not isinstance(profile,dict):raise KinematicsError('profile must be a dictionary or JSON path')
        self._profile=copy.deepcopy(profile)
        p=self._profile
        if p.get('schema')!=1:raise KinematicsError('unsupported arm profile schema')
        try:
            g=p['geometry'];m=p['motor_mapping'];s=p['solver']
            if g['convention']!='craig_modified_dh':raise KinematicsError('unsupported transform convention')
            self._d=_vector(g['d_mm'],6,'d_mm');self._a=_vector(g['a_mm'],6,'a_mm')
            self._alpha=_vector(g['alpha_deg'],6,'alpha_deg')
            self._offsets=_vector(g['joint_offsets_deg'],6,'joint_offsets_deg')
            self._offset_sign=g['offset_sign']
            if type(self._offset_sign) is not int or self._offset_sign not in (-1,1):raise KinematicsError('offset_sign must be -1 or +1')
            self._ratios=_vector(m['ratios'],6,'ratios');self._directions=_vector(m['directions'],6,'directions')
            self._motor_ref=_vector(m['motor_reference_deg'],6,'motor_reference_deg')
            self._joint_ref=_vector(m['joint_reference_deg'],6,'joint_reference_deg')
            if m['units']!='motor_degrees' or any(r<=0 for r in self._ratios) or any(d not in (-1,1) for d in self._directions):
                raise KinematicsError('invalid motor mapping')
            self._continuous_joints=_continuous_joints(p.get('continuous_joints',[]))
            self._limits=_limits(p['joint_limits_deg'],self._continuous_joints)
            if any(self._limits[node-1] is not None for node in self._continuous_joints):
                raise KinematicsError('continuous joints must have null physical limits')
            self._position_tolerance=float(s['position_tolerance_mm']);self._orientation_tolerance=math.radians(float(s['orientation_tolerance_deg']))
            self._scale=float(s['orientation_scale_mm']);self._step=math.radians(float(s['max_step_deg']))
            self._iterations=s['max_iterations'];self._seeds=s['max_seeds']
            if not all(math.isfinite(v) and v>0 for v in (self._position_tolerance,self._orientation_tolerance,self._scale,self._step)):
                raise KinematicsError('invalid solver tolerance/scale/step')
            if not (type(self._iterations) is int and 1<=self._iterations<=1000 and type(self._seeds) is int and 1<=self._seeds<=64):
                raise KinematicsError('solver iteration/seed limits invalid')
            if type(p['reference_only']) is not bool or any(type(p['calibration'][k]) is not bool for k in ('geometry','motor_mapping','joint_limits','tcp')):
                raise KinematicsError('calibration flags must be boolean')
            if p['target_frame'] not in ('model_endpoint','physical_tcp'):raise KinematicsError('unknown target frame')
            self._tcp=None if p['model_endpoint_to_tcp'] is None else _validate_transform(p['model_endpoint_to_tcp'],'model_endpoint_to_tcp')
            if p['target_frame']=='physical_tcp' and self._tcp is None:
                raise CalibrationError('physical TCP transform is not configured')
        except KeyError as exc:raise KinematicsError('missing profile field: %s' % exc)
        except (TypeError,OverflowError) as exc:raise KinematicsError('invalid profile field: %s' % exc)
        try:canonical=json.dumps(p,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)
        except ValueError as exc:raise KinematicsError('profile contains non-finite JSON data: %s' % exc)
        self.profile_digest=hashlib.sha256(canonical.encode('utf-8')).hexdigest()
        self.last_solve={}

    @property
    def profile(self):return copy.deepcopy(self._profile)
    @property
    def reference_only(self):return self._profile['reference_only']
    @property
    def target_frame(self):return self._profile['target_frame']
    @property
    def continuous_joints(self):
        """One-based joint numbers explicitly declared to have no physical bounds."""
        return self._continuous_joints
    @property
    def joint_limits_deg(self):
        """Physical intervals; None denotes an explicitly continuous joint."""
        return copy.deepcopy(self._limits)

    def calibration_errors(self, require_tcp=False):
        errors=[]
        if self.reference_only:errors.append('reference profile is not calibrated for live motion')
        for key in ('geometry','motor_mapping','joint_limits'):
            if not self._profile['calibration'][key]:errors.append('%s calibration is missing' % key)
        if self._profile.get('joint_limits_kind')!='calibrated_physical':
            errors.append('bounded physical joint limits must be calibrated and continuous joints explicitly declared')
        if require_tcp or self.target_frame=='physical_tcp':
            if self._tcp is None:errors.append('physical TCP transform is missing')
            if not self._profile['calibration']['tcp']:errors.append('physical TCP calibration is missing')
        return errors

    def require_calibrated(self, require_tcp=False):
        errors=self.calibration_errors(require_tcp)
        if errors:raise CalibrationError('; '.join(errors))

    def motor_to_joints(self,motor_deg):
        motor=_vector(motor_deg,6,'motor_deg')
        return [q+d*(value-m)/r for value,m,q,d,r in zip(motor,self._motor_ref,self._joint_ref,self._directions,self._ratios)]

    def joints_to_motor(self,joints_deg):
        joints=_vector(joints_deg,6,'joints_deg')
        return [m+d*r*(value-q) for value,m,q,d,r in zip(joints,self._motor_ref,self._joint_ref,self._directions,self._ratios)]

    def _forward_chain(self,joints_deg,include_frames):
        """Equivalent Craig MDH recurrence, without homogeneous intermediates.

        For every axis: origin=p+a*R[:,0], axis=(R*Rx(alpha))[:,2],
        p_new=origin+d*axis and R_new=R*Rx(alpha)*Rz(theta). Forward-only
        callers do not allocate joint frame lists used by the Jacobian.
        """
        q=_vector(joints_deg,6,'joints_deg')
        rotation=[[1.0,0.0,0.0],[0.0,1.0,0.0],[0.0,0.0,1.0]]
        position=[0.0,0.0,0.0]
        if include_frames:
            axes=[];origins=[];points=[list(position)]
        for i in range(6):
            alpha=math.radians(self._alpha[i]%360.0)
            ca,sa=math.cos(alpha),math.sin(alpha)
            theta=math.radians((q[i]+self._offset_sign*self._offsets[i])%360.0)
            ct,st=math.cos(theta),math.sin(theta)
            a,d=self._a[i],self._d[i]
            next_rotation=[];next_position=[]
            if include_frames:
                axis=[];origin=[]
            for k,(r0,r1,r2) in enumerate(rotation):
                transverse=ca*r1+sa*r2
                axial=-sa*r1+ca*r2
                offset=position[k]+a*r0
                next_rotation.append([ct*r0+st*transverse,-st*r0+ct*transverse,axial])
                next_position.append(offset+d*axial)
                if include_frames:
                    axis.append(axial);origin.append(offset)
            rotation,position=next_rotation,next_position
            if include_frames:
                axes.append(axis);origins.append(origin);points.append(list(position))
        t=[rotation[i]+[position[i]] for i in range(3)]+[[0.0,0.0,0.0,1.0]]
        if self.target_frame=='physical_tcp':t=_multiply(t,self._tcp)
        if include_frames:return t,axes,origins,points
        return t

    def _chain(self,joints_deg):
        return self._forward_chain(joints_deg,True)

    def forward(self,joints_deg):
        return self._forward_chain(joints_deg,False)

    def joint_origins(self,joints_deg):
        """Seven model chain nodes, base plus each MDH frame; excludes extra TCP."""
        return self._chain(joints_deg)[3]

    def _residual(self,t,target):
        position=[target[i][3]-t[i][3] for i in range(3)]
        rotation=_rotation_log(_multiply(_rotation(target),_transpose(_rotation(t))))
        return [v/self._scale for v in position]+rotation, _norm(position), _norm(rotation)

    def _iterate(self,start,target,limits):
        q=list(start);damping=0.02;best=(float('inf'),list(q),None)
        for iteration in range(self._iterations):
            t,axes,origins,_=self._chain(q)
            error,position_error,orientation_error=self._residual(t,target)
            cost=sum(v*v for v in error)
            if cost<best[0]:best=(cost,list(q),(position_error,orientation_error,iteration+1))
            if position_error<=self._position_tolerance and orientation_error<=self._orientation_tolerance:
                return list(q),best[2]
            endpoint=[t[i][3] for i in range(3)]
            columns=[]
            for axis,origin in zip(axes,origins):
                linear=_cross(axis,[endpoint[i]-origin[i] for i in range(3)])
                columns.append([v/self._scale for v in linear]+axis)
            j=_transpose(columns)
            normal=[[sum(j[k][i]*j[k][h] for k in range(6)) for h in range(6)] for i in range(6)]
            gradient=[sum(j[k][i]*error[k] for k in range(6)) for i in range(6)]
            for i in range(6):normal[i][i]+=damping*damping
            try:step=_solve_linear(normal,gradient)
            except ArithmeticError:break
            maximum=max(abs(v) for v in step)
            if maximum>self._step:step=[v*self._step/maximum for v in step]
            improved=False
            for scale in (1.0,0.5,0.25,0.125,0.0625):
                candidate=[max(lo,min(hi,value+math.degrees(delta)*scale)) for value,delta,(lo,hi) in zip(q,step,limits)]
                trial=self._residual(self.forward(candidate),target)[0]
                trial_cost=sum(v*v for v in trial)
                # A fixed cost floor can reject valid progress just outside a
                # strict Cartesian tolerance. Scale the roundoff guard with
                # the current squared residual; pose tolerances remain the
                # sole convergence criterion, and iteration bounds still hold.
                if cost-trial_cost > 8*sys.float_info.epsilon*cost:
                    q=candidate;damping=max(1e-5,damping*0.7);improved=True;break
            if not improved:
                damping=min(100,damping*4)
                if damping>=100 or maximum<1e-10:break
        return None,best

    def solve(self,position_mm,rpy_deg,seed_deg,limits_deg=None):
        position=_vector(position_mm,3,'position_mm');seed=_vector(seed_deg,6,'seed_deg')
        rotation=rpy_to_matrix(rpy_deg)
        physical_limits=self.joint_limits_deg if limits_deg is None else _limits(limits_deg,self._continuous_joints)
        # A continuous rotary joint has infinitely many equivalent orientations.
        # Search one full turn around the measured seed, not around global zero.
        # This finite numerical window is not a physical joint limit; retaining
        # the seed's turn count prevents a +179 to -179 target making a long turn.
        limits=[[reference-180.0,reference+180.0] if interval is None else interval
                for interval,reference in zip(physical_limits,seed)]
        radius=sum(abs(v) for v in self._a+self._d)
        if self.target_frame=='physical_tcp':radius+=_norm([self._tcp[i][3] for i in range(3)])
        if _norm(position)>radius+self._position_tolerance:
            raise UnreachableTarget('target exceeds conservative model reach bound')
        target=[rotation[i]+[position[i]] for i in range(3)]+[[0,0,0,1]]
        starts=[]
        def add(values):
            candidate=[_nearest_equivalent(v,lo,hi,ref) for v,(lo,hi),ref in zip(values,limits,seed)]
            if not any(max(abs(a-b) for a,b in zip(candidate,old))<1e-6 for old in starts):starts.append(candidate)
        add(seed);add([0]*6);add([(lo+hi)/2 for lo,hi in limits])
        for offsets in ((0,35,-55,0,30,0),(0,-35,55,0,-30,0),(0,0,0,180,-90,180)):
            add([a+b for a,b in zip(seed,offsets)])
        for index in range(1,self._seeds+1):
            add([lo+(hi-lo)*_halton(index,base) for (lo,hi),base in zip(limits,(2,3,5,7,11,13))])
        best_cost=float('inf');best_error=None;attempts=0
        for start in starts[:self._seeds]:
            attempts+=1;solution,detail=self._iterate(start,target,limits)
            if solution is not None:
                solution=[_nearest_equivalent(v,lo,hi,ref) for v,(lo,hi),ref in zip(solution,limits,seed)]
                _,pe,oe=self._residual(self.forward(solution),target)
                if pe<=self._position_tolerance and oe<=self._orientation_tolerance:
                    self.last_solve={'converged':True,'seed_attempts':attempts,'iterations':detail[2],
                        'position_error_mm':pe,'orientation_error_deg':math.degrees(oe),'target_frame':self.target_frame}
                    return solution
            elif detail[0]<best_cost:best_cost=detail[0];best_error=detail[2]
        self.last_solve={'converged':False,'seed_attempts':attempts,'best_residual':best_error,'target_frame':self.target_frame}
        raise UnreachableTarget('no limit-valid IK solution found in %d bounded seed attempts; this is not a proof of global infeasibility' % attempts)