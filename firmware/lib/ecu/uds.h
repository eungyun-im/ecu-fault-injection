/* UDS (ISO 14229) server: the subset this ECU needs for fault memory and fault injection.
 *
 * Works on complete messages. Segmentation is done by isotp.c underneath. */

#ifndef UDS_H
#define UDS_H

#include <stdint.h>

#define UDS_RESPONSE_MAX (48U)

#define UDS_SESSION_DEFAULT (0x01U)
#define UDS_SESSION_EXTENDED (0x03U)

/* Fault injection routines (RoutineControl 0x31 01), test builds only */
#define ROUTINE_HALT_CPU (0xF001U)
#define ROUTINE_BLOCK_TASK (0xF002U)
#define ROUTINE_CORRUPT_STATUS (0xF003U)

/* Actions that take effect after the response has been sent */
#define ACTION_NONE (0U)
#define ACTION_RESET (1U)
#define ACTION_HALT (2U)
#define ACTION_BLOCK (3U)

typedef struct
{
    uint8_t session;
    uint32_t last_request_ms;
} uds_t;

void uds_init(uds_t *uds, uint32_t now_ms);

/* Handle one request. Returns the response length, 0 for no response.
 * response must hold UDS_RESPONSE_MAX bytes. */
uint16_t uds_handle(uds_t *uds, const uint8_t *request, uint16_t length, uint8_t *response,
                    uint32_t now_ms);

/* S3 server timer: fall back to the default session after a quiet period. */
void uds_step(uds_t *uds, uint32_t now_ms);

/* Provided by ecu.c */
uint8_t ecu_dtc_mask(void);
void ecu_clear_dtcs(void);
uint8_t ecu_reset_cause(void);
uint8_t ecu_watchdog_resets(void);
uint8_t ecu_bus_off_count(void);
void ecu_schedule(uint8_t action, uint16_t parameter);
void ecu_corrupt_status(uint8_t frames);

#endif /* UDS_H */
