# Board-level schematic

Signal-level schematic of the low-voltage side of the ESP32 supervisor. Cable and mains harness live one directory over in [`../harness/`](../harness/).

- **[`esp32_supervisor.py`](esp32_supervisor.py)** — SchemDraw source. This is the artifact under version control; the SVG is a regenerated view.
- **[`esp32_supervisor.svg`](esp32_supervisor.svg)** — rendered output. Regenerate any time the source changes.

## Rendering

The script has PEP 723 inline metadata, so `uv` handles dependencies and venv:

```bash
uv run hardware/schematic/esp32_supervisor.py
```

That's it — no `pip install`, no venv setup. Writes `esp32_supervisor.svg` next to the script.

If you don't have `uv`:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install "schemdraw>=0.19"
python3 hardware/schematic/esp32_supervisor.py
```

## What's on the sheet

- ESP32-DevKitC-32E with the pin assignments from [`../../ARCHITECTURE.md § Pin assignments`](../../ARCHITECTURE.md#pin-assignments)
- MAX31855 SPI thermocouple front-end (SCK / MISO / CS to GPIO18 / 19 / 5)
- NTC divider for the frame secondary sensor (3V3 → 10 kΩ → GPIO34 → NTC → GND)
- Opto-isolated relay module driven by GPIO26 with the 10 kΩ pulldown that guarantees floating-GPIO = relay-open
- Ack button (GPIO27 to GND, firmware pullup)
- Status LED annotation on GPIO2 (onboard on the DevKitC — external label only)

## What's *not* on this sheet

- The mains coil circuit itself — that's a wiring diagram, see [`../harness/mains_and_coil.yml`](../harness/mains_and_coil.yml)
- Motor sensor pigtail — see [`../harness/motor_pigtail.yml`](../harness/motor_pigtail.yml)
- Isolation boundaries — called out with labels but not drawn as a boundary; the PSU input, thermocouple AlN, and relay opto-input/contact-gap are the three isolation gaps

## Long-term

When it's time to lay out a real PCB, port this to KiCad. The SchemDraw script is a documentation artifact, not an EDA design.
