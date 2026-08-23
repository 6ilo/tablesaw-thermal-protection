# Wiring table — ESP32 supervisor

The pin-level, build-without-translating-a-schematic reference. If you
are wiring the board and only want to look at one thing, look at this
table.

Schematic cross-checks: [`esp32_supervisor.svg`](esp32_supervisor.svg)
for signal topology, [`esp32_pictorial.svg`](esp32_pictorial.svg) for
where the modules physically sit,
[`ladder_coil_circuit.svg`](ladder_coil_circuit.svg) for the coil
circuit.

Parts, ASINs and full specs: [`../BOM.csv`](../BOM.csv). Everything
here that isn't one of the three purchased parts is scrounged — one
level-shifting part, three resistors, a USB phone charger, hookup wire.

What is already fitted is in [`../../BUILD-LOG.md`](../../BUILD-LOG.md).
Several numbers on this page are still "measure this and write it
down" — the divider resistor, the two-point calibration, and the whole
fob pigtail table. None of them has been measured yet.

## ESP32 power — through the USB-C connector

| ESP32 | Goes to | Notes |
|---|---|---|
| `USB-C` port | UL-listed USB phone charger | **No VIN wire.** The board is powered through its own USB-C connector. A listed charger is a certified reinforced-isolation AC-DC supply, so the isolation question in TASK-2 does not arise here. |
| `GND` | Common GND bus | Everything else's ground lands here. The DevKitC-32E has several GND pins; tie the ones you use together. |
| `3V3` | NTC divider top | Regulated on the module. Do not connect an external 3.3 V supply here. |

## DROK NTC divider — the trip source

Divider topology: `3V3 → 10 kΩ 1% → GPIO34 → NTC 10 kΩ B3950 → GND`

| Node | Goes to | Wire colour | Notes |
|---|---|---|---|
| Top of 10 kΩ | ESP32 `3V3` | orange | Any resistor near 10 kΩ works. **Measure it** and put the measured value into the β equation — a 5% part can read 9.5–10.5 kΩ. |
| Junction | ESP32 `GPIO34` | purple | ADC1_CH6, **input-only**. ADC1 stays usable while Wi-Fi is up. Do not move this to an ADC2 pin (GPIO0/2/4/12–15/25–27) — those read zero. |
| Bottom of NTC | Common GND bus | black | |
| Probe body | Motor **frame**, fin channel near the drive end | — | Thermal grease, hose-clamped, insulated on the outboard face. Not the winding: the PVC lead and the 125 °C ceiling both rule that out. |

The probe ships with a JST XH 2.54 2-pin connector and **the mate is
now fitted**, so the probe plugs into the ESP32 side instead of being
soldered to it. Keep that joint inside the enclosure, not out on the
motor where dust and vibration reach it. The probe is non-polarised —
it is a thermistor, so either conductor may go to the divider junction.

**This NTC holds trip authority on its own.** There is no K-type and
no thermostat yet, so thresholds are set from an observed baseline
(BUILD-TONIGHT.md § 7 steps 8–9), not from the 110 °C winding figure
in ARCHITECTURE.md.

## Fob drive — GPIO26 through a level shifter

### The fob as it is now

The fob is open and its board — silkscreened `CYS02-E2` — is pigtailed
out to a connector on six conductors. Photos: [`../photos/`](../photos/).

| Conductor | Lands on | Confidence |
|---|---|---|
| red | cell holder, positive | from photographs |
| black | cell holder, negative | from photographs |
| yellow + orange | one button position — yellow at its top, orange at its bottom | from photographs |
| blue + green | the other button position, same arrangement | from photographs |

**Nothing in that table has been metered.** Which pair is the ON button,
which conductor of it the encoder sees, and what the cell voltage is are
all unrecorded. Fill in this table from a meter before the level shifter
is wired, and change "from photographs" to the measurement.

Having both pads of a button on the pigtail is the useful part: a switch
across a pair closes that button with no reference to fob ground, so the
optocoupler needs nothing tied together and the NPN version's shared-ground
requirement goes away.

The rail voltage is the part that matters for safety. This project's
documents assumed the ON pad sat on a ~12 V rail; the board on the bench
carries a coin-cell holder instead. **Never connect GPIO26 to a fob pad
directly** — not because 12 V is certain, but because the number is
unknown and anything above 3.3 V destroys the ESP32.

### Optocoupler version (recommended — galvanic isolation)

| Pin | Goes to | Wire colour | Notes |
|---|---|---|---|
| `A` (anode) | ESP32 `GPIO26` via 330 Ω | brown | |
| `K` (cathode) | Common GND bus | black | |
| `C` (collector) | ON-button pad, encoder side | brown | Meter the pair to find which side the encoder sees. |
| `E` (emitter) | the other ON-button pad | black | Battery negative works too if you are down to a single pad. |

No shared ground between the ESP32 and the fob is required, and with
both pads on the pigtail there is nothing to share.

### NPN version

| Pin | Goes to | Notes |
|---|---|---|
| Base | ESP32 `GPIO26` via 1 kΩ | 470 Ω–10 kΩ all work |
| Collector | ON-button pad, encoder side | |
| Emitter | the other ON-button pad | Both pads are on the pigtail, so no ground tie is needed. Working from a single pad instead, this goes to fob battery negative and **ties ESP32 GND to fob GND** — that common reference is then required for it to switch at all |

2N3904 / 2N2222 / BC547 / S8050 are all fine.

### MOSFET fallback (switches fob power, not the button)

Tape or solder-bridge the fob's ON button closed, then switch the
fob's battery negative low-side with a logic-level N-FET (2N7000,
BSS138, AO3400, IRLML2502, IRLZ44N). Gate through 220 Ω, plus a
100 kΩ gate-to-source resistor for a defined off-state.

### Mandatory on every version

| Component | Between | Why |
|---|---|---|
| 10 kΩ pulldown | `GPIO26` and GND | ESP32 GPIOs float during boot, after a crash, and through a brown-out. Floating must mean *not transmitting*, which means the receiver contact opens. This is not optional. |

## Status LED

| ESP32 pin | Behaviour |
|---|---|
| `GPIO2` | Onboard LED on the DevKitC. No external wire. Six patterns — see BUILD-TONIGHT.md § 5. |

If the board in front of you has no user LED on `GPIO2` — some DevKitC
revisions only fit a power LED — wire one from `GPIO2` through a 330 Ω
resistor to GND. Without it the operator loses the only indicator at
the machine.

## Ack button — GPIO27 to GND

| Node | Goes to | Notes |
|---|---|---|
| One side | ESP32 `GPIO27` | Internal pullup, so the pin idles HIGH and a press pulls it LOW. No external resistor. |
| Other side | Common GND bus | |

The firmware fits this on **both** build paths, and it is the only way
out of `MANUAL_LOCKOUT`. Power-cycling does not clear a lockout — the
state is persisted to NVS precisely so that it cannot be, which is what
error code `E07` publishes.

Any scrounged momentary switch works. So does a bare wire touched from
`GPIO27` to GND, which is enough to get a build commissioned before a
proper button is fitted. A press is only accepted below `RESET_C`;
pressed while the motor is still hot it is logged as `E08` and ignored.

## Receiver — mains side

Not on the low-voltage sheet. Full chain in
[`ladder_coil_circuit.svg`](ladder_coil_circuit.svg):

```
L1 → RX → STOP → [START ∥ M1 aux] → OL → M1 coil → L2
```

### Terminals

Four screw terminals in two pairs, per the manufacturer's wiring
diagram in the listing gallery:

| Terminal | Goes to | Notes |
|---|---|---|
| `AC IN L` | Control-circuit **L1**, ahead of STOP and the seal-in | Both the receiver's own supply *and* the line side of its relay. The unit does not separate them. |
| `AC IN N` | — | Bonded to `AC OUT N` internally. Same node; use either. |
| `AC OUT L` | **STOP**, then the rest of the rung | *Switched* `AC IN L`. **Not a dry contact.** |
| `AC OUT N` | Control-circuit **L2** / return | The manufacturer's diagram lands the incoming return here. |

Two consequences a dry relay module would not impose:

1. **`AC IN L` must stay permanently live**, so the receiver goes at
   the head of the rung. Feed it from downstream of the seal-in and
   the unit is unpowered — relay open — at the moment START is
   pressed, so the coil never latches and the saw never runs.
2. **There is no dry contact to relocate and no jumper to fit.** One L
   pair carries the rung, the N pair carries the return. Do not move
   the receiver between the seal-in and the coil — that position
   assumes the dry relay module of TASK-3, which the project does not
   own.

### Do not follow the manufacturer's diagram literally

That diagram runs `AC OUT L` and `AC OUT N` straight to a contactor's
coil terminals `A1`/`A2`. For a pump or a dust collector that is
correct, and it is the right general idea — let the small relay switch
a coil rather than the load.

**On a saw it is unsafe.** Wiring the coil directly bypasses the
3-wire seal-in, so the coil is energised whenever the relay is closed
and **the saw restarts by itself** the moment the RF link recovers or
the motor cools below `RESET_C`. That is exactly what SR-4 forbids.

Keep the seal-in. `AC OUT L` feeds STOP, and after any trip the coil
stays dropped until a human presses START.

### One listing claim to distrust

The listing's spec table says **"Contact Type: Normally Closed."** Do
not act on that either way. Settle it by observation in the
momentary-mode check: hold a fob button and the contact must close;
release it and the contact must open. **If the contact is closed while
nothing is transmitting, stop** — the fail-safe inversion this whole
design rests on is not there.

## Sanity checklist before first power-up

1. **10 kΩ pulldown between GPIO26 and GND.** Measure it: ~10 kΩ.
   Without it a floating GPIO26 on boot can transmit.
2. **With the ESP32 unpowered, the fob must not transmit** and the
   receiver contact must be open. Verify by observation.
3. **Fob pigtail metered** — cell voltage, which pair is the ON button,
   which conductor of it the encoder sees — and the table above filled
   in from the meter rather than from the photographs.
4. **Divider resistor measured**, and the measured value is in the
   firmware's β equation.
5. **NTC on GPIO34 (ADC1)**, not on an ADC2 pin.
6. **Two-point calibration done** — ice water and boiling water,
   both within ±2 °C, before the probe is mounted.
7. **Receiver programmed to momentary**, verified by holding a fob
   button and watching the contact drop within about a second of
   release. Record the decay time; the heartbeat has to beat it. The
   contact must be **open** with nothing transmitting.
8. **Receiver `AC IN L` tapped upstream of the seal-in**, `AC OUT L`
   feeding STOP, and the N bus on the control return. Not wired
   straight to the coil.
9. **Charger is a listed USB wall wart**, not the unidentified
   "220 to 12 V buck converter" (see ARCHITECTURE.md TASK-2). Which
   outlet it is fed from — the accessory 240 V receptacle or a
   separate wall outlet — is recorded in
   [`../../BUILD-LOG.md`](../../BUILD-LOG.md), because it decides
   whether the machine disconnect de-energises the supervisor.
10. **The accessory receptacle is not part of this wiring.** It is fed
    off the incoming supply, ahead of everything protective, and
    nothing on this page lands on it.

## What this build does not have

- **No passive layer.** SR-3 is unmet until the bimetallic
  thermostat (TASK-6) is fitted. Every protective function on the
  rung depends on the ESP32 continuing to transmit.
- **Frame temperature, not winding temperature.** The NTC trails the
  winding, so it is slower and less direct than the K-type of TASK-1.
- **Continuous 433 MHz transmission** during ARMED — see
  BUILD-TONIGHT.md § 9 on FCC Part 15.
- **A probe that has fallen off but still reads shop ambient** is the
  one fault the heartbeat does not catch. The `probe_verified` latch
  in the firmware is a partial mitigation.
