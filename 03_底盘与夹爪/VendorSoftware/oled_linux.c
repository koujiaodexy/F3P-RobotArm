#define _GNU_SOURCE
#include "oled_linux.h"
#include <fcntl.h>
#include <stdio.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
static volatile uint32_t *regs;
static int fd=-1,lock_fd=-1,writable;
static void barrier(void) {
#ifdef __aarch64__
 __asm__ volatile("dmb sy" ::: "memory");
#else
 __sync_synchronize();
#endif
}
static uint32_t rd(unsigned a){barrier();uint32_t v=regs[a];barrier();return v;}
static void wr(unsigned a,uint32_t v){if(writable){barrier();regs[a]=v;barrier();}}
static uint64_t ns(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000ULL+t.tv_nsec;}
static void pause_us(unsigned us){struct timespec t={0,(long)us*1000};nanosleep(&t,NULL);}
void Oled_Close(void){if(regs)munmap((void*)regs,4096);if(fd>=0)close(fd);if(lock_fd>=0)close(lock_fd);regs=NULL;fd=lock_fd=-1;writable=0;}
int Oled_Open(int write_access){
 fd=open("/dev/mem",(write_access?O_RDWR:O_RDONLY)|O_SYNC|O_CLOEXEC);
 if(fd<0){perror("OLED /dev/mem");return -1;}
 void *p=mmap(NULL,4096,PROT_READ|(write_access?PROT_WRITE:0),MAP_SHARED,fd,0xa0000000ULL);
 if(p==MAP_FAILED){perror("OLED mmap");Oled_Close();return -1;}regs=p;
 if(rd(0xa2)!=0x4f4c4431||rd(0x92)!=133333333||rd(0xa7)!=667){
  fputs("OLED ABI/clock mismatch: no writes.\n",stderr);Oled_Close();return -1;
 }
 if(write_access){
  lock_fd=open("/run/lock/f3p-oled.lock",O_RDWR|O_CREAT|O_NOFOLLOW|O_CLOEXEC,0600);
  if(lock_fd<0||flock(lock_fd,LOCK_EX|LOCK_NB)){fputs("OLED writer already running or lock unavailable.\n",stderr);Oled_Close();return -1;}
 }
 writable=write_access;return 0;
}
static int packet(uint8_t control,const uint8_t *payload,unsigned n){
 if(!n||n>30||(rd(0xa3)&1))return -1;
 wr(0xa5,0x4f4c0000);wr(0xa4,0x78);wr(0xa4,control);
 for(unsigned i=0;i<n;i++)wr(0xa4,payload[i]);
 wr(0xa5,0x4f4c0001);
 uint64_t deadline=ns()+20000000ULL;
 while(rd(0xa3)&1){if(ns()>deadline)return -1;pause_us(100);}
 return (rd(0xa3)&14)?-1:0;
}
int Oled_InitPanel(void){
 // Same SSD1306 128x64, page mode, 0x3c setup as the original M0 driver.
 static const uint8_t init[]={0xae,0x20,0x02,0xb0,0xc8,0x00,0x10,0x40,0x81,0x7f,0xa1,0xa6,
  0xa8,0x3f,0xa4,0xd3,0x00,0xd5,0x80,0xd9,0xf1,0xda,0x12,0xdb,0x40,0x8d,0x14,0xaf};
 pause_us(100000); // Power stabilization: OLED process only, never the PID thread.
 return packet(0,init,sizeof(init));
}
int Oled_SendFrame(const uint8_t frame[1024]){
 for(unsigned page=0;page<8;page++){
  uint8_t pos[3]={(uint8_t)(0xb0+page),0,0x10};if(packet(0,pos,3))return -1;
  for(unsigned x=0;x<128;x+=30){unsigned n=128-x;if(n>30)n=30;if(packet(0x40,frame+page*128+x,n))return -1;}
 }
 return 0;
}
