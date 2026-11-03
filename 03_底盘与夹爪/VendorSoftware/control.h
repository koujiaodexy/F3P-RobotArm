#ifndef CONTROL_H
#define CONTROL_H
#include <stdint.h>

typedef struct {
    float kp, ki, kd, feedforward;
} PidGains;

typedef struct {
    float ramp, integral, last_speed, pwm;
    uint16_t stalled_ticks, wrong_ticks;
} WheelControl;

enum { FAULT_NONE, FAULT_ENCODER_SIGN, FAULT_STALL, FAULT_REVERSE,
       FAULT_CONFIG, FAULT_UART };

unsigned Control_StepPolicy(WheelControl *s,const PidGains *g,uint32_t pid_mode,float target,float speed,int enforce_encoder_direction);
float Control_Clamp(float value, float low, float high);
void Control_Reset(WheelControl *state, float speed);
unsigned Control_Step(WheelControl *state, const PidGains *gains,
    uint32_t pid_mode, float target, float speed);
int Control_ValidGains(const PidGains *gains);

#endif
