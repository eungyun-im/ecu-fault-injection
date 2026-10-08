"""Software-in-the-loop target: the ECU code on the PC, in simulated time.

Time only moves when a test calls advance(), one millisecond per step, so a
run is exactly repeatable and a five-second timeout costs no real time.
"""

from collections import deque

import isotp
from udsoncan.connections import BaseConnection
from udsoncan.exceptions import TimeoutException

from bench import messages as m
from bench.base import ISOTP_PARAMS, Bench
from bench.device_model import DeviceModel
from bench.ecu_model import EcuModel


class SimConnection(BaseConnection):
    """Carries udsoncan requests over ISO-TP on the simulated bus, waiting in simulated time."""

    def __init__(self, bench, name=None):
        BaseConnection.__init__(self, name)
        self._bench = bench
        self._opened = False
        self._rx = deque()
        address = isotp.Address(
            isotp.AddressingMode.Normal_11bits, txid=m.DIAG_REQUEST_ID, rxid=m.DIAG_RESPONSE_ID
        )
        self.layer = isotp.TransportLayerLogic(
            rxfn=lambda timeout: self._rx.popleft() if self._rx else None,
            txfn=lambda message: bench.send(message.arbitration_id, bytes(message.data)),
            address=address,
            params=ISOTP_PARAMS,
        )

    def on_frame(self, can_id, data):
        if can_id == m.DIAG_RESPONSE_ID:
            self._rx.append(isotp.CanMessage(arbitration_id=can_id, dlc=len(data), data=data))

    def open(self):
        self._opened = True
        return self

    def close(self):
        self._opened = False

    def is_open(self):
        return self._opened

    def empty_rxqueue(self):
        while self.layer.available():
            self.layer.recv()

    def specific_send(self, payload, timeout=None):
        self.layer.send(bytes(payload))

    def specific_wait_frame(self, timeout=2):
        for _ in range(round(timeout * 1000)):
            if self.layer.available():
                break
            self._bench.advance(1)
        if not self.layer.available():
            raise TimeoutException(f"no response within {timeout} s of simulated time")
        return bytes(self.layer.recv())


class SilBench(Bench):
    is_sil = True

    def __init__(self, variant="test", bootloader=False):
        """variant: which build of the application. bootloader: a whole ECU with an
        empty application slot, as it leaves the flashing station."""
        super().__init__()
        self.now_ms = 0
        self.ecu = DeviceModel(self._from_ecu) if bootloader else EcuModel(self._from_ecu, variant)
        self._make_tester(SimConnection(self))

    def _from_ecu(self, can_id, data):
        self.record(can_id, data)
        self.connection.on_frame(can_id, data)

    def send(self, can_id, data):
        self.record(can_id, data)
        self.ecu.receive(can_id, bytes(data), self.now_ms)

    def advance(self, ms):
        for _ in range(int(ms)):
            self.now_ms += 1
            self.restbus.tick(self.now_ms)
            self.ecu.tick(self.now_ms)
            self.connection.layer.process()

    def reset_ecu(self):
        self.ecu.power_on(self.now_ms)
        self.advance(1)
