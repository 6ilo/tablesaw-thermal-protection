# Pinout sheets

Bench-facing pinout cards: the board in the middle, every pin the build uses
flanking it as a colour-coded chip, and what each one connects to beside it.
Generated from a short YAML spec by [`../../tools/pinmap.py`](../../tools/pinmap.py).

| Sheet | Spec |
|---|---|
| [`path_a_supervisor.svg`](path_a_supervisor.svg) | [`path_a_supervisor.yml`](path_a_supervisor.yml) |

```bash
python3 tools/pinmap.py build      # render every spec
python3 tools/pinmap.py check      # CI gate — roles resolve, sheets current
```

Needs only `PyYAML`, already in [`tools/requirements.txt`](../../tools/requirements.txt).

## The pin numbers are not in the spec

A row names a **role**, not a number:

```yaml
- side: right
  role: SAW_PIN_HOLD
  label: Optocoupler anode, via 330 Ω
  class: control
```

`GPIO26` is read out of [`firmware/include/saw_config.h`](../../firmware/include/saw_config.h)
at render time. Change the pin there, run `build`, and the sheet follows. Name a
role that does not exist and the render fails with the list of ones that do.

That is the reason this generator exists rather than a hand-drawn SVG.
[`../README.md` § Where the sheets are behind the build](../README.md) records
two CircuiTikZ sheets that still say there is no ack button, months after
`SAW_HAS_ACK_BUTTON` began defaulting to 1 — a drawing and a firmware header
disagreeing, with nothing to notice. These sheets cannot do that: the disagreement
is a failed build, not a picture nobody re-read. `.github/workflows/pinmaps.yml`
watches `saw_config.h` for exactly that reason.

## Where this sits among the three generators

The repository draws three different pictures, and they are not interchangeable.

| Tool | Source | Draws | Read by |
|---|---|---|---|
| CircuiTikZ | [`../schematic/*.tex`](../schematic/) | IEC/IEEE schematics and the coil ladder | an electrician auditing the safety logic |
| WireViz | [`../harness/*.yml`](../harness/) | connector-and-cable harnesses | whoever is making up a loom |
| **pinmap** | [`*.yml`](.) | this board's pins and what lands on them | whoever is at the bench with a wire in hand |

CircuiTikZ needs a LaTeX install and draws symbols; WireViz needs Graphviz and
draws cables. This one needs neither and draws the header.

## Adding a sheet

Copy a spec, edit the rows, run `build`. Fields:

- `side` — `left` or `right`.
- `role` — a `SAW_PIN_*` name. **Preferred**, because it is checked.
- `pin` — a literal, for rails only (`3V3`, `GND`, `USB-C`), which have no role.
- `label` — what it connects to.
- `note` — the caveat that belongs next to it, not in a separate document.
- `class` — `power`, `gnd`, `analog`, `control`, `input`, `comms`, `unused`.
  Drives the colour and the legend; the palette is shared with
  [`../schematic/tsstyle.tex`](../schematic/tsstyle.tex).

Layout is computed — pill widths, board size, sheet height and the legend all
follow from the content, so adding a row is one line and never a reflow.

## What a generated sheet still cannot know

It reads `saw_config.h`, so it is right about **which pin has which role**. It
knows nothing about what is physically fitted. A pin drawn here is not a pin
wired, and `class: unused` on the MAX31855 rows is a statement about this build,
not about the part existing. [`../../BUILD-LOG.md`](../../BUILD-LOG.md) remains the
only record of what is actually on the bench.
