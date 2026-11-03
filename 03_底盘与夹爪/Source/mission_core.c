#include "mission_core.h"
#include "motor_config.h"
#include <string.h>
#include <ctype.h>
#include <limits.h>
#include <math.h>
#include <stdlib.h>
static int active(const MissionState *s){return s->drive.phase==PARK_RUN||s->drive.phase==PARK_SETTLE;}
static int token_ok(const char *p){size_t n=strlen(p);if(!n||n>64)return 0;for(size_t i=0;i<n;i++)if(!isalnum((unsigned char)p[i])&&p[i]!='_'&&p[i]!='-')return 0;return 1;}
static void release(MissionState *s){s->owner[0]=0;s->deadline_ms=0;ParkingRemote_Init(&s->lease);
 s->shelf_mode=s->shelf_started=s->shelf_arm_lock=0;s->shelf_command_id=0;s->shelf_started_ms=0;
 if(s->drive.config.route_mode==3)s->drive.config.route_mode=2;}
void Mission_Fault(MissionState *s,unsigned f){Parking_Fault(&s->drive,f);Console_Fault(&s->grip,f<=11?f:CF_LINK);memset(&s->grip_lease,0,sizeof(s->grip_lease));s->grip.remote_active=0;release(s);}
void Mission_Init(MissionState *s,const ConsoleInput *in,const ParkingConfig *cfg){
 memset(s,0,sizeof(*s));KeyDebounce_Init(&s->trim_keys,in->keys);ParkingConfig c=*cfg;c.route_mode=2;Parking_Init(&s->drive,in,&c);KeyConsole_Init(&s->grip,in);s->grip.mode=MODE_GRIP;
}
int Mission_Command(MissionState *s,const ConsoleInput *in,const char *token,const char *cmd,uint64_t now){
 if(!token_ok(token))return -1;
 if(!strcmp(cmd,"status"))return 0;
 if(!strcmp(cmd,"stop")){Parking_Stop(&s->drive);Console_Fault(&s->grip,0);memset(&s->grip_lease,0,sizeof(s->grip_lease));s->grip.remote_active=0;release(s);return 0;}
 if(!strcmp(cmd,"start"))return -1; /* Bare legacy start is forbidden; shelf start is generation/owner-bound. */
 if(!strcmp(cmd,"prepare")){
  if(s->owner[0]||s->grip_lease.owner[0]||s->grip.grip_phase||s->grip.fault)return -1;
  if(ParkingRemote_Command(&s->lease,&s->drive,in,token,cmd,now))return -1;
  strcpy(s->owner,token);s->deadline_ms=now+750;s->complete=0;return 0;
 }
 if(!s->owner[0]||strcmp(token,s->owner)||now>=s->deadline_ms||s->drive.fault||s->grip.fault)return -1;
 if(!strcmp(cmd,"heartbeat")){
  s->deadline_ms=now+750;
  if(s->lease.active)return ParkingRemote_Command(&s->lease,&s->drive,in,token,cmd,now);
  return s->shelf_mode||s->drive.phase==PARK_DONE?0:-1;
 }
 if(!strcmp(cmd,"finish")){
  if(s->drive.phase!=PARK_DONE||s->shelf_arm_lock||s->grip_lease.owner[0]||s->grip.grip_phase||(in->grip_status&31)||(in->motor_status&7))return -1;
  s->complete=1;release(s);return 0;
 }return -1;
}
int Mission_GripCommand(MissionState *s,const ConsoleInput *in,const char *token,const char *cmd,uint64_t now){
 if(!strcmp(cmd,"stop")){Mission_Command(s,in,"emergency","stop",now);return 0;}
 if(!strcmp(cmd,"acquire")&&s->shelf_mode&&!s->shelf_arm_lock)return -1;
 if(!strcmp(cmd,"acquire")&&(active(s)||s->drive.fault||(s->owner[0]&&s->drive.phase!=PARK_DONE)))return -1;
 return Remote_Command(&s->grip_lease,&s->grip,in,token,cmd,now);
}
static int shelf_owned(const MissionState *s,const char *owner,uint64_t now){
 return s->shelf_mode&&s->owner[0]&&token_ok(owner)&&!strcmp(owner,s->owner)&&now<s->deadline_ms&&
        !s->drive.fault&&!s->grip.fault;
}
int Mission_ShelfPrepare(MissionState *s,const ConsoleInput *in,const char *owner,uint64_t now,
                         uint32_t id,unsigned kind,double target,double speed){
 /* GUI stop and successful finish leave STOP/DONE without a fault. Prepare
    may reset these idle states, but never acknowledge a fault or start wheels.
    Mission_Command retains the owner, IMU, motion and output checks below. */
 if(!s||!in||!owner||!id||s->owner[0]||s->shelf_mode||
    (s->drive.phase!=PARK_READY&&s->drive.phase!=PARK_STOP&&s->drive.phase!=PARK_DONE)||
    s->drive.fault||s->grip.fault||!s->drive.config.calibrated||in->motor_max_pwm<s->drive.config.turn_pwm||in->arm_idle!=1)return -1;
 s->drive.config.route_mode=3;
 if(Mission_Command(s,in,owner,"prepare",now)){s->drive.config.route_mode=2;return -1;}
 if(Parking_ConfigureDynamic(&s->drive,in,kind,target,speed)){
  Mission_Command(s,in,owner,"stop",now);return -1;
 }
 s->shelf_mode=1;s->shelf_request_id=0;s->shelf_command_id=id;s->shelf_raw_counts[0]=in->counts[0];s->shelf_raw_counts[1]=in->counts[1];
 s->shelf_net_counts[0]=s->shelf_net_counts[1]=0;s->shelf_measured_ms=now;s->shelf_quiet_ms=0;return 0;
}
/* No MMIO here. A validated start changes state; the next tick rechecks all
   interlocks and is the sole place that can publish enabled wheel outputs. */
int Mission_ShelfStart(MissionState *s,const ConsoleInput *in,const char *owner,uint64_t now){
 if(!s||!in||!owner||!shelf_owned(s,owner,now)||s->shelf_started||
    s->drive.phase!=PARK_READY||s->drive.config.route_mode!=3||!s->shelf_command_id||
    !s->lease.active||!s->lease.prepared||strcmp(owner,s->lease.owner)||now>=s->lease.deadline_ms||
    s->shelf_arm_lock||s->grip_lease.owner[0]||s->grip.grip_phase||
    s->shelf_quiet_ms<250||in->keys||in->arm_idle!=1||
    (in->motor_status&7)||(in->grip_status&31)||!s->drive.imu_ready||
    !s->drive.config.calibrated||in->motor_max_pwm<s->drive.config.turn_pwm)return -1;
 if(Parking_Start(&s->drive,in))return -1;
 s->shelf_started=1;s->shelf_started_ms=now;
 s->shelf_net_counts[0]=s->shelf_net_counts[1]=0;
 s->shelf_raw_counts[0]=in->counts[0];s->shelf_raw_counts[1]=in->counts[1];
 s->shelf_measured_ms=now;s->lease.prepared=0;return 0;
}
/* Task-state reset only: no fault acknowledgement, hardware clear, position
   zeroing, lease acquisition, or output commands are permitted by this API. */
int Mission_Reset(MissionState *s,const ConsoleInput *in,uint64_t now){
 if(!s||!in||s->owner[0]||s->lease.active||s->shelf_mode||s->shelf_arm_lock||
    s->grip_lease.owner[0]||s->grip.remote_active||s->grip.grip_phase||
    s->drive.fault||s->grip.fault||
    (s->drive.phase!=PARK_READY&&s->drive.phase!=PARK_STOP&&s->drive.phase!=PARK_DONE)||
    in->keys||in->arm_idle!=1||(in->motor_status&7)||(in->grip_status&31)||
    in->counts[0]!=s->drive.counts[0]||in->counts[1]!=s->drive.counts[1]||
    !isfinite(s->drive.speed[0])||!isfinite(s->drive.speed[1])||
    fabsf(s->drive.speed[0])>.5f||fabsf(s->drive.speed[1])>.5f)return -1;
 Parking_Reset(&s->drive,in);release(s);s->complete=0;s->shelf_request_id=0;
 s->shelf_net_counts[0]=s->shelf_net_counts[1]=0;
 s->shelf_raw_counts[0]=in->counts[0];s->shelf_raw_counts[1]=in->counts[1];
 s->shelf_measured_ms=now;s->shelf_quiet_ms=0;return 0;
}
int Mission_ShelfNext(MissionState *s,const ConsoleInput *in,const char *owner,uint64_t now,
                      uint32_t id,unsigned kind,double target,double speed){
 if(!s||!in||!owner||!shelf_owned(s,owner,now)||!s->shelf_started||id<=s->shelf_command_id||
    s->shelf_arm_lock||s->grip_lease.owner[0]||s->grip.grip_phase||
    s->drive.phase!=PARK_DONE||s->shelf_quiet_ms<250||in->arm_idle!=1||(in->grip_status&31)||(in->motor_status&7))return -1;
 if(Parking_StartDynamicNext(&s->drive,in,kind,target,speed))return -1;
 s->shelf_command_id=id;return 0;
}
int Mission_ShelfBrake(MissionState *s,const char *owner,uint64_t now,uint32_t id){
 if(!s||!owner||!shelf_owned(s,owner,now)||!s->shelf_started||id<=s->shelf_command_id)return -1;
 if(Parking_BrakeDynamicSearch(&s->drive))return -1;
 s->shelf_command_id=id;return 0;
}
int Mission_ShelfArmLock(MissionState *s,const ConsoleInput *in,const char *owner,uint64_t now,unsigned locked){
 if(!s||!in||!owner||!shelf_owned(s,owner,now)||!s->shelf_started||locked>1||
    s->drive.phase!=PARK_DONE||s->shelf_quiet_ms<250||(in->motor_status&7))return -1;
 if(!locked&&(in->arm_idle!=1||s->grip_lease.owner[0]||s->grip.grip_phase||(in->grip_status&31)))return -1;
 s->shelf_arm_lock=locked;return 0;
}
void Mission_Tick(MissionState *s,const ConsoleInput *input,MissionOutput *out,uint64_t now){
 memset(out,0,sizeof(*out));ConsoleInput in=*input;
 if(s->drive.config.trim_keys_enabled){
  unsigned event=KeyDebounce_Update10ms(&s->trim_keys,in.keys);
  if((event==2||event==4)&&!active(s)&&!s->drive.fault&&!s->grip.fault&&
     !(in.motor_status&7)&&fabsf(s->drive.speed[0])<.5f&&fabsf(s->drive.speed[1])<.5f){
   s->drive.config.right_trim_percent=fmax(-5.,fmin(5.,s->drive.config.right_trim_percent+(event==2?.25:-.25)));
  }
  /* Consume single trim keys before legacy start/page handling; chords and STOP stay raw. */
  if(in.keys==2||in.keys==4)in.keys=0;
 }
 if(s->shelf_mode){
  int moved=0;
  const int sign[2]={ENCODER_LEFT_DIR,ENCODER_RIGHT_DIR};
  for(unsigned i=0;i<2;i++){
   uint32_t raw=in.counts[i]-s->shelf_raw_counts[i];
   int64_t delta=raw<=INT32_MAX?(int64_t)raw:(int64_t)raw-4294967296LL;
   s->shelf_raw_counts[i]=in.counts[i];delta*=sign[i];
   if(llabs(delta)>2000||((delta>0&&s->shelf_net_counts[i]>INT64_MAX-delta)||
                          (delta<0&&s->shelf_net_counts[i]<INT64_MIN-delta))){Mission_Fault(s,CF_SAMPLE);out->grip.grip_action=GA_STOP;return;}
   s->shelf_net_counts[i]+=delta;moved|=delta!=0;
  }
  s->shelf_measured_ms=now;
  if(s->shelf_arm_lock&&moved){Mission_Fault(s,CF_SAMPLE);out->grip.grip_action=GA_STOP;return;}
  if(!moved&&!(in.motor_status&7)&&s->drive.imu_ready&&fabs(s->drive.gyro_z_dps)<2){
   if(s->shelf_quiet_ms<10000)s->shelf_quiet_ms+=10;
  }else s->shelf_quiet_ms=0;
 }
 if(s->owner[0]&&now>=s->deadline_ms)Mission_Fault(s,CF_LINK);
 /* Both controllers see raw KEY4. No legacy PID/manual-grip button can run here. */
 if(in.keys&8){release(s);memset(&s->grip_lease,0,sizeof(s->grip_lease));s->grip.remote_active=0;}
 ParkingRemote_Tick(&s->lease,&s->drive,&in,now);
 if(s->shelf_mode&&!s->shelf_started&&(in.keys&2)&&s->shelf_quiet_ms<250){
  Mission_Fault(s,CF_SAMPLE);out->grip.grip_action=GA_STOP;return;
 }
 ConsoleInput wheel=in;
 if(!s->owner[0]||!s->lease.active)wheel.keys&=(uint8_t)~2U;
 if(s->owner[0]||s->grip_lease.owner[0])wheel.keys&=(uint8_t)~1U;
 if(s->drive.phase==PARK_DONE||(!active(s)&&(s->grip_lease.owner[0]||s->grip.grip_phase)))wheel.grip_status=0;
 Parking_Tick(&s->drive,&wheel,&out->drive);
 if(s->shelf_mode&&!s->shelf_started&&s->drive.phase==PARK_RUN){
  s->shelf_started=1;s->shelf_started_ms=now;s->shelf_net_counts[0]=s->shelf_net_counts[1]=0;
 }
 if(s->shelf_mode&&s->shelf_started&&now-s->shelf_started_ms>=600000U)Mission_Fault(s,CF_LINK);
 if(s->drive.phase==PARK_RUN)s->lease.prepared=0;
 if(s->owner[0]&&(s->drive.fault||s->drive.phase==PARK_STOP))release(s);
 ConsoleInput grip=in;grip.keys&=8U;s->grip.mode=MODE_GRIP;s->grip.running=0;
 Remote_Tick(&s->grip_lease,&s->grip,&grip,&out->grip,now);
 out->grip.motor_run=0;out->grip.motor_pwm[0]=out->grip.motor_pwm[1]=0;
 if((s->drive.fault&&s->grip_lease.owner[0])||(s->grip.fault&&active(s)))Mission_Fault(s,CF_LINK);
 if(out->drive.enable&&(in.grip_status&31||s->grip_lease.owner[0]||s->shelf_arm_lock||
    (s->shelf_mode&&in.arm_idle!=1)||out->grip.grip_action==GA_COMMAND))Mission_Fault(s,CF_GRIP);
 if(s->drive.fault||in.keys&8){out->drive.enable=0;out->drive.pwm[0]=out->drive.pwm[1]=0;}
 /* A released close remains held by the local console until open/stop.
    Never allow a wheel phase to coexist with that retained hold. */
 if(s->drive.fault||s->grip.fault||in.keys&8||active(s)){out->grip.grip_action=GA_STOP;out->grip.grip_heartbeat=0;}
}
