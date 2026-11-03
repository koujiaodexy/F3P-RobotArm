#ifndef MISSION_CORE_H
#define MISSION_CORE_H
#include "parking_remote.h"
#include "console_remote.h"
typedef struct {
 KeyDebounce trim_keys; ParkingState drive; ParkingRemote lease;
 ConsoleState grip; ConsoleRemote grip_lease;
 char owner[65]; uint64_t deadline_ms; unsigned complete;
 unsigned shelf_mode,shelf_started,shelf_arm_lock;uint32_t shelf_command_id,shelf_request_id;uint64_t shelf_started_ms;
 uint32_t shelf_raw_counts[2];int64_t shelf_net_counts[2];uint64_t shelf_measured_ms;
 uint32_t shelf_quiet_ms;
} MissionState;
typedef struct {DistanceOutput drive;ConsoleOutput grip;} MissionOutput;
void Mission_Init(MissionState *,const ConsoleInput *,const ParkingConfig *);
int Mission_Command(MissionState *,const ConsoleInput *,const char *,const char *,uint64_t);
int Mission_GripCommand(MissionState *,const ConsoleInput *,const char *,const char *,uint64_t);
void Mission_Tick(MissionState *,const ConsoleInput *,MissionOutput *,uint64_t);
void Mission_Fault(MissionState *,unsigned);
int Mission_ShelfPrepare(MissionState *,const ConsoleInput *,const char *,uint64_t,uint32_t,unsigned,double,double);
int Mission_ShelfStart(MissionState *,const ConsoleInput *,const char *,uint64_t);
int Mission_Reset(MissionState *,const ConsoleInput *,uint64_t);
int Mission_ShelfNext(MissionState *,const ConsoleInput *,const char *,uint64_t,uint32_t,unsigned,double,double);
int Mission_ShelfBrake(MissionState *,const char *,uint64_t,uint32_t);
int Mission_ShelfArmLock(MissionState *,const ConsoleInput *,const char *,uint64_t,unsigned);
#endif
