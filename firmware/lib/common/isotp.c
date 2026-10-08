#include "isotp.h"

#include <string.h>

#define PCI_SINGLE (0x0U)
#define PCI_FIRST (0x1U)
#define PCI_CONSECUTIVE (0x2U)
#define PCI_FLOW_CONTROL (0x3U)

#define FLOW_CONTINUE (0x0U)
#define FLOW_WAIT (0x1U)
#define FLOW_OVERFLOW (0x2U)

#define SINGLE_FRAME_MAX (7U)
#define FIRST_FRAME_DATA (6U)
#define CONSECUTIVE_FRAME_DATA (7U)

static void empty_frame(const isotp_t *link, can_frame_t *frame)
{
    frame->id = link->tx_id;
    frame->dlc = 8U;
    (void)memset(frame->data, 0, sizeof(frame->data));
}

static void send_flow_control(const isotp_t *link, uint8_t status)
{
    can_frame_t frame;

    empty_frame(link, &frame);
    frame.data[0] = (uint8_t)((PCI_FLOW_CONTROL << 4U) | status);
    /* Block size 0 and separation time 0: send everything, as fast as possible. */
    (void)link->send(&frame);
}

void isotp_init(isotp_t *link, can_send_fn send, uint32_t rx_id, uint32_t tx_id)
{
    (void)memset(link, 0, sizeof(*link));
    link->send = send;
    link->rx_id = rx_id;
    link->tx_id = tx_id;
    link->tx_state = ISOTP_TX_IDLE;
}

static void on_single_frame(isotp_t *link, const can_frame_t *frame)
{
    const uint8_t length = (uint8_t)(frame->data[0] & 0x0FU);

    if ((length >= 1U) && (length <= SINGLE_FRAME_MAX) && (frame->dlc > length))
    {
        (void)memcpy(link->rx_buffer, &frame->data[1], length);
        link->rx_length = length;
        link->rx_active = false;
        link->rx_ready = true;
    }
}

static void on_first_frame(isotp_t *link, const can_frame_t *frame, uint32_t now_ms)
{
    const uint16_t length =
        (uint16_t)((((uint16_t)frame->data[0] & 0x0FU) << 8U) | (uint16_t)frame->data[1]);

    if ((frame->dlc == 8U) && (length > SINGLE_FRAME_MAX))
    {
        if (length > ISOTP_BUFFER_SIZE)
        {
            link->rx_active = false;
            send_flow_control(link, FLOW_OVERFLOW);
        }
        else
        {
            (void)memcpy(link->rx_buffer, &frame->data[2], FIRST_FRAME_DATA);
            link->rx_length = length;
            link->rx_position = FIRST_FRAME_DATA;
            link->rx_sequence = 1U;
            link->rx_active = true;
            link->rx_ready = false;
            link->rx_timer_ms = now_ms;
            send_flow_control(link, FLOW_CONTINUE);
        }
    }
}

static void on_consecutive_frame(isotp_t *link, const can_frame_t *frame, uint32_t now_ms)
{
    if (link->rx_active)
    {
        const uint16_t remaining = (uint16_t)(link->rx_length - link->rx_position);
        const uint8_t count = (remaining > CONSECUTIVE_FRAME_DATA) ? CONSECUTIVE_FRAME_DATA
                                                                   : (uint8_t)remaining;

        if (((frame->data[0] & 0x0FU) != link->rx_sequence) || (frame->dlc <= count))
        {
            /* Wrong sequence number or a short frame: drop the whole message. */
            link->rx_active = false;
        }
        else
        {
            (void)memcpy(&link->rx_buffer[link->rx_position], &frame->data[1], count);
            link->rx_position = (uint16_t)(link->rx_position + count);
            link->rx_sequence = (uint8_t)((link->rx_sequence + 1U) & 0x0FU);
            link->rx_timer_ms = now_ms;
            if (link->rx_position >= link->rx_length)
            {
                link->rx_active = false;
                link->rx_ready = true;
            }
        }
    }
}

static uint32_t separation_ms(uint8_t st_min)
{
    uint32_t result;

    if (st_min <= 0x7FU)
    {
        result = st_min;
    }
    else if ((st_min >= 0xF1U) && (st_min <= 0xF9U))
    {
        /* 100 to 900 microseconds: rounded up to the 1 ms tick. */
        result = 1U;
    }
    else
    {
        /* Reserved values are treated as the longest separation time. */
        result = 0x7FU;
    }

    return result;
}

static void on_flow_control(isotp_t *link, const can_frame_t *frame, uint32_t now_ms)
{
    if (link->tx_state == ISOTP_TX_WAIT_FLOW_CONTROL)
    {
        const uint8_t status = (uint8_t)(frame->data[0] & 0x0FU);

        if (status == FLOW_CONTINUE)
        {
            link->tx_block_size = (frame->dlc >= 2U) ? frame->data[1] : 0U;
            link->tx_block_left = link->tx_block_size;
            link->tx_separation_ms = separation_ms((frame->dlc >= 3U) ? frame->data[2] : 0U);
            link->tx_gap_ms = 0U;
            link->tx_timer_ms = now_ms;
            link->tx_state = ISOTP_TX_CONSECUTIVE;
        }
        else if (status == FLOW_WAIT)
        {
            link->tx_timer_ms = now_ms;
        }
        else
        {
            link->tx_state = ISOTP_TX_IDLE;
        }
    }
}

void isotp_on_frame(isotp_t *link, const can_frame_t *frame, uint32_t now_ms)
{
    if ((frame->id == link->rx_id) && (frame->dlc >= 1U) && (frame->dlc <= 8U))
    {
        switch (frame->data[0] >> 4U)
        {
        case PCI_SINGLE:
            on_single_frame(link, frame);
            break;
        case PCI_FIRST:
            on_first_frame(link, frame, now_ms);
            break;
        case PCI_CONSECUTIVE:
            on_consecutive_frame(link, frame, now_ms);
            break;
        case PCI_FLOW_CONTROL:
            on_flow_control(link, frame, now_ms);
            break;
        default:
            /* Reserved frame type: ignored. */
            break;
        }
    }
}

static void send_first(isotp_t *link, uint32_t now_ms)
{
    can_frame_t frame;

    empty_frame(link, &frame);
    if (link->tx_length <= SINGLE_FRAME_MAX)
    {
        frame.data[0] = (uint8_t)link->tx_length;
        (void)memcpy(&frame.data[1], link->tx_buffer, link->tx_length);
        if (link->send(&frame))
        {
            link->tx_state = ISOTP_TX_IDLE;
        }
    }
    else
    {
        frame.data[0] = (uint8_t)((PCI_FIRST << 4U) | ((link->tx_length >> 8U) & 0x0FU));
        frame.data[1] = (uint8_t)(link->tx_length & 0xFFU);
        (void)memcpy(&frame.data[2], link->tx_buffer, FIRST_FRAME_DATA);
        if (link->send(&frame))
        {
            link->tx_position = FIRST_FRAME_DATA;
            link->tx_sequence = 1U;
            link->tx_timer_ms = now_ms;
            link->tx_state = ISOTP_TX_WAIT_FLOW_CONTROL;
        }
    }
}

static void send_consecutive(isotp_t *link, uint32_t now_ms)
{
    const uint16_t remaining = (uint16_t)(link->tx_length - link->tx_position);
    const uint8_t count =
        (remaining > CONSECUTIVE_FRAME_DATA) ? CONSECUTIVE_FRAME_DATA : (uint8_t)remaining;
    can_frame_t frame;

    empty_frame(link, &frame);
    frame.data[0] = (uint8_t)((PCI_CONSECUTIVE << 4U) | link->tx_sequence);
    (void)memcpy(&frame.data[1], &link->tx_buffer[link->tx_position], count);

    /* When the frame cannot be queued, the same frame is tried again in the next step. */
    if (link->send(&frame))
    {
        link->tx_position = (uint16_t)(link->tx_position + count);
        link->tx_sequence = (uint8_t)((link->tx_sequence + 1U) & 0x0FU);
        link->tx_timer_ms = now_ms;
        link->tx_gap_ms = link->tx_separation_ms;

        if (link->tx_position >= link->tx_length)
        {
            link->tx_state = ISOTP_TX_IDLE;
        }
        else if (link->tx_block_size != 0U)
        {
            link->tx_block_left--;
            if (link->tx_block_left == 0U)
            {
                link->tx_state = ISOTP_TX_WAIT_FLOW_CONTROL;
            }
        }
        else
        {
            /* No block limit: keep sending. */
        }
    }
}

void isotp_step(isotp_t *link, uint32_t now_ms)
{
    if (link->rx_active && ((now_ms - link->rx_timer_ms) > ISOTP_TIMEOUT_MS))
    {
        link->rx_active = false;
    }

    switch (link->tx_state)
    {
    case ISOTP_TX_FIRST:
        send_first(link, now_ms);
        break;
    case ISOTP_TX_WAIT_FLOW_CONTROL:
        if ((now_ms - link->tx_timer_ms) > ISOTP_TIMEOUT_MS)
        {
            link->tx_state = ISOTP_TX_IDLE;
        }
        break;
    case ISOTP_TX_CONSECUTIVE:
        if ((now_ms - link->tx_timer_ms) >= link->tx_gap_ms)
        {
            send_consecutive(link, now_ms);
        }
        break;
    case ISOTP_TX_IDLE:
    default:
        break;
    }
}

bool isotp_receive(isotp_t *link, const uint8_t **data, uint16_t *length)
{
    const bool ready = link->rx_ready;

    if (ready)
    {
        link->rx_ready = false;
        *data = link->rx_buffer;
        *length = link->rx_length;
    }

    return ready;
}

bool isotp_send(isotp_t *link, const uint8_t *data, uint16_t length)
{
    const bool fits = (length >= 1U) && (length <= ISOTP_BUFFER_SIZE);

    if (fits)
    {
        (void)memcpy(link->tx_buffer, data, length);
        link->tx_length = length;
        link->tx_position = 0U;
        link->tx_state = ISOTP_TX_FIRST;
    }

    return fits;
}

bool isotp_tx_idle(const isotp_t *link)
{
    return link->tx_state == ISOTP_TX_IDLE;
}
