#ifndef CONSOLE_WIRING_H
#define CONSOLE_WIRING_H
#include <stdint.h>
#include "motor_config.h"
/* Hardware counter order is separate from physical wheel order. */
static inline void Console_MapEncoderCounts(const uint32_t hardware[2],uint32_t physical[2]){
 uint32_t left=hardware[ENCODER_LEFT_CHANNEL];
 uint32_t right=hardware[ENCODER_RIGHT_CHANNEL];
 physical[0]=left;physical[1]=right;
}
/* Commands carry physical-wheel polarity; place them on the paired outputs. */
static inline void Console_MapMotorCommands(const int physical[2],int hardware[2]){
 int left=physical[0],right=physical[1];
 hardware[MOTOR_LEFT_CHANNEL]=left;
 hardware[MOTOR_RIGHT_CHANNEL]=right;
}
#endif
