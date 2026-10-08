/* CAN frame and the memory layout shared by the bootloader and the application. */

#ifndef CAN_H
#define CAN_H

#include <stdbool.h>
#include <stdint.h>

typedef struct
{
    uint32_t id;
    uint8_t dlc;
    uint8_t data[8];
} can_frame_t;

/* Queue one frame for transmission. Returns false when the frame could not be queued. */
typedef bool (*can_send_fn)(const can_frame_t *frame);

#define CAN_ID_DIAG_REQUEST (0x7E0U)
#define CAN_ID_DIAG_RESPONSE (0x7E8U)

/* The word that survives a reset. The application keeps its fault memory in the
 * low bytes. Bit 24 is how it asks the bootloader to stay after the next reset. */
#define NV_BOOT_REQUEST (0x01000000U)

/* Diagnostic sessions and timing, the same in both programs */
#define UDS_SESSION_DEFAULT (0x01U)
#define UDS_SESSION_PROGRAMMING (0x02U)
#define UDS_SESSION_EXTENDED (0x03U)
#define UDS_S3_SERVER_MS (5000U)
#define UDS_P2_SERVER_MAX_MS (50U)
#define UDS_P2_STAR_SERVER_MAX_MS (5000U)

#endif /* CAN_H */
