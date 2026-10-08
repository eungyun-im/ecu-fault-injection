# What the two targets measure

The same tests run on two targets. They answer different questions.

| | Software in the loop | Hardware in the loop |
|---|---|---|
| ECU code | `firmware/lib/ecu`, compiled for the PC | The same files, compiled for the MCU |
| Platform | A model: `bench/ecu_model.py` | The real MCU, CAN controller, watchdog and oscillator |
| Time | Simulated, 1 ms steps, repeatable | Real |
| Shows | The logic reacts correctly to each event | The event really happens, and how long everything really takes |
| Cannot show | Anything about the hardware | Rare timing-dependent cases, unless repeated often |

## Why the simulated reaction times have no spread

In the simulation a missing command is detected exactly 51 ms after the last one, every
time: the ECU runs once per millisecond and nothing else varies. That number is the
design value. On the board the same reaction has a spread, from the phase between the
PC and the ECU, the tolerance of the oscillators and the time the bus is busy. The
campaign (`python -m bench.campaign`) exists to measure that spread. The requirement is
about its worst case, not its average.

## Uncertainty of the measurement on the board

Every time in a test is taken on the PC, when a frame is handed to the bench. Between
the bus and that moment are the USB adapter, the USB stack and the scheduler of the
operating system. Typical delays are 1 to a few milliseconds, with occasional longer ones.

- The limits in the tests are widened by `--timing-slack-ms` (default 5 ms on the board, 0 in simulation).
- A reaction time is a difference of two such timestamps, so a constant delay cancels out and the jitter remains.
- The command is sent from a Python thread. On Windows with Python older than 3.11, `time.sleep` is coarse (about 15 ms), which shows up as jitter in the command cycle. Use Python 3.11 or newer.
- A result close to a limit is neither a pass nor a fail until the uncertainty is smaller than the margin. A logic analyzer on the bus, or an adapter with hardware timestamps, settles it.

## What only the board can answer

These are open until the run on the board. They are the reason for building it.

| Question | Where the answer comes from |
|---|---|
| Does the real watchdog restart a stuck CPU, and after how long? Its clock (LSI) has a wide tolerance. | `test_stuck_cpu_is_restarted_by_the_watchdog`, campaign `cpu_halt` |
| How long does a restart take, from reset to the first frame? | Same |
| Do the fault memory and the restart counter survive a reset in the backup register? | `test_fault_memory_survives_a_reset` |
| Is the internal oscillator accurate enough for 500 kbit/s with this bit timing? | A long run without error frames |
| Does the ECU come back from a real bus-off? | `test_ecu_rejoins_the_bus_after_a_short_circuit` |
| What is the jitter of the 10 ms status message? | `test_status_message_cycle_time` |
