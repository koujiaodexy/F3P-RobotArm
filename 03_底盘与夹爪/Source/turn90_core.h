
#ifndef TURN90_CORE_H
#define TURN90_CORE_H
#include "distance_core.h"
#define TURN90_MAGIC 0x54393031U
/* Bench20261026: positive HW0 and HW1 each drive the current physical wheels forward.
 * Override legacy motor polarity only for the independent turn90 test. */
#define TURN90_LEFT_MOTOR_FORWARD_DIR 1
#define TURN90_RIGHT_MOTOR_FORWARD_DIR 1
#define TURN90_MIN_PWM 100U
#define TURN90_MAX_PWM 800U
#define TURN90_STEP_PWM 25U
enum {T90_READY,T90_RUN,T90_SETTLE,T90_DONE,T90_STOP,T90_FAULT};
typedef struct {unsigned initial_pwm;int yaw_sign,direction;} Turn90Config;
typedef struct {
 uint32_t magic,phase,fault,run_id,total_ms,settle_ms,quiet_ms,selected_pwm,applied_pwm,peak_pwm,initial_pwm;
 uint32_t counts[2],stall_ms[2],wrong_ticks[2];int64_t run_counts[2],path_counts[2];uint32_t angle_watch_ms;double angle_watch_yaw;
 float speed[2];double yaw_deg,yaw_unwrapped,previous_yaw,yaw_start,angle_deg,gyro_z_dps,target_deg;
 uint32_t imu_ready,had_yaw;KeyDebounce keys;Turn90Config config;
} Turn90State;
int Turn90_SetTarget(Turn90State *,double);
int Turn90_Start(Turn90State *,const ConsoleInput *);
void Turn90_Init(Turn90State *,const ConsoleInput *,const Turn90Config *);
int Turn90_ConfigValid(const Turn90Config *);
void Turn90_ImuSample(Turn90State *,int,double,double);
void Turn90_Tick(Turn90State *,const ConsoleInput *,DistanceOutput *);
void Turn90_Stop(Turn90State *);
void Turn90_Fault(Turn90State *,unsigned);
const char *Turn90_Phase(unsigned);
void Turn90_Frame(const Turn90State *,int,uint8_t[1024],char[4][22]);
int Turn90_Run(unsigned);
int Turn90_Render(const char *);
#endif
