#ifndef KEY_DEBOUNCE_H
#define KEY_DEBOUNCE_H

#include <stdint.h>

/* Call once per 10 ms. Press and release both require four stable samples. */
#define KEY_DEBOUNCE_TICKS 4U
#define KEY_DEBOUNCE_CONFLICT 0x10U

typedef struct {
    uint8_t stable_mask;
    uint8_t change_ticks[4];
    uint8_t release_ticks;
    uint8_t locked;
    uint8_t conflict_sent;
} KeyDebounce;

static inline void KeyDebounce_Init(KeyDebounce *s, uint8_t raw)
{
    s->stable_mask = 0U;
    for (unsigned i = 0U; i < 4U; i++) s->change_ticks[i] = 0U;
    s->release_ticks = 0U;
    s->locked = (raw & 0x0FU) != 0U;
    s->conflict_sent = 0U;
}

static inline uint8_t KeyDebounce_Update10ms(KeyDebounce *s, uint8_t raw)
{
    raw &= 0x0FU;
    for (unsigned i = 0U; i < 4U; i++) {
        uint8_t bit = (uint8_t)(1U << i);
        if ((raw & bit) == (s->stable_mask & bit)) {
            s->change_ticks[i] = 0U;
        } else if (++s->change_ticks[i] >= KEY_DEBOUNCE_TICKS) {
            s->stable_mask ^= bit;
            s->change_ticks[i] = 0U;
        }
    }
    if (raw != 0U) s->release_ticks = 0U;
    else if (s->release_ticks < KEY_DEBOUNCE_TICKS) s->release_ticks++;

    /* A full debounced release is required even after a chord or boot hold. */
    if (s->stable_mask == 0U && s->release_ticks >= KEY_DEBOUNCE_TICKS) {
        s->locked = 0U;
        s->conflict_sent = 0U;
        return 0U;
    }
    if (s->stable_mask && (s->stable_mask & (s->stable_mask - 1U))) {
        s->locked = 1U;
        if (!s->conflict_sent) {
            s->conflict_sent = 1U;
            return KEY_DEBOUNCE_CONFLICT;
        }
    } else if (s->stable_mask && !s->locked) {
        s->locked = 1U;
        return s->stable_mask;
    }
    return 0U;
}

#endif
