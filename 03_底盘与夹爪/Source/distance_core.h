#ifndef DISTANCE_CORE_H
#define DISTANCE_CORE_H
#include "console_core.h"
#include <stdint.h>
#define DISTANCE_MAGIC 0x44495331U
enum {DIST_READY,DIST_RUN,DIST_SETTLING,DIST_DONE,DIST_STOPPED,DIST_FAULT};
typedef struct {double mm_per_count[2],target_mm;unsigned calibrated;} DistanceConfig;
typedef struct {
 uint32_t magic,phase,fault,elapsed_ms,settle_ms,quiet_ms,page,end_phase,run_serial;
 uint32_t counts[2],stall_ms[2];
 unsigned heading_required,imu_ready;int yaw_sign,steering_polarity;double yaw_deg,yaw_start_deg,yaw_error_deg,gyro_z_dps,yaw_integral;int64_t net[2],path[2];double mm[2];float speed[2],pwm[2];
 WheelControl wheel[2];KeyDebounce keys;DistanceConfig config;
} DistanceState;
typedef struct {int pwm[2];unsigned enable,clear_stopped;} DistanceOutput;
int Distance_ConfigValid(const DistanceConfig *c);
void Distance_DefaultConfig(DistanceConfig *c);
void Distance_Init(DistanceState *s,const ConsoleInput *in,const DistanceConfig *config);
void Distance_EnableHeading(DistanceState *s,int sign);
int Distance_SetSteeringPolarity(DistanceState *s,int polarity);
void Distance_HeadingSample(DistanceState *s,int fresh,double yaw_deg,double gyro_z_dps);
void Distance_Fault(DistanceState *s,unsigned code);
void Distance_Tick(DistanceState *s,const ConsoleInput *in,DistanceOutput *out);
void Distance_Frame(const DistanceState *s,int lost,uint8_t frame[1024],char lines[4][22]);
const char *Distance_Phase(unsigned phase);
int Distance_Run(unsigned smoke_seconds);
int Distance_RunHeading(unsigned smoke_seconds);
int Distance_Render(const char *path);
#endif
