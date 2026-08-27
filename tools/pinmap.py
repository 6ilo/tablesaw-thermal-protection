#!/usr/bin/env python3
"""
Pinout-card diagrams: a short YAML spec in, an SVG out.

Why this exists, given the repository already renders diagrams two other ways:

  * CircuiTikZ (hardware/schematic/*.tex) draws IEC/IEEE schematics. It needs a
    LaTeX install, and its output is symbol-level — correct for an electrician
    auditing the coil rung, wrong for someone at a bench asking "which header
    pin does the purple wire go on".
  * WireViz (hardware/harness/*.yml) draws connector-and-cable harnesses through
    Graphviz. Also right for its job, also not a pinout card.

This is the third picture: the board in the middle, every used pin flanking it as
a colour-coded chip, and what each one connects to written beside it.

THE POINT IS THE PIN NUMBERS ARE NOT IN THE SPEC.

A row names a *role* — `SAW_PIN_NTC` — and the number is read out of
firmware/include/saw_config.h at render time. So a diagram cannot quietly
disagree with the firmware about which pin does what. That is not hypothetical:
hardware/README.md § "Where the sheets are behind the build" records two
CircuiTikZ sheets that still state there is no ack button, months after
SAW_HAS_ACK_BUTTON began defaulting to 1. A generated sheet cannot drift,
because the drift is a build error instead of a picture nobody re-read.

    python3 tools/pinmap.py build                 # render every spec
    python3 tools/pinmap.py build <spec.yml>      # render one
    python3 tools/pinmap.py check                 # CI gate: roles resolve, SVGs current

Pure standard library plus PyYAML, which tools/requirements.txt already carries.
No svgwrite, no cairo, nothing that needs a compiler — the same constraint that
keeps codedocs.py installable anywhere Python is.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svgcanvas import Canvas, tw          # noqa: E402

REPO = Path(__file__).resolve().parent.parent
CONFIG_H = REPO / "firmware" / "include" / "saw_config.h"
SPEC_DIR = REPO / "hardware" / "pinmaps"
PIN_DB = REPO / "hardware" / "parts" / "esp32_pins.json"

# Shared with hardware/schematic/tsstyle.tex so a generated card sits beside the
# CircuiTikZ sheets without looking like it came from somewhere else.
INK = "#16181D"
MUTE = "#6E7178"
RULE = "#C7CAD1"
PANEL = "#F5F6F7"

CLASSES = {
    "power":   ("#B3261E", "supply"),
    "gnd":     ("#16181D", "ground / common"),
    "analog":  ("#15607A", "analog in (ADC1)"),
    "control": ("#1E6B45", "protection output"),
    "input":   ("#5B4B8A", "digital in"),
    "comms":   ("#6E7178", "bus / comms"),
    "unused":  ("#C7CAD1", "not used on this build"),
}



def role_map(path=CONFIG_H):
    """{'SAW_PIN_NTC': 34, ...} straight out of the firmware header."""
    if not path.exists():
        raise SystemExit(f"pinmap: cannot read {path}")
    pat = re.compile(r"^#define\s+(SAW_PIN_[A-Z0-9_]+)\s+(\d+)", re.M)
    return {m.group(1): int(m.group(2)) for m in pat.finditer(path.read_text())}


def capability(path=PIN_DB):
    """Per-GPIO function tags, from Espressif's own headers via ingest_esp32_pins.py.

    Absent is not fatal: the sheet renders without tags rather than refusing to
    draw. A missing database should not stop somebody printing a wiring card.
    """
    if not path.exists():
        return {}
    d = json.loads(path.read_text())
    return {int(k): v for k, v in d["pins"].items()}


# Capability tags are neutral facts; these three are warnings, and colouring them
# the same as ADC1_CH6 would bury the one that can cost somebody an afternoon.
TAG_WARN = {"INPUT ONLY": "#B3261E", "STRAPPING": "#8A6716", "FLASH": "#8A6716"}


def resolve(row, roles):
    """A row carries `role` (preferred, checked) or a literal `pin` (rails only)."""
    if "role" in row:
        role = row["role"]
        if role not in roles:
            raise SystemExit(
                f"pinmap: {role!r} is not defined in {CONFIG_H.relative_to(REPO)}.\n"
                f"        known roles: {', '.join(sorted(roles))}"
            )
        return f"GPIO{roles[role]}", role
    if "pin" in row:
        return str(row["pin"]), None
    raise SystemExit(f"pinmap: row needs a `role` or a `pin`: {row!r}")


def render(spec, roles):
    left = [r for r in spec["pins"] if r.get("side", "left") == "left"]
    right = [r for r in spec["pins"] if r.get("side") == "right"]

    PITCH, PILL_H = 58, 30
    TOP = 132
    # The board sizes to its own caption. A fixed width silently ran the
    # sub-line out under the right-hand pills the moment a board name grew.
    board = spec.get("board", {})
    BOARD_W = max(190,
                  tw(board.get("name", ""), 14.5) + 36,
                  tw(board.get("sub", ""), 11.5, mono=True) + 36)
    GAP = 34            # board edge to pill
    W = 1180

    rows = max(len(left), len(right))
    board_h = max(rows * PITCH + 40, 260)
    used = sorted({r.get("class", "unused") for r in spec["pins"]},
                  key=lambda c: list(CLASSES).index(c) if c in CLASSES else 99)
    legend_y = TOP + board_h + 74
    H = legend_y + 88

    bx = (W - BOARD_W) / 2
    c = Canvas(W, H)

    c.rect(0, 0, W, H, "#FFFFFF")

    # --- title block -----------------------------------------------------
    c.text(40, 52, spec.get("title", "Pinout"), 27, INK, weight="700")
    if spec.get("subtitle"):
        c.text(40, 78, spec["subtitle"], 14.5, MUTE)
    c.line(40, 98, W - 40, 98, RULE, 1)

    # --- the board --------------------------------------------------------
    c.rect(bx, TOP, BOARD_W, board_h, INK, r=9)
    # the module can, plus a token antenna so the orientation reads at a glance
    can_w, can_h = BOARD_W - 46, 62
    c.rect(bx + 23, TOP + 16, can_w, can_h, "#3A3F45", r=4)
    c.text(bx + BOARD_W / 2, TOP + 52, "WROOM-32E", 11, "#AAB0B6",
           anchor="middle", mono=True)
    ax = bx + BOARD_W / 2
    c.add(f'<path d="M{ax-26:.1f} {TOP+90} l9 -12 l9 12 l9 -12 l9 12" '
          f'fill="none" stroke="#5A6067" stroke-width="2.5"/>')

    c.text(bx + BOARD_W / 2, TOP + board_h - 46, board.get("name", ""), 14.5,
           "#FFFFFF", anchor="middle", weight="700")
    c.text(bx + BOARD_W / 2, TOP + board_h - 27, board.get("sub", ""), 11.5,
           "#9BA2A8", anchor="middle", mono=True)
    # USB tab, so "which end is the cable" needs no caption
    c.rect(bx + BOARD_W / 2 - 24, TOP + board_h - 9, 48, 16, "#8A9096", r=3)

    # --- pin rows ---------------------------------------------------------
    caps = capability()

    def chip(x, y, text, colour, side):
        """A function tag. Returns the x to continue from, growing outward."""
        w = tw(text, 10, mono=True) + 13
        cx = x - w if side == "left" else x
        c.rect(cx, y, w, 16, "none", r=3, stroke=colour, sw=1.2)
        c.text(cx + w / 2, y + 11.5, text, 10, colour, anchor="middle", mono=True, ls=0.3)
        return (cx - 5) if side == "left" else (cx + w + 5)

    def row(r, i, side):
        pin, role = resolve(r, roles)
        cls = r.get("class", "unused")
        colour, _ = CLASSES.get(cls, CLASSES["unused"])
        y = TOP + 34 + i * PITCH
        cy = y + PILL_H / 2

        pw = max(tw(pin, 14, mono=True) + 24, 74)
        if side == "left":
            px = bx - GAP - pw
            c.line(px + pw, cy, bx, cy, colour, 2)
            c.add(f'<circle cx="{bx:.1f}" cy="{cy:.1f}" r="3.5" fill="{colour}"/>')
        else:
            px = bx + BOARD_W + GAP
            c.line(bx + BOARD_W, cy, px, cy, colour, 2)
            c.add(f'<circle cx="{bx+BOARD_W:.1f}" cy="{cy:.1f}" r="3.5" fill="{colour}"/>')

        c.rect(px, y, pw, PILL_H, colour, r=6)
        c.text(px + pw / 2, y + 20, pin, 14, "#FFFFFF", anchor="middle",
               weight="700", mono=True)

        tx = px - 14 if side == "left" else px + pw + 14
        anchor = "end" if side == "left" else "start"
        c.text(tx, y + 14, r.get("label", ""), 14.5, INK, anchor=anchor, weight="600")

        # Function tags, from the capability database rather than from the spec —
        # the spec never states them, so they cannot be stated wrongly.
        m = re.match(r"GPIO(\d+)$", pin)
        tags = caps.get(int(m.group(1)), {}).get("tags", []) if m else []
        cursor = tx
        for t in tags:
            cursor = chip(cursor, y + 20, t, TAG_WARN.get(t, MUTE), side)

        note = r.get("note")
        if note:
            c.text(tx, y + 48, note, 12, MUTE, anchor=anchor)

        # role provenance, small, under the pill — this is the honesty bit
        if role:
            c.text(px + pw / 2, y + PILL_H + 11, role.replace("SAW_PIN_", ""),
                   8.5, MUTE, anchor="middle", mono=True, ls=0.4)

    for i, r in enumerate(left):
        row(r, i, "left")
    for i, r in enumerate(right):
        row(r, i, "right")

    # --- legend -----------------------------------------------------------
    c.line(40, legend_y - 26, W - 40, legend_y - 26, RULE, 1)
    x = 40
    for cls in used:
        colour, desc = CLASSES.get(cls, CLASSES["unused"])
        c.rect(x, legend_y - 11, 15, 15, colour, r=3)
        c.text(x + 23, legend_y + 1, desc, 12.5, INK)
        x += 23 + tw(desc, 12.5) + 34

    # Two lines rather than one: a single line ran past the right margin and the
    # provenance is the last thing that should be clipped off a generated sheet.
    c.text(40, H - 36,
           "Pin numbers from firmware/include/saw_config.h. Function tags from Espressif "
           "ESP-IDF release/v5.5 via hardware/parts/esp32_pins.json.", 11, MUTE)
    c.text(40, H - 21,
           "Neither is typed into the spec, so neither can disagree with its source. "
           "Regenerate: python3 tools/pinmap.py build", 11, MUTE)

    return c.render(W, H)
def specs(one=None):
    if one:
        p = Path(one)
        return [p if p.exists() else SPEC_DIR / one]
    return sorted(SPEC_DIR.glob("*.yml"))


def build(args):
    roles = role_map()
    found = specs(args.spec)
    if not found:
        raise SystemExit(f"pinmap: no specs in {SPEC_DIR.relative_to(REPO)}")
    for s in found:
        spec = yaml.safe_load(s.read_text())
        out = s.with_suffix(".svg")
        out.write_text(render(spec, roles))
        print(f"  {out.relative_to(REPO)}  ({len(spec['pins'])} pins)")
    print(f"OK — {len(found)} sheet(s) from {len(roles)} firmware pin roles")


def check(args):
    """Roles resolve, and every committed SVG matches what the spec renders now."""
    roles = role_map()
    stale = []
    for s in specs(None):
        spec = yaml.safe_load(s.read_text())
        want = render(spec, roles)           # also raises on an unknown role
        out = s.with_suffix(".svg")
        if not out.exists() or out.read_text() != want:
            stale.append(out.relative_to(REPO))
    if stale:
        print("pinmap: these sheets are stale:", file=sys.stderr)
        for p in stale:
            print(f"  {p}", file=sys.stderr)
        print("run: python3 tools/pinmap.py build", file=sys.stderr)
        return 1
    print(f"OK — every pinmap sheet matches its spec and {CONFIG_H.name}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="render specs to SVG")
    b.add_argument("spec", nargs="?", help="one spec; default is all")
    sub.add_parser("check", help="CI gate: roles resolve and SVGs are current")
    args = ap.parse_args()
    sys.exit(check(args) if args.cmd == "check" else build(args) or 0)


if __name__ == "__main__":
    main()
