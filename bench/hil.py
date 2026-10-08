"""Hardware-in-the-loop target: the board on a real CAN bus, in real time.

The bench reaches the bus through any python-can interface. With a CANable
adapter that is usually

    --can-interface slcan  --can-channel COM5          (Windows, serial firmware)
    --can-interface slcan  --can-channel /dev/ttyACM0  (Linux, serial firmware)
    --can-interface socketcan --can-channel can0       (Linux, candleLight firmware)

Timestamps are taken on the PC when a frame is handed to the bench. They carry
the delay of the USB adapter and of the operating system, typically one to a
few milliseconds. See docs/measurement.md.
"""

import threading
import time

import can
import isotp
from udsoncan.connections import PythonIsoTpConnection

from bench import messages as m
from bench.base import ISOTP_PARAMS, Bench


class HilBench(Bench):
    poll_ms = 2

    def __init__(self, interface, channel, bitrate=500000, timing_slack_ms=5):
        super().__init__()
        self.timing_slack_ms = timing_slack_ms
        self._t0 = time.monotonic()
        self._bus = can.Bus(interface=interface, channel=channel, bitrate=bitrate)
        self._log_transmissions()
        self._notifier = can.Notifier(self._bus, [self._on_message])
        address = isotp.Address(
            isotp.AddressingMode.Normal_11bits, txid=m.DIAG_REQUEST_ID, rxid=m.DIAG_RESPONSE_ID
        )
        stack = isotp.NotifierBasedCanStack(
            bus=self._bus,
            notifier=self._notifier,
            address=address,
            params=ISOTP_PARAMS,
        )
        self._make_tester(PythonIsoTpConnection(stack))
        self._running = True
        self._restbus_thread = threading.Thread(target=self._run_restbus, daemon=True)
        self._restbus_thread.start()

    @property
    def now_ms(self):
        return (time.monotonic() - self._t0) * 1000.0

    def _log_transmissions(self):
        """Record every frame the bench sends, whoever sends it, and serialize the senders.

        Three threads transmit: the test, the rest-bus simulation and the ISO-TP stack.
        """
        transmit = self._bus.send
        lock = threading.Lock()

        def send(message, timeout=None):
            with lock:
                self.record(message.arbitration_id, bytes(message.data))
                return transmit(message, timeout)

        self._bus.send = send

    def _on_message(self, message):
        if not (message.is_error_frame or message.is_remote_frame or message.is_extended_id):
            self.record(message.arbitration_id, bytes(message.data))

    def _run_restbus(self):
        # The command has to keep flowing while a test waits or talks diagnostics,
        # so it is sent from its own thread.
        while self._running:
            try:
                self.restbus.tick(self.now_ms)
            except can.CanError:
                pass
            time.sleep(0.001)

    def send(self, can_id, data):
        self._bus.send(can.Message(arbitration_id=can_id, data=bytes(data), is_extended_id=False))

    def advance(self, ms):
        time.sleep(ms / 1000.0)

    def reset_ecu(self):
        self.tester.ecu_reset(1)
        # The response is on the bus before the ECU restarts. Wait until it is back.
        self.advance(100)
        self.wait_for(lambda status: True, 2000, "status message after the reset")

    def close(self):
        self._running = False
        self._restbus_thread.join(timeout=1)
        try:
            self.tester.close()
        finally:
            self._notifier.stop()
            self._bus.shutdown()
