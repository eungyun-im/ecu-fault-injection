"""The ECU model on a python-can bus in real time: a stand-in for the board.

It exists to check the hardware-in-the-loop side of the bench (bench/hil.py)
without hardware. Results obtained with it say nothing about the board.

    python -m bench.virtual_ecu --interface socketcan --channel vcan0
"""

import argparse
import threading
import time

import can

from bench.ecu_model import EcuModel


class VirtualEcu:
    def __init__(self, interface, channel, variant="test"):
        self._bus = can.Bus(interface=interface, channel=channel)
        self._t0 = time.monotonic()
        self._model = EcuModel(self._transmit, variant)
        self._running = False
        self._thread = None

    def _now_ms(self):
        return int((time.monotonic() - self._t0) * 1000)

    def _transmit(self, can_id, data):
        self._bus.send(can.Message(arbitration_id=can_id, data=data, is_extended_id=False))

    def run(self):
        self._running = True
        last_ms = self._now_ms()
        self._model.power_on(last_ms)
        while self._running:
            message = self._bus.recv(timeout=0.001)
            now_ms = self._now_ms()
            # One step per elapsed millisecond, so the ECU code sees an even clock.
            while last_ms < now_ms:
                last_ms += 1
                self._model.tick(last_ms)
            # A frame is stamped with the time of the last step, never with a later one.
            if message is not None and not message.is_extended_id:
                self._model.receive(message.arbitration_id, bytes(message.data), last_ms)

    def start(self):
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1)
        self._bus.shutdown()


def main():
    parser = argparse.ArgumentParser(description="Run the ECU model on a CAN interface.")
    parser.add_argument("--interface", default="socketcan")
    parser.add_argument("--channel", default="vcan0")
    args = parser.parse_args()
    ecu = VirtualEcu(args.interface, args.channel)
    print(f"ECU model running on {args.interface}:{args.channel}. Stop with Ctrl+C.")
    try:
        ecu.run()
    except KeyboardInterrupt:
        pass
    finally:
        ecu.stop()


if __name__ == "__main__":
    main()
