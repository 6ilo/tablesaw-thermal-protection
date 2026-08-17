# Harness diagrams

Wireviz source files for the cable and interconnect diagrams. Two harnesses:

- **[`mains_and_coil.yml`](mains_and_coil.yml)** — inside the starter enclosure. PSU tap in parallel with L1/L2 (through the 250 mA fuse), plus the seal-in → thermostat → ESP32 relay → contactor coil → OL → L2 chain.
- **[`motor_pigtail.yml`](motor_pigtail.yml)** — leaves the motor through the existing conduit entry. K-type thermocouple leads at the winding (yellow +, red −, PTFE) plus the two thermostat leads (black, fiberglass), landing on a 4-way terminal block inside the ESP32 enclosure.

## Rendering

Wireviz needs the Graphviz `dot` binary at runtime. One-time setup:

```bash
sudo apt install graphviz            # system dependency
uv tool install wireviz              # or: pipx install wireviz
```

Then from the repo root:

```bash
wireviz hardware/harness/mains_and_coil.yml
wireviz hardware/harness/motor_pigtail.yml
```

Each command produces `.svg`, `.png`, `.html`, `.gv`, `.tsv`, and `.bom.tsv` alongside its `.yml`. Commit only the `.svg` (or `.svg` + `.bom.tsv`) — the rest are intermediates.

## Why Wireviz for these, not KiCad or SchemDraw

Wireviz is purpose-built for harness / cable diagrams: it draws connectors as multi-pin blocks, cables as wire bundles with per-wire colour and gauge, and it emits a BOM as a side effect. That matches this project's interconnect much better than either a full EDA tool (overkill for a wire diagram) or a signal-schematic library (SchemDraw is for signal schematics; the K-type + thermostat pigtail is a *cable*, not a circuit).

Signal-level board schematic lives in [`../schematic/`](../schematic/).
