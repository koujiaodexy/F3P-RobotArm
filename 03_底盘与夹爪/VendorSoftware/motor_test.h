#ifndef MOTOR_TEST_H
#define MOTOR_TEST_H
#include "control.h"

enum { TEST_WHEEL_DIRECTION = 1U, TEST_DUAL_PID = 2U };

typedef struct {
    uint32_t ms, mode, running, fault;
    int32_t count[2];
    float speed[2], target[2], pwm[2];
} MotorMonitor;

extern volatile MotorMonitor g_monitor;
void MotorTest_Init(void);
void MotorTest_Tick10ms(void);
void MotorTest_Stop(void);
void Console_Init(void);
void Console_Poll(void);

#endif
