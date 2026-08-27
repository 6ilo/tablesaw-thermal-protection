# Parts database

Machine-readable inputs for the diagram generators. **Everything here is generated
and committed**, and nothing in a normal build or CI run touches the network — a
diagram tool that needs the internet is a diagram tool that fails on a bench.

| Path | What | Regenerate with |
|---|---|---|
| [`esp32_pins.json`](esp32_pins.json) | Per-GPIO capability: ADC unit + channel, touch pad, RTC channel, input-only, strapping, flash-reserved | `python3 tools/ingest_esp32_pins.py` |
| [`wokwi/`](wokwi/) | Pictorial SVG art for discrete parts, with named pin coordinates | `node tools/ingest_wokwi.mjs` |

Both ingesters are run rarely and by hand. They need the network; the generators
that consume their output do not.

## Where the pin capability comes from

[Espressif's ESP-IDF](https://github.com/espressif/esp-idf), pinned to `release/v5.5`,
Apache-2.0. The analog capability is parsed out of the vendor's own two-column
`#define` tables — `adc_channel.h`, `touch_sensor_channel.h`, `rtc_io_channel.h` —
so `GPIO34 → ADC1_CH6` is a parse of the definition rather than a fact retyped from
a tutorial.

Two things that bit during ingestion and are worth knowing before anyone edits this:

- **The ref is pinned deliberately.** `touch_sensor_channel.h` has *moved* out of
  `components/soc` on `master` (it is now under `components/esp_hal_touch_sens`), so
  a tool pointed at `master` silently loses every touch tag the day that reaches a
  release. It 404s today; `release/v5.5` serves it.
- **The headers are not the whole story.** Nothing in them marks strapping pins or
  the GPIOs swallowed by the on-module flash. Those come from the GPIO documentation
  source in the same tree, and the ingester *asserts* its parse against the known
  sets — if Espressif reword that prose, the run fails loudly rather than emitting a
  sheet with no strapping warnings on it.

## Where the component art comes from

[`@wokwi/elements`](https://github.com/wokwi/wokwi-elements) v1.9.2, **MIT**,
Copyright (c) 2020 Uri Shaked. Full text in [`wokwi/LICENSE.wokwi`](wokwi/LICENSE.wokwi).
MIT is attribution-only, so this is a clean fit for an MIT repository — which is why
it was chosen over the larger Fritzing parts library, whose art is share-alike.

Extraction renders the real components in a headless browser and serialises what
they draw, rather than parsing their source. The SVG lives in a `lit` template
literal with interpolations — a resistor computes its colour bands from its `value`
at render time — so static parsing would mean reimplementing the interpolation and
getting a *different* picture from the one the component actually produces.

**The board is deliberately not taken from Wokwi.** Their ESP32 element is a DevKit
**v1**: 30 pins, Arduino-style `D13`/`D25` names. This project uses a DevKitC-32E —
38 pins — and the firmware speaks GPIO numbers. Relabelling someone else's board art
into a board we do not own is how a drawing starts lying, so the board is ours.

## The contract

The genuinely valuable thing taken from Wokwi is not the six pictures, it is the
shape every element exposes:

```json
{ "name": "A", "x": 25, "y": 42, "signals": [], "description": "Anode" }
```

A named pin, a coordinate to route a wire to, signal semantics, and a human
description. Parts drawn by this project use the same shape, so the router cannot
tell an imported part from a local one — and anything Wokwi adds later drops in
without touching the renderer.

## What this database does not know

It is right about **capability** — which pin *can* be an ADC input. It knows nothing
about what is **fitted**. A pin tagged `ADC1_CH6` is not a pin wired to anything, and
a part present here is not a part on the bench.
[`../../BUILD-LOG.md`](../../BUILD-LOG.md) remains the only record of what physically
exists.
