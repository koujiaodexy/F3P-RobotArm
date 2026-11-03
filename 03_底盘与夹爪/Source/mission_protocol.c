#include "mission_protocol.h"
#include <errno.h>
#include <ctype.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int uint_value(const char *s,uint64_t max,uint64_t *v){
 if(!s||!*s)return 0;
 for(const char *p=s;*p;p++)if(*p<'0'||*p>'9')return 0;
 errno=0;char *end;unsigned long long n=strtoull(s,&end,10);
 if(errno||*end||n>max)return 0;
 *v=(uint64_t)n;return 1;
}
static int real_value(const char *s,double *v){
 if(!s||!*s)return 0;
 errno=0;char *end;double n=strtod(s,&end);
 if(errno||*end||!isfinite(n))return 0;
 *v=n;return 1;
}
static int token_valid(const char *s){
 size_t n=strlen(s);if(!n||n>64)return 0;
 for(size_t i=0;i<n;i++)if(!isalnum((unsigned char)s[i])&&s[i]!='_'&&s[i]!='-')return 0;
 return 1;
}
int Mission_Protocol(MissionState *s,const ConsoleInput *in,uint64_t now,uint64_t generation,
                     const char *request,size_t length,char *reply,size_t capacity){
 char buf[256],*words[12],*owner="",*verb="";unsigned count=0;int ok=0;
 uint64_t gen=0,seq=0,id=0,kind=0,lock=0;double target=0,speed=0;
 if(length&&length<sizeof(buf)&&!memchr(request,0,length)){
  memcpy(buf,request,length);buf[length]=0;char *p=buf;
  while(*p&&count<12){while(*p&&isspace((unsigned char)*p))p++;if(!*p)break;
   words[count++]=p;while(*p&&!isspace((unsigned char)*p))p++;if(*p)*p++=0;
  }
  if(count>=2&&token_valid(words[0])){
   owner=words[0];verb=words[1];
   if(count==2&&!strcmp(verb,"status"))ok=1;
   else if(count==2&&!strcmp(verb,"stop"))ok=Mission_Command(s,in,owner,"stop",now)==0;
   else if(count==4&&!strcmp(verb,"reset")&&
      uint_value(words[2],UINT64_MAX,&gen)&&gen==generation&&
      uint_value(words[3],UINT32_MAX,&seq)&&seq>0)ok=Mission_Reset(s,in,now)==0;
   else if(count>=5&&!strcmp(verb,"shelf")&&
      uint_value(words[2],UINT64_MAX,&gen)&&gen==generation&&
      uint_value(words[3],UINT32_MAX,&seq)&&seq>0){
    verb=words[4];
    int prepare=!strcmp(verb,"prepare");
    int owned=s->owner[0]&&!strcmp(s->owner,owner)&&seq>s->shelf_request_id;
    if((prepare&&!s->owner[0])||owned){
     if(count==9&&(prepare||!strcmp(verb,"next"))&&
       uint_value(words[5],UINT32_MAX,&id)&&id>0&&uint_value(words[6],2,&kind)&&
       real_value(words[7],&target)&&real_value(words[8],&speed)){
      ok=(prepare?Mission_ShelfPrepare(s,in,owner,now,(uint32_t)id,(unsigned)kind,target,speed):
           Mission_ShelfNext(s,in,owner,now,(uint32_t)id,(unsigned)kind,target,speed))==0;
     }else if(count==6&&!strcmp(verb,"brake")&&uint_value(words[5],UINT32_MAX,&id)&&id>0)
      ok=Mission_ShelfBrake(s,owner,now,(uint32_t)id)==0;
     else if(count==6&&!strcmp(verb,"lock")&&uint_value(words[5],1,&lock))
      ok=Mission_ShelfArmLock(s,in,owner,now,(unsigned)lock)==0;
     else if(count==5&&!strcmp(verb,"start"))
      ok=Mission_ShelfStart(s,in,owner,now)==0;
     else if(count==5&&(!strcmp(verb,"heartbeat")||!strcmp(verb,"finish")))
      ok=Mission_Command(s,in,owner,verb,now)==0;
     if(ok)s->shelf_request_id=(uint32_t)seq;
    }
   }
  }
 }
 int n=snprintf(reply,capacity,
  "{\"ok\":%s,\"protocol\":1,\"touch_control_version\":1,\"generation\":\"%" PRIu64 "\",\"request_id\":%" PRIu64 ","
  "\"request_owner\":\"%s\",\"owner\":\"%s\",\"phase\":\"%s\",\"fault\":%u,\"grip_fault\":%u,"
  "\"armed\":%s,\"complete\":%s,\"run_id\":%u,\"shelf_mode\":%s,\"shelf_started\":%s,"
  "\"shelf_command_id\":%u,\"shelf_arm_lock\":%s,\"odo_mm_lr\":[%.4f,%.4f],\"measured_ms\":%" PRIu64 ","
  "\"quiet_ms\":%u,\"imu_ready\":%s,\"arm_idle\":%s,\"gripper_active\":%s,\"motor_active\":%s,\"motor_max_pwm\":%u,\"turn_pwm\":%u,\"grip_open_wait_ms\":%u,\"right_trim_percent\":%.2f,\"trim_keys_enabled\":%s}",
  ok?"true":"false",generation,seq,owner,s->owner,Parking_Phase(s->drive.phase),s->drive.fault,s->grip.fault,
  s->owner[0]?"true":"false",s->complete?"true":"false",s->drive.run_id,s->shelf_mode?"true":"false",
  s->shelf_started?"true":"false",s->shelf_command_id,s->shelf_arm_lock?"true":"false",
  s->shelf_net_counts[0]*s->drive.config.mm_per_count[0],s->shelf_net_counts[1]*s->drive.config.mm_per_count[1],
  s->shelf_measured_ms,s->shelf_quiet_ms,s->drive.imu_ready?"true":"false",in->arm_idle==1?"true":"false",
  (in->grip_status&31)||s->grip_lease.owner[0]||s->grip.grip_phase?"true":"false",(in->motor_status&7)?"true":"false",in->motor_max_pwm,s->drive.config.turn_pwm,GRIP_OPEN_HOLD_TICKS*10U,s->drive.config.right_trim_percent,s->drive.config.trim_keys_enabled?"true":"false");
 return n>0&&(size_t)n<capacity?n:-1;
}
