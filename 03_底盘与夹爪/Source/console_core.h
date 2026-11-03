#ifndef CONSOLE_CORE_H
#define CONSOLE_CORE_H
#include <stdint.h>
#include "control.h"
#include "key_debounce.h"
enum {MODE_PID=1,MODE_GRIP=2};
enum {CF_NONE=0,CF_SAMPLE=6,CF_MOTOR=7,CF_GRIP=8,CF_OLED=9,CF_KEYS=10,CF_LINK=11};
enum {GRIP_IDLE=0,GRIP_WAIT=1,GRIP_ACTIVE=2};
enum {GA_NONE=0,GA_STOP=1,GA_COMMAND=2};
enum {GC_NONE=0,GC_CLOSE=1,GC_OPEN=2};
#define VIEW_MAGIC 0x4b4f4c31U
#define HEALTH_MAGIC 0x4f4b4831U
#define GRIP_MIN_US 500U
#define GRIP_MAX_US 2500U
/* Command endpoints are not measured shaft or jaw angles. */
#define GRIP_OPEN_US 1027U
#define GRIP_CLOSE_US 1880U
/* 10ms ticks; opening and closing settle for 1s, close stays held until open. */
#define GRIP_CLOSE_HOLD_TICKS 100U
#define GRIP_OPEN_HOLD_TICKS 100U
typedef struct {
 uint32_t counts[2],motor_status,grip_status,grip_active_us,arm_idle,motor_max_pwm;
 uint8_t keys,oled_ready;
} ConsoleInput;
typedef struct {
 int motor_pwm[2];
 uint32_t motor_run,grip_action,grip_pulse,grip_heartbeat,clear_stopped;
} ConsoleOutput;
typedef struct {
 uint32_t magic,ms,mode,running,fault,target,grip_phase,grip_pulse,grip_remaining_ms,oled_ready,grip_cycle,remote_active;
 float speed[2],pwm[2];
} ConsoleView;
typedef struct {uint32_t magic,ready;} ConsoleHealth;
typedef struct {
 uint32_t ms,mode,fault,selected,target,counts[2],grip_phase,grip_pulse,grip_ticks,grip_wait,grip_cycle;
 uint8_t running,cooldown,oled_ready,remote_active;
 float speed[2],pwm[2];WheelControl wheel[2];KeyDebounce keys;
} ConsoleState;
void KeyConsole_Init(ConsoleState *s,const ConsoleInput *in);
void Console_Tick(ConsoleState *s,const ConsoleInput *in,ConsoleOutput *out);
void Console_Resync(ConsoleState *s,const ConsoleInput *in,int timing_fault);
void Console_Fault(ConsoleState *s,uint32_t code);
void Console_View(const ConsoleState *s,ConsoleView *v);
void Console_Frame(const ConsoleView *v,int link_lost,uint8_t frame[1024],char lines[4][22]);
#endif
