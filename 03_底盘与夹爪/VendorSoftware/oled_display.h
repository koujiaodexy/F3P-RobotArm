#ifndef OLED_DISPLAY_H
#define OLED_DISPLAY_H
#include <stdint.h>
#include "motor_test.h"
int Oled_ParseLine(const char *line,MotorMonitor *m);
void Oled_Frame(const MotorMonitor *m,int link_lost,uint8_t frame[1024],char lines[4][22]);
int Oled_WritePbm(const char *path,const uint8_t frame[1024]);
#endif
