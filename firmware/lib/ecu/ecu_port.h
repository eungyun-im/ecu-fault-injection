/* What the ECU software needs from the platform underneath it.
 *
 * The code in this folder is plain C99 and touches no hardware. On the board
 * these functions are provided by firmware/src/main.c, on the PC by the test
 * bench (bench/sil.py). That is what lets one test suite run on both. */

#ifndef ECU_PORT_H
#define ECU_PORT_H

#include <stdbool.h>
#include <stdint.h>

typedef struct
{
    uint32_t id;
    uint8_t dlc;
    uint8_t data[8];
} can_frame_t;

#define RESET_CAUSE_UNKNOWN (0U)
#define RESET_CAUSE_POWER_ON (1U)
#define RESET_CAUSE_EXTERNAL_PIN (2U)
#define RESET_CAUSE_SOFTWARE (3U)
#define RESET_CAUSE_WATCHDOG (4U)

typedef struct
{
    /* Queue one frame for transmission. Returns false when the frame could not be queued. */
    bool (*can_send)(const can_frame_t *frame);
    /* True while the CAN controller is in the bus-off state. */
    bool (*can_bus_off)(void);
    /* Ask the CAN controller to leave bus-off and rejoin the bus. */
    void (*can_recover)(void);
    /* Drive the actuator enable output. */
    void (*set_output)(bool enabled);
    /* Restart the watchdog timer. */
    void (*watchdog_feed)(void);
    /* One of RESET_CAUSE_*: why the ECU last started. */
    uint8_t (*reset_cause)(void);
    /* One 32-bit word that survives an ECU reset. */
    uint32_t (*nv_read)(void);
    void (*nv_write)(uint32_t value);
    /* Restart the ECU. Does not return on the board. */
    void (*system_reset)(void);
    /* Fault injection only. halt() never returns on the board; block_ms() keeps the CPU busy. */
    void (*halt)(void);
    void (*block_ms)(uint32_t duration_ms);
} ecu_port_t;

#endif /* ECU_PORT_H */
