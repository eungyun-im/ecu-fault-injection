/* ISO-TP (ISO 15765-2) for one diagnostic connection on classic CAN.
 *
 * Normal 11-bit addressing, 8-byte frames padded with 0x00. Handles single
 * frames and segmented messages in both directions, up to ISOTP_BUFFER_SIZE
 * bytes. A longer request is refused with a flow control "overflow" frame.
 * The buffer is sized for one block of a firmware download. */

#ifndef ISOTP_H
#define ISOTP_H

#include <stdbool.h>
#include <stdint.h>

#include "can.h"

#define ISOTP_BUFFER_SIZE (140U)
#define ISOTP_TIMEOUT_MS (1000U)

typedef enum
{
    ISOTP_TX_IDLE = 0,
    ISOTP_TX_FIRST = 1,
    ISOTP_TX_WAIT_FLOW_CONTROL = 2,
    ISOTP_TX_CONSECUTIVE = 3
} isotp_tx_state_t;

typedef struct
{
    can_send_fn send;
    uint32_t rx_id;
    uint32_t tx_id;

    uint8_t rx_buffer[ISOTP_BUFFER_SIZE];
    uint16_t rx_length;
    uint16_t rx_position;
    uint8_t rx_sequence;
    bool rx_active;
    bool rx_ready;
    uint32_t rx_timer_ms;

    uint8_t tx_buffer[ISOTP_BUFFER_SIZE];
    uint16_t tx_length;
    uint16_t tx_position;
    uint8_t tx_sequence;
    uint8_t tx_block_size;
    uint8_t tx_block_left;
    uint32_t tx_gap_ms;
    uint32_t tx_separation_ms;
    uint32_t tx_timer_ms;
    isotp_tx_state_t tx_state;
} isotp_t;

void isotp_init(isotp_t *link, can_send_fn send, uint32_t rx_id, uint32_t tx_id);
void isotp_on_frame(isotp_t *link, const can_frame_t *frame, uint32_t now_ms);
void isotp_step(isotp_t *link, uint32_t now_ms);

/* True once per complete received message. data stays valid until the next isotp_on_frame. */
bool isotp_receive(isotp_t *link, const uint8_t **data, uint16_t *length);

/* Start sending a message. Returns false when it does not fit the buffer. */
bool isotp_send(isotp_t *link, const uint8_t *data, uint16_t length);
bool isotp_tx_idle(const isotp_t *link);

#endif /* ISOTP_H */
