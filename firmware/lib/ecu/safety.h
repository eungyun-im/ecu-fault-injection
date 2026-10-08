/* Safety state machine: when the actuator output may be enabled. */

#ifndef SAFETY_H
#define SAFETY_H

#include <stdint.h>

typedef enum
{
    SAFETY_STATE_INIT = 0,
    SAFETY_STATE_NORMAL = 1,
    SAFETY_STATE_SAFE = 2
} safety_state_t;

typedef struct
{
    safety_state_t state;
    uint32_t healthy_ms;
    uint8_t flags;
} safety_t;

void safety_init(safety_t *safety);

/* Advance by dt_ms. `faults` are the FAULT_* bits present in this step.
 * Returns the state after the step. */
safety_state_t safety_step(safety_t *safety, uint8_t faults, uint32_t dt_ms);

#endif /* SAFETY_H */
