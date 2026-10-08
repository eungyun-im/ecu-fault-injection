"""What a test sees of the bench, whichever target is behind it.

Two targets implement this interface:

    bench/sil.py   the ECU code compiled for the PC, in simulated time
    bench/hil.py   the board on a real CAN bus, in real time

A test only uses what is defined here, so the same test runs on both.
"""

import udsoncan
from udsoncan.client import Client

from bench import messages as m
from bench.restbus import RestBus

# ISO-TP on the tester side: classic CAN, 8-byte padded frames, no block size limit.
ISOTP_PARAMS = {
    "stmin": 0,
    "blocksize": 0,
    "tx_data_length": 8,
    "tx_data_min_length": 8,
    "tx_padding": 0x00,
    "can_fd": False,
    "max_frame_size": 4095,
    "rx_flowcontrol_timeout": 1000,
    "rx_consecutive_frame_timeout": 1000,
}


def client_config():
    config = dict(udsoncan.configs.default_client_config)
    config.update(
        exception_on_negative_response=True,
        exception_on_invalid_response=True,
        exception_on_unexpected_response=True,
        request_timeout=2,
        p2_timeout=1,
        p2_star_timeout=5,
        data_identifiers={
            m.DID_VIN: udsoncan.AsciiCodec(17),
            m.DID_SW_VERSION: ">BBB",
            m.DID_RESET_CAUSE: ">B",
            m.DID_WATCHDOG_RESETS: ">B",
            m.DID_BUS_OFF_COUNT: ">B",
            m.DID_BUILD_INFO: ">B",
        },
    )
    return config


class Bench:
    is_sil = False
    #: Allowance added to every timing limit for the uncertainty of the measurement itself.
    timing_slack_ms = 0
    #: Step of wait_for, in milliseconds.
    poll_ms = 1

    def __init__(self):
        self.frames = []
        self.restbus = RestBus(self.send)
        self.connection = None
        self.tester = None

    # Provided by the target

    now_ms = 0

    def send(self, can_id, data):
        """Put one frame on the bus as the bench."""
        raise NotImplementedError

    def advance(self, ms):
        """Let ms milliseconds pass."""
        raise NotImplementedError

    def reset_ecu(self):
        """Restart the ECU and return once it is sending again."""
        raise NotImplementedError

    def close(self):
        pass

    # Bus log

    def record(self, can_id, data):
        self.frames.append(m.Frame(self.now_ms, can_id, bytes(data)))

    def frames_of(self, can_id, since_ms=0):
        return [f for f in list(self.frames) if f.can_id == can_id and f.t_ms >= since_ms]

    def statuses(self, since_ms=0):
        return [m.decode_status(f) for f in self.frames_of(m.STATUS_ID, since_ms) if len(f.data) == 8]

    def status(self):
        """The most recent ActuatorStatus, or None."""
        for frame in reversed(list(self.frames)):
            if frame.can_id == m.STATUS_ID and len(frame.data) == 8:
                return m.decode_status(frame)
        return None

    def wait_for(self, predicate, timeout_ms, what="the expected status"):
        """Advance until a new ActuatorStatus satisfies predicate. Returns that status."""
        start = self.now_ms
        seen = len(self.frames)
        while True:
            frames = list(self.frames)
            for frame in frames[seen:]:
                if frame.can_id == m.STATUS_ID and len(frame.data) == 8:
                    status = m.decode_status(frame)
                    if predicate(status):
                        return status
            seen = len(frames)
            if self.now_ms - start > timeout_ms:
                raise AssertionError(f"no {what} within {timeout_ms} ms")
            self.advance(self.poll_ms)

    def wait_for_state(self, state, timeout_ms):
        return self.wait_for(
            lambda s: s.state == state, timeout_ms, f"status with state {m.STATE_NAMES[state]}"
        )

    # Diagnostics

    def request(self, payload, timeout_ms=1000):
        """Send raw request bytes. Returns the raw response, or None when there is none."""
        self.connection.empty_rxqueue()
        self.connection.send(bytes(payload))
        return self.connection.wait_frame(timeout=timeout_ms / 1000)

    def read(self, did):
        """Value of a data identifier. Single-value identifiers come back as that value."""
        value = self.tester.read_data_by_identifier(did).service_data.values[did]
        return value[0] if isinstance(value, tuple) and len(value) == 1 else value

    def dtcs(self):
        """Set of stored DTC numbers."""
        response = self.tester.get_dtc_by_status_mask(0xFF)
        return {dtc.id for dtc in response.service_data.dtcs}

    def clear_dtcs(self):
        self.tester.clear_dtc(0xFFFFFF)

    def extended_session(self):
        self.tester.change_session(3)

    def build_info(self):
        return self.read(m.DID_BUILD_INFO)

    # Fault injection inside the ECU (test builds only)

    def inject(self, routine, parameters=b""):
        self.extended_session()
        self.tester.start_routine(routine, data=bytes(parameters) or None)

    def halt_cpu(self):
        self.inject(m.ROUTINE_HALT_CPU)

    def block_task(self, duration_ms):
        self.inject(m.ROUTINE_BLOCK_TASK, duration_ms.to_bytes(2, "big"))

    def corrupt_status(self, frames):
        self.inject(m.ROUTINE_CORRUPT_STATUS, bytes([frames]))

    # Test setup

    def prepare(self):
        """Known starting point: healthy sender, ECU freshly started and in NORMAL, no DTCs."""
        self.restbus.reset()
        self.reset_ecu()
        self.wait_for_state(m.NORMAL, m.RECOVERY_MS + 1000)
        if self.dtcs():
            self.clear_dtcs()
        return self

    def _make_tester(self, connection):
        self.connection = connection
        self.tester = Client(connection, config=client_config())
        self.tester.open()
