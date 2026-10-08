/* Bootloader: decides at every start whether the application may run, and
 * replaces it over CAN.
 *
 * Like the application, this code touches no hardware. The platform under it
 * is the boot_port_t below: firmware/src/boot_main.c on the board,
 * bench/device_model.py on the PC.
 *
 * Flash layout (docs/update.md):
 *
 *   bootloader | application slot ...................... | info page
 *
 * The info page holds length, CRC and version of the installed application.
 * It is erased before the slot is touched and written only after the new image
 * has been checked, so an update that stops anywhere in between leaves an ECU
 * that knows it has no valid application.
 */

#ifndef BOOT_H
#define BOOT_H

#include <stdbool.h>
#include <stdint.h>

#include "can.h"

#define BOOT_APP_ADDRESS (0x08004000U)
#define BOOT_APP_MAX_SIZE (0x0001B800U) /* 110 kB, up to the info page */
#define BOOT_PAGE_SIZE (2048U)
#define BOOT_BLOCK_DATA_MAX (128U)
#define BOOT_INFO_MAGIC (0xB007AB1EU)

#define CAN_ID_BOOT_STATUS (0x211U)
#define BOOT_STATUS_CYCLE_MS (100U)

#define BOOT_VERSION_MAJOR (1U)
#define BOOT_VERSION_MINOR (0U)
#define BOOT_VERSION_PATCH (0U)

/* Routines (RoutineControl 0x31 01), programming session */
#define ROUTINE_CHECK_PRECONDITIONS (0xFF00U)
#define ROUTINE_CHECK_AND_ACTIVATE (0xFF01U)
#define ROUTINE_ERASE_APPLICATION (0xFF02U) /* test builds only */

/* A test build can erase the application on request, so a bench can start over. */
#ifndef BOOT_TEST_BUILD
#define BOOT_TEST_BUILD 0
#endif

typedef enum
{
    BOOT_STATE_IDLE = 0,
    BOOT_STATE_ERASING = 1,
    BOOT_STATE_DOWNLOADING = 2,
    BOOT_STATE_TRANSFERRED = 3
} boot_state_t;

typedef struct
{
    uint32_t magic;
    uint32_t length;
    uint32_t crc;
    uint8_t version[3];
    uint8_t reserved;
} boot_info_t;

typedef struct
{
    can_send_fn can_send;
    /* The application slot as memory, BOOT_APP_MAX_SIZE bytes. */
    const uint8_t *(*flash_app)(void);
    /* Erase one page of the application slot. Page 0 starts at BOOT_APP_ADDRESS. */
    bool (*flash_erase_page)(uint32_t page);
    /* Program erased flash. offset and length are multiples of 8. */
    bool (*flash_write)(uint32_t offset, const uint8_t *data, uint32_t length);
    void (*info_read)(boot_info_t *info);
    bool (*info_erase)(void);
    bool (*info_write)(const boot_info_t *info);
    /* The word that survives a reset (see can.h). */
    uint32_t (*nv_read)(void);
    void (*nv_write)(uint32_t value);
    void (*system_reset)(void);
} boot_port_t;

/* True when the slot holds an application whose length and CRC match the info page. */
bool boot_application_valid(const boot_port_t *port, boot_info_t *info);

/* Call first, before any hardware is set up. Returns true when the bootloader
 * has to stay: the application asked for it, or there is no valid application.
 * When it returns false, jump to the application. */
bool boot_start(const boot_port_t *port);

void boot_init(const boot_port_t *port, uint32_t now_ms);
void boot_on_frame(const can_frame_t *frame, uint32_t now_ms);
void boot_step(uint32_t now_ms);

#endif /* BOOT_H */
