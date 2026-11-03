#include "control.h"
#include "motor_config.h"

float Control_Clamp(float value, float low, float high)
{
    return value < low ? low : (value > high ? high : value);
}

static float Approach(float current, float target, float step)
{
    return current + Control_Clamp(target - current, -step, step);
}

void Control_Reset(WheelControl *s, float speed)
{
    s->ramp = s->integral = s->pwm = 0.0f;
    s->last_speed = speed;
    s->stalled_ticks = s->wrong_ticks = 0U;
}

int Control_ValidGains(const PidGains *g)
{
    /* Range comparisons reject NaN and infinity as well. */
    return g->kp >= 0.0f && g->kp <= 100.0f &&
        g->ki >= 0.0f && g->ki <= 20.0f &&
        g->kd >= 0.0f && g->kd <= 100.0f &&
        g->feedforward >= 0.0f && g->feedforward <= 30.0f;
}

unsigned Control_StepPolicy(WheelControl *s, const PidGains *g,
    uint32_t pid_mode, float target, float speed,int enforce_encoder_direction)
{
    float wanted;
    if (!(target >= -(pid_mode ? SPEED_LIMIT : PWM_LIMIT) &&
          target <= (pid_mode ? SPEED_LIMIT : PWM_LIMIT)) ||
        !Control_ValidGains(g)) return FAULT_CONFIG;
    if (target == 0.0f) {
        Control_Reset(s, speed);
        return FAULT_NONE;
    }
    if (s->pwm * target < 0.0f || s->ramp * target < 0.0f)
        return FAULT_REVERSE;

    float sign = target > 0.0f ? 1.0f : -1.0f;
    if (pid_mode) {
        s->ramp = Approach(s->ramp, target, TARGET_SLEW_PER_TICK);
        float error = (s->ramp - speed) * sign;
        float proportional = g->kp * error;
        float derivative = -g->kd * (speed - s->last_speed) * sign;
        float feedforward = g->feedforward * s->ramp * sign;
        float candidate = Control_Clamp(s->integral + g->ki * error,
            -PWM_LIMIT, PWM_LIMIT);
        float unconstrained = proportional + candidate + derivative + feedforward;
        /* Integrate when unsaturated or when error drives back from a rail. */
        if ((unconstrained >= 0.0f && unconstrained <= PWM_LIMIT) ||
            (unconstrained > PWM_LIMIT && error < 0.0f) ||
            (unconstrained < 0.0f && error > 0.0f)) s->integral = candidate;
        wanted = sign * Control_Clamp(proportional + s->integral +
            derivative + feedforward, 0.0f, PWM_LIMIT);

        if (speed * sign < -1.0f) s->wrong_ticks++;
        else s->wrong_ticks = 0U;
        if (enforce_encoder_direction && s->wrong_ticks >= 3U) return FAULT_ENCODER_SIGN;
        if (s->ramp * sign >= 3.0f && s->pwm * sign >= 150.0f &&
            speed > -0.5f && speed < 0.5f) s->stalled_ticks++;
        else s->stalled_ticks = 0U;
        if (s->stalled_ticks >= 50U) return FAULT_STALL;
    } else {
        s->ramp = target;
        s->integral = 0.0f;
        wanted = target;
    }
    s->last_speed = speed;
    s->pwm = Approach(s->pwm, wanted, PWM_SLEW_PER_TICK);
    return FAULT_NONE;
}

unsigned Control_Step(WheelControl *s,const PidGains *g,uint32_t pid_mode,float target,float speed){return Control_StepPolicy(s,g,pid_mode,target,speed,1);}
