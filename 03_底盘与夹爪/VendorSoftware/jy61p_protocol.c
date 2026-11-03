#include "jy61p_protocol.h"
#include <inttypes.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
static int signed16(const uint8_t *p){unsigned v=p[0]|((unsigned)p[1]<<8);return v>=32768?(int)v-65536:(int)v;}
void Imu_Init(ImuState *s){memset(s,0,sizeof(*s));}
void Imu_Invalidate(ImuState *s){s->used=0;s->valid_mask=0;}
static void shift_one(ImuState *s){memmove(s->bytes,s->bytes+1,--s->used);s->discarded++;}
unsigned Imu_Feed(ImuState *s,uint8_t b,uint64_t now){
 if(!s->used&&b!=0x55){s->discarded++;return 0;}
 s->bytes[s->used++]=b;if(s->used<11)return 0;
 unsigned sum=0;for(unsigned i=0;i<10;i++)sum+=s->bytes[i];
 if((uint8_t)sum!=s->bytes[10]){
  s->bad_checksum++;shift_one(s);
  while(s->used&&s->bytes[0]!=0x55)shift_one(s);
  return 0;
 }
 float *v=NULL,scale=0;unsigned field=0,n=3;
 switch(s->bytes[1]){
  case 0x51:v=s->accel_g;scale=16.0f/32768;field=0;break;
  case 0x52:v=s->gyro_dps;scale=2000.0f/32768;field=1;break;
  case 0x53:v=s->angle_deg;scale=180.0f/32768;field=2;break;
  case 0x59:v=s->quaternion;scale=1.0f/32768;field=3;n=4;break;
  default:s->unknown_frames++;s->used=0;return 0;
 }
 for(unsigned i=0;i<n;i++)v[i]=(float)signed16(s->bytes+2+2*i)*scale;
 s->used=0;s->valid_frames++;s->stamp_ms[field]=now;s->valid_mask|=1U<<field;return 1U<<field;
}
int Imu_Fresh(const ImuState *s,unsigned f,uint64_t now,uint64_t age){return f<4&&(s->valid_mask&(1U<<f))&&now>=s->stamp_ms[f]&&now-s->stamp_ms[f]<=age;}
typedef struct{char *b;size_t cap,n;int bad;} Json;
static void add(Json *j,const char *fmt,...){
 if(j->bad)return;
 va_list ap;va_start(ap,fmt);int n=vsnprintf(j->b+j->n,j->cap-j->n,fmt,ap);va_end(ap);
 if(n<0||(size_t)n>=j->cap-j->n){j->bad=1;return;}j->n+=(size_t)n;
}
static void vector(Json *j,const float *v,unsigned n,int fresh){
 if(!fresh){add(j,"null");return;}
 add(j,"[");for(unsigned i=0;i<n;i++)add(j,"%s%.5f",i?",":"",(double)v[i]);add(j,"]");
}
int Imu_FormatJson(const ImuState *s,unsigned baud,uint64_t now,int acquired,uint64_t errors,char *out,size_t cap){
 if(!cap)return -1;
 Json j={out,cap,0,0};int fresh[4],any=0;
 for(unsigned i=0;i<4;i++){fresh[i]=Imu_Fresh(s,i,now,500);any|=fresh[i];}
 const char *link=!acquired?"searching":!s->valid_frames?"waiting":fresh[2]?"ok":any?"partial":"stale";
 add(&j,"{\"baud\":%u,\"link\":\"%s\",\"frames\":%" PRIu64 ",\"checksum_errors\":%" PRIu64 ",\"uart_errors\":%" PRIu64 ",\"accel_g\":",baud,link,s->valid_frames,s->bad_checksum,errors);
 vector(&j,s->accel_g,3,fresh[0]);add(&j,",\"gyro_dps\":");vector(&j,s->gyro_dps,3,fresh[1]);
 add(&j,",\"angle_deg\":");vector(&j,s->angle_deg,3,fresh[2]);add(&j,",\"quaternion\":");vector(&j,s->quaternion,4,fresh[3]);
 add(&j,",\"age_ms\":[");for(unsigned i=0;i<4;i++){
  if(i)add(&j,",");
  if((s->valid_mask&(1U<<i))&&now>=s->stamp_ms[i])add(&j,"%" PRIu64,now-s->stamp_ms[i]);else add(&j,"null");
 }
 add(&j,"]}\n");return j.bad?-1:(int)j.n;
}
