# Schematics and wiring

Documentation-grade diagrams and the pin table for the retrofit. Not
a PCB / EDA design — the eventual PCB port will be KiCad. Everything
here is drawn with [CircuiTikZ](https://ctan.org/pkg/circuitikz) and
rendered to SVG, so it diffs as source, reviews on GitHub without any
tooling, and uses the same IEC/IEEE symbol set an electrician already
reads.

**Every sheet is drawn for the hardware actually on hand.** Parts,
ASINs and purchase status live in [`../BOM.csv`](../BOM.csv) — that is
the single source for what exists and what is still TASK-*n*. The
end-state design these sheets are a waypoint towards is described in
[`../../ARCHITECTURE.md`](../../ARCHITECTURE.md).

## Contents

| Artifact | Role | Rendered from |
|---|---|---|
| [`WIRING.md`](WIRING.md) | Full pin-to-pin table. **Start here if you are wiring the board.** | (markdown, no render step) |
| [`esp32_supervisor.svg`](esp32_supervisor.svg) | Signal-level schematic — authoritative for signal topology | [`esp32_supervisor.tex`](esp32_supervisor.tex) |
| [`esp32_pictorial.svg`](esp32_pictorial.svg) | Block-and-wire pictorial — where each module sits, colour-coded wires | [`esp32_pictorial.tex`](esp32_pictorial.tex) |
| [`ladder_coil_circuit.svg`](ladder_coil_circuit.svg) | Ladder-logic view of the 3-wire seal-in with the retrofit interposed | [`ladder_coil_circuit.tex`](ladder_coil_circuit.tex) |
| [`oneline_mains.svg`](oneline_mains.svg) | One-line of the mains distribution, control branch and supervisor supply | [`oneline_mains.tex`](oneline_mains.tex) |
| [`starter_annotated.svg`](starter_annotated.svg) | Photo of the open starter, marked with where the receiver's four wires land | [`starter_annotated.py`](starter_annotated.py) + [`starter_photo.jpg`](starter_photo.jpg) |

Shared style lives in [`tsstyle.tex`](tsstyle.tex) — palette, line
weights, block and label styles, the isolation-boundary style, and the
title-block macro. Sheets carry geometry only, so a look-and-feel
change is a one-file edit.

Which one to look at when:

- **Bench-building the board** — `WIRING.md`, then cross-check against
  `esp32_pictorial.svg`.
- **Reviewing the safety logic** — `ladder_coil_circuit.svg`. The
  ladder is the primary audit artifact for an electrician.
- **Wiring inside the starter enclosure or the wall disconnect** —
  `oneline_mains.svg` and [`../harness/`](../harness/).
- **Understanding a specific GPIO** — `esp32_supervisor.svg` is
  authoritative for signal topology; the pictorial is spatial only.
- **Standing in front of the open starter with a screwdriver** —
  `starter_annotated.svg`. The ladder says what the topology is; this
  says which screw.

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
| Blue conductor | SELV (the isolated 5 V from the charger) |
| Black conductor | logic / signal, or DC ground |
| Dashed red line | isolation boundary — nothing may be drawn across it |
| Filled dot | a junction. The **only** thing that means "connected" |
| White break in a wire | a crossing, not a connection |
| Green tint panel | added by the retrofit (vs. the OEM machine) |
| Dashed grey outline | a part that is not fitted yet, or an off-board assembly |

Prose belongs in the legend boxes and title block, not scattered
across the canvas. If a note needs more than a few lines, it belongs
in `WIRING.md` or `../../ARCHITECTURE.md` instead.

## What's on each sheet

### `esp32_supervisor.svg` — signal schematic

- ESP32-DevKitC-32E fed through its **USB-C connector** from a
  UL-listed phone charger. No VIN wire, and no isolated-PSU module —
  the charger is the reinforced-isolation barrier.
- DROK NTC divider on GPIO34 (3V3 → 10 kΩ → GPIO34 → NTC → GND). The
  NTC is the **trip source**, not an advisory second sensor.
- GPIO26 → 330 Ω → optocoupler → the fob's ON-button pad, with the
  10 kΩ pulldown that guarantees floating-GPIO = not transmitting.
  NPN, MOSFET and reed-relay alternates are legended.
- The 433 MHz hop drawn as an air gap, not a conductor.
- A "not fitted, and why" legend tying each absent part to its TASK.

### `esp32_pictorial.svg` — spatial / colour-coded view

Laid out the way a breadboard actually sits: the shared rails along
the bottom, modules above them. There are only two rails — 3V3 and
GND — because nothing in this build runs off 5 V. Wire colours match
the `WIRING.md` colour code exactly. Pin-level truth lives in
`WIRING.md` and `esp32_supervisor.svg`; this drawing is spatial only.

### `ladder_coil_circuit.svg` — coil-circuit ladder

```
L1 → RX → STOP → [START ∥ M1 aux] → OL → M1 coil → L2
```

- The receiver's four real terminals (`AC IN L`/`N`, `AC OUT L`/`N`)
  with its internal relay drawn across the L pair and the N pair shown
  as the bonded bus it is. `AC OUT L` is switched `AC IN L`, so there
  is no dry contact anywhere on the part.
- `AC IN L` tapped from L1 **ahead of the seal-in**, because it is both
  the receiver's supply and the line side of its relay.
- A legend on why the manufacturer's own diagram — output straight to
  a contactor coil `A1`/`A2` — must not be copied here: it bypasses the
  seal-in and lets the saw restart by itself. SR-4.
- The learn-button mode table (1 press = momentary; 2 = toggle; 3 =
  interlock, the fail-dangerous factory default), plus the listing's
  "Normally Closed" spec-table claim flagged for verification.
- A ghost slot marking where the passive thermostat lands once TASK-6
  is bought, so the gap is visible rather than implied.

### `oneline_mains.svg` — mains distribution

- Utility → wall disconnect → 30 A motor branch → M1 → OL → motor.
  **Untouched by the retrofit** — same disconnect, same branch, same
  contactor, same overload heaters.
- Control branch: tap → receiver `AC IN L`/`N` → `AC OUT L` into the
  seal-in rung.
- Supervisor supply drawn as what it is: a **separate wall outlet**,
  not a tap off the machine. The legend spells out the consequence —
  opening the machine disconnect does not de-energise the ESP32.
- **This sheet is now behind the build.** An accessory 240 V receptacle
  has been added off the incoming supply, outside the protected path,
  and it is not drawn. It also reopens the supply question above: if
  the ESP32's charger moves to that receptacle, the legend is wrong in
  the one direction that matters. See
  [`../README.md`](../README.md) and
  [`../../BUILD-LOG.md`](../../BUILD-LOG.md); redraw once the supply
  decision is recorded, not twice.

## What's *not* here

Cable and interconnect diagrams live in [`../harness/`](../harness/):
[`frame_probe.yml`](../harness/frame_probe.yml) for the sensor run,
[`fob_and_receiver.yml`](../harness/fob_and_receiver.yml) for the
heartbeat path and the receiver's mains landings.

## Long-term

When it's time to lay out a real PCB, port `esp32_supervisor.tex` to
KiCad. Everything here is a documentation artifact, not an EDA
design — deliberately. The point is that these diagrams live in the
same repo as the firmware and the safety spec, review on GitHub
without any tooling, and regenerate with one `make`.

### `starter_annotated.svg` — which screw

Every other sheet is abstract. This one puts the receiver's four
terminals on a photograph of the open enclosure.

`AC IN L` takes control L1 ahead of STOP, `AC OUT L` feeds the lifted
STOP conductor, and `AC OUT N` takes the control-circuit return —
three conductors through the two conduit hubs. The cut point is marked
on the photo.

**What the sheet asserts, and what it refuses to.** The only markings
legible in the photograph are the moulded numerals `2` and `3` on the
barrier strip — the same terminals `ARCHITECTURE.md` names — plus a
third numeral that reads inverted. Those get amber boxes. Five brass
screws are ringed in white and lettered A–E: the rings mark screws
that *exist*, not screws *identified*. Which numeral serves which
screw, where the coil terminals sit, and whether the two side blocks
are auxiliary contacts are all unresolved from a photograph, so the
sheet says so on its face and hands the question to a meter. Step 2 of
its procedure settles it in about a minute.

The contactor body carries a grey "inside the starter" band: coil,
seal-in aux and OL contact are factory-wired, and no receiver
conductor lands in there.

#### Regenerating it

```bash
make starter_annotated.svg     # or: python3 starter_annotated.py
```

Python rather than CircuiTikZ, because the sheet is registered to
photograph pixel coordinates and TikZ is the wrong tool for that. It
needs no TeX install — only Python 3 and `starter_photo.jpg`.

The photo is **embedded as a data URI**, which is not optional: an SVG
that references an external image renders blank on GitHub and inside
any `<img>` tag. That puts the sheet at ~590 KB, which is the price of
it working anywhere you open it.

`starter_photo.jpg` is committed because it is a build input. To
re-shoot it, crop to **1125 × 1500** (3:4 portrait), replace the file
and re-run. Feature coordinates live in the `NUM`, `SCREWS`, `STRIP`,
`BODY`, `BUNDLE` and hub constants at the top of `starter_annotated.py`;
a differently framed photo means nudging those and nothing else.
