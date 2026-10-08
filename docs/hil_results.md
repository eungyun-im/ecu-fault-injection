# Results on the board

**Not run yet.** This page is filled in after the first run on the hardware. Until then
every number in this repository comes from the software-in-the-loop target.

## Bench

| | |
|---|---|
| Date | |
| Board and revision | NUCLEO-G431RB, |
| Firmware | commit , build `test` |
| Adapter and its firmware | |
| PC and Python version | |
| Termination measured | |

## Test suite

`pytest --target hil --can-channel <port> -v`

| Passed | Failed | Skipped |
|---|---|---|
| | | |

Failed tests, each with a defect report in [`defects/`](defects):

| Test | Observation | Report |
|---|---|---|
| | | |

## Campaign

`python -m bench.campaign --target hil --can-channel <port> --runs 30`, the table as printed:

## Open questions from measurement.md

| Question | Answer |
|---|---|
| Watchdog restart: time from the stuck CPU to the first frame | |
| Fault memory survives a reset | |
| Error frames in a 10 minute run | |
| Bus-off recovery | |
| Jitter of the status message | |

## Differences between simulation and board

What the simulation predicted, what the board did differently, and why.
