#include "e2e.h"

#define CRC8_POLYNOMIAL (0x1DU)
#define CRC8_INITIAL (0xFFU)
#define CRC8_FINAL_XOR (0xFFU)
#define FRAME_CRC_INPUT_BYTES (9U)

uint8_t e2e_crc8(const uint8_t *data, uint32_t length)
{
    uint8_t crc = CRC8_INITIAL;

    for (uint32_t i = 0U; i < length; i++)
    {
        crc ^= data[i];
        for (uint8_t bit = 0U; bit < 8U; bit++)
        {
            if ((crc & 0x80U) != 0U)
            {
                crc = (uint8_t)((uint8_t)(crc << 1U) ^ CRC8_POLYNOMIAL);
            }
            else
            {
                crc = (uint8_t)(crc << 1U);
            }
        }
    }

    return (uint8_t)(crc ^ CRC8_FINAL_XOR);
}

uint8_t e2e_frame_crc(uint32_t can_id, const uint8_t data[8])
{
    /* The identifier is part of the CRC, so a frame that is valid for one
     * message is not accepted as another (masquerading). */
    uint8_t input[FRAME_CRC_INPUT_BYTES];

    input[0] = (uint8_t)(can_id & 0xFFU);
    input[1] = (uint8_t)((can_id >> 8U) & 0xFFU);
    for (uint8_t i = 1U; i < 8U; i++)
    {
        input[i + 1U] = data[i];
    }

    return e2e_crc8(input, FRAME_CRC_INPUT_BYTES);
}

void e2e_protect(uint32_t can_id, uint8_t data[8], uint8_t counter)
{
    data[1] = (uint8_t)(counter & 0x0FU);
    data[0] = e2e_frame_crc(can_id, data);
}

bool e2e_crc_ok(uint32_t can_id, const uint8_t data[8])
{
    return data[0] == e2e_frame_crc(can_id, data);
}

uint8_t e2e_next_counter(uint8_t counter)
{
    return (counter >= E2E_COUNTER_MAX) ? 0U : (uint8_t)(counter + 1U);
}

bool e2e_counter_ok(uint8_t previous, uint8_t received)
{
    /* TODO (SAFE-03): not implemented yet, every counter is accepted.
     *
     * The counter runs 0, 1, ... 14, 0, 1, ... and the value 15 is never sent.
     * Accept a step of 1 up to E2E_COUNTER_MAX_DELTA (so one lost frame is
     * tolerated) and reject a repeated counter, a larger jump and the value 15.
     * Then return true from e2e_counter_check_implemented(): the tests in
     * tests/test_e2e_counter.py stop skipping and become the acceptance check. */
    (void)previous;
    (void)received;
    return true;
}

bool e2e_counter_check_implemented(void)
{
    return false;
}
