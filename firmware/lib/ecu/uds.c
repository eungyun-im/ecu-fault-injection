#include "uds.h"

#include <stdbool.h>
#include <string.h>

#include "e2e.h"
#include "ecu_config.h"

#define SID_SESSION_CONTROL (0x10U)
#define SID_ECU_RESET (0x11U)
#define SID_CLEAR_DTC (0x14U)
#define SID_READ_DTC (0x19U)
#define SID_READ_DID (0x22U)
#define SID_ROUTINE_CONTROL (0x31U)
#define SID_TESTER_PRESENT (0x3EU)

#define POSITIVE_OFFSET (0x40U)
#define NEGATIVE_RESPONSE (0x7FU)

#define NRC_SERVICE_NOT_SUPPORTED (0x11U)
#define NRC_SUB_FUNCTION_NOT_SUPPORTED (0x12U)
#define NRC_INCORRECT_LENGTH (0x13U)
#define NRC_REQUEST_OUT_OF_RANGE (0x31U)
#define NRC_NOT_SUPPORTED_IN_SESSION (0x7FU)

#define DID_VIN (0xF190U)
#define DID_SW_VERSION (0xF195U)
#define DID_RESET_CAUSE (0x0200U)
#define DID_WATCHDOG_RESETS (0x0201U)
#define DID_BUS_OFF_COUNT (0x0202U)
#define DID_BUILD_INFO (0x0203U)

#define DTC_STATUS_CONFIRMED (0x09U) /* testFailed | confirmedDTC */
#define DTC_STATUS_AVAILABILITY_MASK (0xFFU)
#define REPORT_DTC_BY_STATUS_MASK (0x02U)
#define HARD_RESET (0x01U)
#define START_ROUTINE (0x01U)

#define VIN_LENGTH (17U)

static const uint8_t VIN[VIN_LENGTH + 1U] = "KMUFAULTBENCH0001";

/* DTC of each fault bit, in bit order. */
static const uint32_t DTC_CODES[FAULT_COUNT] = {
    0xC10000UL, /* FAULT_TIMEOUT: lost communication with the command sender */
    0xC10100UL, /* FAULT_CRC: command CRC error */
    0xC10200UL, /* FAULT_COUNTER: command alive counter error */
    0xC10300UL, /* FAULT_RANGE: command value out of range */
    0x4A0100UL, /* FAULT_DEADLINE: cyclic task deadline exceeded */
    0xC07300UL, /* FAULT_BUS_OFF: CAN bus off */
    0x4A0200UL  /* FAULT_WATCHDOG_RESET: restarted by the watchdog */
};

void uds_init(uds_t *uds, uint32_t now_ms)
{
    uds->session = UDS_SESSION_DEFAULT;
    uds->last_request_ms = now_ms;
}

static uint16_t negative(uint8_t *response, uint8_t service, uint8_t code)
{
    response[0] = NEGATIVE_RESPONSE;
    response[1] = service;
    response[2] = code;
    return 3U;
}

static uint16_t session_control(uds_t *uds, const uint8_t *request, uint16_t length,
                                uint8_t *response)
{
    uint16_t result;

    if (length != 2U)
    {
        result = negative(response, SID_SESSION_CONTROL, NRC_INCORRECT_LENGTH);
    }
    else if ((request[1] != UDS_SESSION_DEFAULT) && (request[1] != UDS_SESSION_EXTENDED))
    {
        result = negative(response, SID_SESSION_CONTROL, NRC_SUB_FUNCTION_NOT_SUPPORTED);
    }
    else
    {
        uds->session = request[1];
        response[0] = SID_SESSION_CONTROL + POSITIVE_OFFSET;
        response[1] = request[1];
        /* P2 in 1 ms units, P2* in 10 ms units */
        response[2] = (uint8_t)(UDS_P2_SERVER_MAX_MS >> 8U);
        response[3] = (uint8_t)(UDS_P2_SERVER_MAX_MS & 0xFFU);
        response[4] = (uint8_t)((UDS_P2_STAR_SERVER_MAX_MS / 10U) >> 8U);
        response[5] = (uint8_t)((UDS_P2_STAR_SERVER_MAX_MS / 10U) & 0xFFU);
        result = 6U;
    }

    return result;
}

static uint16_t ecu_reset(const uint8_t *request, uint16_t length, uint8_t *response)
{
    uint16_t result;

    if (length != 2U)
    {
        result = negative(response, SID_ECU_RESET, NRC_INCORRECT_LENGTH);
    }
    else if (request[1] != HARD_RESET)
    {
        result = negative(response, SID_ECU_RESET, NRC_SUB_FUNCTION_NOT_SUPPORTED);
    }
    else
    {
        ecu_schedule(ACTION_RESET, 0U);
        response[0] = SID_ECU_RESET + POSITIVE_OFFSET;
        response[1] = HARD_RESET;
        result = 2U;
    }

    return result;
}

static uint16_t tester_present(const uint8_t *request, uint16_t length, uint8_t *response)
{
    uint16_t result;

    if (length != 2U)
    {
        result = negative(response, SID_TESTER_PRESENT, NRC_INCORRECT_LENGTH);
    }
    else if (request[1] != 0x00U)
    {
        result = negative(response, SID_TESTER_PRESENT, NRC_SUB_FUNCTION_NOT_SUPPORTED);
    }
    else
    {
        response[0] = SID_TESTER_PRESENT + POSITIVE_OFFSET;
        response[1] = 0x00U;
        result = 2U;
    }

    return result;
}

static uint8_t build_info(void)
{
    uint8_t info = 0U;

    if (ECU_FAULT_INJECTION != 0)
    {
        info |= BUILD_FAULT_INJECTION;
    }
    if (e2e_counter_check_implemented())
    {
        info |= BUILD_COUNTER_CHECK;
    }

    return info;
}

static uint16_t read_did(const uint8_t *request, uint16_t length, uint8_t *response)
{
    uint16_t result = 3U;

    if (length != 3U)
    {
        result = negative(response, SID_READ_DID, NRC_INCORRECT_LENGTH);
    }
    else
    {
        const uint16_t did = (uint16_t)(((uint16_t)request[1] << 8U) | (uint16_t)request[2]);

        response[0] = SID_READ_DID + POSITIVE_OFFSET;
        response[1] = request[1];
        response[2] = request[2];

        switch (did)
        {
        case DID_VIN:
            (void)memcpy(&response[3], VIN, VIN_LENGTH);
            result = (uint16_t)(3U + VIN_LENGTH);
            break;
        case DID_SW_VERSION:
            response[3] = SW_VERSION_MAJOR;
            response[4] = SW_VERSION_MINOR;
            response[5] = SW_VERSION_PATCH;
            result = 6U;
            break;
        case DID_RESET_CAUSE:
            response[3] = ecu_reset_cause();
            result = 4U;
            break;
        case DID_WATCHDOG_RESETS:
            response[3] = ecu_watchdog_resets();
            result = 4U;
            break;
        case DID_BUS_OFF_COUNT:
            response[3] = ecu_bus_off_count();
            result = 4U;
            break;
        case DID_BUILD_INFO:
            response[3] = build_info();
            result = 4U;
            break;
        default:
            result = negative(response, SID_READ_DID, NRC_REQUEST_OUT_OF_RANGE);
            break;
        }
    }

    return result;
}

static uint16_t read_dtcs(const uint8_t *request, uint16_t length, uint8_t *response)
{
    uint16_t result;

    if (length != 3U)
    {
        result = negative(response, SID_READ_DTC, NRC_INCORRECT_LENGTH);
    }
    else if (request[1] != REPORT_DTC_BY_STATUS_MASK)
    {
        result = negative(response, SID_READ_DTC, NRC_SUB_FUNCTION_NOT_SUPPORTED);
    }
    else
    {
        const uint8_t stored = ecu_dtc_mask();

        response[0] = SID_READ_DTC + POSITIVE_OFFSET;
        response[1] = REPORT_DTC_BY_STATUS_MASK;
        response[2] = DTC_STATUS_AVAILABILITY_MASK;
        result = 3U;

        if ((request[2] & DTC_STATUS_CONFIRMED) != 0U)
        {
            for (uint8_t bit = 0U; bit < FAULT_COUNT; bit++)
            {
                if ((stored & (uint8_t)(1U << bit)) != 0U)
                {
                    response[result] = (uint8_t)((DTC_CODES[bit] >> 16U) & 0xFFU);
                    response[result + 1U] = (uint8_t)((DTC_CODES[bit] >> 8U) & 0xFFU);
                    response[result + 2U] = (uint8_t)(DTC_CODES[bit] & 0xFFU);
                    response[result + 3U] = DTC_STATUS_CONFIRMED;
                    result = (uint16_t)(result + 4U);
                }
            }
        }
    }

    return result;
}

static uint16_t clear_dtcs(const uint8_t *request, uint16_t length, uint8_t *response)
{
    uint16_t result;

    if (length != 4U)
    {
        result = negative(response, SID_CLEAR_DTC, NRC_INCORRECT_LENGTH);
    }
    else if ((request[1] != 0xFFU) || (request[2] != 0xFFU) || (request[3] != 0xFFU))
    {
        result = negative(response, SID_CLEAR_DTC, NRC_REQUEST_OUT_OF_RANGE);
    }
    else
    {
        ecu_clear_dtcs();
        response[0] = SID_CLEAR_DTC + POSITIVE_OFFSET;
        result = 1U;
    }

    return result;
}

#if ECU_FAULT_INJECTION
/* Start a fault injection routine. Returns false for an unknown routine or wrong parameters. */
static bool start_routine(uint16_t routine, const uint8_t *parameters, uint16_t count)
{
    bool started = true;

    if ((routine == ROUTINE_HALT_CPU) && (count == 0U))
    {
        ecu_schedule(ACTION_HALT, 0U);
    }
    else if ((routine == ROUTINE_BLOCK_TASK) && (count == 2U))
    {
        ecu_schedule(ACTION_BLOCK,
                     (uint16_t)(((uint16_t)parameters[0] << 8U) | (uint16_t)parameters[1]));
    }
    else if ((routine == ROUTINE_CORRUPT_STATUS) && (count == 1U))
    {
        ecu_corrupt_status(parameters[0]);
    }
    else
    {
        started = false;
    }

    return started;
}
#else
static bool start_routine(uint16_t routine, const uint8_t *parameters, uint16_t count)
{
    /* DIAG-06: a release build contains no fault injection routine. */
    (void)routine;
    (void)parameters;
    (void)count;
    return false;
}
#endif

static uint16_t routine_control(const uds_t *uds, const uint8_t *request, uint16_t length,
                                uint8_t *response)
{
    uint16_t result;

    if (uds->session != UDS_SESSION_EXTENDED)
    {
        result = negative(response, SID_ROUTINE_CONTROL, NRC_NOT_SUPPORTED_IN_SESSION);
    }
    else if (length < 4U)
    {
        result = negative(response, SID_ROUTINE_CONTROL, NRC_INCORRECT_LENGTH);
    }
    else if (request[1] != START_ROUTINE)
    {
        result = negative(response, SID_ROUTINE_CONTROL, NRC_SUB_FUNCTION_NOT_SUPPORTED);
    }
    else
    {
        const uint16_t routine = (uint16_t)(((uint16_t)request[2] << 8U) | (uint16_t)request[3]);

        if (start_routine(routine, &request[4], (uint16_t)(length - 4U)))
        {
            response[0] = SID_ROUTINE_CONTROL + POSITIVE_OFFSET;
            response[1] = START_ROUTINE;
            response[2] = request[2];
            response[3] = request[3];
            result = 4U;
        }
        else
        {
            result = negative(response, SID_ROUTINE_CONTROL, NRC_REQUEST_OUT_OF_RANGE);
        }
    }

    return result;
}

uint16_t uds_handle(uds_t *uds, const uint8_t *request, uint16_t length, uint8_t *response,
                    uint32_t now_ms)
{
    uint16_t result = 0U;

    if (length >= 1U)
    {
        uds->last_request_ms = now_ms;

        switch (request[0])
        {
        case SID_SESSION_CONTROL:
            result = session_control(uds, request, length, response);
            break;
        case SID_ECU_RESET:
            result = ecu_reset(request, length, response);
            break;
        case SID_CLEAR_DTC:
            result = clear_dtcs(request, length, response);
            break;
        case SID_READ_DTC:
            result = read_dtcs(request, length, response);
            break;
        case SID_READ_DID:
            result = read_did(request, length, response);
            break;
        case SID_ROUTINE_CONTROL:
            result = routine_control(uds, request, length, response);
            break;
        case SID_TESTER_PRESENT:
            result = tester_present(request, length, response);
            break;
        default:
            result = negative(response, request[0], NRC_SERVICE_NOT_SUPPORTED);
            break;
        }
    }

    return result;
}

void uds_step(uds_t *uds, uint32_t now_ms)
{
    if ((uds->session != UDS_SESSION_DEFAULT) &&
        ((now_ms - uds->last_request_ms) >= UDS_S3_SERVER_MS))
    {
        uds->session = UDS_SESSION_DEFAULT;
    }
}
