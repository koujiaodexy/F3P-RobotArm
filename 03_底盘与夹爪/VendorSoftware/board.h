#ifndef BOARD_H
#define BOARD_H
#include <stdint.h>
/* Single control thread: no MCU interrupt state exists in the Linux port. */
static inline uint32_t __get_PRIMASK(void) { return 0; }
static inline void __disable_irq(void) {}
static inline void __set_PRIMASK(uint32_t v) { (void)v; }
void Board_SetMotor(unsigned wheel, int power);
uint8_t Board_Keys(void);
uint32_t Board_Count(unsigned wheel);
void Board_Leds(uint8_t running, uint8_t pid_mode);
#endif
