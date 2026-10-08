#include "monitor.h"

#include "e2e.h"
#include "ecu_config.h"

void monitor_init(monitor_t *monitor, uint32_t now_ms)
{
    monitor->last_rx_ms = now_ms;
    monitor->have_counter = false;
    monitor->last_counter = 0U;
    monitor->bad_frames = 0U;
    monitor->content_fault = 0U;
    monitor->timeout = false;
    monitor->enable = false;
    monitor->demand = 0U;
}

/* Which check a received frame fails, or 0 when it is good. */
static uint8_t check_frame(monitor_t *monitor, const can_frame_t *frame)
{
    uint8_t error = 0U;

    if (!e2e_crc_ok(frame->id, frame->data))
    {
        /* Nothing in a frame with a wrong CRC can be trusted, the counter included.
         * The sender went on counting, so the next good frame has no predecessor
         * to be compared with. Without this, two damaged frames would turn the
         * good frame after them into a counter error. */
        error = FAULT_CRC;
        monitor->have_counter = false;
    }
    else
    {
        const uint8_t counter = (uint8_t)(frame->data[1] & 0x0FU);

        if (monitor->have_counter && !e2e_counter_ok(monitor->last_counter, counter))
        {
            error = FAULT_COUNTER;
        }
        else if ((frame->data[2] > 1U) || (frame->data[3] > COMMAND_DEMAND_MAX))
        {
            /* SAFE-04: transmitted correctly, but the sender asks for something impossible. */
            error = FAULT_RANGE;
        }
        else
        {
            /* Good frame. */
        }

        /* Follow the sender's counter even after an error, so one jump is one error. */
        monitor->last_counter = counter;
        monitor->have_counter = true;
    }

    return error;
}

void monitor_on_frame(monitor_t *monitor, const can_frame_t *frame, uint32_t now_ms)
{
    if ((frame->id == CAN_ID_COMMAND) && (frame->dlc == 8U))
    {
        const uint8_t error = check_frame(monitor, frame);

        monitor->last_rx_ms = now_ms;

        if (error == 0U)
        {
            monitor->bad_frames = 0U;
            monitor->content_fault = 0U;
            monitor->enable = (frame->data[2] == 1U);
            monitor->demand = frame->data[3];
        }
        else
        {
            /* A bad frame is discarded and the last good command stays in use.
             * The fault is qualified when bad frames follow each other. */
            if (monitor->bad_frames < UINT8_MAX)
            {
                monitor->bad_frames++;
            }
            if (monitor->bad_frames >= COMMAND_MAX_BAD_FRAMES)
            {
                monitor->content_fault = error;
            }
        }
    }
}

void monitor_step(monitor_t *monitor, uint32_t now_ms)
{
    /* SAFE-01. Monitoring starts at power-up, so a bus that never speaks is a timeout too. */
    monitor->timeout = ((now_ms - monitor->last_rx_ms) > COMMAND_TIMEOUT_MS);
    if (monitor->timeout)
    {
        /* The first frame after a silence has no predecessor to compare its counter with. */
        monitor->have_counter = false;
    }
}

uint8_t monitor_faults(const monitor_t *monitor)
{
    uint8_t faults = monitor->content_fault;

    if (monitor->timeout)
    {
        faults |= FAULT_TIMEOUT;
    }

    return faults;
}
