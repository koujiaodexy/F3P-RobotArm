#include "oled_display.h"
#include "motor_config.h"
#include <ctype.h>
#include <errno.h>
#include <stdlib.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
void Oled_GetGlyph(char ch,uint8_t glyph[5]);
// Parse integer fields before narrowing: scanf %u silently wraps on common libc.
static int csv_u32(const char **cursor,uint32_t *value) {
 const char *p=*cursor;while(isspace((unsigned char)*p))p++;
 if(!isdigit((unsigned char)*p))return -1;
 char *end;errno=0;unsigned long long n=strtoull(p,&end,10);
 if(errno||n>UINT32_MAX||*end!=',')return -1;
 *value=(uint32_t)n;*cursor=end+1;return 0;
}
int Oled_ParseLine(const char *s,MotorMonitor *m) {
 if(!s||!m)return -1;
 MotorMonitor n={0};uint32_t ms,mode,run,fault;
 if(csv_u32(&s,&ms)||csv_u32(&s,&mode)||csv_u32(&s,&run)||csv_u32(&s,&fault))return -1;
 if((mode!=TEST_WHEEL_DIRECTION&&mode!=TEST_DUAL_PID)||run>1||fault>FAULT_UART)return -1;
 float *fields[]={&n.target[0],&n.target[1],&n.speed[0],&n.speed[1],&n.pwm[0],&n.pwm[1]};
 for(unsigned i=0;i<6;i++) {
  char *end;errno=0;float v=strtof(s,&end);
  if(end==s||errno||!isfinite(v))return -1;
  *fields[i]=v;
  if(i<5){if(*end!=',')return -1;s=end+1;}else s=end;
 }
 for(;*s;s++)if(!isspace((unsigned char)*s))return -1;
 for(unsigned i=0;i<2;i++)if(fabsf(n.pwm[i])>PWM_LIMIT)return -1;
 n.ms=ms;n.mode=mode;n.running=run;n.fault=fault;*m=n;return 0;
}
void Oled_Frame(const MotorMonitor *m,int lost,uint8_t frame[1024],char lines[4][22]) {
 memset(frame,0,1024);memset(lines,0,4*22);
 if(!m||lost) {
  snprintf(lines[0],22,"%s",lost?"LINK LOST":"WAIT CONTROL");
  snprintf(lines[1],22,"F3P MOTOR MONITOR");
  snprintf(lines[2],22,"10MS PID  200MS OLED");
  snprintf(lines[3],22,"%s",lost?"CHECK CONTROL LINK":"KEY1 RUN/STOP");
 } else {
  snprintf(lines[0],22,"%s %s",m->mode==TEST_DUAL_PID?"2 DUAL PID":"1 WHEEL DIR",m->running?"RUN":"STOP");
  snprintf(lines[1],22,"SET:%+.0f %+.0f",(double)(m->mode==TEST_DUAL_PID?PID_TARGET_SPEED:TEST_PWM_LEFT),
           (double)(m->mode==TEST_DUAL_PID?PID_TARGET_SPEED:TEST_PWM_RIGHT));
  if(fabsf(m->speed[0])>99999||fabsf(m->speed[1])>99999)snprintf(lines[2],22,"SPD: OUT OF RANGE");
  else snprintf(lines[2],22,"SPD:%+.0f %+.0f",(double)m->speed[0],(double)m->speed[1]);
  if(m->fault)snprintf(lines[3],22,"F:%u STOP",m->fault);
  else snprintf(lines[3],22,"OUT:%+.0f %+.0f",(double)m->pwm[0],(double)m->pwm[1]);
 }
 // Original five-column glyphs, doubled vertically into four 16-pixel rows.
 for(unsigned row=0;row<4;row++)for(unsigned ch=0;lines[row][ch]&&ch<21;ch++) {
  uint8_t g[5];Oled_GetGlyph(lines[row][ch],g);
  for(unsigned x=0;x<5;x++)for(unsigned y=0;y<8;y++)if(g[x]&(1U<<y))for(unsigned k=0;k<2;k++){
   unsigned py=row*16+y*2+k;frame[(py/8)*128+ch*6+x]|=(uint8_t)(1U<<(py%8));
  }
 }
}
int Oled_WritePbm(const char *path,const uint8_t frame[1024]) {
 FILE *f=fopen(path,"wb");if(!f)return -1;
 fprintf(f,"P4\n128 64\n");
 for(unsigned y=0;y<64;y++)for(unsigned x=0;x<128;x+=8) {
  unsigned b=0;for(unsigned i=0;i<8;i++)if(frame[(y/8)*128+x+i]&(1U<<(y%8)))b|=1U<<(7-i);
  if(fputc((int)b,f)==EOF){fclose(f);return -1;}
 }
 return fclose(f);
}
