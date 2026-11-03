#include "console_remote.h"
#include <string.h>
static void revoke(ConsoleRemote *r,ConsoleState *s,unsigned fault){
 memset(r,0,sizeof(*r));s->remote_active=0;Console_Fault(s,fault);
}
int Remote_Command(ConsoleRemote *r,ConsoleState *s,const ConsoleInput *in,
 const char *owner,const char *command,uint64_t now){
 if(!strcmp(command,"stop")){revoke(r,s,CF_LINK);return 0;}
 if(!strcmp(command,"acquire")){
  if(r->owner[0]||!owner[0]||strlen(owner)>64||s->running||s->grip_phase||
     s->fault||in->keys||(in->motor_status&7)||(in->grip_status&31))return -1;
  memset(r,0,sizeof(*r));strcpy(r->owner,owner);r->heartbeat_ms=now;
  s->mode=MODE_GRIP;s->remote_active=1;return 0;
 }
 if(!r->owner[0]||strcmp(owner,r->owner))return -1;
 if(now-r->heartbeat_ms>750||s->fault||(in->keys&8)||
    (in->motor_status&6)||(in->grip_status&22)){
  revoke(r,s,CF_LINK);return -1;
 }
 if(!strcmp(command,"ping")){r->heartbeat_ms=now;return 0;}
 if(!strcmp(command,"release")){
  /* A normally released task may have failed to reach the drop. Keep its
     acknowledged close powered under the local controller until opened.
     KEY4, driver faults and an expired lease still take priority above. */
  int holding=r->pulse==GRIP_CLOSE_US&&r->phase==GRIP_ACTIVE&&r->settled&&
              (in->grip_status&1)&&in->grip_active_us==GRIP_CLOSE_US;
  revoke(r,s,CF_NONE);
  if(holding){s->mode=MODE_GRIP;s->grip_phase=GRIP_ACTIVE;s->grip_cycle=GC_CLOSE;s->grip_pulse=GRIP_CLOSE_US;s->grip_ticks=0;}
  return 0;
 }
 if(!strcmp(command,"open")||!strcmp(command,"close")){
  r->pulse=!strcmp(command,"open")?GRIP_OPEN_US:GRIP_CLOSE_US;
  r->phase=GRIP_WAIT;r->ticks=r->wait=r->settled=0;r->heartbeat_ms=now;return 0;
 }
 return -1;
}
void Remote_Tick(ConsoleRemote *r,ConsoleState *s,const ConsoleInput *in,
 ConsoleOutput *out,uint64_t now){
 if(!r->owner[0]){Console_Tick(s,in,out);return;}
 if(now-r->heartbeat_ms>750||(in->keys&8)||s->fault||
    (in->motor_status&6)||(in->grip_status&22)){
  unsigned fault=(in->keys&8)?CF_KEYS:CF_LINK;
  revoke(r,s,fault);memset(out,0,sizeof(*out));out->grip_action=GA_STOP;return;
 }
 ConsoleInput masked=*in;masked.keys=0;
 s->running=0;s->grip_phase=GRIP_IDLE;s->grip_cycle=GC_NONE;
 Console_Tick(s,&masked,out);
 out->motor_run=0;out->motor_pwm[0]=out->motor_pwm[1]=0;
 if(s->fault){revoke(r,s,s->fault);out->grip_action=GA_STOP;return;}
 if(r->phase==GRIP_WAIT){
  if(!r->wait){out->grip_action=GA_COMMAND;out->grip_pulse=r->pulse;}
  if((in->grip_status&1)&&in->grip_active_us==r->pulse){
   r->phase=GRIP_ACTIVE;r->ticks=r->pulse==GRIP_CLOSE_US?GRIP_CLOSE_HOLD_TICKS:GRIP_OPEN_HOLD_TICKS;
  }else if(++r->wait>=10){revoke(r,s,CF_GRIP);out->grip_action=GA_STOP;return;}
 }else if(r->phase==GRIP_ACTIVE){
  if(!(in->grip_status&1)||in->grip_active_us!=r->pulse){
   revoke(r,s,CF_GRIP);out->grip_action=GA_STOP;return;
  }
  if(r->ticks&&!--r->ticks){
   r->settled=1;
   /* Hold the object closed until the drop command, including during pauses. */
   if(r->pulse==GRIP_OPEN_US){r->phase=GRIP_IDLE;out->grip_action=GA_STOP;}
  }
 }
 out->grip_heartbeat=r->phase!=GRIP_IDLE;
 s->grip_phase=r->phase;s->grip_pulse=r->pulse;s->grip_ticks=r->ticks;
}
