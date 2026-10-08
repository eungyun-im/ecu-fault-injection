#include "boot.h"

#include <string.h>

#include "crc32.h"
#include "isotp.h"

#define SID_SESSION_CONTROL (0x10U)
#define SID_ECU_RESET (0x11U)
#define SID_READ_DID (0x22U)
#define SID_ROUTINE_CONTROL (0x31U)
#define SID_REQUEST_DOWNLOAD (0x34U)
#define SID_TRANSFER_DATA (0x36U)
#define SID_TRANSFER_EXIT (0x37U)
#define SID_TESTER_PRESENT (0x3EU)

#define POSITIVE_OFFSET (0x40U)
#define NEGATIVE_RESPONSE (0x7FU)

#define NRC_SERVICE_NOT_SUPPORTED (0x11U)
#define NRC_SUB_FUNCTION_NOT_SUPPORTED (0x12U)
#define NRC_INCORRECT_LENGTH (0x13U)
#define NRC_SEQUENCE_ERROR (0x24U)
#define NRC_REQUEST_OUT_OF_RANGE (0x31U)
#define NRC_PROGRAMMING_FAILURE (0x72U)
#define NRC_WRONG_BLOCK_SEQUENCE (0x73U)
#define NRC_RESPONSE_PENDING (0x78U)
#define NRC_NOT_SUPPORTED_IN_SESSION (0x7FU)

#define DID_BOOT_VERSION (0xF180U)
#define DID_INSTALLED_APPLICATION (0x0210U)

#define RESPONSE_MAX (8U)
#define RESET_DELAY_MS (20U)
/* Largest TransferData request: service, block counter and the data. */
#define BLOCK_LENGTH_MAX (BOOT_BLOCK_DATA_MAX + 2U)

typedef struct
{
    const boot_port_t *port;
    isotp_t link;
    bool requested;

    uint8_t session;
    uint32_t last_request_ms;

    bool installed_valid;
    uint8_t installed_version[3];

    boot_state_t state;
    bool preconditions_ok;
    uint8_t new_version[3];
    uint32_t size;
    uint32_t received;
    uint8_t next_block;
    bool info_erased;
    uint32_t erase_page;
    uint32_t erase_pages;

    bool reset_pending;
    uint32_t reset_since_ms;

    uint32_t next_status_ms;
    uint8_t status_counter;
} boot_t;

static boot_t boot;

bool boot_application_valid(const boot_port_t *port, boot_info_t *info)
{
    boot_info_t local;
    boot_info_t *target = (info != NULL) ? info : &local;
    bool valid = false;

    port->info_read(target);
    if ((target->magic == BOOT_INFO_MAGIC) && (target->length >= 1U) &&
        (target->length <= BOOT_APP_MAX_SIZE))
    {
        /* UPD-01: checked at every start, so flash that has changed since the
         * installation is noticed too. */
        valid = (crc32_compute(port->flash_app(), target->length) == target->crc);
    }

    return valid;
}

bool boot_start(const boot_port_t *port)
{
    const uint32_t nv = port->nv_read();
    const bool requested = ((nv & NV_BOOT_REQUEST) != 0U);

    if (requested)
    {
        /* One request, one stay: the next reset starts the application again. */
        port->nv_write(nv & ~NV_BOOT_REQUEST);
    }
    boot.requested = requested;

    return requested || !boot_application_valid(port, NULL);
}

static void read_installed(void)
{
    boot_info_t info;

    boot.installed_valid = boot_application_valid(boot.port, &info);
    if (boot.installed_valid)
    {
        (void)memcpy(boot.installed_version, info.version, sizeof(boot.installed_version));
    }
    else
    {
        (void)memset(boot.installed_version, 0, sizeof(boot.installed_version));
    }
}

static void abort_download(void)
{
    boot.state = BOOT_STATE_IDLE;
    boot.preconditions_ok = false;
}

void boot_init(const boot_port_t *port, uint32_t now_ms)
{
    const bool requested = boot.requested;

    (void)memset(&boot, 0, sizeof(boot));
    boot.port = port;
    isotp_init(&boot.link, port->can_send, CAN_ID_DIAG_REQUEST, CAN_ID_DIAG_RESPONSE);
    /* The application answered the session request and then restarted into the
     * bootloader, so the tester expects the programming session to be active. */
    boot.session = requested ? UDS_SESSION_PROGRAMMING : UDS_SESSION_DEFAULT;
    boot.last_request_ms = now_ms;
    boot.next_status_ms = now_ms;
    boot.state = BOOT_STATE_IDLE;
    read_installed();
}

void boot_on_frame(const can_frame_t *frame, uint32_t now_ms)
{
    isotp_on_frame(&boot.link, frame, now_ms);
}

/* Diagnostic services */

static uint16_t negative(uint8_t *response, uint8_t service, uint8_t code)
{
    response[0] = NEGATIVE_RESPONSE;
    response[1] = service;
    response[2] = code;
    return 3U;
}

static bool version_lower(const uint8_t a[3], const uint8_t b[3])
{
    bool lower = false;

    for (uint8_t i = 0U; i < 3U; i++)
    {
        if (a[i] != b[i])
        {
            lower = (a[i] < b[i]);
            break;
        }
    }

    return lower;
}

static uint16_t session_control(const uint8_t *request, uint16_t length, uint8_t *response)
{
    uint16_t result;

    if (length != 2U)
    {
        result = negative(response, SID_SESSION_CONTROL, NRC_INCORRECT_LENGTH);
    }
    else if ((request[1] != UDS_SESSION_DEFAULT) && (request[1] != UDS_SESSION_PROGRAMMING))
    {
        result = negative(response, SID_SESSION_CONTROL, NRC_SUB_FUNCTION_NOT_SUPPORTED);
    }
    else
    {
        /* A session change is the tester's way to start over. */
        abort_download();
        boot.session = request[1];
        response[0] = SID_SESSION_CONTROL + POSITIVE_OFFSET;
        response[1] = request[1];
        response[2] = (uint8_t)(UDS_P2_SERVER_MAX_MS >> 8U);
        response[3] = (uint8_t)(UDS_P2_SERVER_MAX_MS & 0xFFU);
        response[4] = (uint8_t)((UDS_P2_STAR_SERVER_MAX_MS / 10U) >> 8U);
        response[5] = (uint8_t)((UDS_P2_STAR_SERVER_MAX_MS / 10U) & 0xFFU);
        result = 6U;
    }

    return result;
}

static uint16_t ecu_reset(const uint8_t *request, uint16_t length, uint8_t *response,
                          uint32_t now_ms)
{
    uint16_t result;

    if (length != 2U)
    {
        result = negative(response, SID_ECU_RESET, NRC_INCORRECT_LENGTH);
    }
    else if (request[1] != 0x01U)
    {
        result = negative(response, SID_ECU_RESET, NRC_SUB_FUNCTION_NOT_SUPPORTED);
    }
    else
    {
        boot.reset_pending = true;
        boot.reset_since_ms = now_ms;
        response[0] = SID_ECU_RESET + POSITIVE_OFFSET;
        response[1] = 0x01U;
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

static uint16_t read_did(const uint8_t *request, uint16_t length, uint8_t *response)
{
    uint16_t result;

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
        if (did == DID_BOOT_VERSION)
        {
            response[3] = BOOT_VERSION_MAJOR;
            response[4] = BOOT_VERSION_MINOR;
            response[5] = BOOT_VERSION_PATCH;
            result = 6U;
        }
        else if (did == DID_INSTALLED_APPLICATION)
        {
            response[3] = boot.installed_valid ? 1U : 0U;
            (void)memcpy(&response[4], boot.installed_version, 3U);
            result = 7U;
        }
        else
        {
            result = negative(response, SID_READ_DID, NRC_REQUEST_OUT_OF_RANGE);
        }
    }

    return result;
}

/* UPD-05: the version is checked before anything is erased, so a refused
 * update leaves the installed application untouched. */
static uint16_t check_preconditions(const uint8_t *request, uint16_t length, uint8_t *response)
{
    uint16_t result;

    if (length != 7U)
    {
        result = negative(response, SID_ROUTINE_CONTROL, NRC_INCORRECT_LENGTH);
    }
    else if (boot.state != BOOT_STATE_IDLE)
    {
        result = negative(response, SID_ROUTINE_CONTROL, NRC_SEQUENCE_ERROR);
    }
    else if (boot.installed_valid && version_lower(&request[4], boot.installed_version))
    {
        boot.preconditions_ok = false;
        result = negative(response, SID_ROUTINE_CONTROL, NRC_REQUEST_OUT_OF_RANGE);
    }
    else
    {
        boot.preconditions_ok = true;
        (void)memcpy(boot.new_version, &request[4], sizeof(boot.new_version));
        (void)memcpy(response, request, 4U);
        response[0] = SID_ROUTINE_CONTROL + POSITIVE_OFFSET;
        result = 4U;
    }

    return result;
}

/* UPD-03: the application becomes valid only here, after the whole image in
 * flash has been read back and its CRC matches the one the tester announced. */
static uint16_t check_and_activate(const uint8_t *request, uint16_t length, uint8_t *response)
{
    uint16_t result;

    if (length != 8U)
    {
        result = negative(response, SID_ROUTINE_CONTROL, NRC_INCORRECT_LENGTH);
    }
    else if (boot.state != BOOT_STATE_TRANSFERRED)
    {
        result = negative(response, SID_ROUTINE_CONTROL, NRC_SEQUENCE_ERROR);
    }
    else
    {
        const uint32_t expected = ((uint32_t)request[4] << 24U) | ((uint32_t)request[5] << 16U) |
                                  ((uint32_t)request[6] << 8U) | (uint32_t)request[7];
        boot_info_t info;

        info.magic = BOOT_INFO_MAGIC;
        info.length = boot.size;
        info.crc = crc32_compute(boot.port->flash_app(), boot.size);
        (void)memcpy(info.version, boot.new_version, sizeof(info.version));
        info.reserved = 0xFFU;

        abort_download();
        if ((info.crc == expected) && boot.port->info_write(&info))
        {
            read_installed();
        }
        if (boot.installed_valid)
        {
            (void)memcpy(response, request, 4U);
            response[0] = SID_ROUTINE_CONTROL + POSITIVE_OFFSET;
            result = 4U;
        }
        else
        {
            result = negative(response, SID_ROUTINE_CONTROL, NRC_PROGRAMMING_FAILURE);
        }
    }

    return result;
}

static uint16_t erase_application(const uint8_t *request, uint16_t length, uint8_t *response)
{
    uint16_t result;

    if ((BOOT_TEST_BUILD == 0) || (length != 4U) || (boot.state != BOOT_STATE_IDLE))
    {
        result = negative(response, SID_ROUTINE_CONTROL, NRC_REQUEST_OUT_OF_RANGE);
    }
    else if (!boot.port->info_erase())
    {
        result = negative(response, SID_ROUTINE_CONTROL, NRC_PROGRAMMING_FAILURE);
    }
    else
    {
        read_installed();
        (void)memcpy(response, request, 4U);
        response[0] = SID_ROUTINE_CONTROL + POSITIVE_OFFSET;
        result = 4U;
    }

    return result;
}

static uint16_t routine_control(const uint8_t *request, uint16_t length, uint8_t *response)
{
    uint16_t result;

    if (length < 4U)
    {
        result = negative(response, SID_ROUTINE_CONTROL, NRC_INCORRECT_LENGTH);
    }
    else if (request[1] != 0x01U)
    {
        result = negative(response, SID_ROUTINE_CONTROL, NRC_SUB_FUNCTION_NOT_SUPPORTED);
    }
    else
    {
        const uint16_t routine = (uint16_t)(((uint16_t)request[2] << 8U) | (uint16_t)request[3]);

        if (routine == ROUTINE_CHECK_PRECONDITIONS)
        {
            result = check_preconditions(request, length, response);
        }
        else if (routine == ROUTINE_CHECK_AND_ACTIVATE)
        {
            result = check_and_activate(request, length, response);
        }
        else if (routine == ROUTINE_ERASE_APPLICATION)
        {
            result = erase_application(request, length, response);
        }
        else
        {
            result = negative(response, SID_ROUTINE_CONTROL, NRC_REQUEST_OUT_OF_RANGE);
        }
    }

    return result;
}

static uint16_t request_download(const uint8_t *request, uint16_t length, uint8_t *response)
{
    uint16_t result;

    /* 34, data format 00, address and size format 44, address, size */
    if (length != 11U)
    {
        result = negative(response, SID_REQUEST_DOWNLOAD, NRC_INCORRECT_LENGTH);
    }
    else if ((boot.state != BOOT_STATE_IDLE) || !boot.preconditions_ok)
    {
        result = negative(response, SID_REQUEST_DOWNLOAD, NRC_SEQUENCE_ERROR);
    }
    else
    {
        const uint32_t address = ((uint32_t)request[3] << 24U) | ((uint32_t)request[4] << 16U) |
                                 ((uint32_t)request[5] << 8U) | (uint32_t)request[6];
        const uint32_t size = ((uint32_t)request[7] << 24U) | ((uint32_t)request[8] << 16U) |
                              ((uint32_t)request[9] << 8U) | (uint32_t)request[10];

        if ((request[1] != 0x00U) || (request[2] != 0x44U) || (address != BOOT_APP_ADDRESS) ||
            (size == 0U) || (size > BOOT_APP_MAX_SIZE))
        {
            /* Refused before anything is erased: the installed application stays. */
            result = negative(response, SID_REQUEST_DOWNLOAD, NRC_REQUEST_OUT_OF_RANGE);
        }
        else
        {
            boot.size = size;
            boot.received = 0U;
            boot.next_block = 1U;
            boot.info_erased = false;
            boot.erase_page = 0U;
            boot.erase_pages = (size + BOOT_PAGE_SIZE - 1U) / BOOT_PAGE_SIZE;
            boot.state = BOOT_STATE_ERASING;
            /* Erasing takes longer than P2. The answer follows when it is done. */
            result = negative(response, SID_REQUEST_DOWNLOAD, NRC_RESPONSE_PENDING);
        }
    }

    return result;
}

static uint16_t transfer_data(const uint8_t *request, uint16_t length, uint8_t *response)
{
    uint16_t result;

    if (boot.state != BOOT_STATE_DOWNLOADING)
    {
        result = negative(response, SID_TRANSFER_DATA, NRC_SEQUENCE_ERROR);
    }
    else if ((length < 3U) || (length > BLOCK_LENGTH_MAX))
    {
        result = negative(response, SID_TRANSFER_DATA, NRC_INCORRECT_LENGTH);
    }
    else if (request[1] != boot.next_block)
    {
        /* UPD-04: a lost, repeated or reordered block must not shift the image. */
        result = negative(response, SID_TRANSFER_DATA, NRC_WRONG_BLOCK_SEQUENCE);
    }
    else
    {
        const uint32_t count = (uint32_t)length - 2U;
        const bool last = ((boot.received + count) == boot.size);

        if (((boot.received + count) > boot.size) || (((count % 8U) != 0U) && !last))
        {
            result = negative(response, SID_TRANSFER_DATA, NRC_REQUEST_OUT_OF_RANGE);
        }
        else
        {
            /* Flash is programmed in units of 8 bytes. The last block is padded. */
            uint8_t padded[BOOT_BLOCK_DATA_MAX];
            const uint32_t padded_count = (count + 7U) & ~(uint32_t)7U;

            (void)memset(padded, 0xFF, sizeof(padded));
            (void)memcpy(padded, &request[2], count);
            if (boot.port->flash_write(boot.received, padded, padded_count))
            {
                boot.received += count;
                boot.next_block = (uint8_t)(boot.next_block + 1U);
                response[0] = SID_TRANSFER_DATA + POSITIVE_OFFSET;
                response[1] = request[1];
                result = 2U;
            }
            else
            {
                abort_download();
                result = negative(response, SID_TRANSFER_DATA, NRC_PROGRAMMING_FAILURE);
            }
        }
    }

    return result;
}

static uint16_t transfer_exit(uint16_t length, uint8_t *response)
{
    uint16_t result;

    if (length != 1U)
    {
        result = negative(response, SID_TRANSFER_EXIT, NRC_INCORRECT_LENGTH);
    }
    else if ((boot.state != BOOT_STATE_DOWNLOADING) || (boot.received != boot.size))
    {
        result = negative(response, SID_TRANSFER_EXIT, NRC_SEQUENCE_ERROR);
    }
    else
    {
        boot.state = BOOT_STATE_TRANSFERRED;
        response[0] = SID_TRANSFER_EXIT + POSITIVE_OFFSET;
        result = 1U;
    }

    return result;
}

static bool is_programming_service(uint8_t service)
{
    return (service == SID_ROUTINE_CONTROL) || (service == SID_REQUEST_DOWNLOAD) ||
           (service == SID_TRANSFER_DATA) || (service == SID_TRANSFER_EXIT);
}

static uint16_t handle(const uint8_t *request, uint16_t length, uint8_t *response, uint32_t now_ms)
{
    uint16_t result;
    const uint8_t service = request[0];

    boot.last_request_ms = now_ms;

    if (is_programming_service(service) && (boot.session != UDS_SESSION_PROGRAMMING))
    {
        result = negative(response, service, NRC_NOT_SUPPORTED_IN_SESSION);
    }
    else
    {
        switch (service)
        {
        case SID_SESSION_CONTROL:
            result = session_control(request, length, response);
            break;
        case SID_ECU_RESET:
            result = ecu_reset(request, length, response, now_ms);
            break;
        case SID_READ_DID:
            result = read_did(request, length, response);
            break;
        case SID_ROUTINE_CONTROL:
            result = routine_control(request, length, response);
            break;
        case SID_REQUEST_DOWNLOAD:
            result = request_download(request, length, response);
            break;
        case SID_TRANSFER_DATA:
            result = transfer_data(request, length, response);
            break;
        case SID_TRANSFER_EXIT:
            result = transfer_exit(length, response);
            break;
        case SID_TESTER_PRESENT:
            result = tester_present(request, length, response);
            break;
        default:
            result = negative(response, service, NRC_SERVICE_NOT_SUPPORTED);
            break;
        }
    }

    return result;
}

/* Cyclic part */

/* One page per step, so the CAN side stays alive during the erase. */
static void erase_step(uint32_t now_ms)
{
    uint8_t response[RESPONSE_MAX];
    uint16_t length = 0U;
    bool ok = true;

    /* A long erase is not a silent tester. */
    boot.last_request_ms = now_ms;

    if (!boot.info_erased)
    {
        /* UPD-02: the info page goes first. From here on there is no valid application. */
        ok = boot.port->info_erase();
        boot.info_erased = true;
        read_installed();
    }
    else if (boot.erase_page < boot.erase_pages)
    {
        ok = boot.port->flash_erase_page(boot.erase_page);
        boot.erase_page++;
    }
    else
    {
        boot.state = BOOT_STATE_DOWNLOADING;
        response[0] = SID_REQUEST_DOWNLOAD + POSITIVE_OFFSET;
        response[1] = 0x20U; /* the maximum block length follows in 2 bytes */
        response[2] = (uint8_t)(BLOCK_LENGTH_MAX >> 8U);
        response[3] = (uint8_t)(BLOCK_LENGTH_MAX & 0xFFU);
        length = 4U;
    }

    if (!ok)
    {
        abort_download();
        length = negative(response, SID_REQUEST_DOWNLOAD, NRC_PROGRAMMING_FAILURE);
    }
    if (length > 0U)
    {
        (void)isotp_send(&boot.link, response, length);
    }
}

static void transmit_status(uint32_t now_ms)
{
    if ((int32_t)(now_ms - boot.next_status_ms) >= 0)
    {
        can_frame_t frame;

        frame.id = CAN_ID_BOOT_STATUS;
        frame.dlc = 8U;
        frame.data[0] = (uint8_t)boot.state;
        frame.data[1] = boot.session;
        frame.data[2] = boot.installed_valid ? 1U : 0U;
        frame.data[3] = boot.installed_version[0];
        frame.data[4] = boot.installed_version[1];
        frame.data[5] = boot.installed_version[2];
        frame.data[6] = 0U;
        frame.data[7] = boot.status_counter;
        if (boot.port->can_send(&frame))
        {
            boot.status_counter++;
        }
        boot.next_status_ms = now_ms + BOOT_STATUS_CYCLE_MS;
    }
}

void boot_step(uint32_t now_ms)
{
    const uint8_t *request = NULL;
    uint16_t length = 0U;

    transmit_status(now_ms);

    isotp_step(&boot.link, now_ms);
    if (isotp_receive(&boot.link, &request, &length) && (length >= 1U))
    {
        uint8_t response[RESPONSE_MAX];
        const uint16_t response_length = handle(request, length, response, now_ms);

        (void)isotp_send(&boot.link, response, response_length);
        isotp_step(&boot.link, now_ms);
    }
    else if ((boot.state == BOOT_STATE_ERASING) && isotp_tx_idle(&boot.link))
    {
        erase_step(now_ms);
    }
    else
    {
        /* Nothing to do in this step. */
    }

    /* UPD-06: a tester that goes silent does not leave the bootloader waiting forever. */
    if ((boot.session != UDS_SESSION_DEFAULT) &&
        ((now_ms - boot.last_request_ms) >= UDS_S3_SERVER_MS))
    {
        boot.session = UDS_SESSION_DEFAULT;
        abort_download();
    }

    if (boot.reset_pending && isotp_tx_idle(&boot.link) &&
        ((now_ms - boot.reset_since_ms) >= RESET_DELAY_MS))
    {
        boot.reset_pending = false;
        boot.port->system_reset();
    }
}
