
#include "turn90_core.h"
#include "motor_config.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>
static const int enc_sign[2]={ENCODER_LEFT_DIR,ENCODER_RIGHT_DIR};
static const int motor_sign[2]={TURN90_LEFT_MOTOR_FORWARD_DIR,TURN90_RIGHT_MOTOR_FORWARD_DIR};
static int active(const Turn90State *s){return s->phase==T90_RUN||s->phase==T90_SETTLE;}
static double wrap(double a){return a-360.*floor((a+180.)/360.);}
int Turn90_ConfigValid(const Turn90Config *c){return c&&c->initial_pwm>=TURN90_MIN_PWM&&c->initial_pwm<=TURN90_MAX_PWM&&(c->yaw_sign==1||c->yaw_sign==-1)&&(c->direction==1||c->direction==-1);}
void Turn90_Fault(Turn90State *s,unsigned f){s->fault=f;s->applied_pwm=0;s->phase=T90_FAULT;}
void Turn90_Stop(Turn90State *s){s->applied_pwm=0;if(s->phase!=T90_FAULT)s->phase=T90_STOP;}
void Turn90_Init(Turn90State *s,const ConsoleInput *in,const Turn90Config *c){
 memset(s,0,sizeof(*s));s->magic=TURN90_MAGIC;s->target_deg=90;s->config=*c;s->selected_pwm=c->initial_pwm;s->counts[0]=in->counts[0];s->counts[1]=in->counts[1];KeyDebounce_Init(&s->keys,in->keys);s->keys.locked=1;if(!Turn90_ConfigValid(c))Turn90_Fault(s,FAULT_CONFIG);
}
void Turn90_ImuSample(Turn90State *s,int fresh,double yaw,double rate){
 s->imu_ready=fresh&&isfinite(yaw)&&isfinite(rate)&&fabs(yaw)<=180.01&&fabs(rate)<=2000;if(!s->imu_ready)return;
 yaw*=s->config.yaw_sign;rate*=s->config.yaw_sign;
 if(s->had_yaw)s->yaw_unwrapped+=wrap(yaw-s->previous_yaw);else{s->had_yaw=1;s->yaw_unwrapped=yaw;}
 s->previous_yaw=s->yaw_deg=yaw;s->gyro_z_dps=rate;
}
int Turn90_SetTarget(Turn90State *s,double target){if(active(s)||(target!=45&&target!=90&&target!=180))return -1;s->target_deg=target;return 0;}
int Turn90_Start(Turn90State *s,const ConsoleInput *in){
 (void)in;
 if(active(s)||s->fault)return -1;
 if(!s->imu_ready){Turn90_Fault(s,16);return -1;}

 if(s->quiet_ms<250||fabs(s->gyro_z_dps)>2||fabsf(s->speed[0])>.5f||fabsf(s->speed[1])>.5f){Turn90_Fault(s,CF_SAMPLE);return -1;}
 s->run_id++;s->phase=T90_RUN;s->total_ms=s->settle_ms=s->quiet_ms=s->applied_pwm=s->peak_pwm=0;s->initial_pwm=s->selected_pwm;
 memset(s->run_counts,0,sizeof(s->run_counts));memset(s->path_counts,0,sizeof(s->path_counts));s->angle_watch_ms=0;s->angle_watch_yaw=s->yaw_unwrapped;memset(s->stall_ms,0,sizeof(s->stall_ms));memset(s->wrong_ticks,0,sizeof(s->wrong_ticks));s->yaw_start=s->yaw_unwrapped;s->angle_deg=0;return 0;
}
const char *Turn90_Phase(unsigned n){static const char *v[]={"WAIT","RUN","BRAKE","DONE","STOP","FAULT"};return n<6?v[n]:"INVALID";}
void Turn90_Tick(Turn90State *s,const ConsoleInput *in,DistanceOutput *out){
 memset(out,0,sizeof(*out));int was_active=active(s),moved=0;
 for(unsigned i=0;i<2;i++){
  uint32_t u=in->counts[i]-s->counts[i];s->counts[i]=in->counts[i];int64_t d=u<=INT32_MAX?(int64_t)u:(int64_t)u-4294967296LL;d*=enc_sign[i];s->speed[i]=(float)d;
  if(llabs(d)>2000){Turn90_Fault(s,12);return;}
  if(was_active){s->run_counts[i]+=d;s->path_counts[i]+=llabs(d);}
  moved|=d!=0;
 }
 if(!active(s))s->quiet_ms=(!moved&&s->imu_ready&&fabs(s->gyro_z_dps)<2)?(s->quiet_ms<1000?s->quiet_ms+10:1000):0;
 unsigned event=KeyDebounce_Update10ms(&s->keys,in->keys);
 if(in->keys&8){
  Turn90_Stop(s);
  if(event==8&&!(in->motor_status&6)&&!(in->grip_status&31)&&Turn90_ConfigValid(&s->config)){s->fault=0;s->phase=T90_STOP;out->clear_stopped=1;}
  return;
 }
 if(in->keys&&(in->keys&(in->keys-1))){Turn90_Fault(s,CF_KEYS);s->keys.locked=1;return;}

 if((in->motor_status&6)||(in->grip_status&31)){Turn90_Fault(s,(in->motor_status&6)?CF_MOTOR:CF_GRIP);return;}
 if(event==KEY_DEBOUNCE_CONFLICT){Turn90_Fault(s,CF_KEYS);return;}
 if(s->fault==CF_OLED&&!s->run_id){s->fault=0;s->phase=T90_READY;KeyDebounce_Init(&s->keys,in->keys);s->keys.locked=1;event=0;}
 /* Setting changes are retained between trials; never restart a faulted trial. */
 if(event==2)s->selected_pwm=s->selected_pwm+TURN90_STEP_PWM>TURN90_MAX_PWM?TURN90_MAX_PWM:s->selected_pwm+TURN90_STEP_PWM;
 if(event==4)s->selected_pwm=s->selected_pwm<TURN90_MIN_PWM+TURN90_STEP_PWM?TURN90_MIN_PWM:s->selected_pwm-TURN90_STEP_PWM;
 if(s->fault)return;
 if(event==1&&!active(s))(void)Turn90_Start(s,in);
 if(!active(s))return;
 if(!s->imu_ready){Turn90_Fault(s,16);return;}
 s->total_ms+=10;if(s->total_ms>=(s->target_deg>90?60000U:30000U)){Turn90_Fault(s,19);return;}
 s->angle_deg=s->config.direction*(s->yaw_unwrapped-s->yaw_start);
 if(s->angle_deg< -3){Turn90_Fault(s,21);return;}
 if(s->angle_deg>s->target_deg+4){Turn90_Fault(s,22);return;}
 if(s->phase==T90_SETTLE){
  s->applied_pwm=0;s->settle_ms+=10;s->quiet_ms=(!moved&&fabs(s->gyro_z_dps)<2)?s->quiet_ms+10:0;
  if(s->settle_ms>=3000){Turn90_Fault(s,23);return;}
  if(s->quiet_ms>=250){if(fabs(s->angle_deg-s->target_deg)>1.5)Turn90_Fault(s,17);else s->phase=T90_DONE;}
  return;
 }
 if(fabs(s->yaw_unwrapped-s->angle_watch_yaw)>=.35){s->angle_watch_ms=0;s->angle_watch_yaw=s->yaw_unwrapped;}else s->angle_watch_ms+=10;
 if(s->angle_watch_ms>=1500&&(s->path_counts[0]+s->path_counts[1])/2>100){Turn90_Fault(s,18);return;}
 if(s->angle_deg>=s->target_deg-.75){s->phase=T90_SETTLE;s->applied_pwm=s->settle_ms=s->quiet_ms=0;return;}
 /* New staged 45/180-degree legs reduce power near the endpoint. The
  * retained default 90-degree manual test keeps its original behavior.
  * 250 is only an approach cap, not a claim about physical breakaway torque. */
 unsigned demand=s->selected_pwm;
 if(s->target_deg!=90&&demand>250){
  double remaining=s->target_deg-s->angle_deg;
  if(remaining<15){double blend=fmax(0.,fmin(1.,(remaining-3.)/12.));demand=250+(unsigned)((s->selected_pwm-250)*blend);}
 }
 if(s->applied_pwm<demand)s->applied_pwm=demand-s->applied_pwm>20?s->applied_pwm+20:demand;
 else if(s->applied_pwm>demand)s->applied_pwm=s->applied_pwm-demand>20?s->applied_pwm-20:demand;
 if(s->applied_pwm>s->peak_pwm)s->peak_pwm=s->applied_pwm;
 for(unsigned i=0;i<2;i++){
  int expected=(i?1:-1)*s->config.direction;
  if(s->speed[i]*expected< -1)s->wrong_ticks[i]++;else s->wrong_ticks[i]=0;
  /* User disabled F1 for this manual turn test. Keep wrong_ticks as telemetry only. */
  if(fabsf(s->speed[i])<.5f&&s->applied_pwm>=150)s->stall_ms[i]+=10;else s->stall_ms[i]=0;
  if(s->stall_ms[i]>=1500){Turn90_Fault(s,FAULT_STALL);memset(out,0,sizeof(*out));return;}
  out->pwm[i]=expected*(int)s->applied_pwm*motor_sign[i];
 }
 out->enable=1;
}
