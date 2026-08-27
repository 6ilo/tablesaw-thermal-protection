#!/usr/bin/env python3
"""
Build hardware/parts/esp32_pins.json from Espressif's own ESP-IDF sources.

Run rarely, commit the output. Nothing at build or CI time touches the network —
tools/pinmap.py reads the committed JSON. That is deliberate: a diagram generator
that needs the internet is a diagram generator that fails on a bench.

WHY THESE SOURCES

The per-GPIO analog capability (ADC unit + channel, touch pad, RTC channel) is not
folklore to be typed in from a blog. Espressif publish it as two-column #define
tables, both directions, and they are the definition rather than a description of
it. Those headers do NOT, however, say which pins are strapping pins or which are
swallowed by the on-module flash, and pretending otherwise would put a confident
wrong answer on a bench sheet. Those two facts come from the GPIO doc source in
the same tree, and are cross-checked below.

WHY A PINNED REF, NOT master

`touch_sensor_channel.h` was MOVED out of components/soc on master --- it now lives
under components/esp_hal_touch_sens --- so a build pinned to master silently loses
every touch tag the day that lands in a release. Pinning is not caution, it is the
difference between a sheet that says TOUCH0 and one that quietly stops.

    python3 tools/ingest_esp32_pins.py            # fetch, parse, write, verify
    python3 tools/ingest_esp32_pins.py --check    # verify the committed file only
"""

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "hardware" / "parts" / "esp32_pins.json"

IDF_REF = "release/v5.5"
RAW = f"https://raw.githubusercontent.com/espressif/esp-idf/{IDF_REF}"
SOC = f"{RAW}/components/soc/esp32/include/soc"
DOCS = f"{RAW}/docs/en/api-reference/peripherals/gpio/esp32.inc"

SOURCES = {
    "adc": f"{SOC}/adc_channel.h",
    "touch": f"{SOC}/touch_sensor_channel.h",
    "rtcio": f"{SOC}/rtc_io_channel.h",
    "caps": f"{SOC}/soc_caps.h",
    "docs": DOCS,
}

# Independently known facts, asserted against what we parse. If Espressif reword
# the doc sentences these regexes read, the run FAILS rather than silently
# emitting a sheet with no strapping warnings on it.
EXPECT_STRAPPING = {0, 2, 5, 12, 15}
EXPECT_FLASH = {6, 7, 8, 9, 10, 11, 16, 17}
EXPECT_INPUT_ONLY = {34, 35, 36, 37, 38, 39}
EXPECT_ABSENT = {24, 28, 29, 30, 31}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "tablesaw-pinmap"})
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status != 200:
            raise SystemExit(f"ingest: {url} returned HTTP {r.status}")
        return r.read().decode("utf-8", "replace")


def parse(texts):
    """Every fact below is a parse of a real line, not a literal typed in here."""
    pins = {}

    def slot(g):
        return pins.setdefault(g, {"gpio": g, "tags": [], "adc": None, "touch": None,
                                   "rtc": None, "input_only": False,
                                   "strapping": False, "flash_reserved": False})

    # ADC — "#define ADC1_GPIO34_CHANNEL 6"
    for unit, gpio, ch in re.findall(r"#define\s+ADC(\d)_GPIO(\d+)_CHANNEL\s+(\d+)", texts["adc"]):
        p = slot(int(gpio))
        p["adc"] = {"unit": int(unit), "channel": int(ch)}
        p["tags"].append(f"ADC{unit}_CH{ch}")

    # Touch — "#define TOUCH_PAD_GPIO4_CHANNEL 0"
    for gpio, ch in re.findall(r"#define\s+TOUCH_PAD_GPIO(\d+)_CHANNEL\s+(\d+)", texts["touch"]):
        p = slot(int(gpio))
        p["touch"] = int(ch)
        p["tags"].append(f"TOUCH{ch}")

    # RTC — "#define RTCIO_GPIO36_CHANNEL 0"
    for gpio, ch in re.findall(r"#define\s+RTCIO_GPIO(\d+)_CHANNEL\s+(\d+)", texts["rtcio"]):
        p = slot(int(gpio))
        p["rtc"] = int(ch)
        p["tags"].append(f"RTC_GPIO{ch}")

    # Pin count and the two validity masks.
    caps = texts["caps"]
    m = re.search(r"#define\s+SOC_GPIO_PIN_COUNT\s+(\d+)", caps)
    count = int(m.group(1)) if m else 40
    # The masks are written as BIT lists rather than literals, so read the BITs out.
    # Line-scoped on purpose. The OUTPUT mask is defined in terms of the VALID mask
    # and sits on the very next line, so anything that can run past a newline reads
    # BIT34-39 into the "absent" set and quietly deletes six real pins.
    def mask_bits(name):
        m = re.search(rf"^#define\s+{name}\b[^\n]*", caps, re.M)
        return set(int(b) for b in re.findall(r"BIT(\d+)", m.group(0))) if m else set()

    absent = mask_bits("SOC_GPIO_VALID_GPIO_MASK")
    input_only = mask_bits("SOC_GPIO_VALID_OUTPUT_GPIO_MASK")

    # Strapping and flash-reserved: prose in the GPIO doc source, because they are
    # not in any header. Parsed, then asserted, so a reword breaks the build.
    doc = texts["docs"]
    strap = set()
    ms = re.search(r"Strapping pin:\s*(.+?)\s+are strapping pins", doc, re.S)
    if ms:
        strap = set(int(g) for g in re.findall(r"GPIO(\d+)", ms.group(1)))
    flash = set()
    mf = re.search(r"SPI0/1:\s*GPIO(\d+)-(\d+)\s+and\s+GPIO(\d+)-(\d+)", doc)
    if mf:
        a, b, c, d = (int(x) for x in mf.groups())
        flash = set(range(a, b + 1)) | set(range(c, d + 1))

    for g in range(count):
        if g in absent:
            continue
        p = slot(g)
        if g in input_only:
            p["input_only"] = True
            p["tags"].append("INPUT ONLY")
        if g in strap:
            p["strapping"] = True
            p["tags"].append("STRAPPING")
        if g in flash:
            p["flash_reserved"] = True
            p["tags"].append("FLASH")

    return count, absent, input_only, strap, flash, pins


def verify(absent, input_only, strap, flash):
    """Cross-check the parse against independently known facts. Loud, not silent."""
    problems = []
    for name, got, want in (
        ("absent", absent, EXPECT_ABSENT),
        ("input-only", input_only, EXPECT_INPUT_ONLY),
        ("strapping", strap, EXPECT_STRAPPING),
        ("flash-reserved", flash, EXPECT_FLASH),
    ):
        if got != want:
            problems.append(f"  {name}: parsed {sorted(got)}, expected {sorted(want)}")
    if problems:
        raise SystemExit(
            "ingest: parsed capability does not match known ESP32 facts.\n"
            + "\n".join(problems)
            + "\n\nEspressif have probably reworded a source. Fix the parser rather "
              "than the expectation, then re-check against the datasheet."
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="validate the committed JSON without fetching")
    args = ap.parse_args()

    if args.check:
        if not OUT.exists():
            raise SystemExit(f"ingest: {OUT.relative_to(REPO)} is missing — run without --check")
        d = json.loads(OUT.read_text())
        pins = {int(k): v for k, v in d["pins"].items()}
        verify(set(range(40)) - set(pins),
               {g for g, p in pins.items() if p["input_only"]},
               {g for g, p in pins.items() if p["strapping"]},
               {g for g, p in pins.items() if p["flash_reserved"]})
        print(f"OK — {len(pins)} GPIOs, source ESP-IDF {d['source']['ref']}")
        return 0

    texts = {}
    for k, url in SOURCES.items():
        texts[k] = fetch(url)
        print(f"  fetched {k:6s} {len(texts[k]):>7,} bytes")

    count, absent, input_only, strap, flash, pins = parse(texts)
    verify(absent, input_only, strap, flash)

    doc = {
        "source": {
            "project": "Espressif ESP-IDF",
            "ref": IDF_REF,
            "urls": SOURCES,
            "licence": "Apache-2.0",
            "note": "Pinned to a release ref on purpose: touch_sensor_channel.h moved "
                    "out of components/soc on master, so master silently loses touch tags.",
        },
        "chip": {"name": "ESP32", "pin_count": count,
                 "absent": sorted(absent)},
        "pins": {str(g): p for g, p in sorted(pins.items())},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1) + "\n")

    tagged = sum(1 for p in pins.values() if p["tags"])
    print(f"\nwrote {OUT.relative_to(REPO)}")
    print(f"OK — {len(pins)} GPIOs, {tagged} carry tags; "
          f"ADC {sum(1 for p in pins.values() if p['adc'])}, "
          f"touch {sum(1 for p in pins.values() if p['touch'] is not None)}, "
          f"rtc {sum(1 for p in pins.values() if p['rtc'] is not None)}")
    print(f"     GPIO34 -> {', '.join(pins[34]['tags'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
