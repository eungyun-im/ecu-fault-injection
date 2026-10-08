"""CAN matrix of the bench: identifiers, layouts and names. Mirrors docs/can_matrix.md."""

from dataclasses import dataclass

COMMAND_ID = 0x200
STATUS_ID = 0x210
BOOT_STATUS_ID = 0x211
DIAG_REQUEST_ID = 0x7E0
DIAG_RESPONSE_ID = 0x7E8

COMMAND_CYCLE_MS = 10
STATUS_CYCLE_MS = 10

# Safety states (ActuatorStatus byte 2)
INIT, NORMAL, SAFE = 0, 1, 2
STATE_NAMES = {INIT: "INIT", NORMAL: "NORMAL", SAFE: "SAFE"}

# Fault bits (ActuatorStatus byte 4, and the order of the DTCs)
FAULT_TIMEOUT = 0x01
FAULT_CRC = 0x02
FAULT_COUNTER = 0x04
FAULT_RANGE = 0x08
FAULT_DEADLINE = 0x10
FAULT_BUS_OFF = 0x20

DTC_TIMEOUT = 0xC10000
DTC_CRC = 0xC10100
DTC_COUNTER = 0xC10200
DTC_RANGE = 0xC10300
DTC_DEADLINE = 0x4A0100
DTC_BUS_OFF = 0xC07300
DTC_WATCHDOG_RESET = 0x4A0200

# Reset causes (ActuatorStatus byte 5, DID 0x0200)
RESET_UNKNOWN, RESET_POWER_ON, RESET_PIN, RESET_SOFTWARE, RESET_WATCHDOG = range(5)

# Data identifiers
DID_VIN = 0xF190
DID_SW_VERSION = 0xF195
DID_RESET_CAUSE = 0x0200
DID_WATCHDOG_RESETS = 0x0201
DID_BUS_OFF_COUNT = 0x0202
DID_BUILD_INFO = 0x0203
DID_BOOT_VERSION = 0xF180
DID_INSTALLED_APPLICATION = 0x0210

BUILD_FAULT_INJECTION = 0x01
BUILD_COUNTER_CHECK = 0x02
BUILD_BOOTLOADER = 0x04

# Fault injection routines (RoutineControl, test builds only)
ROUTINE_HALT_CPU = 0xF001
ROUTINE_BLOCK_TASK = 0xF002
ROUTINE_CORRUPT_STATUS = 0xF003

# Timing requirements, in milliseconds
COMMAND_TIMEOUT_MS = 50
RECOVERY_MS = 500
TASK_DEADLINE_MS = 5
WATCHDOG_TIMEOUT_MS = 100


@dataclass(frozen=True)
class Frame:
    t_ms: float
    can_id: int
    data: bytes


@dataclass(frozen=True)
class Status:
    """Decoded ActuatorStatus."""

    t_ms: float
    crc: int
    counter: int
    state: int
    applied: int
    flags: int
    reset_cause: int
    data: bytes


@dataclass(frozen=True)
class BootStatus:
    """Decoded BootStatus: what the bootloader reports while it is running."""

    t_ms: float
    state: int
    session: int
    app_valid: bool
    version: tuple


# Bootloader states (BootStatus byte 0)
BOOT_IDLE, BOOT_ERASING, BOOT_DOWNLOADING, BOOT_TRANSFERRED = range(4)


def decode_boot_status(frame):
    d = frame.data
    return BootStatus(frame.t_ms, d[0], d[1], bool(d[2]), tuple(d[3:6]))


def decode_status(frame):
    d = frame.data
    return Status(frame.t_ms, d[0], d[1] & 0x0F, d[2], d[3], d[4], d[5], d)
