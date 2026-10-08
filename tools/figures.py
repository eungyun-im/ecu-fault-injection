"""Generate the README figures.

    python -m tools.figures

Writes docs/img/*.svg in a light and a dark variant.

    bench-wiring     drawing of the bench: board, transceiver, bus, adapter
    scenario         one run on the software-in-the-loop target, as a timeline
    reaction-times   results/campaign_*.csv, reaction time against the limit
"""

from pathlib import Path

from bench import campaign, ecu_lib
from bench import messages as m
from tools.svgfig import Figure, save_both, scale

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "docs" / "img"

FAULT_LABELS = {
    "command_timeout": ("Command lost", "last command to safe state"),
    "command_crc": ("Command CRC wrong", "first bad frame to safe state"),
    "command_range": ("Command out of range", "first bad frame to safe state"),
    "cpu_halt": ("CPU stuck", "last status to first status after restart"),
}
STATE_ROLE = {m.INIT: "grid", m.NORMAL: "series1", m.SAFE: "series2"}


def outline(fig, x, y, w, h, stroke="secondary", fill="surface", rx=6, width=1.5):
    fig.add(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fig.color(fill)}" '
        f'stroke="{fig.color(stroke)}" stroke-width="{width}"/>'
    )


def path(fig, points, stroke, width=2):
    d = "M" + " L".join(f"{x},{y}" for x, y in points)
    fig.add(
        f'<path d="{d}" fill="none" stroke="{fig.color(stroke)}" stroke-width="{width}" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
    )


# Bench wiring


def wiring_figure(mode):
    fig = Figure(
        760, 400, mode,
        "The bench: one ECU, one bus, one PC",
        "Drawing, not to scale. Pin positions are in docs/wiring.md",
    )

    # NUCLEO-G431RB, top view: ST-LINK part with USB on top, MCU part below
    bx, by, bw, bh = 24, 76, 190, 300
    outline(fig, bx, by, bw, bh, rx=10)
    fig.line(bx + 10, by + 78, bx + bw - 10, by + 78, stroke="grid", dash="4 4")
    outline(fig, bx + 75, by - 8, 40, 22, rx=3)  # USB connector
    fig.text(bx + bw / 2, by + 34, "ST-LINK", size=11, color="secondary", anchor="middle")
    fig.text(bx + bw / 2, by + 50, "USB: power, flashing", size=10, color="secondary", anchor="middle")
    for column in (bx + 12, bx + bw - 24):  # morpho headers CN7 and CN10
        outline(fig, column, by + 92, 12, 196, stroke="grid", rx=2, width=1)
    outline(fig, bx + 68, by + 150, 54, 54, rx=3)  # MCU
    fig.text(bx + bw / 2, by + 174, "STM32", size=10, anchor="middle", weight=600)
    fig.text(bx + bw / 2, by + 188, "G431RB", size=10, anchor="middle", weight=600)
    fig.dot(bx + 60, by + 112, "series3", r=5)
    fig.text(bx + 70, by + 116, "LD2: output enabled", size=10, color="secondary")
    fig.text(bx + bw / 2, by + 232, "FDCAN1", size=10, color="secondary", anchor="middle")
    fig.text(bx + bw / 2, by + 246, "watchdog (IWDG)", size=10, color="secondary", anchor="middle")
    fig.text(bx + bw / 2, by + 260, "reset flags", size=10, color="secondary", anchor="middle")
    fig.text(bx + bw / 2, by + bh + 16, "NUCLEO-G431RB (the ECU)", size=12, weight=600, anchor="middle")

    # Transceiver module
    tx, ty, tw, th = 320, 150, 110, 150
    outline(fig, tx, ty, tw, th)
    fig.text(tx + tw / 2, ty + th + 16, "SN65HVD230", size=12, weight=600, anchor="middle")
    fig.text(tx + tw / 2, ty + th + 31, "CAN transceiver", size=10, color="secondary", anchor="middle")

    wires = [
        ("PA12  TX", "CTX", "series1", 0),
        ("PA11  RX", "CRX", "series2", 1),
        ("3V3", "3V3", "series3", 2),
        ("GND", "GND", "secondary", 3),
    ]
    pin_x = bx + bw - 18
    for board_label, module_label, role, index in wires:
        y = ty + 24 + index * 34
        path(fig, [(pin_x, y), (tx, y)], role)
        fig.dot(pin_x, y, role, r=4)
        fig.text(pin_x + 14, y - 6, board_label, size=10, color="secondary")
        fig.text(tx + 8, y + 4, module_label, size=10)

    # Bus with termination at both ends
    ax, aw, ah = 620, 110, 150
    high_y, low_y = ty + 40, ty + 92
    outline(fig, ax, ty, aw, ah)  # USB-CAN adapter
    for label, y, role in (("CANH", high_y, "series1"), ("CANL", low_y, "series2")):
        path(fig, [(tx + tw, y), (ax, y)], role)
        fig.text(tx + tw - 8, y + 4, label, size=10, anchor="end")
        fig.text(ax + 8, y + 4, label, size=10)
    for x in (tx + tw + 34, ax - 34):
        outline(fig, x - 7, high_y + 12, 14, low_y - high_y - 24, rx=2)
        fig.line(x, high_y, x, high_y + 12, stroke="secondary", width=1.5)
        fig.line(x, low_y - 12, x, low_y, stroke="secondary", width=1.5)
    fig.text((tx + tw + ax) / 2, (high_y + low_y) / 2 + 4, "120 Ω at each end", size=10,
             color="secondary", anchor="middle")
    fig.text((tx + tw + ax) / 2, high_y - 12, "CAN bus, 500 kbit/s", size=11, anchor="middle", weight=600)

    fig.text(ax + aw / 2, ty + ah + 16, "CANable", size=12, weight=600, anchor="middle")
    fig.text(ax + aw / 2, ty + ah + 31, "USB-CAN adapter", size=10, color="secondary", anchor="middle")
    fig.text(ax + aw / 2, ty + 126, "USB to the PC:", size=10, color="secondary", anchor="middle")
    fig.text(ax + aw / 2, ty + 140, "pytest, python-can", size=10, color="secondary", anchor="middle")
    path(fig, [(ax, ty + 126), (tx + tw, ty + 126)], "secondary", width=1.5)
    fig.text(ax - 8, ty + 120, "GND", size=10, color="secondary", anchor="end")

    fig.text(tx - 46, 96, "A jumper wire across CANH and CANL is the bus-off test.",
             size=11, color="secondary")
    return fig


# Scenario timeline


def run_scenario():
    """One software-in-the-loop run with two injected faults. Returns (statuses, events)."""
    from bench.sil import SilBench

    for variant in ecu_lib.VARIANTS:
        ecu_lib.build(variant)
    bench = SilBench().prepare()
    start = bench.now_ms
    events = []
    bench.advance(150)
    bench.restbus.demand = 80
    bench.advance(150)
    events.append((bench.now_ms - start, "3 commands with a wrong CRC"))
    bench.restbus.corrupt_frames = 3
    bench.advance(800)
    events.append((bench.now_ms - start, "CPU halted"))
    bench.halt_cpu()
    bench.advance(2000 - (bench.now_ms - start))
    statuses = [(s.t_ms - start, s.state, s.applied) for s in bench.statuses(start)]
    return statuses, events


def scenario_figure(mode, statuses, events):
    fig = Figure(
        760, 330, mode,
        "Two injected faults, one run (software in the loop)",
        "The output is switched off at once and comes back after 500 ms of valid commands",
    )
    left, right, band_y, top, bottom = 64, 736, 84, 132, 280
    end = 2000
    x = scale((0, end), (left, right))
    y = scale((0, 100), (bottom, top))

    # State band
    fig.text(left - 8, band_y + 14, "State", size=11, color="secondary", anchor="end")
    segment_start, state = statuses[0][0], statuses[0][1]
    segments = []
    for t, s, _ in statuses[1:]:
        if s != state:
            segments.append((segment_start, t, state))
            segment_start, state = t, s
    segments.append((segment_start, end, state))
    for a, b, s in segments:
        fig.rect(x(a) + 1, band_y, max(x(b) - x(a) - 2, 1), 20, STATE_ROLE[s], rx=3)
        if x(b) - x(a) > 44:
            fig.text((x(a) + x(b)) / 2, band_y + 14, m.STATE_NAMES[s], size=10, anchor="middle",
                     color="text" if s == m.INIT else "#ffffff", weight=600)

    # Applied demand
    for value in (0, 50, 100):
        fig.line(left, y(value), right, y(value))
        fig.text(left - 8, y(value) + 4, f"{value} %", size=11, color="secondary", anchor="end")
    points = []
    previous = statuses[0][2]
    for t, _, applied in statuses:
        if applied != previous:
            points.append((x(t), y(previous)))
        points.append((x(t), y(applied)))
        previous = applied
    points.append((x(end), y(previous)))
    fig.polyline(points, "series1", width=2)
    fig.text(x(170) + 6, y(80) - 8, "applied demand", size=11, color="secondary")

    for t, label in events:
        fig.line(x(t), band_y + 24, x(t), bottom, stroke="secondary", dash="3 4")
        fig.text(x(t) + 6, bottom - 34, label, size=11, weight=600)
        fig.text(x(t) + 6, bottom - 20, f"injected at {t:.0f} ms", size=10, color="secondary")
    for tick in range(0, end + 1, 500):
        fig.text(x(tick), bottom + 18, f"{tick} ms", size=11, color="secondary",
                 anchor="end" if tick == end else "middle")
    return fig


# Campaign


def reaction_figure(mode, summaries):
    targets = list(summaries)
    names = list(dict.fromkeys(s["fault"] for rows in summaries.values() for s in rows))
    row_h = 30 + 18 * len(targets)
    fig = Figure(
        760, 96 + row_h * len(names) + 34, mode,
        "Reaction time to each injected fault, as a share of the allowed time",
        "Range and median over the injections of a campaign. The line at 100 % is the requirement",
    )
    label_x, left, right, value_x = 24, 250, 510, 528
    x = scale((0, 100), (left, right))
    top = 88
    for tick in (0, 50, 100):
        stroke = "secondary" if tick == 100 else "grid"
        fig.line(x(tick), top - 8, x(tick), top + row_h * len(names) - 8, stroke=stroke)
        fig.text(x(tick), top + row_h * len(names) + 10, f"{tick} %", size=11, color="secondary",
                 anchor="middle")
    for row, name in enumerate(names):
        y0 = top + row * row_h
        title, measured = FAULT_LABELS.get(name, (name, ""))
        fig.text(label_x, y0 + 12, title, size=13, weight=600)
        fig.text(label_x, y0 + 28, measured, size=10, color="secondary")
        for index, target in enumerate(targets):
            entry = next((s for s in summaries[target] if s["fault"] == name), None)
            if entry is None:
                continue
            role = "series1" if target == "sil" else "series2"
            y = y0 + 8 + 18 * index
            low, high = x(100 * entry["min"] / entry["limit"]), x(100 * entry["max"] / entry["limit"])
            fig.line(low, y, max(high, low), y, stroke=role, width=4)
            fig.dot(x(100 * entry["median"] / entry["limit"]), y, role, r=5)
            spread = f"{entry['min']:g} to {entry['max']:g} ms" if entry["max"] > entry["min"] else f"{entry['median']:g} ms"
            fig.text(value_x, y + 4,
                     f"{spread} of {entry['limit']:g} ms  (n = {entry['n']})", size=11, color="secondary")
    legend_y = top + row_h * len(names) + 26
    legend = {"sil": "Software in the loop (simulated time)", "hil": "Board (measured on the bus)"}
    offset = label_x
    for target in targets:
        fig.dot(offset + 5, legend_y - 4, "series1" if target == "sil" else "series2", r=5)
        fig.text(offset + 16, legend_y, legend[target], size=11, color="secondary")
        offset += 280
    return fig


def main():
    save_both(IMG, "bench-wiring", wiring_figure)

    statuses, events = run_scenario()
    save_both(IMG, "scenario", lambda mode: scenario_figure(mode, statuses, events))

    summaries = {}
    for target in ("sil", "hil"):
        csv_path = campaign.RESULTS / f"campaign_{target}.csv"
        if csv_path.exists():
            summaries[target] = campaign.summarize(campaign.load(csv_path))
    if summaries:
        save_both(IMG, "reaction-times", lambda mode: reaction_figure(mode, summaries))


if __name__ == "__main__":
    main()
