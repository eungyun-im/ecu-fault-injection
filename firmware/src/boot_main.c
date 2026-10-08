/* The bootloader on the NUCLEO-G431RB: connects firmware/lib/boot to the board.
 *
 * Flash, 128 kB in pages of 2 kB:
 *
 *   0x08000000  bootloader          16 kB   pages 0 to 7
 *   0x08004000  application slot   110 kB   pages 8 to 62
 *   0x0801F800  info page            2 kB   page 63
 */

#include <string.h>

#include "stm32g4xx_hal.h"

#include "board.h"
#include "boot.h"

#define FLASH_START (0x08000000U)
#define INFO_ADDRESS (BOOT_APP_ADDRESS + BOOT_APP_MAX_SIZE)
#define APP_FIRST_PAGE ((BOOT_APP_ADDRESS - FLASH_START) / BOOT_PAGE_SIZE)
#define INFO_PAGE ((INFO_ADDRESS - FLASH_START) / BOOT_PAGE_SIZE)
#define RAM_START (0x20000000U)
#define RAM_END (0x20008000U)

/* A page erase takes about 25 ms. The period only has to catch a bootloader that is stuck. */
#define WATCHDOG_PERIOD_MS (1000U)

/* Flash */

static bool erase_page(uint32_t page)
{
    FLASH_EraseInitTypeDef erase = {0};
    uint32_t failed_page = 0U;
    bool ok;

    erase.TypeErase = FLASH_TYPEERASE_PAGES;
    erase.Page = page;
    erase.NbPages = 1U;

    (void)HAL_FLASH_Unlock();
    ok = (HAL_FLASHEx_Erase(&erase, &failed_page) == HAL_OK);
    (void)HAL_FLASH_Lock();

    return ok;
}

static bool program(uint32_t address, const uint8_t *data, uint32_t length)
{
    bool ok = true;

    (void)HAL_FLASH_Unlock();
    for (uint32_t i = 0U; ok && (i < length); i += 8U)
    {
        uint64_t doubleword;

        (void)memcpy(&doubleword, &data[i], sizeof(doubleword));
        ok = (HAL_FLASH_Program(FLASH_TYPEPROGRAM_DOUBLEWORD, address + i, doubleword) == HAL_OK);
    }
    (void)HAL_FLASH_Lock();

    return ok;
}

static const uint8_t *port_flash_app(void)
{
    return (const uint8_t *)BOOT_APP_ADDRESS;
}

static bool port_flash_erase_page(uint32_t page)
{
    return ((APP_FIRST_PAGE + page) < INFO_PAGE) && erase_page(APP_FIRST_PAGE + page);
}

static bool port_flash_write(uint32_t offset, const uint8_t *data, uint32_t length)
{
    return ((offset + length) <= BOOT_APP_MAX_SIZE) && program(BOOT_APP_ADDRESS + offset, data, length);
}

static void port_info_read(boot_info_t *info)
{
    (void)memcpy(info, (const void *)INFO_ADDRESS, sizeof(*info));
}

static bool port_info_erase(void)
{
    return erase_page(INFO_PAGE);
}

static bool port_info_write(const boot_info_t *info)
{
    uint8_t buffer[16];

    (void)memset(buffer, 0xFF, sizeof(buffer));
    (void)memcpy(buffer, info, sizeof(*info));

    return program(INFO_ADDRESS, buffer, sizeof(buffer));
}

static void port_system_reset(void)
{
    NVIC_SystemReset();
}

static const boot_port_t PORT = {
    .can_send = board_can_send,
    .flash_app = port_flash_app,
    .flash_erase_page = port_flash_erase_page,
    .flash_write = port_flash_write,
    .info_read = port_info_read,
    .info_erase = port_info_erase,
    .info_write = port_info_write,
    .nv_read = board_nv_read,
    .nv_write = board_nv_write,
    .system_reset = port_system_reset,
};

/* Start of the application */

static void start_application(void)
{
    const uint32_t *vectors = (const uint32_t *)BOOT_APP_ADDRESS;
    const uint32_t stack = vectors[0];
    const uint32_t entry = vectors[1];

    /* A last plausibility check on what is about to be executed. */
    if ((stack > RAM_START) && (stack <= RAM_END) && (entry >= BOOT_APP_ADDRESS) &&
        (entry < INFO_ADDRESS))
    {
        SCB->VTOR = BOOT_APP_ADDRESS;
        __set_MSP(stack);
        ((void (*)(void))entry)();
    }
}

int main(void)
{
    uint32_t last_tick;

    /* The decision comes first, before any peripheral or interrupt is set up,
     * so the application starts from the same state as after a reset. */
    board_backup_init();
    if (!boot_start(&PORT))
    {
        start_application();
    }

    HAL_Init();
    board_led_init();
    if (!board_can_init() || !board_watchdog_init(WATCHDOG_PERIOD_MS))
    {
        for (;;)
        {
        }
    }

    last_tick = HAL_GetTick();
    boot_init(&PORT, last_tick);

    for (;;)
    {
        const uint32_t now = HAL_GetTick();

        board_can_poll(boot_on_frame, now);
        if (now != last_tick)
        {
            last_tick = now;
            board_watchdog_feed();
            boot_step(now);
            /* Slow blink: the bootloader is running. */
            board_led((now % 1000U) < 100U);
        }
    }
}
