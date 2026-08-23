# Personal-site project page

[`index.html`](index.html) is a **project write-up for a personal website** — a single
self-contained page telling the story of this retrofit for a general reader. It is not part
of the build, not an operator document, and nothing on the saw serves it.

Drop it on any static host. There are no relative asset paths: the three photographs are
inlined as data URIs, the four schematics are inlined as SVG, and the typefaces come from
Google Fonts, so the file works from a `file://` URL, a subdirectory, or a bare bucket.

It is **2.1 MB**, most of that the `circuitikz` sheets. They are text and compress well;
the base64 photographs are the part that will not. If size ever matters more than the
single-file property, split the sheets back out to `<img src="...svg">` and lose the
portability.

## The typeface

**Redaction**, by Titus Kaphar and Reginald Dwayne Betts for their show at MoMA PS1.
© 2019 MCKL Inc., dual licensed **SIL OFL 1.1 / LGPL 2.1** — which is what permits
embedding it in the page.

`redaction.us` is unreachable from the build environment and the font is not on Google
Fonts, so the subsets come from Fontsource on npm:

```bash
npm pack @fontsource/redaction @fontsource/redaction-35
```

The family ships in seven grades of degradation. The page uses two: **grade 35** for
display, where the halftone texture is the point, and the **clean cut** for anything
anyone has to read. Both are embedded as base64 `woff2` in `@font-face` blocks at the top
of the stylesheet — latin subsets, 400 / 400 italic / 700 for the text cut and 400 for
grade 35, about 126 KB before encoding.

`IBM Plex Mono` stays as the utility voice for part numbers, codes and tabular data; it
comes from Google Fonts over the network.

## What it is allowed to say

The same rule as everywhere else in this repository: **never state a fact the repository
does not establish.** The page opens on the fact that nothing has been commissioned,
marks SR-3 unmet, and gives every unmeasured value a **redaction bar** rather than a
plausible-looking number. That device is the design carrying the discipline: if nobody has
measured it, it is blacked out. Keep it if you restyle the page.

Unpurchased parts stay dashed on the ladder rung, the same way
[`ladder_coil_circuit.svg`](../hardware/schematic/ladder_coil_circuit.svg) draws the ghost
thermostat.

## Colour

The page is **predominantly** greyscale, not entirely. Page furniture — type, rules,
tables, the requirement grid — has no hue at all. Colour appears in exactly three places
and each one carries meaning:

**The spectrum.** One `--spectrum` gradient, built from seven `--sp1`…`--sp7` tokens with
a lighter set for dark mode. It marks *what is live, closed, or hot*, and nothing else:

| Where | Why |
|---|---|
| The rule above the masthead, and each beat marker | Signature |
| Both temperature scales | Its natural home — the axis really is thermal |
| The `ARMED` box in the state machine | The one state in which the saw can run |
| The `drive GPIO26` box in the core diagram | The live output |
| The dashboard's chart stroke, and the ARMED LED | Live temperature, live state |

Resist adding a sixth use. The accent is legible because it is rationed.

**The drawings.** The four `circuitikz` sheets and the whiteboard keep their ink.
On the sheets the coding is load-bearing — conductors, warnings and signal classes each
carry a hue. On the whiteboard, green is what already existed and purple is what was being
added, which is the entire content of the sketch.

**The dashboard.** Its state colours are the operator's real ones — green armed, amber
cooling, red tripped, purple locked out — because that is what somebody would actually see.

Everything photographic is greyscale, applied as a CSS filter so the originals in the
repository stay untouched. The whiteboard is the one photograph exempted, for the reason
above.

## Keeping it honest

This page is **not** wired into `tools/codedocs.py`, so CI will not catch it quoting a
stale threshold. It is a portfolio page rather than something an operator reads at the
machine, which is why it sits outside that gate — but it does quote numbers, so when any
of these change, change them here too:

| If this changes | Update |
|---|---|
| A threshold in [ARCHITECTURE.md § Thresholds](../ARCHITECTURE.md#thresholds-defaults-configurable) | The thresholds table beside the dashboard, and the dashboard's own `trip / warn / reset` readout |
| A Path A threshold in [`firmware/include/saw_config.h`](../firmware/include/saw_config.h) | The same table's frame row |
| The build state in [BUILD-LOG.md](../BUILD-LOG.md) | The ledger and photo captions in § 9, the unknowns in § 10, and the title block |
| A safety requirement in [ARCHITECTURE.md § Safety requirements](../ARCHITECTURE.md#safety-requirements) | The SR grid in § 7 |
| An error code in [`docs/codes/`](../docs/codes/) | The code table inside the dashboard |
| The dashboard markup in [`firmware/src/saw_net.cpp`](../firmware/src/saw_net.cpp) | The § 6 mockup — it mirrors the real layout, classes and labels |
| A sheet in [`hardware/schematic/`](../hardware/schematic/) | Re-inline it — see below |
| A state colour in [`firmware/src/saw_net.cpp`](../firmware/src/saw_net.cpp) | The `.dash` palette, which mirrors it |
| A photograph in [`hardware/photos/`](../hardware/photos/) | Re-inline it — see below |

The date in the title block and the footer is the build log's own "last updated", not the
date the page was edited.

## `assets/`

[`assets/2026-08-23-concept-whiteboard.jpg`](assets/) is the initial concept sketch, shot
on a whiteboard and used in § 3. It lives here rather than in
[`hardware/photos/`](../hardware/photos/) on purpose: that directory is the **as-built**
record, and this is a pre-build concept — three things on the board turned out not to
survive verification, which is exactly why the page uses it.

The source is EXIF-rotated; `PIL.ImageOps.exif_transpose` alone gives the upright image.
It is cropped to the board interior and resized to 1800 px wide.

## Re-inlining an image or a sheet

The four sheets are inlined as live SVG rather than `<img>`, so CSS can size and filter
them. Because they share one document, every `id` is namespaced on the way in — `s1-` for
the ladder, `s2-` supervisor, `s3-` pictorial, `s4-` mains — and every `xlink:href` is
rewritten to match. Skip that and the four sets of `dvisvgm` glyph ids collide, and the
sheets render each other's lettering.

Per sheet, in order:

1. Read the file and slice from the first `<svg`, dropping the XML declaration and the
   `dvisvgm` comment, neither of which may appear mid-document.
2. Rewrite `id='X'` to `id='sN-X'`, then `xlink:href='#X'` to `xlink:href='#sN-X'`.
3. Strip the root `width` and `height` so `.sheet-frame svg` sizes it.

Photographs are base64 JPEG data URIs assigned to `.photo-*` background rules in a second
`<style>` block at the end of the file, kept apart from the stylesheet so the base64 does
not sit in the middle of the CSS. Each rule's `aspect-ratio` is the source image's pixel
dimensions — change one and change the other, or the photograph gets cropped.

## The dashboard mockup

§ 6 reproduces the real dashboard from
[`firmware/src/saw_net.cpp`](../firmware/src/saw_net.cpp) — its markup, class names and
layout, scoped under `.dash` so the two stylesheets do not collide. Its state colours are the
device's real ones, so the mockup reads as a screenshot rather than as page furniture.

The readings are illustrative, and the caption says so, because the device has never been
powered. They are nonetheless the values a Path A build would print — the thresholds from
`saw_config.h`, the `UNCALIBRATED` footer flag, `no frame sensor` (Path A's trip source
*is* the frame, so there is no second reading to difference against), and the 749 h ring
that `saw_store_retention_hours()` works out from `SAW_LOG_RING_BYTES` and a 16-byte
record. If any of those change, change the mockup.
