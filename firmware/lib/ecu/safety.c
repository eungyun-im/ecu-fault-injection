#include "safety.h"

#include "ecu_config.h"

void safety_init(safety_t *safety)
{
    safety->state = SAFETY_STATE_INIT;
    safety->healthy_ms = 0U;
    safety->flags = 0U;
}

safety_state_t safety_step(safety_t *safety, uint8_t faults, uint32_t dt_ms)
{
    if (faults != 0U)
    {
        /* SAFE-05: any qualified fault disables the output at once. The flags
         * keep every reason seen since the output was last enabled. */
        safety->flags |= faults;
        safety->healthy_ms = 0U;
        if (safety->state == SAFETY_STATE_NORMAL)
        {
            safety->state = SAFETY_STATE_SAFE;
        }
    }
    else if (safety->state != SAFETY_STATE_NORMAL)
    {
        /* SAFE-06: the output comes back only after an unbroken healthy period.
         * The same rule applies after power-up. */
        if (dt_ms > (RECOVERY_MS - safety->healthy_ms))
        {
            safety->healthy_ms = RECOVERY_MS;
        }
        else
        {
            safety->healthy_ms += dt_ms;
        }

        if (safety->healthy_ms >= RECOVERY_MS)
        {
            safety->state = SAFETY_STATE_NORMAL;
            safety->healthy_ms = 0U;
            safety->flags = 0U;
        }
    }
    else
    {
        /* Normal and healthy: nothing to do. */
    }

    return safety->state;
}
