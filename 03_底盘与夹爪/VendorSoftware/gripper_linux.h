#ifndef GRIPPER_LINUX_H
#define GRIPPER_LINUX_H
#include <stdint.h>
/* access:0=probe,1=exclusive controller,2=stop-only without controller lock. */
int Gripper_Open(int access);
void Gripper_Close(void);
int Gripper_Stop(void);
int Gripper_Limits(uint32_t min_us,uint32_t max_us);
int Gripper_Command(uint32_t pulse_us);
void Gripper_Heartbeat(void);
uint32_t Gripper_Status(void);
uint32_t Gripper_ActiveUs(void);
#endif
