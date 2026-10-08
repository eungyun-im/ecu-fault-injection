"""Fault injection campaign: inject each fault many times and record the reaction time.

A test answers "was the limit met this time". A campaign answers "how much
margin is there, and how much does it vary": every injection lands at a
different moment relative to the ECU's cycle, so the reaction time is a
distribution, not a number.

    python -m bench.campaign --runs 30
    python -m bench.campaign --runs 30 --target hil --can-channel COM5

Writes results/campaign_<target>.csv and prints a summary table.
"""

import argparse
import csv
import random
import statistics
from pathlib import Path

from bench import e2e, ecu_lib
from bench import messages as m

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
FIELDS = ["target", "fault", "requirement", "run", "phase_ms", "reaction_ms", "limit_ms", "met"]


def _last_command_before(bench, t_ms):
    return [f.t_ms for f in bench.frames_of(m.COMMAND_ID) if f.t_ms <= t_ms][-1]


def _first_bad_command(bench, since_ms):
    for frame in bench.frames_of(m.COMMAND_ID, since_ms):
        bad_crc = not e2e.crc_ok(m.COMMAND_ID, frame.data)
        if bad_crc or frame.data[3] > 100:
            return frame.t_ms
    raise RuntimeError("no faulty command was sent")


def command_timeout(bench):
    """Reaction time: last command on the bus to the safe state."""
    bench.restbus.sending = False
    injected = bench.now_ms
    safe = bench.wait_for_state(m.SAFE, 500)
    return safe.t_ms - _last_command_before(bench, injected)


def command_crc(bench):
    """Reaction time: first corrupted command to the safe state."""
    start = bench.now_ms
    bench.restbus.corrupt_frames = 1000
    safe = bench.wait_for_state(m.SAFE, 500)
    return safe.t_ms - _first_bad_command(bench, start)


def command_range(bench):
    """Reaction time: first out-of-range command to the safe state."""
    start = bench.now_ms
    bench.restbus.demand = 101
    safe = bench.wait_for_state(m.SAFE, 500)
    return safe.t_ms - _first_bad_command(bench, start)


def cpu_halt(bench):
    """Reaction time: last status before the CPU stopped to the first status after the restart."""
    bench.halt_cpu()
    restarted = bench.wait_for(lambda s: s.reset_cause == m.RESET_WATCHDOG, 3000, "restart")
    before = [s.t_ms for s in bench.statuses() if s.t_ms < restarted.t_ms][-1]
    return restarted.t_ms - before


# name: (function, requirement, limit in ms, needs fault injection build)
FAULTS = {
    "command_timeout": (command_timeout, "SAFE-01", 60, False),
    "command_crc": (command_crc, "SAFE-02", 50, False),
    "command_range": (command_range, "SAFE-04", 50, False),
    "cpu_halt": (cpu_halt, "SAFE-07", 500, True),
}


def run(bench, target, runs, seed=20261008):
    rng = random.Random(seed)
    rows = []
    for name, (inject, requirement, limit, needs_injection) in FAULTS.items():
        for index in range(runs):
            bench.prepare()
            if needs_injection and not bench.build_info() & m.BUILD_FAULT_INJECTION:
                break
            phase = rng.randrange(0, 20)
            bench.advance(100 + phase)
            reaction = inject(bench)
            rows.append(
                {
                    "target": target,
                    "fault": name,
                    "requirement": requirement,
                    "run": index + 1,
                    "phase_ms": phase,
                    "reaction_ms": round(reaction, 1),
                    "limit_ms": limit,
                    "met": int(reaction <= limit + bench.timing_slack_ms),
                }
            )
    return rows


def summarize(rows):
    """One line per fault: count, minimum, median, 95th percentile, maximum, limit, worst margin."""
    summary = []
    for name in dict.fromkeys(row["fault"] for row in rows):
        values = sorted(float(row["reaction_ms"]) for row in rows if row["fault"] == name)
        first = next(row for row in rows if row["fault"] == name)
        limit = float(first["limit_ms"])
        p95 = values[min(len(values) - 1, round(0.95 * (len(values) - 1)))]
        summary.append(
            {
                "fault": name,
                "requirement": first["requirement"],
                "n": len(values),
                "min": values[0],
                "median": statistics.median(values),
                "p95": p95,
                "max": values[-1],
                "limit": limit,
                "margin": limit - values[-1],
            }
        )
    return summary


def load(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def save(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def markdown(summary):
    lines = [
        "| Fault | Requirement | Runs | Min | Median | 95th pct | Max | Limit | Margin |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in summary:
        lines.append(
            f"| {s['fault']} | {s['requirement']} | {s['n']} | {s['min']:g} | {s['median']:g} "
            f"| {s['p95']:g} | {s['max']:g} | {s['limit']:g} | {s['margin']:g} |"
        )
    return "\n".join(lines)


def open_bench(args):
    """Returns (bench, cleanup)."""
    if args.target == "sil":
        from bench.sil import SilBench

        ecu_lib.build_all()
        return SilBench(), lambda: None
    from bench.hil import HilBench

    if args.can_channel is None:
        raise SystemExit("--target hil needs --can-channel")
    bench = HilBench(args.can_interface, args.can_channel, args.bitrate, args.timing_slack_ms)
    return bench, bench.close


def main():
    parser = argparse.ArgumentParser(description="Run a fault injection campaign.")
    parser.add_argument("--target", choices=("sil", "hil"), default="sil")
    parser.add_argument("--runs", type=int, default=30, help="injections per fault")
    parser.add_argument("--can-interface", default="slcan")
    parser.add_argument("--can-channel", default=None)
    parser.add_argument("--bitrate", type=int, default=500000)
    parser.add_argument("--timing-slack-ms", type=float, default=5.0)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    bench, cleanup = open_bench(args)
    try:
        rows = run(bench, args.target, args.runs)
    finally:
        cleanup()
    path = args.out or RESULTS / f"campaign_{args.target}.csv"
    save(rows, path)
    print(markdown(summarize(rows)))
    print(f"\n{len(rows)} injections, {sum(1 - r['met'] for r in rows)} over the limit. Wrote {path}")


if __name__ == "__main__":
    main()
