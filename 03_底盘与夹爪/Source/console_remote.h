#ifndef CONSOLE_REMOTE_H
#define CONSOLE_REMOTE_H
#include "console_core.h"
/* Sole MMIO owner. OLED is optional; KEY4 and all actuator/lease guards remain. */
typedef struct {
 char owner[65];
 uint64_t heartbeat_ms;
 uint32_t pulse,phase,ticks,wait,settled;
} ConsoleRemote;
int Remote_Command(ConsoleRemote *r,ConsoleState *s,const ConsoleInput *in,
 const char *owner,const char *command,uint64_t now);
void Remote_Tick(ConsoleRemote *r,ConsoleState *s,const ConsoleInput *in,
 ConsoleOutput *out,uint64_t now);
#endif
