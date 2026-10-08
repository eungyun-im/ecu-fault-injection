/* CRC-32 (IEEE 802.3, the one zlib computes), used to check a firmware image. */

#ifndef CRC32_H
#define CRC32_H

#include <stdint.h>

uint32_t crc32_compute(const uint8_t *data, uint32_t length);

#endif /* CRC32_H */
