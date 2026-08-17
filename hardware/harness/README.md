# Harness diagrams

Wireviz source for the cable and interconnect diagrams. Both are drawn
for the hardware on hand; parts and purchase status live in
[`../BOM.csv`](../BOM.csv).

- **[`frame_probe.yml`](frame_probe.yml)** — the DROK NTC probe
  clamped to the outside of the motor frame, extended back to the
  ESP32 enclosure. Nothing on this run is at mains potential and it
  does not enter the motor.
- **[`fob_and_receiver.yml`](fob_and_receiver.yml)** — the heartbeat
  path. ESP32 `GPIO26` through an optocoupler into the VONVOFF fob's
  ON pad, and the VONVOFF receiver landed at the head of the
  coil-circuit rung: `AC IN L` from control L1, `AC OUT L` into STOP,
  and the bonded N pair on the control return. The 433 MHz hop is
  deliberately *not* drawn as a cable — it is an air gap, and drawing
  it as a conductor is how someone talks themselves into trusting it.

## Rendering

Wireviz needs the Graphviz `dot` binary at runtime. One-time setup:

```bash
sudo apt install graphviz            # system dependency
uv tool install wireviz              # or: pipx install wireviz
```

Then from the repo root:

```bash
wireviz hardware/harness/frame_probe.yml
wireviz hardware/harness/fob_and_receiver.yml
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
[`../schematic/`](../schematic/).
