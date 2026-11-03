#ifndef PARKING_REMOTE_H
#define PARKING_REMOTE_H
#include "parking_core.h"
typedef struct {char owner[65];unsigned active,prepared;uint64_t deadline_ms;} ParkingRemote;
void ParkingRemote_Init(ParkingRemote *);
int ParkingRemote_Command(ParkingRemote *,ParkingState *,const ConsoleInput *,const char *,const char *,uint64_t);
void ParkingRemote_Tick(ParkingRemote *,ParkingState *,const ConsoleInput *,uint64_t);
#endif
