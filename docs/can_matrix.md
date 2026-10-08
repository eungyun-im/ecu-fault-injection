# CAN matrix

Classic CAN, 500 kbit/s, 11-bit identifiers, 8 data bytes.

## ActuatorCommand `0x200`, bench to ECU, every 10 ms

| Byte | Signal | Values |
|---|---|---|
| 0 | CRC | CRC-8 SAE J1850 over `0x00 0x02` (identifier, low byte first) and bytes 1 to 7 |
| 1 | Alive counter | low nibble, 0 to 14, then 0 again |
| 2 | `enable` | 0 or 1 |
| 3 | `demand` | 0 to 100 % |
| 4 to 7 | unused | 0 |

## ActuatorStatus `0x210`, ECU to bench, every 10 ms and on change of state

| Byte | Signal | Values |
|---|---|---|
| 0 | CRC | as above, with the identifier `0x10 0x02` |
| 1 | Alive counter | low nibble, 0 to 14 |
| 2 | State | 0 INIT, 1 NORMAL, 2 SAFE |
| 3 | Applied demand | 0 to 100 % |
| 4 | Fault flags | see below. Every fault seen since the output was last enabled |
| 5 | Cause of the last start | 0 unknown, 1 power-on, 2 reset pin, 3 software, 4 watchdog |
| 6 to 7 | unused | 0 |

## Faults

The bit in the fault flags, and the DTC that is stored.

| Bit | Fault | DTC |
|---|---|---|
| `0x01` | Command timeout | `0xC10000` |
| `0x02` | Command CRC error | `0xC10100` |
| `0x04` | Command alive counter error | `0xC10200` |
| `0x08` | Command value out of range | `0xC10300` |
| `0x10` | Task deadline exceeded | `0x4A0100` |
| `0x20` | CAN bus-off | `0xC07300` |
| DTC only | Restarted by the watchdog | `0x4A0200` |

## Diagnostics

Request `0x7E0`, response `0x7E8`. ISO-TP with normal addressing, frames padded to 8 bytes.

| DID | Content | Bytes |
|---|---|---|
| `0xF190` | VIN | 17 |
| `0xF195` | Software version | 3 |
| `0x0200` | Cause of the last start | 1 |
| `0x0201` | Number of watchdog restarts | 1 |
| `0x0202` | Number of bus-off events since start | 1 |
| `0x0203` | Build information: bit 0 fault injection included, bit 1 alive counter check implemented | 1 |

| Routine (`0x31 01`, test build, extended session) | Parameter | Effect |
|---|---|---|
| `0xF001` | none | The CPU stops in an endless loop |
| `0xF002` | duration in ms, 2 bytes | The cyclic task is held up for that long |
| `0xF003` | number of frames, 1 byte | The next ActuatorStatus frames carry a wrong CRC |
