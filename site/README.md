# Personal-site project page

[`index.html`](index.html) is a **project write-up for a personal website** — a single
self-contained page describing this retrofit for a general reader. It is not part of the
build, not an operator document, and nothing on the saw serves it.

Drop it on any static host. There are no relative asset paths: the two as-built
photographs are inlined as data URIs and the three typefaces come from Google Fonts, so
the file works from a `file://` URL, a subdirectory, or a bare S3 bucket without editing.

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
| A threshold in [ARCHITECTURE.md § Thresholds](../ARCHITECTURE.md#thresholds-defaults-configurable) | The temperature scale in § 5 |
| The build state in [BUILD-LOG.md](../BUILD-LOG.md) | The ledger and the photo captions in § 8, the open items in § 9, and the status line in the title block |
| A safety requirement in [ARCHITECTURE.md § Safety requirements](../ARCHITECTURE.md#safety-requirements) | The SR grid in § 7 |
| An error code in [`docs/codes/`](../docs/codes/) | The code table in § 6 |
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
