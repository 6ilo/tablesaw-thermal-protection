# Personal-site project page

[`index.html`](index.html) is a **project write-up for a personal website** — a single
self-contained page describing this retrofit for a general reader. It is not part of the
build, not an operator document, and nothing on the saw serves it.

Drop it on any static host. There are no relative asset paths: the two as-built
photographs are inlined as data URIs, the four schematics are inlined as SVG, and the
three typefaces come from Google Fonts, so the file works from a `file://` URL, a
subdirectory, or a bare S3 bucket without editing.

It is **1.7 MB**, most of that the four `circuitikz` sheets. They are text, so any host
with gzip or brotli serves them at a fraction of that; the base64 photographs are the part
that will not compress. If the size ever matters more than the single-file property, split
the schematics back out to `<img src="...svg">` and lose the portability.

## What it is allowed to say

The same rule as everywhere else in this repository: **never state a fact the repository
does not establish.** This page leads with the fact that nothing has been commissioned,
carries the build ledger and the open measurements, and marks unpurchased parts as
unpurchased — including the ghost thermostat on the ladder diagram, drawn dashed the same
way [`ladder_coil_circuit.svg`](../hardware/schematic/ladder_coil_circuit.svg) draws it.
Solid outline means it exists; dashed means it does not, yet. That distinction is load
bearing, so keep it if you restyle the page.

## Keeping it honest

This page is **not** wired into `tools/codedocs.py`, so CI will not catch it quoting a
stale threshold. It is a portfolio page rather than something an operator reads at the
machine, which is why it sits outside that gate — but it does quote numbers, so when any
of these change, change them here too:

| If this changes | Update |
|---|---|
| A threshold in [ARCHITECTURE.md § Thresholds](../ARCHITECTURE.md#thresholds-defaults-configurable) | Both scales in § 6, and the dashboard's `trip / warn / reset` readout |
| A Path A threshold in [`firmware/include/saw_config.h`](../firmware/include/saw_config.h) | The Path A scale in § 6 |
| The build state in [BUILD-LOG.md](../BUILD-LOG.md) | The ledger and photo captions in § 10, the open items in § 11, and the status line in the title block |
| A safety requirement in [ARCHITECTURE.md § Safety requirements](../ARCHITECTURE.md#safety-requirements) | The SR grid in § 9 |
| An error code in [`docs/codes/`](../docs/codes/) | The code table in the § 3 dashboard |
| The dashboard markup in [`firmware/src/saw_net.cpp`](../firmware/src/saw_net.cpp) | The § 3 mockup — it mirrors the real layout, classes and palette |
| A sheet in [`hardware/schematic/`](../hardware/schematic/) | Re-inline it — see below |
| A photograph in [`hardware/photos/`](../hardware/photos/) | Re-inline it — see below |

The date in the title block and the footer is the build log's own "last updated", not the
date the page was edited.

## Re-inlining a photograph

```bash
python3 - <<'PY'
import base64, pathlib, re
html = pathlib.Path("site/index.html")
src  = pathlib.Path("hardware/photos/2026-08-23-starter-enclosure.jpg")
b64  = base64.b64encode(src.read_bytes()).decode()
text = html.read_text()
text = re.sub(r'(\.photo-starter \{ background-image: url\(")[^"]*("\); \})',
              lambda m: m.group(1) + "data:image/jpeg;base64," + b64 + m.group(2), text)
html.write_text(text)
PY
```

The two `.photo-*` rules live in a second `<style>` block at the very end of the file,
kept apart from the stylesheet so the base64 does not sit in the middle of the CSS. Each
rule's `aspect-ratio` is the source image's pixel dimensions — change one and change the
other, or the photograph gets cropped.

## Re-inlining a schematic

The four sheets are inlined as live SVG rather than `<img>`, so CSS can size them. Because
they share one document, every `id` is namespaced on the way in — `s1-` for the ladder,
`s2-` supervisor, `s3-` pictorial, `s4-` mains — and every `xlink:href` is rewritten to
match. Skip that step and the four sets of `dvisvgm` glyph ids collide, and the sheets
render each other's lettering.

The build steps, in order, for one sheet:

1. Read the file and slice from the first `<svg` — this drops the XML declaration and the
   `dvisvgm` comment, which cannot appear mid-document.
2. `re.sub` `id='X'` to `id='sN-X'`, then `xlink:href='#X'` to `xlink:href='#sN-X'`.
3. Strip the root `width` and `height` attributes so `.sheet-frame svg` sizes it.

Sheets sit in `.sheet-frame`, which paints a **fixed white ground in both themes**. That is
deliberate: these are colour-coded engineering drawings, and inverting them for dark mode
would recolour the meaning — the red conductors on the mains one-line would come back cyan.

The authored diagrams — figures 1, 4 and 5, hand-written inline SVG — are the opposite
case. They carry literal hues as a light-theme fallback, and `.fig-svg [fill="..."]` rules
remap those to theme tokens, so the accent never sinks into a dark background. CSS beats
SVG presentation attributes, which is what makes that work.

## The dashboard mockup

§ 3 reproduces the real dashboard from
[`firmware/src/saw_net.cpp`](../firmware/src/saw_net.cpp) — its markup, its class names and
its palette, scoped under `.dash` so the two stylesheets do not collide. It is deliberately
fixed-light: it depicts a screen rather than being page furniture.

The readings are illustrative, and the caption says so, because the device has never been
powered. They are nonetheless the values a Path A build would actually print — the
thresholds from `saw_config.h`, the `UNCALIBRATED` footer flag, `no frame sensor` (Path A's
trip source *is* the frame, so there is no second frame reading to difference against), and
the 749 h ring that `saw_store_retention_hours()` works out from
`SAW_LOG_RING_BYTES`. If any of those change, change the mockup.
