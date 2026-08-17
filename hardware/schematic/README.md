# Schematics and wiring

Documentation-grade diagrams and pin tables for the retrofit. Not a
PCB / EDA design — the eventual PCB port will be KiCad. Everything
here is drawn with [CircuiTikZ](https://ctan.org/pkg/circuitikz) and
rendered to SVG, so it diffs as source, reviews on GitHub without any
tooling, and uses the same IEC/IEEE symbol set an electrician already
reads.

## Two sets of sheets, and which hardware each is drawn for

The project has two build paths, and so does this directory. **The
distinction is load-bearing: pick the wrong set and you will be
looking at parts that are not in the box.**

| Prefix | Path | Hardware |
|---|---|---|
| `pathA_*` | **Path A** — [BUILD-TONIGHT.md](../../BUILD-TONIGHT.md) | Only parts on hand. Every component has an ASIN. |
| everything else | **Path B** — [ARCHITECTURE.md](../../ARCHITECTURE.md) | End-state target. The MAX31855, the relay module, the isolated PSU and the thermostat are all **unpurchased** (TASK-1/2/3/6). |

Each sheet carries a banner across the top saying which it is. Both
sets share the same style, symbol set, and conventions.

### Path A — the hardware actually on hand

| Artifact | Role | Rendered from |
|---|---|---|
| [`WIRING-PATH-A.md`](WIRING-PATH-A.md) | Pin-to-pin table. **Start here if you are building tonight.** | (markdown, no render step) |
| [`pathA_supervisor.svg`](pathA_supervisor.svg) | Signal schematic — USB-C power, DROK NTC divider, GPIO26 → level shifter → 433 MHz fob | [`pathA_supervisor.tex`](pathA_supervisor.tex) |
| [`pathA_ladder_coil_circuit.svg`](pathA_ladder_coil_circuit.svg) | Ladder — the VONVOFF receiver at the head of the rung, with its own supply tapped across the rails | [`pathA_ladder_coil_circuit.tex`](pathA_ladder_coil_circuit.tex) |

The three parts these sheets are drawn for:

| ASIN | Part |
|---|---|
| `B0GF1ZJCCN` | ESP32-DevKitC-32E, 2-pack — ESP32-WROOM-32E, 8 MB, **USB-C, 38-pin** |
| `B0F8NQ9S4R` | DROK 10 kΩ / B3950 NTC probe, 3-pack — −25 to +125 °C, JST XH 2.54 |
| `B07CTL3TG6` | VONVOFF 433 MHz RF switch kit — AC 100–240 V, 30 A on a 40 A relay, 2 fobs |

### Path B — the end-state target

| Artifact | Role | Rendered from |
|---|---|---|
| [`WIRING.md`](WIRING.md) | Full pin-to-pin table for the target build | (markdown, no render step) |
| [`esp32_supervisor.svg`](esp32_supervisor.svg) | Signal-level schematic for the low-voltage side | [`esp32_supervisor.tex`](esp32_supervisor.tex) |
| [`esp32_pictorial.svg`](esp32_pictorial.svg) | Block-and-wire pictorial — where each module sits, colour-coded wires | [`esp32_pictorial.tex`](esp32_pictorial.tex) |
| [`ladder_coil_circuit.svg`](ladder_coil_circuit.svg) | Ladder-logic view of the 3-wire seal-in with the retrofit interposed | [`ladder_coil_circuit.tex`](ladder_coil_circuit.tex) |
| [`oneline_mains.svg`](oneline_mains.svg) | One-line diagram of the mains distribution + control-supply tap | [`oneline_mains.tex`](oneline_mains.tex) |

Shared style lives in [`tsstyle.tex`](tsstyle.tex) — palette, line
weights, block and label styles, the isolation-boundary style, and the
title-block macro. Sheets carry geometry only, so a look-and-feel
change is a one-file edit.

Which one to look at when:

- **Building tonight from parts on hand** — `WIRING-PATH-A.md`, then
  cross-check against `pathA_supervisor.svg`.
- **Bench-building the Path B board** — `WIRING.md` then cross-check
  against `esp32_pictorial.svg`.
- **Reviewing the safety logic** — the ladder sheet for the path you
  are actually building. It is the primary audit artifact for an
  electrician.
- **Wiring inside the starter enclosure or the wall disconnect** —
  `oneline_mains.svg` and `../harness/`.
- **Understanding a specific ESP32 GPIO / SPI wire** — the schematic
  is authoritative for signal topology; the pictorial is just spatial.

### The one thing both paths get wrong if you skim

The Path B relay is a **dry, three-terminal, opto-isolated module**
that sits between the seal-in and the coil. The Path A receiver is a
**line-powered RF switch** that must sit at the head of the rung with
its own supply tapped ahead of the seal-in. They are not
interchangeable, and swapping one position for the other produces a
saw that either cannot start or is not protected.

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

### `pathA_supervisor.svg` — Path A signal schematic

- ESP32-DevKitC-32E fed through its **USB-C connector** from a
  UL-listed phone charger. No VIN wire, and no isolated-PSU module —
  the charger is the reinforced-isolation barrier.
- DROK NTC divider on GPIO34 (3V3 → 10 kΩ → GPIO34 → NTC → GND). In
  this build the NTC is the **trip source**, not an advisory second
  sensor.
- GPIO26 → 330 Ω → optocoupler → the fob's ON-button pad, with the
  10 kΩ pulldown that guarantees floating-GPIO = not transmitting.
  NPN, MOSFET and reed-relay alternates are legended.
- The 433 MHz hop drawn as an air gap, not a conductor.

### `pathA_ladder_coil_circuit.svg` — Path A ladder

```
L1 → RX → STOP → [START ∥ M1 aux] → OL → M1 coil → L2
```

- The receiver's `AC-IN` pair tapped across the rails **ahead of the
  seal-in**, because it is line-powered and must be listening before
  START is pressed.
- Its contact at the head of the rung — the placement that is correct
  whether the output turns out to be a dry contact or an
  internally-derived switched line, with the meter check to tell them
  apart in the legend.
- The learn-button mode table (1 press = momentary; 2 = toggle; 3 =
  interlock, the fail-dangerous factory default).
- A ghost slot marking where Path B's thermostat lands, so the gap is
  visible rather than implied.

### `esp32_supervisor.svg` — Path B signal schematic

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

### `esp32_pictorial.svg` — Path B spatial / colour-coded view

Laid out the way a breadboard actually sits: two power rails along the
bottom, modules above them. Wire colours match the `WIRING.md` colour
code exactly. Pin-level truth lives in `WIRING.md` and
`esp32_supervisor.svg`; this drawing is spatial only.

### `ladder_coil_circuit.svg` — Path B coil-circuit ladder

The end-state retrofit as an electrician sees it. Neither `TSTAT` nor
`KA` has been purchased:

```
L1 → STOP → [START ∥ M1 aux] → TSTAT (NC) → KA (ESP32 relay, NO)
   → OL → M1 coil → L2
```

`TSTAT` and `KA` are in series — either open drops the coil, which
breaks the M1-aux seal-in, which means the motor cannot restart on
its own. Fail-safe topology. The legend tabulates what opens each
element and what opens `KA` specifically.

### `oneline_mains.svg` — Path B mains distribution

- Utility → wall disconnect → tap point → 30 A motor branch → M1 →
  OL → motor
- Retrofit control-supply branch: tap → 250 mA fuse → isolated
  AC-DC PSU → 5 V SELV → ESP32
- The PSU's reinforced isolation barrier drawn through the middle of
  the part, primary and secondary labelled
- L2 return conductor closes the loop
- Isolation and "what changed vs. OEM" summary in the legend

## What's *not* here

Cable and interconnect diagrams live in [`../harness/`](../harness/),
split the same way:

| | Path A (on hand) | Path B (target) |
|---|---|---|
| Sensor run | [`pathA_frame_probe.yml`](../harness/pathA_frame_probe.yml) | [`motor_pigtail.yml`](../harness/motor_pigtail.yml) |
| Mains side | [`pathA_fob_and_receiver.yml`](../harness/pathA_fob_and_receiver.yml) | [`mains_and_coil.yml`](../harness/mains_and_coil.yml) |

Purchased-part inventory with ASINs: [`../BOM.csv`](../BOM.csv).

## Long-term

When it's time to lay out a real PCB, port `esp32_supervisor.tex` to
KiCad. Everything here is a documentation artifact, not an EDA
design — deliberately. The point is that these diagrams live in the
same repo as the firmware and the safety spec, review on GitHub
without any tooling, and regenerate with one `make`.
