#include "ecu.h"

#include <stdbool.h>
#include <string.h>

#include "e2e.h"
#include "ecu_config.h"
#include "isotp.h"
#include "monitor.h"
#include "safety.h"
#include "uds.h"

/* Layout of the word kept across resets */
#define NV_MAGIC (0xA5UL)
#define NV_MAGIC_SHIFT (16U)
#define NV_WATCHDOG_SHIFT (8U)

typedef struct
{
    const ecu_port_t *port;
    uint32_t last_step_ms;

    monitor_t monitor;
    safety_t safety;
    isotp_t link;
    uds_t uds;

    /* Fault memory */
    uint8_t dtc_mask;
    uint8_t watchdog_resets;
    uint8_t reset_cause;

    /* CAN bus-off handling */
    bool bus_off;
    uint32_t bus_off_since_ms;
    uint8_t bus_off_count;

    /* ActuatorStatus transmission */
    uint32_t next_status_ms;
    uint8_t status_counter;
    uint8_t last_sent_state;
    bool status_sent_once;
    uint8_t corrupt_status_frames;

    /* Action to run once the diagnostic response is out */
    uint8_t action;
    uint16_t action_parameter;
    uint32_t action_since_ms;
} ecu_t;

static ecu_t ecu;

static void store_fault_memory(void)
{
    ecu.port->nv_write((NV_MAGIC << NV_MAGIC_SHIFT) |
                       ((uint32_t)ecu.watchdog_resets << NV_WATCHDOG_SHIFT) |
                       (uint32_t)ecu.dtc_mask);
}

static void load_fault_memory(void)
{
    const uint32_t word = ecu.port->nv_read();

    if (((word >> NV_MAGIC_SHIFT) & 0xFFUL) == NV_MAGIC)
    {
        ecu.dtc_mask = (uint8_t)(word & 0xFFUL);
        ecu.watchdog_resets = (uint8_t)((word >> NV_WATCHDOG_SHIFT) & 0xFFUL);
    }
    else
    {
        /* First start after power-up: the word holds no valid data. */
        ecu.dtc_mask = 0U;
        ecu.watchdog_resets = 0U;
    }
}

static void store_dtcs(uint8_t faults)
{
    if ((ecu.dtc_mask | faults) != ecu.dtc_mask)
    {
        ecu.dtc_mask |= faults;
        store_fault_memory();
    }
}

void ecu_init(const ecu_port_t *port, uint32_t now_ms)
{
    (void)memset(&ecu, 0, sizeof(ecu));
    ecu.port = port;
    ecu.last_step_ms = now_ms;
    ecu.next_status_ms = now_ms + STATUS_CYCLE_MS;

    monitor_init(&ecu.monitor, now_ms);
    safety_init(&ecu.safety);
    isotp_init(&ecu.link, port, CAN_ID_DIAG_REQUEST, CAN_ID_DIAG_RESPONSE);
    uds_init(&ecu.uds, now_ms);

    load_fault_memory();
    ecu.reset_cause = port->reset_cause();
    if (ecu.reset_cause == RESET_CAUSE_WATCHDOG)
    {
        /* SAFE-08: a watchdog reset is a detected failure and must leave a trace. */
        if (ecu.watchdog_resets < UINT8_MAX)
        {
            ecu.watchdog_resets++;
        }
        ecu.dtc_mask |= FAULT_WATCHDOG_RESET;
        store_fault_memory();
    }

    port->set_output(false);
}

void ecu_on_frame(const can_frame_t *frame, uint32_t now_ms)
{
    monitor_on_frame(&ecu.monitor, frame, now_ms);
    isotp_on_frame(&ecu.link, frame, now_ms);
}

/* SAFE-09: leave bus-off after a pause, and count how often it happened. */
static uint8_t bus_off_fault(uint32_t now_ms)
{
    uint8_t fault = 0U;

    if (!ecu.bus_off && ecu.port->can_bus_off())
    {
        ecu.bus_off = true;
        ecu.bus_off_since_ms = now_ms;
        if (ecu.bus_off_count < UINT8_MAX)
        {
            ecu.bus_off_count++;
        }
    }

    if (ecu.bus_off)
    {
        fault = FAULT_BUS_OFF;
        if ((now_ms - ecu.bus_off_since_ms) >= BUS_OFF_RECOVERY_MS)
        {
            ecu.port->can_recover();
            ecu.bus_off = false;
        }
    }

    return fault;
}

static void transmit_status(uint32_t now_ms, uint8_t applied)
{
    const uint8_t state = (uint8_t)ecu.safety.state;
    const bool cyclic_due = ((int32_t)(now_ms - ecu.next_status_ms) >= 0);
    const bool changed = (!ecu.status_sent_once) || (state != ecu.last_sent_state);

    if (cyclic_due || changed)
    {
        can_frame_t frame;

        frame.id = CAN_ID_STATUS;
        frame.dlc = 8U;
        frame.data[2] = state;
        frame.data[3] = applied;
        frame.data[4] = ecu.safety.flags;
        frame.data[5] = ecu.reset_cause;
        frame.data[6] = 0U;
        frame.data[7] = 0U;
        e2e_protect(CAN_ID_STATUS, frame.data, ecu.status_counter);

        if (ecu.corrupt_status_frames > 0U)
        {
            frame.data[0] ^= 0xFFU;
        }

        if (ecu.port->can_send(&frame))
        {
            ecu.status_counter = e2e_next_counter(ecu.status_counter);
            ecu.last_sent_state = state;
            ecu.status_sent_once = true;
            if (ecu.corrupt_status_frames > 0U)
            {
                ecu.corrupt_status_frames--;
            }
            if (cyclic_due)
            {
                ecu.next_status_ms += STATUS_CYCLE_MS;
                if ((int32_t)(now_ms - ecu.next_status_ms) >= 0)
                {
                    /* The task was held up for more than a cycle: do not send a burst. */
                    ecu.next_status_ms = now_ms + STATUS_CYCLE_MS;
                }
            }
        }
    }
}

static void serve_diagnostics(uint32_t now_ms)
{
    const uint8_t *request = NULL;
    uint16_t length = 0U;

    isotp_step(&ecu.link, now_ms);
    if (isotp_receive(&ecu.link, &request, &length))
    {
        uint8_t response[UDS_RESPONSE_MAX];
        const uint16_t response_length = uds_handle(&ecu.uds, request, length, response, now_ms);

        if (response_length > 0U)
        {
            (void)isotp_send(&ecu.link, response, response_length);
            isotp_step(&ecu.link, now_ms);
        }
    }
    uds_step(&ecu.uds, now_ms);
}

/* Run a scheduled reset or injected fault once the response has left the ECU. */
static void run_action(uint32_t now_ms)
{
    if ((ecu.action != ACTION_NONE) && isotp_tx_idle(&ecu.link) &&
        ((now_ms - ecu.action_since_ms) >= ACTION_DELAY_MS))
    {
        const uint8_t action = ecu.action;

        ecu.action = ACTION_NONE;
        if (action == ACTION_RESET)
        {
            ecu.port->system_reset();
        }
        else if (action == ACTION_HALT)
        {
            ecu.port->halt();
        }
        else
        {
            ecu.port->block_ms(ecu.action_parameter);
        }
    }
}

void ecu_step(uint32_t now_ms)
{
    const uint32_t dt_ms = now_ms - ecu.last_step_ms;
    uint8_t faults;

    ecu.last_step_ms = now_ms;

    /* SAFE-07: the watchdog is fed from the cyclic task only. If the task stops
     * running, nothing else keeps the watchdog quiet. */
    ecu.port->watchdog_feed();

    monitor_step(&ecu.monitor, now_ms);
    faults = monitor_faults(&ecu.monitor);
    faults |= bus_off_fault(now_ms);
    if (dt_ms > TASK_DEADLINE_MS)
    {
        /* SAFE-10: the task ran late. Timing that the safety functions rely on was violated. */
        faults |= FAULT_DEADLINE;
    }
    store_dtcs(faults);

    const safety_state_t state = safety_step(&ecu.safety, faults, dt_ms);
    const bool enabled = (state == SAFETY_STATE_NORMAL);
    const uint8_t applied = (enabled && ecu.monitor.enable) ? ecu.monitor.demand : 0U;

    ecu.port->set_output(enabled);
    transmit_status(now_ms, applied);
    serve_diagnostics(now_ms);
    run_action(now_ms);
}

/* Interface to uds.c */

uint8_t ecu_dtc_mask(void)
{
    return ecu.dtc_mask;
}

void ecu_clear_dtcs(void)
{
    ecu.dtc_mask = 0U;
    store_fault_memory();
}

uint8_t ecu_reset_cause(void)
{
    return ecu.reset_cause;
}

uint8_t ecu_watchdog_resets(void)
{
    return ecu.watchdog_resets;
}

uint8_t ecu_bus_off_count(void)
{
    return ecu.bus_off_count;
}

void ecu_schedule(uint8_t action, uint16_t parameter)
{
    ecu.action = action;
    ecu.action_parameter = parameter;
    ecu.action_since_ms = ecu.last_step_ms;
}

void ecu_corrupt_status(uint8_t frames)
{
    ecu.corrupt_status_frames = frames;
}
