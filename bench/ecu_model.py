"""The ECU code running on the PC, with a model of the hardware it needs.

The C code is the real thing. What is modeled here is the platform under it:

    watchdog      restarts the ECU when it is not fed for WATCHDOG_TIMEOUT_MS
    CPU           can be halted or kept busy by the fault injection routines
    CAN           can be forced into bus-off, as a short circuit on the bus does
    reset cause   reported to the ECU at start, as the reset flags of the MCU are
    memory        one word that survives a reset, but not a power cycle

A model can only show that the software reacts correctly to these events. That
the real watchdog fires, and when, is what the run on the board is for.
"""

import ctypes

from bench import ecu_lib
from bench import messages as m

RX_FIFO_DEPTH = 3


class EcuModel:
    def __init__(self, transmit, variant="test"):
        """transmit(can_id, data) is called for every frame the ECU sends."""
        self._transmit = transmit
        self._lib = ecu_lib.load(variant)
        self._port = ecu_lib.Port(
            can_send=ecu_lib.CAN_SEND(self._can_send),
            can_bus_off=ecu_lib.BOOL_QUERY(lambda: self.bus_off),
            can_recover=ecu_lib.ACTION(self._can_recover),
            set_output=ecu_lib.SET_BOOL(self._set_output),
            watchdog_feed=ecu_lib.ACTION(self._watchdog_feed),
            reset_cause=ecu_lib.GET_U8(lambda: self.reset_cause),
            nv_read=ecu_lib.GET_U32(lambda: self.nv),
            nv_write=ecu_lib.SET_U32(self._nv_write),
            system_reset=ecu_lib.ACTION(self._system_reset),
            halt=ecu_lib.ACTION(self._halt),
            block_ms=ecu_lib.SET_U32(self._block),
        )
        self.now_ms = 0
        self.nv = 0
        self.output = False
        self.bus_off = False
        self.resets = []
        self._short_until_ms = 0
        self.power_on(0)

    # Life cycle

    def power_on(self, now_ms):
        """Cold start: the memory that only survives a reset is lost."""
        self.nv = 0
        self.bus_off = False
        self._short_until_ms = 0
        self._start(now_ms, m.RESET_POWER_ON)

    def _start(self, now_ms, cause):
        self.now_ms = now_ms
        self.reset_cause = cause
        self.resets.append(cause)
        self._halted = False
        self._blocked_until_ms = 0
        self._reset_requested = False
        self._held = []
        self._last_feed_ms = now_ms
        self._lib.ecu_init(ctypes.byref(self._port), now_ms)

    def _running(self):
        return not self._halted and self.now_ms >= self._blocked_until_ms

    # Called by the bench

    def receive(self, can_id, data, now_ms):
        """A frame arrives from the bus."""
        if self.bus_off:
            return
        frame = ecu_lib.CanFrame(can_id, len(data), (ctypes.c_uint8 * 8)(*data))
        self.now_ms = now_ms
        if self._running():
            self._lib.ecu_on_frame(ctypes.byref(frame), now_ms)
        elif len(self._held) < RX_FIFO_DEPTH:
            # A CPU that is not running does not read the receive FIFO: the first
            # few frames wait there, the rest are lost.
            self._held.append(frame)

    def tick(self, now_ms):
        """One millisecond of ECU time."""
        self.now_ms = now_ms
        if self._running():
            for frame in self._held:
                self._lib.ecu_on_frame(ctypes.byref(frame), now_ms)
            self._held = []
            self._lib.ecu_step(now_ms)
        if now_ms - self._last_feed_ms > m.WATCHDOG_TIMEOUT_MS:
            self._start(now_ms, m.RESET_WATCHDOG)
        elif self._reset_requested:
            self._start(now_ms, m.RESET_SOFTWARE)

    def short_bus(self, duration_ms):
        """Short circuit on the bus: the controller goes bus-off and cannot recover until it ends."""
        self.bus_off = True
        self._short_until_ms = self.now_ms + duration_ms

    # Called by the ECU code

    def _can_send(self, frame_pointer):
        if self.bus_off:
            return False
        frame = frame_pointer.contents
        self._transmit(frame.id, bytes(frame.data[: frame.dlc]))
        return True

    def _can_recover(self):
        if self.now_ms >= self._short_until_ms:
            self.bus_off = False

    def _set_output(self, enabled):
        self.output = bool(enabled)

    def _watchdog_feed(self):
        self._last_feed_ms = self.now_ms

    def _nv_write(self, value):
        self.nv = value

    def _system_reset(self):
        self._reset_requested = True

    def _halt(self):
        self._halted = True

    def _block(self, duration_ms):
        self._blocked_until_ms = self.now_ms + duration_ms

    # Direct access for unit tests

    @property
    def lib(self):
        return self._lib
