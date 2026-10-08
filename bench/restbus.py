"""Rest-bus simulation: the bench plays the node that sends ActuatorCommand.

It is also the fault injector for everything that can go wrong on the way to
the ECU. Each fault is an attribute a test sets:

    restbus.sending = False          the message disappears
    restbus.corrupt_frames = 3       the next 3 frames carry a wrong CRC
    restbus.freeze_counter = True    the alive counter stops advancing
    restbus.counter_step = 3         the counter jumps by 3 per frame
    restbus.demand = 101             a correctly protected but impossible value
"""

from bench import e2e
from bench.messages import COMMAND_CYCLE_MS, COMMAND_ID


class RestBus:
    def __init__(self, send):
        self._send = send
        self._next_ms = None
        self.counter = 0
        self.reset()

    def reset(self):
        """Back to a healthy sender: enabled, demand 40 %."""
        self.sending = True
        self.enable = 1
        self.demand = 40
        self.corrupt_frames = 0
        self.freeze_counter = False
        self.counter_step = 1
        self.dlc = 8

    def frame(self):
        data = bytearray(e2e.protect(COMMAND_ID, bytes([self.enable, self.demand]), self.counter))
        if self.corrupt_frames > 0:
            self.corrupt_frames -= 1
            data[0] ^= 0xFF
        return bytes(data[: self.dlc])

    def tick(self, now_ms):
        """Send the command when its cycle time has come. Call at least once per millisecond."""
        if self._next_ms is None or now_ms - self._next_ms > 10 * COMMAND_CYCLE_MS:
            self._next_ms = now_ms
        if now_ms < self._next_ms:
            return
        self._next_ms += COMMAND_CYCLE_MS
        if not self.sending:
            return
        self._send(COMMAND_ID, self.frame())
        if not self.freeze_counter:
            for _ in range(self.counter_step):
                self.counter = e2e.next_counter(self.counter)
