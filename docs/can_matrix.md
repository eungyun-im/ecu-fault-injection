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

## BootStatus `0x211`, ECU to bench, every 100 ms, only while the bootloader runs

| Byte | Signal | Values |
|---|---|---|
| 0 | State | 0 idle, 1 erasing, 2 downloading, 3 transferred |
| 1 | Session | 1 default, 2 programming |
| 2 | Application valid | 0 or 1 |
| 3 to 5 | Version of the installed application | major, minor, patch. 0 when none |
| 6 | unused | 0 |
| 7 | Counter | advances by 1 with every frame |

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
| `0x0203` | Build information: bit 0 fault injection included, bit 1 alive counter check implemented, bit 2 built for the bootloader | 1 |
| `0xF180` | Bootloader version (bootloader only) | 3 |
| `0x0210` | Installed application: valid flag and version (bootloader only) | 4 |

| Routine (`0x31 01`, test build, extended session) | Parameter | Effect |
|---|---|---|
| `0xF001` | none | The CPU stops in an endless loop |
| `0xF002` | duration in ms, 2 bytes | The cyclic task is held up for that long |
| `0xF003` | number of frames, 1 byte | The next ActuatorStatus frames carry a wrong CRC |

| Routine (`0x31 01`, bootloader, programming session) | Parameter | Effect |
|---|---|---|
| `0xFF00` | version, 3 bytes | Check preconditions: is this version acceptable? |
| `0xFF01` | CRC-32, 4 bytes | Check the image in flash and activate it |
| `0xFF02` | none | Erase the application. Test build of the bootloader only |
