#ifndef PARKING_CORE_H
#define PARKING_CORE_H
#include "distance_core.h"
#include "turn90_core.h"
#define STRAIGHT_PWM_LIMIT 600
#define STRAIGHT_CRUISE_COUNTS 20.0
#define PARKING_MAGIC 0x50415231U
enum {PARK_READY,PARK_RUN,PARK_SETTLE,PARK_DONE,PARK_STOP,PARK_FAULT};
enum {PF_IMU=16,PF_ANGLE=17,PF_IMU_STUCK=18,PF_TIMEOUT=19,PF_TRAVEL=20,PF_TURN_DIRECTION=21,PF_OVERSHOOT=22,PF_SETTLE=23};
typedef struct {double mm_per_count[2],turn_deg,distance_mm[2];int yaw_sign;unsigned calibrated,route_mode,turn_pwm;double right_trim_percent;unsigned trim_keys_enabled;} ParkingConfig;
typedef struct {
 uint32_t magic,phase,step,fault,page,run_id,total_ms,step_ms,settle_ms,quiet_ms,stop_requested,completed_steps;
 uint32_t counts[2],stall_ms[2],angle_quiet_ms;double angle_watch_yaw,angle_watch_path;int64_t total_counts[2],step_counts[2],step_path[2];
 double step_mm[2],completed[7],yaw_deg,yaw_unwrapped,yaw_start,yaw_progress,gyro_z_dps,previous_yaw;
 unsigned imu_ready,had_yaw;float speed[2],pwm[2];WheelControl wheel[2];KeyDebounce keys;ParkingConfig config;
 /* Candidate mode 3: deliberately not exposed by the installed service. */
 unsigned segment_kind,segment_configured;double segment_target,segment_sign,segment_speed_mm_s;
 Turn90State package_turn;
} ParkingState;
void Parking_DefaultConfig(ParkingConfig *,const DistanceConfig *);
int Parking_ConfigValid(const ParkingConfig *);
void Parking_Init(ParkingState *,const ConsoleInput *,const ParkingConfig *);
void Parking_Reset(ParkingState *,const ConsoleInput *);
void Parking_ImuSample(ParkingState *,int,double,double);
int Parking_ConfigureDynamic(ParkingState *,const ConsoleInput *,unsigned,double,double);
int Parking_StartDynamicNext(ParkingState *,const ConsoleInput *,unsigned,double,double);
int Parking_BrakeDynamicSearch(ParkingState *);
int Parking_Start(ParkingState *,const ConsoleInput *);
void Parking_Stop(ParkingState *);
void Parking_Fault(ParkingState *,unsigned);
void Parking_Tick(ParkingState *,const ConsoleInput *,DistanceOutput *);
const char *Parking_Phase(unsigned);
const char *Parking_StepName(unsigned);
void Parking_Frame(const ParkingState *,int,uint8_t[1024],char[4][22]);
unsigned Parking_StepCount(const ParkingState *);
int Parking_IsTurn(const ParkingState *);
double Parking_Target(const ParkingState *);
double Parking_TurnDirection(const ParkingState *);
const char *Parking_StateStepName(const ParkingState *);
int Parking_RunProfile(unsigned,unsigned);
int Parking_RenderRoute(const char *);
int Parking_Run(unsigned);
int Parking_Render(const char *);
#endif
