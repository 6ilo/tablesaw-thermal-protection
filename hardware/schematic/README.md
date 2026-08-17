# Schematics and wiring

Documentation-grade diagrams and pin tables for the retrofit. Not a
PCB / EDA design — the eventual PCB port will be KiCad. Everything
here is drawn with [CircuiTikZ](https://ctan.org/pkg/circuitikz) and
rendered to SVG, so it diffs as source, reviews on GitHub without any
tooling, and uses the same IEC/IEEE symbol set an electrician already
reads.

## Contents

| Artifact | Role | Rendered from |
|---|---|---|
| [`WIRING.md`](WIRING.md) | Full pin-to-pin table. **Start here if you are wiring the board.** | (markdown, no render step) |
| [`esp32_supervisor.svg`](esp32_supervisor.svg) | Signal-level schematic — design of record for the low-voltage side | [`esp32_supervisor.tex`](esp32_supervisor.tex) |
| [`esp32_pictorial.svg`](esp32_pictorial.svg) | Block-and-wire pictorial — where each module sits, colour-coded wires | [`esp32_pictorial.tex`](esp32_pictorial.tex) |
| [`ladder_coil_circuit.svg`](ladder_coil_circuit.svg) | Ladder-logic view of the 3-wire seal-in with the retrofit interposed | [`ladder_coil_circuit.tex`](ladder_coil_circuit.tex) |
| [`oneline_mains.svg`](oneline_mains.svg) | One-line diagram of the mains distribution + control-supply tap | [`oneline_mains.tex`](oneline_mains.tex) |

Shared style lives in [`tsstyle.tex`](tsstyle.tex) — palette, line
weights, block and label styles, the isolation-boundary style, and the
title-block macro. Sheets carry geometry only, so a look-and-feel
change is a one-file edit.

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

```bash
cd hardware/schematic
make            # rebuild every SVG that is out of date
make clean      # drop the LaTeX intermediates
make distclean  # also drop the generated SVGs
```

You need a LaTeX install with `circuitikz` and `dvisvgm`. On Debian /
Ubuntu that is `texlive-pictures texlive-latex-recommended`; for a
self-contained install that needs no root:

```bash
wget -qO- "https://yihui.org/tinytex/install-bin-unix.sh" | sh
export PATH="$HOME/bin:$HOME/.TinyTeX/bin/x86_64-linux:$PATH"
tlmgr install circuitikz standalone siunitx helvetic psnfss dvisvgm
```

### Why `latex` → DVI → `dvisvgm`, not `pdflatex`

`dvisvgm` can read PDF, but only via Ghostscript < 10.01 or `mutool`;
on a current distro neither is a given. The DVI path needs neither,
because `\def\pgfsysdriver{pgfsys-dvisvgm.def}` at the top of each
sheet makes PGF emit SVG natively.

`--no-fonts` traces glyphs to paths. The SVGs therefore carry no font
dependency and render identically in GitHub, a browser, and Inkscape —
which is what the previous renders got wrong (missing glyphs showed as
tofu boxes).

## Drawing conventions

These hold across all four sheets.

| Convention | Meaning |
|---|---|
| Red conductor | at mains potential |
| Blue conductor | SELV (the isolated 5 V rail) |
| Black conductor | logic / signal, or DC ground |
| Dashed red line | isolation boundary — nothing may be drawn across it |
| Filled dot | a junction. The **only** thing that means "connected" |
| White break in a wire | a crossing, not a connection |
| Green tint panel | added by the retrofit (vs. the OEM machine) |

Prose belongs in the legend boxes and title block, not scattered
across the canvas. If a note needs more than a few lines, it belongs
in `WIRING.md` or `../../ARCHITECTURE.md` instead.

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
- The mains boundary at the relay contacts, drawn rather than
  described

### `esp32_pictorial.svg` — spatial / colour-coded view

Laid out the way a breadboard actually sits: two power rails along the
bottom, modules above them. Wire colours match the `WIRING.md` colour
code exactly. Pin-level truth lives in `WIRING.md` and
`esp32_supervisor.svg`; this drawing is spatial only.

### `ladder_coil_circuit.svg` — coil-circuit ladder

The retrofit as an electrician sees it:

```
L1 → STOP → [START ∥ M1 aux] → TSTAT (NC) → KA (ESP32 relay, NO)
   → OL → M1 coil → L2
```

`TSTAT` and `KA` are in series — either open drops the coil, which
breaks the M1-aux seal-in, which means the motor cannot restart on
its own. Fail-safe topology. The legend tabulates what opens each
element and what opens `KA` specifically.

### `oneline_mains.svg` — mains distribution

- Utility → wall disconnect → tap point → 30 A motor branch → M1 →
  OL → motor
- Retrofit control-supply branch: tap → 250 mA fuse → isolated
  AC-DC PSU → 5 V SELV → ESP32
- The PSU's reinforced isolation barrier drawn through the middle of
  the part, primary and secondary labelled
- L2 return conductor closes the loop
- Isolation and "what changed vs. OEM" summary in the legend

## What's *not* here

- The mains coil circuit wiring inside the starter enclosure — see
  [`../harness/mains_and_coil.yml`](../harness/mains_and_coil.yml)
- Motor sensor pigtail — see
  [`../harness/motor_pigtail.yml`](../harness/motor_pigtail.yml)

## Long-term

When it's time to lay out a real PCB, port `esp32_supervisor.tex` to
KiCad. Everything here is a documentation artifact, not an EDA
design — deliberately. The point is that these diagrams live in the
same repo as the firmware and the safety spec, review on GitHub
without any tooling, and regenerate with one `make`.
