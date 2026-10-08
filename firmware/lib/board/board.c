#include "board.h"

#include "stm32g4xx_hal.h"

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

/* Reset causes, the values of ecu_port.h */
#define CAUSE_UNKNOWN (0U)
#define CAUSE_POWER_ON (1U)
#define CAUSE_EXTERNAL_PIN (2U)
#define CAUSE_SOFTWARE (3U)
#define CAUSE_WATCHDOG (4U)

static FDCAN_HandleTypeDef hfdcan1;
static IWDG_HandleTypeDef hiwdg;

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

/* Backup register */

void board_backup_init(void)
{
    SET_BIT(RCC->APB1ENR1, RCC_APB1ENR1_PWREN | RCC_APB1ENR1_RTCAPBEN);
    (void)READ_BIT(RCC->APB1ENR1, RCC_APB1ENR1_PWREN); /* short delay after enabling the clock */
    SET_BIT(PWR->CR1, PWR_CR1_DBP);
}

uint32_t board_nv_read(void)
{
    return TAMP->BKP0R;
}

void board_nv_write(uint32_t value)
{
    TAMP->BKP0R = value;
}

uint8_t board_reset_cause(void)
{
    const uint32_t flags = RCC->CSR;
    uint8_t cause = CAUSE_UNKNOWN;

    /* Several flags can be set at once (the pin flag accompanies every reset),
     * so the order of the checks matters. */
    if ((flags & RCC_CSR_IWDGRSTF) != 0U)
    {
        cause = CAUSE_WATCHDOG;
    }
    else if ((flags & RCC_CSR_SFTRSTF) != 0U)
    {
        cause = CAUSE_SOFTWARE;
    }
    else if ((flags & RCC_CSR_BORRSTF) != 0U)
    {
        cause = CAUSE_POWER_ON;
    }
    else if ((flags & RCC_CSR_PINRSTF) != 0U)
    {
        cause = CAUSE_EXTERNAL_PIN;
    }
    else
    {
        /* Unknown: initial value stands. */
    }
    SET_BIT(RCC->CSR, RCC_CSR_RMVF);

    return cause;
}

/* LED */

void board_led_init(void)
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

void board_led(bool on)
{
    HAL_GPIO_WritePin(LED_PORT, LED_PIN, on ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

/* CAN */

void HAL_FDCAN_MspInit(FDCAN_HandleTypeDef *handle)
{
    if (handle->Instance == FDCAN1)
    {
        RCC_PeriphCLKInitTypeDef clock = {0};
        GPIO_InitTypeDef init = {0};

        /* After reset the FDCAN kernel clock is the external crystal, which is not used here. */
        clock.PeriphClockSelection = RCC_PERIPHCLK_FDCAN;
        clock.FdcanClockSelection = RCC_FDCANCLKSOURCE_PCLK1;
        (void)HAL_RCCEx_PeriphCLKConfig(&clock);

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

bool board_can_init(void)
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

    /* No filter list: every standard data frame goes to receive FIFO 0. */
    return (HAL_FDCAN_Init(&hfdcan1) == HAL_OK) &&
           (HAL_FDCAN_ConfigGlobalFilter(&hfdcan1, FDCAN_ACCEPT_IN_RX_FIFO0, FDCAN_REJECT,
                                         FDCAN_REJECT_REMOTE, FDCAN_REJECT_REMOTE) == HAL_OK) &&
           (HAL_FDCAN_Start(&hfdcan1) == HAL_OK);
}

bool board_can_send(const can_frame_t *frame)
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

void board_can_poll(void (*on_frame)(const can_frame_t *frame, uint32_t now_ms), uint32_t now_ms)
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
                on_frame(&frame, now_ms);
            }
        }
    }
}

bool board_can_bus_off(void)
{
    FDCAN_ProtocolStatusTypeDef status = {0};

    return (HAL_FDCAN_GetProtocolStatus(&hfdcan1, &status) == HAL_OK) && (status.BusOff != 0U);
}

void board_can_recover(void)
{
    /* Bus-off sets the INIT bit. Clearing it starts the recovery sequence. */
    CLEAR_BIT(hfdcan1.Instance->CCCR, FDCAN_CCCR_INIT);
}

/* Watchdog */

bool board_watchdog_init(uint32_t period_ms)
{
    /* LSI 32 kHz / 32 = 1 kHz: one count per millisecond. */
    hiwdg.Instance = IWDG;
    hiwdg.Init.Prescaler = IWDG_PRESCALER_32;
    hiwdg.Init.Reload = (period_ms > 4095U) ? 4095U : period_ms;
    hiwdg.Init.Window = IWDG_WINDOW_DISABLE;

    return HAL_IWDG_Init(&hiwdg) == HAL_OK;
}

void board_watchdog_feed(void)
{
    (void)HAL_IWDG_Refresh(&hiwdg);
}
