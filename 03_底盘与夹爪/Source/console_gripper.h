#ifndef CONSOLE_GRIPPER_H
#define CONSOLE_GRIPPER_H
#include "gripper_linux.h"
int Gripper_QueuePulse(uint32_t us);
void Gripper_RequestStop(void);
int Gripper_ClearStopped(void);
#endif
