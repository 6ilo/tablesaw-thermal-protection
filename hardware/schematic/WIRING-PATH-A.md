# Wiring table — Path A supervisor (hardware on hand)

The pin-level, build-without-translating-a-schematic reference for
the **parts that were actually purchased**. If you are wiring the
bench build from BUILD-TONIGHT.md and only want to look at one
thing, look at this table.

> **This is not the same build as [`WIRING.md`](WIRING.md).** That
> table describes Path B — MAX31855, opto-isolated relay module,
> Mean Well PSU, bimetallic thermostat. None of those parts has
> been bought. Do not mix rows between the two tables.

Schematic cross-checks: [`pathA_supervisor.svg`](pathA_supervisor.svg)
for the board, [`pathA_ladder_coil_circuit.svg`](pathA_ladder_coil_circuit.svg)
for the coil circuit.

## The three parts this build is made of

| ASIN | Part | What the listing actually says |
|---|---|---|
| `B0GF1ZJCCN` | ESP32-DevKitC-32E, 2-pack | ESP32-WROOM-32E, dual-core 240 MHz, 8 MB flash, **USB-C**, **38-pin** |
| `B0F8NQ9S4R` | DROK 10K NTC probe, 3-pack | 10 kΩ / B3950 1%, **−25 to +125 °C**, 5 × 25 mm stainless, 1 m PVC lead, JST XH 2.54 2-pin, 3–5 V |
| `B07CTL3TG6` | VONVOFF 433 MHz RF switch kit | AC 100–240 V single phase, 30 A rated on a 40 A relay, 328 ft, learning-code, **2 fobs + 1 receiver**, modes: point-movement / self-locking / interlock |

Everything else in this build is scrounged: one level-shifting part,
two resistors, a USB phone charger, and hookup wire.

## ESP32 power — through the USB-C connector

| ESP32 | Goes to | Notes |
|---|---|---|
| `USB-C` port | UL-listed USB phone charger | **No VIN wire.** The board is powered through its own USB-C connector. A listed charger is a certified reinforced-isolation AC-DC supply, so the isolation question that blocks Path B (TASK-2) does not arise here. |
| `GND` | Common GND bus | Everything else's ground lands here. The DevKitC-32E has several GND pins; tie the ones you use together. |
| `3V3` | NTC divider top | Regulated on the module. Do not connect an external 3.3 V supply here. |

## DROK NTC divider — the trip source in this build

Divider topology: `3V3 → 10 kΩ 1% → GPIO34 → NTC 10 kΩ B3950 → GND`

| Node | Goes to | Wire colour | Notes |
|---|---|---|---|
| Top of 10 kΩ | ESP32 `3V3` | orange | Any resistor near 10 kΩ works. **Measure it** and put the measured value into the β equation — a 5% part can read 9.5–10.5 kΩ. |
| Junction | ESP32 `GPIO34` | purple | ADC1_CH6, **input-only**. ADC1 stays usable while Wi-Fi is up. Do not move this to an ADC2 pin (GPIO0/2/4/12–15/25–27) — those read zero. |
| Bottom of NTC | Common GND bus | black | |
| Probe body | Motor **frame**, fin channel near the drive end | — | Thermal grease, hose-clamped, insulated on the outboard face. Not the winding: the PVC lead and the 125 °C ceiling both rule that out. |

The probe ships with a JST XH 2.54 2-pin connector. Cut it off and
solder to hookup wire if you do not have the mate.

**Unlike Path B, this NTC is the trip authority.** There is no
K-type and no thermostat. Thresholds are therefore set from an
observed baseline (BUILD-TONIGHT.md § 7 steps 8–9), not from the
110 °C winding figure in ARCHITECTURE.md.

## Fob drive — GPIO26 through a level shifter

The fob's ON-button pad sits on the fob's own ~12 V rail.
**Never connect GPIO26 to it directly.**

### Optocoupler version (recommended — galvanic isolation)

| Pin | Goes to | Wire colour | Notes |
|---|---|---|---|
| `A` (anode) | ESP32 `GPIO26` via 330 Ω | brown | |
| `K` (cathode) | Common GND bus | black | |
| `C` (collector) | Fob ON-button pad, encoder side | brown | Meter the two pads to find which one is *not* fob ground. |
| `E` (emitter) | Fob battery negative | black | |

No shared ground between the ESP32 and the fob is required.

### NPN version

| Pin | Goes to | Notes |
|---|---|---|
| Base | ESP32 `GPIO26` via 1 kΩ | 470 Ω–10 kΩ all work |
| Collector | Fob ON-button pad, encoder side | |
| Emitter | Fob battery negative | **Ties ESP32 GND to fob GND** — that common reference is required for this version to switch at all |

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
| `GPIO2` | Onboard blue LED on the DevKitC. No external wire. Six patterns — see BUILD-TONIGHT.md § 5. |

There is **no ack button** in this build. `MANUAL_LOCKOUT` clears
only by power-cycling the ESP32.

## Receiver — mains side

Not on the low-voltage sheet. Full chain in
[`pathA_ladder_coil_circuit.svg`](pathA_ladder_coil_circuit.svg):

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
   the receiver between the seal-in and the coil — that is the Path B
   position, and it assumes the relay module this project does not own.

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
momentary-mode check below: hold a fob button and the contact must
close; release it and the contact must open. **If the contact is
closed while nothing is transmitting, stop** — the fail-safe
inversion this whole design rests on is not there.

## Sanity checklist before first power-up

1. **10 kΩ pulldown between GPIO26 and GND.** Measure it: ~10 kΩ.
   Without it a floating GPIO26 on boot can transmit.
2. **With the ESP32 unpowered, the fob must not transmit** and the
   receiver contact must be open. Verify by observation.
3. **Divider resistor measured**, and the measured value is in the
   firmware's β equation.
4. **NTC on GPIO34 (ADC1)**, not on an ADC2 pin.
5. **Two-point calibration done** — ice water and boiling water,
   both within ±2 °C, before the probe is mounted.
6. **Receiver programmed to momentary**, verified by holding a fob
   button and watching the contact drop within about a second of
   release. Record the decay time; the heartbeat has to beat it. The
   contact must be **open** with nothing transmitting.
7. **Receiver `AC IN L` tapped upstream of the seal-in**, `AC OUT L`
   feeding STOP, and the N bus on the control return. Not wired
   straight to the coil.
8. **Charger is a listed USB wall wart**, not the unidentified
   "220 to 12 V buck converter" (see ARCHITECTURE.md TASK-2).

## What Path A does not have

- **No passive layer.** SR-3 is unmet until the bimetallic
  thermostat (TASK-6) is fitted. Every protective function on the
  rung depends on the ESP32 continuing to transmit.
- **Frame temperature, not winding temperature.** The NTC trails the
  winding, so it is slower and less direct than the Path B K-type.
- **Continuous 433 MHz transmission** during ARMED — see
  BUILD-TONIGHT.md § 9 on FCC Part 15.
- **A probe that has fallen off but still reads shop ambient** is the
  one fault the heartbeat does not catch. The `probe_verified` latch
  in the firmware is a partial mitigation.
