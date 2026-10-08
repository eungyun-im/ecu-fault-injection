# First run on the board

## 1. Tools

```bash
pip install -r requirements.txt
```

```bash
pip install platformio
```

Python 3.11 or newer. The board target needs no C compiler on the PC besides the one
PlatformIO downloads.

## 2. Flash

Connect the NUCLEO over USB (the ST-LINK side), then build and upload the test build:

```bash
pio run -d firmware -e test -t upload
```

The first build downloads the toolchain and the STM32 libraries.

Without a CAN bus the ECU runs and waits. LD2 stays off, because no command arrives.

## 3. Wire

Follow [wiring.md](wiring.md). Measure 60 Ω between CANH and CANL before powering.

## 4. First contact

Find the port of the adapter (Windows: Device Manager, "Ports"; Linux: `/dev/ttyACM0`).

```bash
python -m bench.hello --can-channel COM5
```

It sends commands for three seconds and reports what the ECU answers.

| What it reports | Likely cause |
|---|---|
| No status frames | TX and RX swapped, no common ground, no termination, wrong bitrate, adapter in listen-only mode |
| Status frames with CRC errors | Bit timing or oscillator problem. Use a shorter cable and check the termination |
| State stays INIT with the timeout flag | The ECU sends but does not receive: check the RX line (PA11) |
| State NORMAL, and LD2 is on | The bench works |

## 5. Test suite

```bash
pytest --target hil --can-channel COM5 -v
```

The run takes a few minutes: every test restarts the ECU and waits for it to reach NORMAL.

The bus-off test needs a hand and a jumper wire:

```bash
pytest --target hil --can-channel COM5 -s --manual tests/test_bus_off.py
```

## 6. Campaign and results

```bash
python -m bench.campaign --target hil --can-channel COM5 --runs 30
```

```bash
python -m tools.figures
```

Commit `results/campaign_hil.csv` and the regenerated figures, and fill in
[hil_results.md](hil_results.md). The reaction-time figure then shows both targets.

Regenerating the figures needs gcc, because the scenario figure is produced by a
software-in-the-loop run. On Windows, do that step in WSL.

## 7. Bootloader and update

A second set-up, after the steps above work. It replaces what is in flash:
[update.md](update.md), section "On the board".

## Other adapters

Any python-can interface works, for example `--can-interface socketcan --can-channel can0`
on Linux with candleLight firmware.
