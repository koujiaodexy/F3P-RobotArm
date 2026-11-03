#ifndef MISSION_PROTOCOL_H
#define MISSION_PROTOCOL_H
#include "mission_core.h"
#include <stddef.h>
/* Pure parser/dispatcher. No hardware access. A reply echoes request identity. */
int Mission_Protocol(MissionState *,const ConsoleInput *,uint64_t now,uint64_t generation,
                     const char *request,size_t length,char *reply,size_t capacity);
#endif
