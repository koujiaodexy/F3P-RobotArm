#ifndef JY61P_LINUX_H
#define JY61P_LINUX_H
#include <stdint.h>
#include <stddef.h>
int ImuHardware_Open(int write_access);
void ImuHardware_Close(void);
int ImuHardware_Configure(unsigned baud);
int ImuHardware_Read(uint8_t *data,size_t cap);
uint32_t ImuHardware_Status(void);
uint32_t ImuHardware_Errors(void);
void ImuHardware_Flush(void);
int ImuHardware_Send(const uint8_t *data,size_t n);
#endif
