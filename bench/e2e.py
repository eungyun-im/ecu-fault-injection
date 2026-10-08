"""End-to-end protection as the bench computes it: CRC in byte 0, alive counter in byte 1.

Written independently of firmware/lib/ecu/e2e.c. The two are compared in
tests/test_e2e_unit.py.
"""

COUNTER_MAX = 14


def crc8(data):
    """CRC-8 SAE J1850: polynomial 0x1D, initial value 0xFF, final XOR 0xFF."""
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1D) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc ^ 0xFF


def frame_crc(can_id, data):
    """CRC over the CAN identifier (low byte, high byte) and data bytes 1 to 7."""
    return crc8(bytes([can_id & 0xFF, (can_id >> 8) & 0xFF]) + bytes(data[1:8]))


def protect(can_id, payload, counter):
    """Return the 8-byte frame for payload (bytes 2 to 7) with counter and CRC filled in."""
    data = bytearray(8)
    data[1] = counter & 0x0F
    data[2 : 2 + len(payload)] = payload
    data[0] = frame_crc(can_id, data)
    return bytes(data)


def crc_ok(can_id, data):
    return len(data) == 8 and data[0] == frame_crc(can_id, data)


def next_counter(counter):
    return 0 if counter >= COUNTER_MAX else counter + 1


def counter_step(previous, received):
    """How many steps the counter advanced from previous to received."""
    return (received - previous) % (COUNTER_MAX + 1)
