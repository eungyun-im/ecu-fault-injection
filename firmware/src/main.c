/* NUCLEO-G431RB port of the ECU.
 *
 *   FDCAN1   PA11 (RX), PA12 (TX), classic CAN, 500 kbit/s
 *   LD2      PA5, actuator enable output
 *   IWDG     independent watchdog, about 100 ms
 *   TAMP     backup register 0, the word that survives a reset
 *
 * The system runs from the internal 16 MHz oscillator (HSI16), which is the
 * state after reset. No PLL and no crystal are configured.
 */

#include "stm32g4xx_hal.h"

#include "ecu.h"

#define LED_PORT GPIOA
#define LED_PIN GPIO_PIN_5
#define CAN_PORT GPIOA
#define CAN_RX_PIN GPIO_PIN_11
#define CAN_TX_PIN GPIO_PIN_12

/* 16 MHz / 2 = 8 MHz time quantum clock, 16 quanta per bit = 500 kbit/s.
 * Sample point 75 %. The wide synchronization jump width leaves room for the
 * tolerance of the internal oscillator. */
#define CAN_PRESCALER (2U)
#define CAN_TIME_SEG1 (11U)
#define CAN_TIME_SEG2 (4U)
#define CAN_SYNC_JUMP_WIDTH (4U)

/* LSI 32 kHz / 4 = 8 kHz, 800 counts = 100 ms */
#define WATCHDOG_PRESCALER IWDG_PRESCALER_4
#define WATCHDOG_RELOAD (799U)

static FDCAN_HandleTypeDef hfdcan1;
static IWDG_HandleTypeDef hiwdg;
static uint8_t boot_reset_cause = RESET_CAUSE_UNKNOWN;

/* DLC code of each data length. A table, because the encoding of these
 * constants differs between versions of the HAL. */
static const uint32_t DLC_CODE[9] = {
    FDCAN_DLC_BYTES_0, FDCAN_DLC_BYTES_1, FDCAN_DLC_BYTES_2, FDCAN_DLC_BYTES_3, FDCAN_DLC_BYTES_4,
    FDCAN_DLC_BYTES_5, FDCAN_DLC_BYTES_6, FDCAN_DLC_BYTES_7, FDCAN_DLC_BYTES_8,
};

void SysTick_Handler(void)
{
    HAL_IncTick();
}

/* Port functions */

static bool port_can_send(const can_frame_t *frame)
{
    FDCAN_TxHeaderTypeDef header = {0};
    bool queued = false;

    if ((frame->dlc <= 8U) && (HAL_FDCAN_GetTxFifoFreeLevel(&hfdcan1) > 0U))
    {
        header.Identifier = frame->id;
        header.IdType = FDCAN_STANDARD_ID;
        header.TxFrameType = FDCAN_DATA_FRAME;
        header.DataLength = DLC_CODE[frame->dlc];
        header.ErrorStateIndicator = FDCAN_ESI_ACTIVE;
        header.BitRateSwitch = FDCAN_BRS_OFF;
        header.FDFormat = FDCAN_CLASSIC_CAN;
        header.TxEventFifoControl = FDCAN_NO_TX_EVENTS;
        header.MessageMarker = 0U;
        queued = (HAL_FDCAN_AddMessageToTxFifoQ(&hfdcan1, &header, (uint8_t *)frame->data) ==
                  HAL_OK);
    }

    return queued;
}

static bool port_can_bus_off(void)
{
    FDCAN_ProtocolStatusTypeDef status = {0};

    return (HAL_FDCAN_GetProtocolStatus(&hfdcan1, &status) == HAL_OK) && (status.BusOff != 0U);
}

static void port_can_recover(void)
{
    /* Bus-off sets the INIT bit. Clearing it starts the recovery sequence. */
    CLEAR_BIT(hfdcan1.Instance->CCCR, FDCAN_CCCR_INIT);
}

static void port_set_output(bool enabled)
{
    HAL_GPIO_WritePin(LED_PORT, LED_PIN, enabled ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

static void port_watchdog_feed(void)
{
    (void)HAL_IWDG_Refresh(&hiwdg);
}

static uint8_t port_reset_cause(void)
{
    return boot_reset_cause;
}

static uint32_t port_nv_read(void)
{
    return TAMP->BKP0R;
}

static void port_nv_write(uint32_t value)
{
    TAMP->BKP0R = value;
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
    .can_send = port_can_send,
    .can_bus_off = port_can_bus_off,
    .can_recover = port_can_recover,
    .set_output = port_set_output,
    .watchdog_feed = port_watchdog_feed,
    .reset_cause = port_reset_cause,
    .nv_read = port_nv_read,
    .nv_write = port_nv_write,
    .system_reset = port_system_reset,
    .halt = port_halt,
    .block_ms = port_block_ms,
};

/* Start-up */

static void fatal(void)
{
    /* Start-up failed. Stay here with the output off; the bench sees a silent ECU. */
    for (;;)
    {
    }
}

static uint8_t read_reset_cause(void)
{
    uint8_t cause = RESET_CAUSE_UNKNOWN;

    /* Several flags can be set at once (the pin flag accompanies every reset),
     * so the order of the checks matters. */
    if (__HAL_RCC_GET_FLAG(RCC_FLAG_IWDGRST) != 0U)
    {
        cause = RESET_CAUSE_WATCHDOG;
    }
    else if (__HAL_RCC_GET_FLAG(RCC_FLAG_SFTRST) != 0U)
    {
        cause = RESET_CAUSE_SOFTWARE;
    }
    else if (__HAL_RCC_GET_FLAG(RCC_FLAG_BORRST) != 0U)
    {
        cause = RESET_CAUSE_POWER_ON;
    }
    else if (__HAL_RCC_GET_FLAG(RCC_FLAG_PINRST) != 0U)
    {
        cause = RESET_CAUSE_EXTERNAL_PIN;
    }
    else
    {
        /* Unknown: initial value stands. */
    }
    __HAL_RCC_CLEAR_RESET_FLAGS();

    return cause;
}

static void gpio_init(void)
{
    GPIO_InitTypeDef init = {0};

    __HAL_RCC_GPIOA_CLK_ENABLE();

    HAL_GPIO_WritePin(LED_PORT, LED_PIN, GPIO_PIN_RESET);
    init.Pin = LED_PIN;
    init.Mode = GPIO_MODE_OUTPUT_PP;
    init.Pull = GPIO_NOPULL;
    init.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(LED_PORT, &init);
}

static void backup_domain_init(void)
{
    __HAL_RCC_PWR_CLK_ENABLE();
    HAL_PWR_EnableBkUpAccess();
    __HAL_RCC_RTCAPB_CLK_ENABLE();
}

void HAL_FDCAN_MspInit(FDCAN_HandleTypeDef *handle)
{
    if (handle->Instance == FDCAN1)
    {
        RCC_PeriphCLKInitTypeDef clock = {0};
        GPIO_InitTypeDef init = {0};

        /* After reset the FDCAN kernel clock is the external crystal, which is not used here. */
        clock.PeriphClockSelection = RCC_PERIPHCLK_FDCAN;
        clock.FdcanClockSelection = RCC_FDCANCLKSOURCE_PCLK1;
        if (HAL_RCCEx_PeriphCLKConfig(&clock) != HAL_OK)
        {
            fatal();
        }

        __HAL_RCC_FDCAN_CLK_ENABLE();
        __HAL_RCC_GPIOA_CLK_ENABLE();

        init.Pin = CAN_RX_PIN | CAN_TX_PIN;
        init.Mode = GPIO_MODE_AF_PP;
        init.Pull = GPIO_NOPULL;
        init.Speed = GPIO_SPEED_FREQ_HIGH;
        init.Alternate = GPIO_AF9_FDCAN1;
        HAL_GPIO_Init(CAN_PORT, &init);
    }
}

static void can_init(void)
{
    hfdcan1.Instance = FDCAN1;
    hfdcan1.Init.ClockDivider = FDCAN_CLOCK_DIV1;
    hfdcan1.Init.FrameFormat = FDCAN_FRAME_CLASSIC;
    hfdcan1.Init.Mode = FDCAN_MODE_NORMAL;
    hfdcan1.Init.AutoRetransmission = ENABLE;
    hfdcan1.Init.TransmitPause = DISABLE;
    hfdcan1.Init.ProtocolException = DISABLE;
    hfdcan1.Init.NominalPrescaler = CAN_PRESCALER;
    hfdcan1.Init.NominalSyncJumpWidth = CAN_SYNC_JUMP_WIDTH;
    hfdcan1.Init.NominalTimeSeg1 = CAN_TIME_SEG1;
    hfdcan1.Init.NominalTimeSeg2 = CAN_TIME_SEG2;
    /* The data phase is not used in classic CAN. Valid values keep the HAL checks quiet. */
    hfdcan1.Init.DataPrescaler = CAN_PRESCALER;
    hfdcan1.Init.DataSyncJumpWidth = CAN_SYNC_JUMP_WIDTH;
    hfdcan1.Init.DataTimeSeg1 = CAN_TIME_SEG1;
    hfdcan1.Init.DataTimeSeg2 = CAN_TIME_SEG2;
    hfdcan1.Init.StdFiltersNbr = 0U;
    hfdcan1.Init.ExtFiltersNbr = 0U;
    hfdcan1.Init.TxFifoQueueMode = FDCAN_TX_FIFO_OPERATION;

    if (HAL_FDCAN_Init(&hfdcan1) != HAL_OK)
    {
        fatal();
    }
    /* No filter list: every standard data frame goes to receive FIFO 0. */
    if (HAL_FDCAN_ConfigGlobalFilter(&hfdcan1, FDCAN_ACCEPT_IN_RX_FIFO0, FDCAN_REJECT,
                                     FDCAN_REJECT_REMOTE, FDCAN_REJECT_REMOTE) != HAL_OK)
    {
        fatal();
    }
    if (HAL_FDCAN_Start(&hfdcan1) != HAL_OK)
    {
        fatal();
    }
}

static void watchdog_init(void)
{
    hiwdg.Instance = IWDG;
    hiwdg.Init.Prescaler = WATCHDOG_PRESCALER;
    hiwdg.Init.Reload = WATCHDOG_RELOAD;
    hiwdg.Init.Window = IWDG_WINDOW_DISABLE;
    if (HAL_IWDG_Init(&hiwdg) != HAL_OK)
    {
        fatal();
    }
}

static void poll_can(uint32_t now_ms)
{
    FDCAN_RxHeaderTypeDef header;
    can_frame_t frame;

    while (HAL_FDCAN_GetRxFifoFillLevel(&hfdcan1, FDCAN_RX_FIFO0) > 0U)
    {
        if (HAL_FDCAN_GetRxMessage(&hfdcan1, FDCAN_RX_FIFO0, &header, frame.data) != HAL_OK)
        {
            break;
        }
        if ((header.IdType == FDCAN_STANDARD_ID) && (header.RxFrameType == FDCAN_DATA_FRAME))
        {
            frame.id = header.Identifier;
            frame.dlc = 0xFFU;
            for (uint8_t length = 0U; length <= 8U; length++)
            {
                if (header.DataLength == DLC_CODE[length])
                {
                    frame.dlc = length;
                }
            }
            if (frame.dlc <= 8U)
            {
                ecu_on_frame(&frame, now_ms);
            }
        }
    }
}

int main(void)
{
    uint32_t last_tick;

    HAL_Init();
    boot_reset_cause = read_reset_cause();
    gpio_init();
    backup_domain_init();
    can_init();
    watchdog_init();

    last_tick = HAL_GetTick();
    ecu_init(&PORT, last_tick);

    for (;;)
    {
        const uint32_t now = HAL_GetTick();

        poll_can(now);
        if (now != last_tick)
        {
            last_tick = now;
            ecu_step(now);
        }
    }
}
