#ifndef OLED_LINUX_H
#define OLED_LINUX_H
#include <stdint.h>
int Oled_Open(int write_access);
void Oled_Close(void);
int Oled_InitPanel(void);
int Oled_SendFrame(const uint8_t frame[1024]);
#endif
