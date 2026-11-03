#ifndef BOARD_LINUX_H
#define BOARD_LINUX_H
#include <stdint.h>
int Hardware_Open(int writable);
void Hardware_Close(void);
int Hardware_Snapshot(uint32_t *seq);
uint32_t Hardware_Status(void);
uint32_t Hardware_ArmIdle(void);
void Hardware_Disarm(void);
void Hardware_ClearStopped(void);
void Hardware_Flush(int running);
#endif

unsigned Hardware_MaxMotorPwm(void);
