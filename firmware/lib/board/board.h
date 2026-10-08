/* NUCLEO-G431RB: the hardware both programs use, the bootloader and the application.
 *
 *   FDCAN1   PA11 (RX), PA12 (TX), classic CAN, 500 kbit/s
 *   LD2      PA5
 *   IWDG     independent watchdog
 *   TAMP     backup register 0, the word that survives a reset
 *
 * The system runs from the internal 16 MHz oscillator (HSI16), which is the
 * state after reset. No PLL and no crystal are configured.
 */

#ifndef BOARD_H
#define BOARD_H

#include <stdbool.h>
#include <stdint.h>

#include "can.h"

/* Give access to the backup register. Uses no HAL, so it can run before HAL_Init. */
void board_backup_init(void);
uint32_t board_nv_read(void);
void board_nv_write(uint32_t value);

/* Why the MCU last started, as RESET_CAUSE_* of ecu_port.h. Reads the flags once and clears them. */
uint8_t board_reset_cause(void);

void board_led_init(void);
void board_led(bool on);

bool board_can_init(void);
bool board_can_send(const can_frame_t *frame);
/* Hand every received standard data frame to on_frame. */
void board_can_poll(void (*on_frame)(const can_frame_t *frame, uint32_t now_ms), uint32_t now_ms);
bool board_can_bus_off(void);
void board_can_recover(void);

/* Start the watchdog with a period in milliseconds (up to about 4000). It cannot be stopped again. */
bool board_watchdog_init(uint32_t period_ms);
void board_watchdog_feed(void);

#endif /* BOARD_H */
