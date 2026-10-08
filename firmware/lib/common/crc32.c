#include "crc32.h"

/* Reflected polynomial 0xEDB88320, four bits per step. */
static const uint32_t NIBBLE_TABLE[16] = {
    0x00000000U, 0x1DB71064U, 0x3B6E20C8U, 0x26D930ACU, 0x76DC4190U, 0x6B6B51F4U,
    0x4DB26158U, 0x5005713CU, 0xEDB88320U, 0xF00F9344U, 0xD6D6A3E8U, 0xCB61B38CU,
    0x9B64C2B0U, 0x86D3D2D4U, 0xA00AE278U, 0xBDBDF21CU,
};

uint32_t crc32_compute(const uint8_t *data, uint32_t length)
{
    uint32_t crc = 0xFFFFFFFFU;

    for (uint32_t i = 0U; i < length; i++)
    {
        crc ^= data[i];
        crc = (crc >> 4U) ^ NIBBLE_TABLE[crc & 0x0FU];
        crc = (crc >> 4U) ^ NIBBLE_TABLE[crc & 0x0FU];
    }

    return crc ^ 0xFFFFFFFFU;
}
