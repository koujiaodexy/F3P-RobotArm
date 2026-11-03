#include "parking_remote.h"
#include <string.h>
#include <ctype.h>
#include <math.h>
void ParkingRemote_Init(ParkingRemote *r){memset(r,0,sizeof(*r));}
static int token_valid(const char *s){size_t n=strlen(s);if(!n||n>64)return 0;for(size_t i=0;i<n;i++)if(!isalnum((unsigned char)s[i])&&s[i]!='_'&&s[i]!='-')return 0;return 1;}
int ParkingRemote_Command(ParkingRemote *r,ParkingState *s,const ConsoleInput *in,const char *token,const char *command,uint64_t now){
 if(!token_valid(token))return -1;
 if(!strcmp(command,"status"))return 0;
 if(!strcmp(command,"stop")){Parking_Stop(s);ParkingRemote_Init(r);return 0;}
 if(!strcmp(command,"prepare")){
  if((r->active&&strcmp(r->owner,token))||s->phase==PARK_RUN||s->phase==PARK_SETTLE||s->fault||in->keys||!s->imu_ready||(in->motor_status&7)||(in->grip_status&31))return -1;
  if(in->counts[0]!=s->counts[0]||in->counts[1]!=s->counts[1]||fabsf(s->speed[0])>.5f||fabsf(s->speed[1])>.5f)return -1;
  Parking_Reset(s,in);strcpy(r->owner,token);r->active=r->prepared=1;r->deadline_ms=now+750;return 0;
 }
 if(!r->active||strcmp(r->owner,token)||now>=r->deadline_ms)return -1;
 if(!strcmp(command,"heartbeat")){r->deadline_ms=now+750;return 0;}
 if(!strcmp(command,"start")){
  if(s->config.route_mode>=2)return -1; /* Physical KEY2 only for initial combined mission. */
  if(!r->prepared||in->keys||Parking_Start(s,in))return -1;
  r->prepared=0;r->deadline_ms=now+750;return 0;
 }return -1;
}
void ParkingRemote_Tick(ParkingRemote *r,ParkingState *s,const ConsoleInput *in,uint64_t now){
 if(!r->active)return;
 if(in->keys&8){Parking_Stop(s);ParkingRemote_Init(r);return;}
 if(in->keys&(s->config.route_mode>=2?1U:3U)){Parking_Fault(s,CF_KEYS);ParkingRemote_Init(r);return;}
 if(now>=r->deadline_ms){Parking_Fault(s,CF_LINK);ParkingRemote_Init(r);return;}
 if(s->phase==PARK_DONE||s->phase==PARK_STOP||s->phase==PARK_FAULT)ParkingRemote_Init(r);
}
