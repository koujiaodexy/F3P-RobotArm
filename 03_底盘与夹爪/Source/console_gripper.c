#define _GNU_SOURCE
#include "gripper_linux.h"
#include <fcntl.h>
#include <stdio.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
static volatile uint32_t *regs;
static int fd=-1,lock_fd=-1,can_write;
static void barrier(void){
#ifdef __aarch64__
 __asm__ volatile("dmb sy" ::: "memory");
#else
 __sync_synchronize();
#endif
}
static uint32_t rd(unsigned a){barrier();uint32_t v=regs[a];barrier();return v;}
static void wr(unsigned a,uint32_t v){if(can_write==1||(can_write==2&&a==0xb3&&v==0)){barrier();regs[a]=(can_write==2)?0x47525354U:v;barrier();}}
static uint64_t ms(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000+t.tv_nsec/1000000;}
static void pause_short(void){struct timespec t={0,200000};nanosleep(&t,NULL);}
uint32_t Gripper_Status(void){return rd(0xb1);}
uint32_t Gripper_ActiveUs(void){return rd(0xb3);}
int Gripper_Stop(void){
 if(!regs||!can_write)return -1;
 wr(0xb3,0);uint64_t end=ms()+50;
 while(rd(0xb1)&9){if(ms()>end)return -1;pause_short();}return 0;
}
void Gripper_Close(void){if(regs){if(can_write)(void)Gripper_Stop();munmap((void*)regs,4096);}if(fd>=0)close(fd);if(lock_fd>=0)close(lock_fd);regs=NULL;fd=lock_fd=-1;can_write=0;}
int Gripper_Open(int writable){
 fd=open("/dev/mem",(writable?O_RDWR:O_RDONLY)|O_SYNC|O_CLOEXEC);if(fd<0){perror("gripper /dev/mem");return -1;}
 void *p=mmap(NULL,4096,PROT_READ|(writable?PROT_WRITE:0),MAP_SHARED,fd,0xa0000000ULL);
 if(p==MAP_FAILED){perror("gripper mmap");Gripper_Close();return -1;}regs=p;
 if(rd(0xb0)!=0x47525031||rd(0xb6)!=2000||rd(0x92)!=133333333){fputs("Gripper ABI/clock mismatch: no writes.\n",stderr);Gripper_Close();return -1;}
 if(writable==1){
  lock_fd=open("/run/lock/f3p-gripper.lock",O_RDWR|O_CREAT|O_NOFOLLOW|O_CLOEXEC,0600);
  if(lock_fd<0||flock(lock_fd,LOCK_EX|LOCK_NB)){fputs("Gripper owner busy or lock unavailable.\n",stderr);Gripper_Close();return -1;}
 }
 can_write=writable;return 0;
}
int Gripper_Limits(uint32_t min,uint32_t max){
 if(can_write!=1||min<500||max>2500||min>max||Gripper_Stop())return -1;
 wr(0xb3,0x47524300); // Clear sticky faults only after the last pulse has ended.
 wr(0xb4,500);wr(0xb5,2500);wr(0xb4,min);wr(0xb5,max);
 return rd(0xb4)==min&&rd(0xb5)==max&&!(rd(0xb1)&22)?0:-1;
}
int Gripper_Command(uint32_t pulse){
 if(can_write!=1||pulse<rd(0xb4)||pulse>rd(0xb5)||(rd(0xb1)&22))return -1;
 wr(0xb2,pulse);wr(0xb3,0x47525001);uint64_t end=ms()+80;
 while(!(rd(0xb1)&1)||rd(0xb3)!=pulse){if((rd(0xb1)&22)||ms()>end)return -1;pause_short();}return 0;
}
void Gripper_Heartbeat(void){wr(0xb6,0x47524842);}

/* Console adapter: frame completion is polled by the 10ms state machine. */
int Gripper_QueuePulse(uint32_t pulse){
 if(can_write!=1||pulse<rd(0xb4)||pulse>rd(0xb5)||(rd(0xb1)&22))return -1;
 wr(0xb2,pulse);wr(0xb3,0x47525001);return 0;
}
void Gripper_RequestStop(void){if(regs&&can_write)wr(0xb3,0);}
int Gripper_ClearStopped(void){
 if(can_write!=1||(rd(0xb1)&9))return -1;
 wr(0xb3,0x47524300);return (rd(0xb1)&22)?-1:0;
}
