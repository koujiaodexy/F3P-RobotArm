#define _GNU_SOURCE
#include "board.h"
#include "board_linux.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <sys/mman.h>
#include <sys/file.h>
#include <unistd.h>
static volatile uint32_t *regs;
static int fd=-1,lock_fd=-1,can_write;
static uint32_t counts[2];
static uint8_t keys;
static int commands[2];
/* AArch64 Device mapping: order MMIO transactions before/after each access. */
static void barrier(void) {
#ifdef __aarch64__
 __asm__ volatile("dmb sy" ::: "memory");
#else
 __sync_synchronize();
#endif
}
static uint32_t rd(unsigned a) { barrier(); uint32_t v=regs[a]; barrier(); return v; }
static void wr(unsigned a,uint32_t v) { if(can_write) { barrier(); regs[a]=v; barrier(); } }
int Hardware_Open(int writable) {
 fd=open("/dev/mem",(writable?O_RDWR:O_RDONLY)|O_SYNC|O_CLOEXEC);
 if(fd<0) { perror("open /dev/mem"); return -1; }
 void *m=mmap(NULL,4096,PROT_READ|(writable?PROT_WRITE:0),MAP_SHARED,fd,0xa0000000ULL);
 if(m==MAP_FAILED) { perror("mmap"); close(fd); fd=-1; return -1; }
 regs=m;
 /* No writes before every ABI/clock guard succeeds. Old firmware is rejected. */
 if(rd(0x90)!=0x4d4f5431 || rd(0x91)!=0x10000 || rd(0x92)!=133333333 ||
    rd(0x93)!=1333333 || rd(0x94)!=13333 || rd(0xa1)!=13333300) {
   fputs("Motor ABI/clock mismatch: no writes performed.\n",stderr);
   munmap(m,4096); regs=NULL;close(fd);fd=-1;return -1;
 }
 if(writable) {
  lock_fd=open("/run/lock/f3p-motor.lock",O_RDWR|O_CREAT|O_NOFOLLOW|O_CLOEXEC,0600);
  if(lock_fd<0 || flock(lock_fd,LOCK_EX|LOCK_NB)) {
   fputs("Motor owner busy or lock unavailable: no writes performed.\n",stderr);
   Hardware_Close();return -1;
  }
 }
 can_write=writable;
 return 0;
}
void Hardware_Disarm(void) { if(regs) wr(0x9c,0); commands[0]=commands[1]=0; }
void Hardware_ClearStopped(void) { if(regs) { Hardware_Disarm();wr(0x9d,0x434c5200); } }
void Hardware_Close(void) { if(regs) { if(can_write) Hardware_Disarm();munmap((void*)regs,4096); } if(fd>=0)close(fd);if(lock_fd>=0)close(lock_fd);regs=NULL;fd=lock_fd=-1;can_write=0; }
int Hardware_Snapshot(uint32_t *seq) {
 for(unsigned i=0;i<16;i++) {
  uint32_t a=rd(0x95),l=rd(0x96),r=rd(0x97),k=rd(0x98),b=rd(0x95);
  if(a==b) { counts[0]=l;counts[1]=r;keys=(uint8_t)(k&15);*seq=a;return 0; }
 }
 return -1;
}
uint32_t Hardware_Status(void) { return rd(0x99); }
/* This checks command/FIFO ownership only; it does not prove the arm pose. */
uint32_t Hardware_ArmIdle(void) { return rd(0)==0x52414331 && !(rd(5)&5) && !(rd(0x1a)&1); }
void Hardware_Flush(int running) {
 if(!running) { Hardware_Disarm();return; }
 wr(0x9a,(uint32_t)commands[0]);wr(0x9b,(uint32_t)commands[1]);wr(0x9c,0x43415201);
}
void Board_SetMotor(unsigned wheel,int power) { if(wheel<2)commands[wheel]=power; }
uint32_t Board_Count(unsigned wheel) { return counts[wheel]; }
uint8_t Board_Keys(void) { return keys; }
/* Expansion board has no MCU status LEDs; equivalent state is in telemetry. */
void Board_Leds(uint8_t running,uint8_t pid_mode) { (void)running;(void)pid_mode; }

/* Zero on legacy firmware; never infer high PWM capability from its ABI. */
unsigned Hardware_MaxMotorPwm(void) { return rd(0xb8); }
