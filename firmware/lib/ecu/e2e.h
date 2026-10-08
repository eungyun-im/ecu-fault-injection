/* End-to-end protection of a CAN message: CRC in byte 0, alive counter in byte 1.
 *
 * Modeled on AUTOSAR E2E Profile 1 (CRC-8 SAE J1850, 4-bit counter 0 to 14,
 * data ID included in the CRC). It is not a compliant implementation. */

#ifndef E2E_H
#define E2E_H

#include <stdbool.h>
#include <stdint.h>

#define E2E_COUNTER_MAX (14U)
#define E2E_COUNTER_MAX_DELTA (2U)

/* CRC-8 SAE J1850: polynomial 0x1D, initial value 0xFF, final XOR 0xFF. */
uint8_t e2e_crc8(const uint8_t *data, uint32_t length);

/* CRC over the CAN identifier (low byte, high byte) and data bytes 1 to 7. */
uint8_t e2e_frame_crc(uint32_t can_id, const uint8_t data[8]);

/* Write the counter into byte 1 and the CRC into byte 0. */
void e2e_protect(uint32_t can_id, uint8_t data[8], uint8_t counter);

bool e2e_crc_ok(uint32_t can_id, const uint8_t data[8]);

/* True when `received` is an acceptable successor of `previous` (SAFE-03). */
bool e2e_counter_ok(uint8_t previous, uint8_t received);

/* True once e2e_counter_ok is implemented. Reported in DID 0x0203. */
bool e2e_counter_check_implemented(void);

uint8_t e2e_next_counter(uint8_t counter);

#endif /* E2E_H */
