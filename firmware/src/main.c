/* The application on the NUCLEO-G431RB: connects firmware/lib/ecu to the board.
 *
 * The same file is built in two ways: alone at the start of flash (builds
 * "test" and "release"), or for the application slot behind the bootloader
 * (builds "app_v100" and "app_v110").
 */

#include "stm32g4xx_hal.h"

#include "board.h"
#include "ecu.h"

#define WATCHDOG_PERIOD_MS (100U)

/* Vector table of this program, from the startup code. */
extern void (*const g_pfnVectors[])(void);

static uint8_t boot_reset_cause;

static void port_set_output(bool enabled)
{
    board_led(enabled);
}

static uint8_t port_reset_cause(void)
{
    return boot_reset_cause;
}

static void port_system_reset(void)
{
    NVIC_SystemReset();
}

static void port_halt(void)
{
    /* Injected fault: the program stops making progress. Interrupts stay
     * enabled, and nothing here feeds the watchdog. */
    for (;;)
    {
    }
}

static void port_block_ms(uint32_t duration_ms)
{
    const uint32_t start = HAL_GetTick();

    while ((HAL_GetTick() - start) < duration_ms)
    {
    }
}

static const ecu_port_t PORT = {
    .can_send = board_can_send,
    .can_bus_off = board_can_bus_off,
    .can_recover = board_can_recover,
    .set_output = port_set_output,
    .watchdog_feed = board_watchdog_feed,
    .reset_cause = port_reset_cause,
    .nv_read = board_nv_read,
    .nv_write = board_nv_write,
    .system_reset = port_system_reset,
    .halt = port_halt,
    .block_ms = port_block_ms,
};

static void fatal(void)
{
    /* Start-up failed. Stay here with the output off; the bench sees a silent ECU. */
    for (;;)
    {
    }
}

int main(void)
{
    uint32_t last_tick;

    /* Interrupts must reach this program's handlers, wherever in flash it was linked. */
    SCB->VTOR = (uint32_t)g_pfnVectors;

    HAL_Init();
    boot_reset_cause = board_reset_cause();
    board_led_init();
    board_backup_init();
    if (!board_can_init() || !board_watchdog_init(WATCHDOG_PERIOD_MS))
    {
        fatal();
    }

    last_tick = HAL_GetTick();
    ecu_init(&PORT, last_tick);

    for (;;)
    {
        const uint32_t now = HAL_GetTick();

        board_can_poll(ecu_on_frame, now);
        if (now != last_tick)
        {
            last_tick = now;
            ecu_step(now);
        }
    }
}
