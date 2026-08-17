# Hardware

Physical build artifacts for the retrofit.

## Contents

| Path | Contents |
|---|---|
| [`schematic/`](schematic/) | Board-level signal schematic of the ESP32 supervisor. SchemDraw source + rendered SVG. |
| [`harness/`](harness/) | Cable and mains-interconnect diagrams. Wireviz YAML source; render locally per the harness README. |

## Intended structure (not yet created)

| Path | Purpose |
|---|---|
| `enclosure/` | 3D-printable brackets, panel cutouts, mounting fixtures — lands here when a physical build exists |
| `photos/` | Annotated photos of the built system (A202C terminal block with retrofit taps marked, sensor mounting on the winding, enclosure interior) |
| `BOM.csv` | Machine-readable BOM — will land here when `wireviz` is run on the harness YAML (Wireviz emits a `.bom.tsv` per harness; combine + convert to CSV) |
| `datasheets/` | PDF copies of datasheets for parts that get hard to find later — Marathon motor plate, Gould A202C wiring diagram, MAX31855, chosen thermostat, isolated PSU |

## Design of record

Until the intended-structure artifacts land, the design lives in:

- [`../ARCHITECTURE.md`](../ARCHITECTURE.md) — Coil circuit, Power supply, Wiring diagram, Pin assignments, Sensor mounting, Bill of materials
- [`../BUILD-TONIGHT.md`](../BUILD-TONIGHT.md) — § 3 Wiring, § 6 Sensor mounting for the same-day expedient build
- [`schematic/`](schematic/) and [`harness/`](harness/) — as they populate, extract the corresponding BOM rows to `BOM.csv` and reduce duplication in the top-level docs

## Safety

Every wiring section in the design docs applies to any work in this directory. See the DANGER block at the top of [`../ARCHITECTURE.md`](../ARCHITECTURE.md) and [`../BUILD-TONIGHT.md § 3`](../BUILD-TONIGHT.md).
