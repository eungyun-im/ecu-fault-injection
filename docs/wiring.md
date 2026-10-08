# Wiring

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="img/bench-wiring-dark.svg">
  <img src="img/bench-wiring-light.svg" alt="NUCLEO-G431RB wired to an SN65HVD230 transceiver, a terminated CAN bus and a CANable adapter" width="760">
</picture>

## Parts

| Part | Role |
|---|---|
| NUCLEO-G431RB | The ECU. The on-board ST-LINK powers and flashes it over USB. |
| SN65HVD230 module | CAN transceiver, 3.3 V: turns the TX and RX signals of the MCU into the bus signal |
| CANable (or compatible) | USB-CAN adapter: connects the PC to the bus |
| 2 x 120 Ω, jumper wires | Bus termination and connections |

## Connections

| From | To | Note |
|---|---|---|
| NUCLEO `PA12` (FDCAN1_TX) | Transceiver `CTX` (also labelled `D` or `TX`) | Morpho connector CN10 |
| NUCLEO `PA11` (FDCAN1_RX) | Transceiver `CRX` (also labelled `R` or `RX`) | Morpho connector CN10 |
| NUCLEO `3V3` | Transceiver `3V3` | Power header CN6, labelled on the board |
| NUCLEO `GND` | Transceiver `GND` | Power header CN6, labelled on the board |
| Transceiver `CANH` | CANable `CANH` | |
| Transceiver `CANL` | CANable `CANL` | |
| NUCLEO `GND` | CANable `GND` | Common reference for the two USB-powered sides |

`PA11` and `PA12` are not labelled on the board. According to the board user manual
(UM2505, STM32G4 Nucleo-64 boards) they are CN10 pin 14 and pin 12. Check the pin table
there before connecting: this repository has not been run on a board yet, so the pin
numbers here are taken from the manual and not from a working bench.

## Termination

A CAN bus needs 120 Ω at each end, 60 Ω in total.

1. With everything unpowered, measure the resistance between CANH and CANL.
2. **60 Ω:** done.
3. **120 Ω:** one end is terminated. Many SN65HVD230 modules carry a 120 Ω resistor, and most CANable adapters have a jumper or switch for one. Add the missing one.
4. **Open circuit:** put a 120 Ω resistor across CANH and CANL at both ends.

A bus without termination often still works on a short cable at 500 kbit/s, and then
fails in the tests that stress it. Measure instead of trying.

## The bus-off test

`tests/test_bus_off.py` asks for a short circuit between CANH and CANL for about a
second. A jumper wire between the two terminals does it. The transceiver outputs are
short-circuit protected, and this is exactly the fault the test is about.
