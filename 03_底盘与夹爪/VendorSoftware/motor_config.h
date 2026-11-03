#ifndef MOTOR_CONFIG_H
#define MOTOR_CONFIG_H

#include <stdint.h>

/* User reversed chassis front/rear 2026-10-25; no wiring changed.
 * New physical left = old right: encoder HW0+, motor HW0-.
 * New physical right = old left: encoder HW1-, motor HW1+.
 * Swapping sides AND reversing each physical wheel makes native forward
 * outputs change from old HW0+/HW1- to new HW0-/HW1+.
 */
#define MOTOR_LEFT_DIR               -1
#define MOTOR_RIGHT_DIR              1
#define ENCODER_LEFT_DIR             -1
#define ENCODER_RIGHT_DIR            1

#define MOTOR_LEFT_CHANNEL            0
#define MOTOR_RIGHT_CHANNEL           1
#if (MOTOR_LEFT_CHANNEL != 0 && MOTOR_LEFT_CHANNEL != 1) || \
    (MOTOR_RIGHT_CHANNEL != 0 && MOTOR_RIGHT_CHANNEL != 1) || \
    MOTOR_LEFT_CHANNEL == MOTOR_RIGHT_CHANNEL
#error "Motor channels must be a permutation of 0 and 1"
#endif

#define ENCODER_LEFT_CHANNEL          0
#define ENCODER_RIGHT_CHANNEL         1
#if (ENCODER_LEFT_CHANNEL != 0 && ENCODER_LEFT_CHANNEL != 1) || \
    (ENCODER_RIGHT_CHANNEL != 0 && ENCODER_RIGHT_CHANNEL != 1) || \
    ENCODER_LEFT_CHANNEL == ENCODER_RIGHT_CHANNEL
#error "Encoder channels must be a permutation of 0 and 1"
#endif

/* Function 1: wheel rotation. Set one side to zero to isolate it. */
#define TEST_PWM_LEFT              200.0f
#define TEST_PWM_RIGHT             200.0f

/* Function 2: both wheels use the same speed and three PID gains. */
#define PID_TARGET_SPEED            20.0f
#define SPEED_PID_KP                20.0f
#define SPEED_PID_KI                 0.2f
#define SPEED_PID_KD                 0.0f
#define PWM_LIMIT                  600.0f
#define SPEED_LIMIT                 40.0f
#define TARGET_SLEW_PER_TICK         0.5f
#define PWM_SLEW_PER_TICK           20.0f
/* Calibration only: the schematic cannot determine the motor gear ratio. */
#define ENCODER_COUNTS_PER_REV     1771.4f

#if (MOTOR_LEFT_DIR != 1 && MOTOR_LEFT_DIR != -1) || \
    (MOTOR_RIGHT_DIR != 1 && MOTOR_RIGHT_DIR != -1) || \
    (ENCODER_LEFT_DIR != 1 && ENCODER_LEFT_DIR != -1) || \
    (ENCODER_RIGHT_DIR != 1 && ENCODER_RIGHT_DIR != -1)
#error "Motor and encoder direction macros must be +1 or -1"
#endif

#endif
