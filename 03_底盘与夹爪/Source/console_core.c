#include "console_core.h"
#include "motor_config.h"
#include <string.h>
static const unsigned targets[]={10,20,30};
static void stop_all(ConsoleState *s){
 s->running=0;s->cooldown=20;s->grip_phase=GRIP_IDLE;s->grip_ticks=s->grip_wait=0;s->grip_cycle=GC_NONE;
 for(unsigned n=0;n<2;n++){Control_Reset(&s->wheel[n],s->speed[n]);s->pwm[n]=0;}
}
void Console_Fault(ConsoleState *s,uint32_t code){stop_all(s);s->fault=code;}
void KeyConsole_Init(ConsoleState *s,const ConsoleInput *in){
 memset(s,0,sizeof(*s));s->mode=MODE_PID;s->selected=1;s->target=targets[1];s->grip_pulse=GRIP_CLOSE_US;
 s->counts[0]=in->counts[0];s->counts[1]=in->counts[1];
 stop_all(s);KeyDebounce_Init(&s->keys,in->keys);s->keys.locked=1;
}
void Console_Resync(ConsoleState *s,const ConsoleInput *in,int timing_fault){
 stop_all(s);if(timing_fault)s->fault=CF_SAMPLE;
 s->counts[0]=in->counts[0];s->counts[1]=in->counts[1];s->speed[0]=s->speed[1]=0;
 KeyDebounce_Init(&s->keys,in->keys);s->keys.locked=1;
}
void Console_Tick(ConsoleState *s,const ConsoleInput *in,ConsoleOutput *o){
 static const int ed[2]={ENCODER_LEFT_DIR,ENCODER_RIGHT_DIR};
 static const int md[2]={MOTOR_LEFT_DIR,MOTOR_RIGHT_DIR};
 static const PidGains g={SPEED_PID_KP,SPEED_PID_KI,SPEED_PID_KD,0};
 memset(o,0,sizeof(*o));s->ms+=10;s->oled_ready=in->oled_ready;
 if(s->cooldown)s->cooldown--;
 for(unsigned n=0;n<2;n++){
  int32_t d=(int32_t)(in->counts[n]-s->counts[n]);s->counts[n]=in->counts[n];s->speed[n]=(float)d*(float)ed[n];
 }
 uint8_t event=KeyDebounce_Update10ms(&s->keys,in->keys);
 /* Raw KEY4 stops before debounce; stable KEY4 also acknowledges latched faults. */
 if(in->keys&8){
  stop_all(s);o->grip_action=GA_STOP;
  if(event==8){s->fault=CF_NONE;o->clear_stopped=1;}
  return;
 }
 if(in->keys&&(in->keys&(in->keys-1))){
  Console_Fault(s,CF_KEYS);s->keys.locked=1;o->grip_action=GA_STOP;return;
 }
 /* The OLED is an optional observer. Its readiness never gates actuation. */
 if(s->fault==CF_OLED){s->fault=CF_NONE;event=0;}
 if((in->motor_status&6)||(in->grip_status&22)){
  Console_Fault(s,(in->motor_status&6)?CF_MOTOR:CF_GRIP);o->grip_action=GA_STOP;return;
 }
 if(event==KEY_DEBOUNCE_CONFLICT){Console_Fault(s,CF_KEYS);o->grip_action=GA_STOP;return;}
 if(event==1){
  stop_all(s);s->mode=s->mode==MODE_PID?MODE_GRIP:MODE_PID;o->grip_action=GA_STOP;return;
 }
 if(s->fault){o->grip_action=GA_STOP;return;}
 if(s->mode==MODE_PID){
  if(event==4&&!s->running){s->selected=(s->selected+1)%3;s->target=targets[s->selected];}
  if(event==2&&!s->running&&!s->cooldown){
   for(unsigned n=0;n<2;n++)Control_Reset(&s->wheel[n],s->speed[n]);
   s->running=1;
  }
  if(!s->running)return;
  for(unsigned n=0;n<2;n++){
   unsigned fault=Control_Step(&s->wheel[n],&g,1,(float)s->target,s->speed[n]);
   if(fault){Console_Fault(s,fault);o->grip_action=GA_STOP;return;}
   s->pwm[n]=s->wheel[n].pwm;
  }
  for(unsigned n=0;n<2;n++)o->motor_pwm[n]=(int)(s->pwm[n]*(float)md[n]);
  o->motor_run=1;return;
 }
 if(s->grip_phase==GRIP_WAIT){
  if((in->grip_status&1)&&in->grip_active_us==s->grip_pulse){s->grip_phase=GRIP_ACTIVE;s->grip_ticks=s->grip_cycle==GC_CLOSE?GRIP_CLOSE_HOLD_TICKS:GRIP_OPEN_HOLD_TICKS;}
  else if(++s->grip_wait>=10){Console_Fault(s,CF_GRIP);o->grip_action=GA_STOP;return;}
 }else if(s->grip_phase==GRIP_ACTIVE){
  if(!(in->grip_status&1)){Console_Fault(s,CF_GRIP);o->grip_action=GA_STOP;return;}
  if(s->grip_ticks&&!--s->grip_ticks){
   /* Closing settles after one second but continues powered holding.
      Only an explicit open, stop, mode switch or real fault ends it. */
   if(s->grip_cycle!=GC_CLOSE){s->grip_phase=GRIP_IDLE;s->grip_cycle=GC_NONE;o->grip_action=GA_STOP;}
  }
 }
 if((event==2||(event==4&&s->grip_phase==GRIP_IDLE))&&!s->cooldown){
  s->grip_pulse=event==2?GRIP_OPEN_US:GRIP_CLOSE_US;
  s->grip_cycle=event==4?GC_CLOSE:GC_NONE;
  s->grip_phase=GRIP_WAIT;s->grip_wait=0;s->grip_ticks=0;
  o->grip_action=GA_COMMAND;o->grip_pulse=s->grip_pulse;
 }
 o->grip_heartbeat=s->grip_phase!=GRIP_IDLE;
}
void Console_View(const ConsoleState *s,ConsoleView *v){
 memset(v,0,sizeof(*v));v->magic=VIEW_MAGIC;v->ms=s->ms;v->mode=s->mode;v->running=s->running;
 v->fault=s->fault;v->target=s->target;v->grip_phase=s->grip_phase;v->grip_pulse=s->grip_pulse;
 v->grip_remaining_ms=s->grip_ticks*10;v->oled_ready=s->oled_ready;v->grip_cycle=s->grip_cycle;
 v->remote_active=s->remote_active;
 for(unsigned n=0;n<2;n++){v->speed[n]=s->speed[n];v->pwm[n]=s->pwm[n];}
}
