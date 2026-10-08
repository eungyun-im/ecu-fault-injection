"""First contact with the board: send commands for a few seconds and report what comes back.

    python -m bench.hello --can-channel COM5
"""

import argparse

from bench import e2e
from bench import messages as m
from bench.hil import HilBench

FLAG_NAMES = {
    m.FAULT_TIMEOUT: "timeout",
    m.FAULT_CRC: "crc",
    m.FAULT_COUNTER: "counter",
    m.FAULT_RANGE: "range",
    m.FAULT_DEADLINE: "deadline",
    m.FAULT_BUS_OFF: "bus-off",
}
RESET_NAMES = ["unknown", "power-on", "reset pin", "software", "watchdog"]


def main():
    parser = argparse.ArgumentParser(description="Check that the bench reaches the ECU.")
    parser.add_argument("--can-interface", default="slcan")
    parser.add_argument("--can-channel", required=True)
    parser.add_argument("--bitrate", type=int, default=500000)
    args = parser.parse_args()

    bench = HilBench(args.can_interface, args.can_channel, args.bitrate)
    try:
        bench.advance(3000)
        statuses = bench.statuses()
        commands = bench.frames_of(m.COMMAND_ID)
        print(f"commands sent:   {len(commands)}")
        print(f"status received: {len(statuses)}")
        if not statuses:
            print("No status frame. See the table in docs/bring_up.md.")
            return
        bad = sum(not e2e.crc_ok(m.STATUS_ID, s.data) for s in statuses)
        last = statuses[-1]
        flags = [name for bit, name in FLAG_NAMES.items() if last.flags & bit] or ["none"]
        print(f"CRC errors:      {bad}")
        print(f"state:           {m.STATE_NAMES.get(last.state, last.state)}")
        print(f"applied demand:  {last.applied} %")
        print(f"fault flags:     {', '.join(flags)}")
        print(f"last start:      {RESET_NAMES[last.reset_cause] if last.reset_cause < 5 else last.reset_cause}")
        try:
            print(f"VIN:             {bench.read(m.DID_VIN)}")
            info = bench.build_info()
            print(f"fault injection: {'included' if info & m.BUILD_FAULT_INJECTION else 'not included'}")
        except Exception as error:  # diagnostics are a second step: report, do not crash
            print(f"diagnostics:     no answer ({type(error).__name__})")
    finally:
        bench.close()


if __name__ == "__main__":
    main()
