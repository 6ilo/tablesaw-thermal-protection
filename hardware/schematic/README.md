# Schematics and wiring

Documentation-grade diagrams and pin tables for the retrofit. Not a
PCB / EDA design — the eventual PCB port will be KiCad. Everything
here is drawn with `schemdraw` (Python) and rendered to SVG so it
diffs cleanly and reviews on GitHub without any tooling.

## Contents

| Artifact | Role | Rendered from |
|---|---|---|
| [`WIRING.md`](WIRING.md) | Full pin-to-pin table. **Start here if you are wiring the board.** | (markdown, no render step) |
| [`esp32_supervisor.svg`](esp32_supervisor.svg) | Signal-level schematic — design of record for the low-voltage side | [`esp32_supervisor.py`](esp32_supervisor.py) |
| [`esp32_pictorial.svg`](esp32_pictorial.svg) | Block-and-wire pictorial — where each module sits, colour-coded wires | [`esp32_pictorial.py`](esp32_pictorial.py) |
| [`ladder_coil_circuit.svg`](ladder_coil_circuit.svg) | Ladder-logic view of the 3-wire seal-in with the retrofit interposed | [`ladder_coil_circuit.py`](ladder_coil_circuit.py) |
| [`oneline_mains.svg`](oneline_mains.svg) | One-line diagram of the mains distribution + control-supply tap | [`oneline_mains.py`](oneline_mains.py) |

Which one to look at when:

- **Bench-building the ESP32 side** — `WIRING.md` then cross-check
  against `esp32_pictorial.svg`.
- **Reviewing the safety logic** — `ladder_coil_circuit.svg`. The
  ladder is the primary audit artifact for an electrician.
- **Wiring inside the starter enclosure or the wall disconnect** —
  `oneline_mains.svg` and `../harness/mains_and_coil.yml`.
- **Understanding a specific ESP32 GPIO / SPI wire** —
  `esp32_supervisor.svg` (the schematic is authoritative for signal
  topology; the pictorial is just spatial).

## Rendering

Each `.py` file carries PEP 723 inline metadata, so `uv` handles
dependencies and the venv:

```bash
uv run hardware/schematic/esp32_supervisor.py
uv run hardware/schematic/esp32_pictorial.py
uv run hardware/schematic/ladder_coil_circuit.py
uv run hardware/schematic/oneline_mains.py
```

Each writes its `.svg` next to the source. No `pip install`, no venv
setup.

If you don't have `uv`:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install "schemdraw>=0.19"
python3 hardware/schematic/esp32_supervisor.py
# ...etc for the other three
```

## What's on each sheet

### `esp32_supervisor.svg` — signal schematic (design of record)

- ESP32-DevKitC-32E with the pin assignments from
  [`../../ARCHITECTURE.md § Pin assignments`](../../ARCHITECTURE.md#pin-assignments)
- MAX31855 SPI thermocouple front-end (SCK / MISO / CS to GPIO18 / 19 / 5)
- NTC divider for the frame secondary sensor
  (3V3 → 10 kΩ → GPIO34 → NTC → GND)
- Opto-isolated relay module driven by GPIO26 with the 10 kΩ
  pulldown that guarantees floating-GPIO = relay-open
- Ack button (GPIO27 to GND, firmware pullup)
- Status LED annotation on GPIO2 (onboard on the DevKitC)

### `esp32_pictorial.svg` — spatial / colour-coded view

Complementary to the schematic — shows relative position of the
ESP32, MAX31855, PSU, relay module, NTC divider, and ack button,
with wires drawn in the same colour code you would use on a
breadboard. Pin-level truth lives in `WIRING.md` and
`esp32_supervisor.svg`; this drawing is spatial only.

### `ladder_coil_circuit.svg` — coil-circuit ladder

The retrofit as an electrician sees it:

```
L1 → STOP → [START ∥ M1 aux] → TSTAT (NC) → KA (ESP32 relay, NO)
   → OL → M1 coil → L2
```

`TSTAT` and `KA` are in series — either open drops the coil, which
breaks the M1-aux seal-in, which means the motor cannot restart on
its own. Fail-safe topology.

### `oneline_mains.svg` — mains distribution

- Utility → wall disconnect → tap point → 30 A motor branch → M1 →
  OL → motor
- Retrofit control-supply branch: tap → 250 mA fuse → isolated
  AC-DC PSU → 5 V SELV → ESP32
- L2 return conductor closes the loop
- Isolation and "what changed vs. OEM" summary in the legend

## What's *not* here

- The mains coil circuit wiring inside the starter enclosure — see
  [`../harness/mains_and_coil.yml`](../harness/mains_and_coil.yml)
- Motor sensor pigtail — see
  [`../harness/motor_pigtail.yml`](../harness/motor_pigtail.yml)
- Isolation boundaries as an explicit drawn boundary — called out
  in text on each sheet, not drawn. The three isolation gaps are
  the PSU input, the thermocouple AlN substrate, and the relay
  opto-input / contact-gap output.

## Long-term

When it's time to lay out a real PCB, port `esp32_supervisor.py` to
KiCad. Everything here is a documentation artifact, not an EDA
design — deliberately. The point is that these diagrams live in the
same repo as the firmware and the safety spec, review on GitHub
without any tooling, and regenerate with one `uv run` command.
