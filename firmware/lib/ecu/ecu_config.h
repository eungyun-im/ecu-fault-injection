/* CAN matrix, timing parameters and fault identifiers. Mirrors docs/can_matrix.md. */

#ifndef ECU_CONFIG_H
#define ECU_CONFIG_H

/* CAN identifiers */
#define CAN_ID_COMMAND (0x200U)
#define CAN_ID_STATUS (0x210U)
#define CAN_ID_DIAG_REQUEST (0x7E0U)
#define CAN_ID_DIAG_RESPONSE (0x7E8U)

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
#define UDS_S3_SERVER_MS (5000U)
#define UDS_P2_SERVER_MAX_MS (50U)
#define UDS_P2_STAR_SERVER_MAX_MS (5000U)
#define ACTION_DELAY_MS (20U)

#define SW_VERSION_MAJOR (1U)
#define SW_VERSION_MINOR (0U)
#define SW_VERSION_PATCH (0U)

/* Build information, DID 0x0203 */
#define BUILD_FAULT_INJECTION (0x01U)
#define BUILD_COUNTER_CHECK (0x02U)

/* Fault injection routines exist only in a test build. A release build must not contain them. */
#ifndef ECU_FAULT_INJECTION
#define ECU_FAULT_INJECTION 0
#endif

#endif /* ECU_CONFIG_H */
