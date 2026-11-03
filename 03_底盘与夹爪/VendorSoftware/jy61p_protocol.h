#ifndef JY61P_PROTOCOL_H
#define JY61P_PROTOCOL_H
#include <stdint.h>
#include <stddef.h>
typedef struct {
 uint8_t bytes[11];unsigned used,valid_mask;
 float accel_g[3],gyro_dps[3],angle_deg[3],quaternion[4];
 uint64_t stamp_ms[4],valid_frames,bad_checksum,discarded,unknown_frames;
} ImuState;
void Imu_Init(ImuState *s);
void Imu_Invalidate(ImuState *s);
unsigned Imu_Feed(ImuState *s,uint8_t byte,uint64_t now_ms);
int Imu_Fresh(const ImuState *s,unsigned field,uint64_t now_ms,uint64_t max_age_ms);
int Imu_FormatJson(const ImuState *s,unsigned baud,uint64_t now_ms,int acquired,
                   uint64_t uart_errors,char *out,size_t cap);
#endif
