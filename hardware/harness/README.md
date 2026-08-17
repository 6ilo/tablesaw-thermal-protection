# Harness diagrams

Wireviz source files for the cable and interconnect diagrams. As in
[`../schematic/`](../schematic/), files are split by build path and
the `pathA_` prefix means *drawn for the hardware on hand*.

## Path A — parts on hand ([BUILD-TONIGHT.md](../../BUILD-TONIGHT.md))

- **[`pathA_frame_probe.yml`](pathA_frame_probe.yml)** — the DROK
  `B0F8NQ9S4R` NTC probe clamped to the outside of the motor frame,
  extended back to the ESP32 enclosure. Nothing on this run is at mains
  potential and it does not enter the motor.
- **[`pathA_fob_and_receiver.yml`](pathA_fob_and_receiver.yml)** — the
  heartbeat path. ESP32 `GPIO26` through an optocoupler into the
  VONVOFF fob's ON pad, and the VONVOFF receiver landed at the head of
  the coil-circuit rung with its own supply tapped across the control
  rails. The 433 MHz hop is deliberately *not* drawn as a cable.

## Path B — end-state target ([ARCHITECTURE.md](../../ARCHITECTURE.md))

- **[`mains_and_coil.yml`](mains_and_coil.yml)** — inside the starter
  enclosure. Isolated-PSU tap in parallel with L1/L2 (through the
  250 mA fuse), plus the seal-in → thermostat → ESP32 relay →
  contactor coil → OL → L2 chain.
- **[`motor_pigtail.yml`](motor_pigtail.yml)** — leaves the motor
  through the existing conduit entry. K-type thermocouple leads at the
  winding (yellow +, red −, PTFE) plus the two thermostat leads (black,
  fiberglass), landing on a 4-way terminal block inside the ESP32
  enclosure.

Neither Path B harness can be built today: the isolated PSU (TASK-2),
the dry relay module (TASK-3), the K-type/MAX31855 (TASK-1) and the
thermostat (TASK-6) are all unpurchased.

**The two mains-side files are not interchangeable.** `mains_and_coil.yml`
models a dry three-terminal relay module between the seal-in and the
coil. The purchased receiver in `pathA_fob_and_receiver.yml` is
line-powered, needs its own supply ahead of the seal-in, and may not
offer a dry contact at all.

## Rendering

Wireviz needs the Graphviz `dot` binary at runtime. One-time setup:

```bash
sudo apt install graphviz            # system dependency
uv tool install wireviz              # or: pipx install wireviz
```

Then from the repo root:

```bash
wireviz hardware/harness/pathA_frame_probe.yml
wireviz hardware/harness/pathA_fob_and_receiver.yml
wireviz hardware/harness/mains_and_coil.yml
wireviz hardware/harness/motor_pigtail.yml
```

Each command produces `.svg`, `.png`, `.html`, `.gv`, `.tsv`, and
`.bom.tsv` alongside its `.yml`. Commit only the `.svg` (or `.svg` +
`.bom.tsv`) — the rest are intermediates.

## Two traps when editing these files

Both were live bugs in this directory and both fail at render time
with errors that do not name the offending line.

1. **Quote `NO`.** YAML 1.1 parses a bare `NO` as boolean `false`, so
   `pinlabels: [COM, NO, NC]` reaches wireviz as `['COM', False, 'NC']`
   and the render dies with `TypeError: sequence item 2: expected str
   instance, bool found`. The same applies to `ON`, `OFF`, `YES`, `Y`
   and `N`. Numeric pin labels need quoting for the same reason
   (`int`, not `bool`).
2. **No `<` or `>` in notes or descriptions.** Wireviz emits notes into
   Graphviz HTML-like labels, so a `->` arrow closes the label early
   and `dot` fails with a syntax error pointing at whatever word
   followed. Write `to`, `:` or an em dash instead.

## Why Wireviz for these, not KiCad or SchemDraw

Wireviz is purpose-built for harness / cable diagrams: it draws
connectors as multi-pin blocks, cables as wire bundles with per-wire
colour and gauge, and it emits a BOM as a side effect. That matches
this project's interconnect much better than either a full EDA tool
(overkill for a wire diagram) or a signal-schematic library (SchemDraw
is for signal schematics; a sensor pigtail is a *cable*, not a
circuit).

Signal-level board schematics live in
[`../schematic/`](../schematic/). Purchased-part inventory with ASINs
is in [`../BOM.csv`](../BOM.csv).
