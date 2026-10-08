"""Unit tests of the CRC in the ECU code, called directly."""

import random

import pytest

from bench import e2e, ecu_lib
from bench.messages import COMMAND_ID, STATUS_ID

pytestmark = pytest.mark.sil_only


@pytest.fixture
def lib(_libraries):
    return ecu_lib.load("test")


@pytest.mark.requirement("SAFE-02")
def test_crc8_check_value(lib):
    # Published check value of CRC-8 SAE J1850 for the ASCII string "123456789".
    assert lib.e2e_crc8(b"123456789", 9) == 0x4B
    assert e2e.crc8(b"123456789") == 0x4B


@pytest.mark.requirement("SAFE-02")
def test_ecu_and_bench_compute_the_same_frame_crc(lib):
    rng = random.Random(20261008)
    for _ in range(500):
        can_id = rng.choice([COMMAND_ID, STATUS_ID, rng.randrange(0x800)])
        data = bytes(rng.randrange(256) for _ in range(8))
        assert lib.e2e_frame_crc(can_id, data) == e2e.frame_crc(can_id, data)


@pytest.mark.requirement("SAFE-02")
def test_every_single_bit_error_changes_the_crc(lib):
    data = e2e.protect(COMMAND_ID, bytes([1, 40]), counter=7)
    for bit in range(8, 64):
        damaged = bytearray(data)
        damaged[bit // 8] ^= 1 << (bit % 8)
        assert lib.e2e_frame_crc(COMMAND_ID, bytes(damaged)) != data[0]


@pytest.mark.requirement("SAFE-02")
def test_crc_covers_the_identifier(lib):
    # A frame protected for one message must not pass as another one.
    data = e2e.protect(COMMAND_ID, bytes([1, 40]), counter=7)
    assert lib.e2e_frame_crc(STATUS_ID, data) != data[0]


COUNTER_CASES = [
    (0, 1, True),
    (0, 2, True),
    (0, 3, False),
    (0, 0, False),
    (7, 7, False),
    (14, 0, True),
    (13, 0, True),
    (14, 1, True),
    (14, 2, False),
    (3, 2, False),
    (5, 15, False),
]


@pytest.mark.requirement("SAFE-03")
@pytest.mark.parametrize("previous, received, accepted", COUNTER_CASES)
def test_counter_check(lib, previous, received, accepted):
    if not lib.e2e_counter_check_implemented():
        pytest.skip("SAFE-03 not implemented: e2e_counter_ok() in firmware/lib/ecu/e2e.c")
    assert lib.e2e_counter_ok(previous, received) is accepted
