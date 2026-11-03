#define _GNU_SOURCE
#include "jy61p_linux.h"
#include <fcntl.h>
#include <stdio.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
static volatile uint32_t *regs;
static int fd=-1,lock_fd=-1,writable;
static void barrier(void){
#ifdef __aarch64__
 __asm__ volatile("dmb sy" ::: "memory");
#else
 __sync_synchronize();
#endif
}
static uint32_t rd(unsigned a){barrier();uint32_t v=regs[a];barrier();return v;}
static void wr(unsigned a,uint32_t v){if(writable){barrier();regs[a]=v;barrier();}}
static uint64_t ms(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000+t.tv_nsec/1000000;}
static int wait_tx(void){uint64_t end=ms()+200;while(rd(0xa9)&2){if(ms()>end)return -1;struct timespec t={0,100000};nanosleep(&t,NULL);}return 0;}
void ImuHardware_Close(void){if(regs)munmap((void*)regs,4096);if(fd>=0)close(fd);if(lock_fd>=0)close(lock_fd);regs=NULL;fd=lock_fd=-1;writable=0;}
int ImuHardware_Open(int write_access){
 fd=open("/dev/mem",(write_access?O_RDWR:O_RDONLY)|O_SYNC|O_CLOEXEC);if(fd<0){perror("IMU /dev/mem");return -1;}
 void *p=mmap(NULL,4096,PROT_READ|(write_access?PROT_WRITE:0),MAP_SHARED,fd,0xa0000000ULL);
 if(p==MAP_FAILED){perror("IMU mmap");ImuHardware_Close();return -1;}regs=p;
 if(rd(0xa8)!=0x4a593631||rd(0xad)!=0x10000||rd(0x92)!=133333333){fputs("IMU ABI/clock mismatch: no writes.\n",stderr);ImuHardware_Close();return -1;}
 if(write_access){
  lock_fd=open("/run/lock/f3p-imu.lock",O_RDWR|O_CREAT|O_NOFOLLOW|O_CLOEXEC,0600);
  if(lock_fd<0||flock(lock_fd,LOCK_EX|LOCK_NB)){fputs("IMU owner already running or lock unavailable.\n",stderr);ImuHardware_Close();return -1;}
 }
 writable=write_access;return 0;
}
int ImuHardware_Configure(unsigned baud){
 switch(baud){case 4800:case 9600:case 19200:case 38400:case 57600:case 115200:case 230400:break;default:return -1;}
 if(wait_tx())return -1;
 uint32_t divisor=(133333333U+baud/2)/baud;wr(0xaa,divisor);
 return rd(0xaa)==divisor&&!(rd(0xa9)&16)?0:-1;
}
int ImuHardware_Read(uint8_t *p,size_t cap){
 size_t n=0;while(n<cap){uint32_t v=rd(0xab);if(!(v&256))break;p[n++]=(uint8_t)v;wr(0xab,0x52585001);}return (int)n;
}
uint32_t ImuHardware_Status(void){return rd(0xa9);}
uint32_t ImuHardware_Errors(void){return rd(0xaf);}
void ImuHardware_Flush(void){if(!(rd(0xa9)&2))wr(0xad,0x4a594300);}
int ImuHardware_Send(const uint8_t *p,size_t n){
 if(!writable||!p||!n||n>32)return -1;
 for(size_t i=0;i<n;i++){if(wait_tx())return -1;wr(0xac,0x54580000U|p[i]);}return wait_tx();
}
