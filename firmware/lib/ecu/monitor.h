/* Reception monitoring of ActuatorCommand: timeout, CRC, alive counter, value range. */

#ifndef MONITOR_H
#define MONITOR_H

#include <stdbool.h>
#include <stdint.h>

#include "ecu_port.h"

typedef struct
{
    uint32_t last_rx_ms;
    bool have_counter;
    uint8_t last_counter;
    uint8_t bad_frames;
    uint8_t content_fault;
    bool timeout;
    bool enable;
    uint8_t demand;
} monitor_t;

void monitor_init(monitor_t *monitor, uint32_t now_ms);
void monitor_on_frame(monitor_t *monitor, const can_frame_t *frame, uint32_t now_ms);
void monitor_step(monitor_t *monitor, uint32_t now_ms);

/* FAULT_* bits that are present right now. Zero means the command can be trusted. */
uint8_t monitor_faults(const monitor_t *monitor);

#endif /* MONITOR_H */
