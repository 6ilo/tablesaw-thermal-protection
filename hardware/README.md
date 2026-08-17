# Hardware

Physical build artifacts for the retrofit.

## Which diagrams describe the hardware you actually have

The project has two build paths and so do the drawings. Files whose
names start with **`pathA`** are drawn for the parts on hand and
nothing else. Everything else is the Path B end-state target and
contains components that have **not been purchased**.

| | Path A — on hand | Path B — target |
|---|---|---|
| Doc | [`../BUILD-TONIGHT.md`](../BUILD-TONIGHT.md) | [`../ARCHITECTURE.md`](../ARCHITECTURE.md) |
| Pin table | [`schematic/WIRING-PATH-A.md`](schematic/WIRING-PATH-A.md) | [`schematic/WIRING.md`](schematic/WIRING.md) |
| Board schematic | [`schematic/pathA_supervisor.svg`](schematic/pathA_supervisor.svg) | [`schematic/esp32_supervisor.svg`](schematic/esp32_supervisor.svg) + [`schematic/esp32_pictorial.svg`](schematic/esp32_pictorial.svg) |
| Coil-circuit ladder | [`schematic/pathA_ladder_coil_circuit.svg`](schematic/pathA_ladder_coil_circuit.svg) | [`schematic/ladder_coil_circuit.svg`](schematic/ladder_coil_circuit.svg) |
| Mains one-line | — (USB charger on a wall outlet) | [`schematic/oneline_mains.svg`](schematic/oneline_mains.svg) |
| Sensor harness | [`harness/pathA_frame_probe.yml`](harness/pathA_frame_probe.yml) | [`harness/motor_pigtail.yml`](harness/motor_pigtail.yml) |
| Mains harness | [`harness/pathA_fob_and_receiver.yml`](harness/pathA_fob_and_receiver.yml) | [`harness/mains_and_coil.yml`](harness/mains_and_coil.yml) |

Every rendered sheet carries a banner across the top saying which set
it belongs to.

## The three parts on hand

| ASIN | Part | Key specs |
|---|---|---|
| `B0GF1ZJCCN` | ESP32-DevKitC-32E, 2-pack | ESP32-WROOM-32E, 240 MHz dual-core, 8 MB flash, **USB-C**, **38-pin** |
| `B0F8NQ9S4R` | DROK 10 kΩ NTC probe, 3-pack | B3950 1%, −25 to +125 °C, 5 × 25 mm stainless, 1 m PVC, JST XH 2.54 |
| `B07CTL3TG6` | VONVOFF 433 MHz RF switch kit | AC 100–240 V, 30 A rated on a 40 A relay, 328 ft, 2 fobs + receiver |

Full inventory, including the parts still to be sourced, is in
[`BOM.csv`](BOM.csv).

Three details about these parts that the Path B drawings do not
capture, and that Path A exists to document:

1. **The board is powered over USB-C.** There is no VIN wire and no
   PSU module in the Path A build.
2. **The NTC is the trip source, not an advisory sensor.** There is no
   K-type. Its 125 °C ceiling and PVC lead are why it lives on the
   motor frame rather than at the winding, and why thresholds come
   from an observed baseline instead of the 110 °C winding figure.
3. **The RF switch is line-powered and may not offer a dry contact.**
   It is not a drop-in for the relay module Path B assumes — its
   supply has to be tapped ahead of the seal-in, and its contact sits
   at the head of the rung.

## Contents

| Path | Contents |
|---|---|
| [`schematic/`](schematic/) | Signal schematics, pictorial, ladder-logic views, mains one-line, and the two pin-to-pin tables. CircuiTikZ source + rendered SVGs. |
| [`harness/`](harness/) | Cable and mains-interconnect diagrams. Wireviz YAML source; render locally per the harness README. |
| [`BOM.csv`](BOM.csv) | Machine-readable inventory — ASINs, specs, purchase status, and which sheet each part appears on. |

## Intended structure (not yet created)

| Path | Purpose |
|---|---|
| `enclosure/` | 3D-printable brackets, panel cutouts, mounting fixtures — lands here when a physical build exists |
| `photos/` | Annotated photos of the built system (A202C terminal block with retrofit taps marked, probe clamped in a fin channel, enclosure interior) |
| `datasheets/` | PDF copies of datasheets for parts that get hard to find later — Marathon motor plate, Gould A202C wiring diagram, MAX31855, chosen thermostat, isolated PSU |

## Design of record

The drawings are documentation artifacts, not an EDA design. Where
they and the prose disagree, the prose in these files is authoritative
until the diagram is corrected:

- [`../ARCHITECTURE.md`](../ARCHITECTURE.md) — coil circuit, power
  supply, wiring diagram, pin assignments, sensor mounting, bill of
  materials
- [`../BUILD-TONIGHT.md`](../BUILD-TONIGHT.md) — § 3 wiring, § 6 sensor
  mounting for the same-day expedient build

## Open questions the drawings flag rather than answer

- **The A202C's coil voltage has not been read off the coil label.**
  It changes what the control rails are, and on Path A it determines
  where the RF receiver's supply is tapped from. The ladder sheets say
  "control circuit hot / return" rather than asserting a number.
- **Whether the VONVOFF's output is a dry contact.** Resolved with a
  meter in thirty seconds; see the legend on
  `pathA_ladder_coil_circuit.svg`.

## Safety

Every wiring section in the design docs applies to any work in this
directory. See the DANGER block at the top of
[`../ARCHITECTURE.md`](../ARCHITECTURE.md) and
[`../BUILD-TONIGHT.md § 3`](../BUILD-TONIGHT.md).
