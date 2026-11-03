#include "parking_core.h"
#include "motor_config.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>
static const int enc_sign[2]={ENCODER_LEFT_DIR,ENCODER_RIGHT_DIR};
static const int motor_sign[2]={MOTOR_LEFT_DIR,MOTOR_RIGHT_DIR};
static const PidGains gains={SPEED_PID_KP,SPEED_PID_KI,SPEED_PID_KD,0};
static double wrap(double a){return a-360.0*floor((a+180.0)/360.0);}
static int active(const ParkingState *s){return s->phase==PARK_RUN||s->phase==PARK_SETTLE;}
unsigned Parking_StepCount(const ParkingState *s){return s->config.route_mode>=2?1:s->config.route_mode?7:4;}
int Parking_IsTurn(const ParkingState *s){if(s->config.route_mode==3)return s->segment_kind==1;if(s->config.route_mode==2)return 0;return s->config.route_mode?(s->step==1||s->step==3||s->step==5):(s->step==0||s->step==2);}
double Parking_TurnDirection(const ParkingState *s){if(s->config.route_mode==3)return s->segment_sign;return s->config.route_mode?(s->step==5?-1.:1.):(s->step==0?1.:-1.);}
double Parking_Target(const ParkingState *s){
 if(s->config.route_mode==3)return s->segment_target;
 if(s->config.route_mode==2)return 1740.;
 if(Parking_IsTurn(s))return s->config.route_mode&&s->step==1?180.:s->config.turn_deg;
 if(s->config.route_mode){if(s->step==0)return 1740.;if(s->step==2)return 1900.;return s->config.distance_mm[s->step==4?0:1];}
 return s->config.distance_mm[s->step==1?0:1];
}
const char *Parking_StateStepName(const ParkingState *s){
 static const char *v[]={"FWD174","UTURN","FWD190","LEFT45","PARK50","RIGHT45","PARK10"};
 if(s->config.route_mode==3)return s->segment_kind==1?"TURN":s->segment_kind==2?"CREEP":"DRIVE";
 if(s->config.route_mode==2)return "FWD174";
 return s->config.route_mode?(s->step<7?v[s->step]:"INVALID"):Parking_StepName(s->step);
}
static int turn(const ParkingState *s){return Parking_IsTurn(s);}
static double turn_sign(const ParkingState *s){return Parking_TurnDirection(s);}
static void reset_pid(ParkingState *s){for(unsigned i=0;i<2;i++){Control_Reset(&s->wheel[i],s->speed[i]);s->pwm[i]=0;s->stall_ms[i]=0;}}
void Parking_DefaultConfig(ParkingConfig *p,const DistanceConfig *d){
 memset(p,0,sizeof(*p));p->mm_per_count[0]=d->mm_per_count[0];p->mm_per_count[1]=d->mm_per_count[1];p->calibrated=d->calibrated;p->turn_deg=45;p->distance_mm[0]=500;p->distance_mm[1]=100;p->yaw_sign=1;p->turn_pwm=700;
}
int Parking_ConfigValid(const ParkingConfig *p){
 return p&&isfinite(p->mm_per_count[0])&&isfinite(p->mm_per_count[1])&&p->mm_per_count[0]>=.000001&&p->mm_per_count[0]<=100&&p->mm_per_count[1]>=.000001&&p->mm_per_count[1]<=100&&
 p->mm_per_count[0]/p->mm_per_count[1]>=.25&&p->mm_per_count[0]/p->mm_per_count[1]<=4&&isfinite(p->turn_deg)&&p->turn_deg>=5&&p->turn_deg<=90&&
 isfinite(p->distance_mm[0])&&p->distance_mm[0]>=50&&p->distance_mm[0]<=2000&&isfinite(p->distance_mm[1])&&p->distance_mm[1]>=50&&p->distance_mm[1]<=2000&&
 (p->yaw_sign==1||p->yaw_sign==-1)&&p->calibrated<=1&&p->route_mode<=3&&p->turn_pwm>=100&&p->turn_pwm<=800&&isfinite(p->right_trim_percent)&&fabs(p->right_trim_percent)<=5.&&p->trim_keys_enabled<=1;
}
void Parking_Fault(ParkingState *s,unsigned fault){reset_pid(s);s->fault=fault;s->phase=PARK_FAULT;}
void Parking_Init(ParkingState *s,const ConsoleInput *in,const ParkingConfig *p){
 memset(s,0,sizeof(*s));s->magic=PARKING_MAGIC;s->config=*p;s->counts[0]=in->counts[0];s->counts[1]=in->counts[1];KeyDebounce_Init(&s->keys,in->keys);s->keys.locked=1;
 if(!Parking_ConfigValid(p))Parking_Fault(s,FAULT_CONFIG);
}
void Parking_Reset(ParkingState *s,const ConsoleInput *in){
 ParkingConfig p=s->config;uint32_t serial=s->run_id;double yaw=s->yaw_deg,unwrapped=s->yaw_unwrapped,previous=s->previous_yaw,rate=s->gyro_z_dps;unsigned ready=s->imu_ready,had=s->had_yaw;float speed0=s->speed[0],speed1=s->speed[1];
 Parking_Init(s,in,&p);s->run_id=serial;s->yaw_deg=yaw;s->yaw_unwrapped=unwrapped;s->previous_yaw=previous;s->gyro_z_dps=rate;s->imu_ready=ready;s->had_yaw=had;s->speed[0]=speed0;s->speed[1]=speed1;
}
void Parking_ImuSample(ParkingState *s,int fresh,double yaw,double rate){
 s->imu_ready=fresh&&isfinite(yaw)&&isfinite(rate)&&fabs(yaw)<=180.01&&fabs(rate)<=2000;
 if(!s->imu_ready)return;
 yaw*=s->config.yaw_sign;rate*=s->config.yaw_sign;
 if(s->had_yaw)s->yaw_unwrapped+=wrap(yaw-s->previous_yaw);else{s->yaw_unwrapped=yaw;s->had_yaw=1;}
 s->previous_yaw=s->yaw_deg=yaw;s->gyro_z_dps=rate;
}
/* kind 0=drive, 1=turn, 2=creep. This configures only; it cannot start.
 * Integration must independently enforce owner, physical start and arm/gripper
 * interlocks before adding any multi-segment execution path. */
int Parking_ConfigureDynamic(ParkingState *s,const ConsoleInput *in,unsigned kind,double value,double speed){
 if(!s||!in||s->config.route_mode!=3||(s->phase!=PARK_READY&&s->phase!=PARK_DONE)||s->fault||
    !s->config.calibrated||!s->imu_ready||in->keys||(in->motor_status&7)||(in->grip_status&31)||
    in->counts[0]!=s->counts[0]||in->counts[1]!=s->counts[1]||fabsf(s->speed[0])>.5f||fabsf(s->speed[1])>.5f||fabs(s->gyro_z_dps)>2||
    !isfinite(value)||!isfinite(speed)||kind>2)return -1;
 if(kind==1){if((fabs(value)!=45&&fabs(value)!=90&&fabs(value)!=180)||speed!=0)return -1;}
 else if(value<1||value>3000||(kind==2?(speed<=0||speed>30):speed!=0))return -1;
 s->segment_kind=kind;s->segment_target=fabs(value);s->segment_sign=value<0?-1.:1.;s->segment_speed_mm_s=speed;s->segment_configured=1;return 0;
}
static void enter_step(ParkingState *s){
 reset_pid(s);s->step_ms=s->settle_ms=s->quiet_ms=0;s->stop_requested=0;s->yaw_start=s->yaw_unwrapped;s->yaw_progress=0;s->angle_quiet_ms=0;s->angle_watch_yaw=s->yaw_unwrapped;s->angle_watch_path=0;
 for(unsigned i=0;i<2;i++){s->step_counts[i]=s->step_path[i]=0;s->step_mm[i]=0;}
 s->phase=PARK_RUN;
 if(s->config.route_mode==3&&turn(s)){
  ConsoleInput input={0};input.counts[0]=s->counts[0];input.counts[1]=s->counts[1];input.oled_ready=1;
  Turn90Config cfg={s->config.turn_pwm,s->config.yaw_sign,turn_sign(s)>0?1:-1};
  Turn90_Init(&s->package_turn,&input,&cfg);
  Turn90_ImuSample(&s->package_turn,s->imu_ready,s->yaw_deg/s->config.yaw_sign,s->gyro_z_dps/s->config.yaw_sign);
  s->package_turn.quiet_ms=250;
  if(Turn90_SetTarget(&s->package_turn,Parking_Target(s))||Turn90_Start(&s->package_turn,&input))Parking_Fault(s,CF_SAMPLE);
 }
}
int Parking_Start(ParkingState *s,const ConsoleInput *in){
 if(s->phase!=PARK_READY||s->fault||(in->keys&&in->keys!=2))return -1;
 if(s->config.route_mode==3&&(!s->segment_configured||!s->config.calibrated))return -1;
 /* OLED is optional; control and IMU health remain mandatory. */
 if((in->motor_status&6)||(in->grip_status&31)){Parking_Fault(s,(in->motor_status&6)?CF_MOTOR:CF_GRIP);return -1;}
 if(!s->imu_ready){Parking_Fault(s,PF_IMU);return -1;}
 if(in->counts[0]!=s->counts[0]||in->counts[1]!=s->counts[1]||fabsf(s->speed[0])>.5f||fabsf(s->speed[1])>.5f||fabs(s->gyro_z_dps)>2){Parking_Fault(s,CF_SAMPLE);return -1;}
 s->run_id++;s->step=s->total_ms=s->completed_steps=0;memset(s->completed,0,sizeof(s->completed));s->total_counts[0]=s->total_counts[1]=0;enter_step(s);return 0;
}
/* Internal primitive; only an authenticated, physically started mission may
   call this. The board service must implement that authorization. */
int Parking_StartDynamicNext(ParkingState *s,const ConsoleInput *in,unsigned kind,double value,double speed){
 if(!s||s->config.route_mode!=3||s->phase!=PARK_DONE||Parking_ConfigureDynamic(s,in,kind,value,speed))return -1;
 Parking_Reset(s,in);
 if(Parking_ConfigureDynamic(s,in,kind,value,speed)||Parking_Start(s,in))return -1;
 return 0;
}
int Parking_BrakeDynamicSearch(ParkingState *s){
 if(!s||s->config.route_mode!=3||s->segment_kind!=2||s->phase!=PARK_RUN)return -1;
 reset_pid(s);s->stop_requested=0;s->phase=PARK_SETTLE;s->settle_ms=s->quiet_ms=0;return 0;
}
void Parking_Stop(ParkingState *s){
 reset_pid(s);s->stop_requested=1;
 if(s->config.route_mode==3&&turn(s)){Turn90_Stop(&s->package_turn);if(s->phase!=PARK_FAULT)s->phase=PARK_STOP;return;}
 if(s->phase==PARK_RUN){s->phase=PARK_SETTLE;s->settle_ms=s->quiet_ms=0;}
 else if(s->phase!=PARK_SETTLE&&s->phase!=PARK_FAULT)s->phase=PARK_STOP;
}
const char *Parking_Phase(unsigned p){static const char *v[]={"READY","RUN","WAIT","DONE","STOP","FAULT"};return p<6?v[p]:"INVALID";}
const char *Parking_StepName(unsigned n){static const char *v[]={"LEFT","FWD1","RIGHT","FWD2"};return n<4?v[n]:"INVALID";}
static void settle(ParkingState *s){reset_pid(s);s->phase=PARK_SETTLE;s->settle_ms=s->quiet_ms=0;}
void Parking_Tick(ParkingState *s,const ConsoleInput *in,DistanceOutput *out){
 memset(out,0,sizeof(*out));int was_active=active(s),moved=0;
 for(unsigned i=0;i<2;i++){
  uint32_t u=in->counts[i]-s->counts[i];s->counts[i]=in->counts[i];int64_t d=u<=INT32_MAX?(int64_t)u:(int64_t)u-4294967296LL;d*=enc_sign[i];s->speed[i]=(float)d;
  if(llabs(d)>2000){Parking_Fault(s,12);return;}
  if(was_active){s->total_counts[i]+=d;s->step_counts[i]+=d;s->step_path[i]+=llabs(d);s->step_mm[i]=s->step_counts[i]*s->config.mm_per_count[i];moved|=d!=0;}
 }
 unsigned event=KeyDebounce_Update10ms(&s->keys,in->keys);
 if(in->keys&8){Parking_Stop(s);if(event==8){s->fault=0;s->phase=PARK_STOP;out->clear_stopped=1;}return;}
 if(in->keys&&(in->keys&(in->keys-1))){Parking_Fault(s,CF_KEYS);s->keys.locked=1;return;}
 if((in->motor_status&6)||(in->grip_status&31)){Parking_Fault(s,(in->motor_status&6)?CF_MOTOR:CF_GRIP);return;}
 if(event==KEY_DEBOUNCE_CONFLICT){Parking_Fault(s,CF_KEYS);return;}
 if(event==4)s->page=(s->page+1)%2;
 if(s->fault==CF_OLED){s->fault=0;s->phase=s->run_id?PARK_STOP:PARK_READY;KeyDebounce_Init(&s->keys,in->keys);s->keys.locked=1;event=0;}
 if(s->fault)return;
 if(event==1&&!active(s)){Parking_Reset(s,in);return;}
 if(event==2&&s->phase==PARK_READY)(void)Parking_Start(s,in);
 if(!active(s))return;
 if(!s->imu_ready){Parking_Fault(s,PF_IMU);return;}
 s->total_ms+=10;if(s->total_ms>=(s->config.route_mode?240000U:120000U)){Parking_Fault(s,PF_TIMEOUT);return;}
 s->yaw_progress=s->yaw_unwrapped-s->yaw_start;
 if(s->config.route_mode==3&&turn(s)){
  /* Exact package turn controller, under the current mission's key/lease locks. */
  ConsoleInput input=*in;input.keys=0;
  Turn90_ImuSample(&s->package_turn,s->imu_ready,s->yaw_deg/s->config.yaw_sign,s->gyro_z_dps/s->config.yaw_sign);
  Turn90_Tick(&s->package_turn,&input,out);
  if(s->package_turn.fault){Parking_Fault(s,s->package_turn.fault);memset(out,0,sizeof(*out));return;}
  s->step_ms=s->package_turn.total_ms;s->quiet_ms=s->package_turn.quiet_ms;
  s->pwm[0]=(float)out->pwm[0];s->pwm[1]=(float)out->pwm[1];
  if(s->package_turn.phase==T90_DONE){s->phase=PARK_DONE;s->completed_steps=1;s->completed[0]=s->package_turn.angle_deg*turn_sign(s);}
  else s->phase=s->package_turn.phase==T90_SETTLE?PARK_SETTLE:PARK_RUN;
  return;
 }
 if(turn(s)){
  double progress=turn_sign(s)*s->yaw_progress;
  if(progress< -3){Parking_Fault(s,PF_TURN_DIRECTION);return;}
  if(progress>Parking_Target(s)+4){Parking_Fault(s,PF_OVERSHOOT);return;}
 }
 if(s->phase==PARK_SETTLE){
  s->settle_ms+=10;s->quiet_ms=(!moved&&fabs(s->gyro_z_dps)<2)?s->quiet_ms+10:0;
  if(s->settle_ms>=3000){Parking_Fault(s,PF_SETTLE);return;}
  if(s->quiet_ms<250)return;
  if(s->stop_requested){s->phase=PARK_STOP;return;}
  double value=turn(s)?s->yaw_progress:.5*(s->step_mm[0]+s->step_mm[1]);
  if(turn(s)&&fabs(fabs(value)-Parking_Target(s))>1.5){Parking_Fault(s,PF_ANGLE);return;}
  s->completed[s->step]=value;s->completed_steps=s->step+1;
  if(s->step+1==Parking_StepCount(s)){s->phase=PARK_DONE;return;}
  s->step++;enter_step(s);return;
 }
 s->step_ms+=10;double desired[2],mean_k=.5*(s->config.mm_per_count[0]+s->config.mm_per_count[1]);
 if(turn(s)){
  if(s->step_ms>=(Parking_Target(s)>90?40000U:20000U)){Parking_Fault(s,PF_TIMEOUT);return;}
  double progress=turn_sign(s)*s->yaw_progress,remaining=Parking_Target(s)-progress;
  double path=.5*(s->step_path[0]*s->config.mm_per_count[0]+s->step_path[1]*s->config.mm_per_count[1]);
  if(path>450.*fmax(1.,Parking_Target(s)/45.)){Parking_Fault(s,PF_TRAVEL);return;}
  if(fabs(s->yaw_unwrapped-s->angle_watch_yaw)>=.35){s->angle_quiet_ms=0;s->angle_watch_yaw=s->yaw_unwrapped;s->angle_watch_path=path;}
  else s->angle_quiet_ms+=10;
  if(s->angle_quiet_ms>=1000&&path-s->angle_watch_path>10){Parking_Fault(s,PF_IMU_STUCK);return;}
  if(remaining<=.75){settle(s);return;}
  double base=fmax(.8,fmin(4.,remaining*.25))*mean_k;
  desired[0]=-turn_sign(s)*base/s->config.mm_per_count[0];desired[1]=turn_sign(s)*base/s->config.mm_per_count[1];
 }else{
  /* Combined missions omit the old 45 s segment timeout. The overall
     mission timeout and stall, encoder, IMU and link guards remain. */
  if(s->config.route_mode<2&&s->step_ms>=45000U){Parking_Fault(s,PF_TIMEOUT);return;}
  if(s->step_mm[0]< -15||s->step_mm[1]< -15){Parking_Fault(s,FAULT_ENCODER_SIGN);return;}
  double goal=Parking_Target(s),remaining=goal-.5*(s->step_mm[0]+s->step_mm[1]);
  if(remaining<=2){settle(s);return;}
  double base=fmax(2.,fmin(STRAIGHT_CRUISE_COUNTS,remaining/20.))*mean_k;
  if(s->config.route_mode==3&&s->segment_kind==2)base=fmin(base,s->segment_speed_mm_s*.01);
  /* Positive yaw is a left turn: speed up left and slow right.
     * Anchor heading at each segment start; use continuous yaw across +/-180.
     * IMU freshness/finiteness is checked above before any motor output.
     * Bound steering to 20% so creep and stopping cannot reverse a wheel. */
  double heading_error=wrap(s->yaw_unwrapped-s->yaw_start);
  double right_factor=1.+s->config.right_trim_percent/100.;
  double corr=.006*(s->step_mm[1]/right_factor-s->step_mm[0])
              +base*(.04*heading_error+.004*s->gyro_z_dps);
  corr=fmax(-.2*base,fmin(.2*base,corr));
  desired[0]=(base+corr)/s->config.mm_per_count[0];desired[1]=(base-corr)*right_factor/s->config.mm_per_count[1];
 }
 for(unsigned i=0;i<2;i++){
  float target=(float)fmax(-30.,fmin(30.,desired[i]));unsigned fault=Control_StepPolicy(&s->wheel[i],&gains,1,target,s->speed[i],1);
  if(fault){Parking_Fault(s,fault);memset(out,0,sizeof(*out));return;}
  s->wheel[i].pwm=Control_Clamp(s->wheel[i].pwm,-STRAIGHT_PWM_LIMIT,STRAIGHT_PWM_LIMIT);s->pwm[i]=s->wheel[i].pwm;
  if(fabsf(s->speed[i])<.5f&&fabsf(s->pwm[i])>=150)s->stall_ms[i]+=10;else s->stall_ms[i]=0;
  if(s->stall_ms[i]>=750){Parking_Fault(s,FAULT_STALL);memset(out,0,sizeof(*out));return;}
  out->pwm[i]=(int)(s->pwm[i]*(s->config.route_mode>=2?1:motor_sign[i]));
 }out->enable=1;
}
