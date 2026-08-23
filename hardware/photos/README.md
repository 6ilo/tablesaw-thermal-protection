# Photos

As-built photographs. These exist because a drawing says what was intended and a photograph
says what is there. Build state and what each of these changed is in
[`../../BUILD-LOG.md`](../../BUILD-LOG.md); this page is captions only.

Images are downscaled to 1400 px on the long edge — enough to read a silkscreen, small
enough that the repository stays clonable over a phone hotspot in a shop.

## 2026-08-23

| Image | Shows |
|---|---|
| [`2026-08-23-starter-enclosure.jpg`](2026-08-23-starter-enclosure.jpg) | The Gould ITE `A202C` mounted in its enclosure with the line, load and bonding conductors landed and the flexible entries made up. Still to do: insulate the exposed terminations, torque to the label figure, and move the assembly to its final location. One module in the lower part of the frame carries a lit green indicator and is **not identified** in this record — see BUILD-LOG's *To confirm and record*. Still frame from the build video |
| [`2026-08-23-fob-cell-side.jpg`](2026-08-23-fob-cell-side.jpg) | `KA1`'s fob board, cell side. The coin-cell holder is the reason the harness file's "12 V A23 cell" is now marked unverified. Red and black land at the holder; a numbered pad matrix and an `R433` marking are both on the silkscreen |
| [`2026-08-23-fob-encoder-side.jpg`](2026-08-23-fob-encoder-side.jpg) | The same board, encoder side — silkscreened `CYS02-E2`. Two button positions, each with a pair of conductors taken off it (green/orange and blue/yellow), plus the encoder IC and the indicator LED |
| [`2026-08-23-fob-pigtail-esp32-topside.jpg`](2026-08-23-fob-pigtail-esp32-topside.jpg) | The pigtailed fob beside the ESP32 (`U1`), board top — USB-C connector, the ESP32 module, and both header rows |
| [`2026-08-23-fob-pigtail-esp32-underside.jpg`](2026-08-23-fob-pigtail-esp32-underside.jpg) | The same pair, board underside |

## Adding to this directory

Name files `YYYY-MM-DD-subject.jpg`, add a row above saying what the photo is *evidence
of*, and put the change it records in [`../../BUILD-LOG.md`](../../BUILD-LOG.md). A photo
with no caption is a photo nobody can use six months later.

Two things not to photograph into this repository: anything showing an energised terminal
being worked on, and anything that would let the wiring be reconstructed wrongly — a
partial shot of a coil rung is worse than no shot, because it looks authoritative. The
sheets in [`../schematic/`](../schematic/) are the authority for topology; these are the
authority for what is physically there.
