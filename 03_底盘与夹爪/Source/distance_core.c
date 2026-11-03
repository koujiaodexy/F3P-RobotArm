#include "distance_core.h"
#include "motor_config.h"
#include <math.h>
#include <string.h>
#include <stdlib.h>
static const int encoder_sign[2]={ENCODER_LEFT_DIR,ENCODER_RIGHT_DIR};
static const int motor_sign[2]={MOTOR_LEFT_DIR,MOTOR_RIGHT_DIR};
static const PidGains gains={SPEED_PID_KP,SPEED_PID_KI,SPEED_PID_KD,0};
void Distance_DefaultConfig(DistanceConfig *c){
 double k=3.14159265358979323846*66.0/1771.4;
 c->mm_per_count[0]=c->mm_per_count[1]=k;c->target_mm=1000.0;c->calibrated=0;
}
int Distance_ConfigValid(const DistanceConfig *c){
 return c&&c->calibrated<=1&&isfinite(c->target_mm)&&c->target_mm>=100&&c->target_mm<=5000&&
 isfinite(c->mm_per_count[0])&&isfinite(c->mm_per_count[1])&&
 c->mm_per_count[0]>=.000001&&c->mm_per_count[0]<=100&&c->mm_per_count[1]>=.000001&&c->mm_per_count[1]<=100;
}
static double angle_error(double x){return x-360.0*floor((x+180.0)/360.0);}
void Distance_EnableHeading(DistanceState *s,int sign){s->heading_required=1;s->yaw_sign=sign<0?-1:1;s->steering_polarity=1;s->imu_ready=0;s->yaw_integral=0;}
int Distance_SetSteeringPolarity(DistanceState *s,int polarity){
 if(polarity!=1&&polarity!=-1)return -1;
 s->steering_polarity=polarity;return 0;
}
void Distance_HeadingSample(DistanceState *s,int fresh,double yaw,double rate){
 s->imu_ready=fresh&&isfinite(yaw)&&isfinite(rate)&&fabs(yaw)<=180.01&&fabs(rate)<=2000;
 if(s->imu_ready){s->yaw_deg=yaw*s->yaw_sign;s->gyro_z_dps=rate*s->yaw_sign;}
}
static void reset_control(DistanceState *s){
 for(unsigned i=0;i<2;i++){Control_Reset(&s->wheel[i],s->speed[i]);s->pwm[i]=0;s->stall_ms[i]=0;}
}
void Distance_Fault(DistanceState *s,unsigned code){reset_control(s);s->phase=DIST_FAULT;s->fault=code;}
void Distance_Init(DistanceState *s,const ConsoleInput *in,const DistanceConfig *config){
 memset(s,0,sizeof(*s));s->magic=DISTANCE_MAGIC;s->config=*config;s->counts[0]=in->counts[0];s->counts[1]=in->counts[1];
 s->phase=DIST_READY;KeyDebounce_Init(&s->keys,in->keys);s->keys.locked=1;
 if(!Distance_ConfigValid(config))Distance_Fault(s,14);
}
static void begin_stop(DistanceState *s,unsigned final_phase){
 reset_control(s);s->phase=DIST_SETTLING;s->settle_ms=s->quiet_ms=0;s->end_phase=final_phase;
}
const char *Distance_Phase(unsigned p){
 static const char *names[]={"READY","RUN","WAIT","DONE","STOP","FAULT"};return p<6?names[p]:"INVALID";
}
void Distance_Tick(DistanceState *s,const ConsoleInput *in,DistanceOutput *out){
 memset(out,0,sizeof(*out));
 int active=s->phase==DIST_RUN||s->phase==DIST_SETTLING,moved=0;
 for(unsigned i=0;i<2;i++){
  uint32_t raw=in->counts[i]-s->counts[i];s->counts[i]=in->counts[i];
  int64_t d=raw<=INT32_MAX?(int64_t)raw:(int64_t)raw-4294967296LL;
  d*=encoder_sign[i];s->speed[i]=(float)d;
  if(d>2000||d< -2000){Distance_Fault(s,12);return;}
  if(active){
   s->net[i]+=d;s->path[i]+=llabs(d);s->mm[i]=(double)s->net[i]*s->config.mm_per_count[i];moved|=d!=0;
  }
 }
 uint8_t event=KeyDebounce_Update10ms(&s->keys,in->keys);
 if(s->phase==DIST_SETTLING){
  s->settle_ms+=10;s->quiet_ms=moved?0:s->quiet_ms+10;
  if(s->quiet_ms>=250)s->phase=s->end_phase;
  else if(s->settle_ms>=3000){Distance_Fault(s,15);return;}
 }
 /* KEY4 acts on the raw input, before debounce. Fault acknowledgement is debounced. */
 if(in->keys&8){
  if(s->phase==DIST_RUN)begin_stop(s,DIST_STOPPED);else reset_control(s);
  if(event==8&&in->oled_ready){s->fault=0;out->clear_stopped=1;if(s->phase==DIST_FAULT)s->phase=DIST_STOPPED;}
  return;
 }
 if(in->keys&&(in->keys&(in->keys-1))){Distance_Fault(s,CF_KEYS);s->keys.locked=1;return;}
 if(!in->oled_ready){Distance_Fault(s,CF_OLED);return;}
 if((in->motor_status&6)||(in->grip_status&31)){
  Distance_Fault(s,(in->motor_status&6)?CF_MOTOR:CF_GRIP);return;
 }
 if(event==KEY_DEBOUNCE_CONFLICT){Distance_Fault(s,CF_KEYS);return;}
 if(event==4)s->page=(s->page+1)%(s->heading_required?3:2);
 if(s->fault==CF_OLED){s->fault=0;s->phase=s->run_serial?DIST_STOPPED:DIST_READY;KeyDebounce_Init(&s->keys,in->keys);s->keys.locked=1;event=0;}
 if(s->fault)return;
 if(event==1&&s->phase!=DIST_RUN&&s->phase!=DIST_SETTLING){
  s->phase=DIST_READY;s->elapsed_ms=0;s->net[0]=s->net[1]=s->path[0]=s->path[1]=0;
  s->mm[0]=s->mm[1]=0;reset_control(s);return;
 }
 if(event==2&&s->phase==DIST_READY){
  if(fabsf(s->speed[0])>.5f||fabsf(s->speed[1])>.5f){Distance_Fault(s,CF_SAMPLE);return;}
  if(s->heading_required&&!s->imu_ready){Distance_Fault(s,16);return;}
  s->yaw_start_deg=s->yaw_deg;s->yaw_error_deg=s->yaw_integral=0;
  s->phase=DIST_RUN;s->run_serial++;s->elapsed_ms=0;s->net[0]=s->net[1]=s->path[0]=s->path[1]=0;s->mm[0]=s->mm[1]=0;reset_control(s);
 }
 if(s->phase!=DIST_RUN)return;
 s->elapsed_ms+=10;
 if(s->elapsed_ms>=120000){Distance_Fault(s,13);return;}
 if(s->mm[0]< -15||s->mm[1]< -15){Distance_Fault(s,FAULT_ENCODER_SIGN);return;}

 double remaining=s->config.target_mm-(s->mm[0]+s->mm[1])*.5;
 if(s->heading_required){
  if(!s->imu_ready){Distance_Fault(s,16);return;}
  s->yaw_error_deg=angle_error(s->yaw_deg-s->yaw_start_deg);
  if(fabs(s->yaw_error_deg)>12){Distance_Fault(s,17);return;}
 }
 if(remaining<=2){begin_stop(s,DIST_DONE);return;}
 double k=.5*(s->config.mm_per_count[0]+s->config.mm_per_count[1]);
 double base=fmin(10.,fmax(2.,remaining/20.))*k,correction=0;
 if(s->heading_required){
  s->yaw_integral=fmax(-.1*base,fmin(.1*base,s->yaw_integral+.00008*s->yaw_error_deg));
  /* Independently map measured yaw feedback onto the existing paired motor/encoder groups. */
  correction=s->steering_polarity*(.020*s->yaw_error_deg+.002*s->gyro_z_dps+s->yaw_integral);
 }else correction=.006*(s->mm[1]-s->mm[0]);
 correction=fmax(-.25*base,fmin(.25*base,correction));
 for(unsigned i=0;i<2;i++){
  double physical_speed=base+(i?-correction:correction);
  float target=(float)fmin(15.,fmax(.5,physical_speed/s->config.mm_per_count[i]));
  unsigned fault=Control_Step(&s->wheel[i],&gains,1,target,s->speed[i]);
  if(fault){Distance_Fault(s,fault);memset(out,0,sizeof(*out));return;}
  s->wheel[i].pwm=Control_Clamp(s->wheel[i].pwm,0,300);s->pwm[i]=s->wheel[i].pwm;
  if(fabsf(s->speed[i])<.5f&&s->pwm[i]>=150)s->stall_ms[i]+=10;else s->stall_ms[i]=0;
  if(s->stall_ms[i]>=1000){Distance_Fault(s,FAULT_STALL);memset(out,0,sizeof(*out));return;}
  out->pwm[i]=(int)(s->pwm[i]*motor_sign[i]);
 }
 out->enable=1;
}
