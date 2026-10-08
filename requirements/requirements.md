# Requirements

The ECU controls one actuator. It receives a demand over CAN and applies it only while it can trust
the command, its own timing and its own program flow. Everything else is a fault, and every fault
ends in the same place: the **safe state**, with the output off.

Limits are stated at the CAN bus. How they are measured, and with what uncertainty, is in
[`docs/measurement.md`](../docs/measurement.md).

## Function

| ID | Requirement |
|---|---|
| FUNC-01 | In the state NORMAL the applied demand equals the commanded demand when `enable` is 1, and is 0 otherwise. A change of the command is applied within 50 ms. |

## Safety mechanisms

| ID | Fault | Detection | Reaction and limit |
|---|---|---|---|
| SAFE-01 | The command message is lost | No ActuatorCommand with 8 data bytes for more than 50 ms. An interruption of up to 50 ms is tolerated. | Safe state no later than 60 ms after the last command |
| SAFE-02 | The command is corrupted on the way | CRC-8 over the identifier and the data does not match. One or two corrupted frames in a row are discarded and the last valid command stays in use. | Safe state on the 3rd corrupted frame in a row, no later than 50 ms after the first |
| SAFE-03 | The sender is stuck, or frames are lost or repeated | Alive counter (0 to 14): a step of 1 or 2 is accepted. A repeated counter, a larger step and the value 15 are errors. | Safe state on the 3rd counter error in a row |
| SAFE-04 | The sender asks for something impossible | A correctly protected command with `demand` above 100 or `enable` above 1 | Safe state on the 3rd such frame in a row, no later than 50 ms after the first. A value above 100 is never applied. |
| SAFE-05 | Any of the faults in this table | | Safe state: output off, applied demand 0, state SAFE and the fault flag in ActuatorStatus, DTC stored |
| SAFE-06 | | | The output is enabled only after 500 ms of valid commands without any fault. This holds after start-up and after every fault. A fault during that time restarts it. |
| SAFE-07 | The program stops making progress | Watchdog, fed only from the cyclic task, period about 100 ms | The ECU is restarted. ActuatorStatus is back on the bus within 500 ms, and the output stays off until SAFE-06 is met. |
| SAFE-08 | | | The cause of the last start (power-on, pin, software, watchdog) is reported in ActuatorStatus and DID `0x0200`. A watchdog restart stores a DTC and increments a counter. DTCs and the counter survive a reset. |
| SAFE-09 | CAN bus-off | State of the CAN controller | The ECU rejoins the bus: ActuatorStatus is back within 1 s after the bus fault is removed. The event is counted and stored as a DTC. |
| SAFE-10 | The cyclic task runs late | More than 5 ms between two runs of the 1 ms task | Safe state and DTC. No restart as long as the watchdog period is not exceeded. |

## Network

| ID | Requirement |
|---|---|
| NET-01 | ActuatorStatus is sent every 10 ms ± 10 %, and additionally on every change of state. |
| NET-02 | ActuatorStatus carries a CRC and an alive counter that advances by 1 with every frame. |

## Diagnostics

| ID | Requirement |
|---|---|
| DIAG-01 | DiagnosticSessionControl `0x10` selects the default or the extended session and reports P2 = 50 ms and P2* = 5000 ms. Requests are answered within P2. Without a request for 5 s the ECU returns to the default session; TesterPresent `0x3E` prevents that. |
| DIAG-02 | ReadDataByIdentifier `0x22` returns the identifiers listed in [`docs/can_matrix.md`](../docs/can_matrix.md). An unknown identifier is answered with NRC `0x31`. |
| DIAG-03 | ReadDTCInformation `0x19 02` reports the stored DTCs. ClearDiagnosticInformation `0x14 FF FF FF` clears them. A DTC stays stored after its fault is gone, and the DTC of a fault that is still present is stored again after clearing. |
| DIAG-04 | An unknown service is answered with NRC `0x11`, a request of the wrong length with NRC `0x13`. A request that does not fit the receive buffer is refused with a flow control overflow frame. No request, however malformed, disturbs the function. |
| DIAG-05 | ECUReset `0x11 01` restarts the ECU after the positive response. |
| DIAG-06 | The fault injection routines of RoutineControl `0x31` exist only in a test build and are accepted only in the extended session. A release build answers them with NRC `0x31`. |

## Scope

- One ECU and one bus. The actuator is the board LED.
- End-to-end protection is modeled on AUTOSAR E2E Profile 1 (CRC-8 SAE J1850, 4-bit counter, data ID in the CRC). It is not a compliant implementation.
- "Survives a reset" means the backup domain of the MCU. A power cycle clears it.
- No ASIL is claimed. The numbers (50 ms, 500 ms, 3 frames) are design values of this project, not derived from a hazard analysis.
