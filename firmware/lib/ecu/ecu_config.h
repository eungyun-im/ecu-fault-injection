/* CAN matrix, timing parameters and fault identifiers. Mirrors docs/can_matrix.md. */

#ifndef ECU_CONFIG_H
#define ECU_CONFIG_H

#include "can.h"

/* CAN identifiers */
#define CAN_ID_COMMAND (0x200U)
#define CAN_ID_STATUS (0x210U)

/* ActuatorCommand, received every 10 ms */
#define COMMAND_TIMEOUT_MS (50U)
#define COMMAND_MAX_BAD_FRAMES (3U)
#define COMMAND_DEMAND_MAX (100U)

/* ActuatorStatus, sent every 10 ms and on every state change */
#define STATUS_CYCLE_MS (10U)

/* Safety state machine */
#define RECOVERY_MS (500U)
#define TASK_DEADLINE_MS (5U)
#define BUS_OFF_RECOVERY_MS (200U)

/* Fault bits. The same bit is used in ActuatorStatus byte 4 and in the stored DTC mask. */
#define FAULT_TIMEOUT (0x01U)
#define FAULT_CRC (0x02U)
#define FAULT_COUNTER (0x04U)
#define FAULT_RANGE (0x08U)
#define FAULT_DEADLINE (0x10U)
#define FAULT_BUS_OFF (0x20U)
#define FAULT_WATCHDOG_RESET (0x40U) /* DTC only: the ECU was restarted by the watchdog */
#define FAULT_COUNT (7U)

/* Diagnostics */
#define ACTION_DELAY_MS (20U)

/* The build can set the version, so two applications can be made from one source. */
#ifndef SW_VERSION_MAJOR
#define SW_VERSION_MAJOR (1U)
#endif
#ifndef SW_VERSION_MINOR
#define SW_VERSION_MINOR (0U)
#endif
#ifndef SW_VERSION_PATCH
#define SW_VERSION_PATCH (0U)
#endif

/* Build information, DID 0x0203 */
#define BUILD_FAULT_INJECTION (0x01U)
#define BUILD_COUNTER_CHECK (0x02U)
#define BUILD_BOOTLOADER (0x04U)

/* Fault injection routines exist only in a test build. A release build must not contain them. */
#ifndef ECU_FAULT_INJECTION
#define ECU_FAULT_INJECTION 0
#endif

/* Set when the application is installed behind the bootloader. It then accepts
 * the programming session, which restarts the ECU into the bootloader. */
#ifndef ECU_BOOTLOADER
#define ECU_BOOTLOADER 0
#endif

#endif /* ECU_CONFIG_H */
