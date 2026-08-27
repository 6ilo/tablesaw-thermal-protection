#!/usr/bin/env python3
"""
Pictorial wiring diagrams from a netlist. The breadboard-view idiom — recognisable
component pictures with wires between them — generated rather than dragged.

WHAT MAKES THIS DIFFERENT FROM A GUI CIRCUIT EDITOR

Fritzing and Cirkit Designer are drag-and-drop: positions come from a mouse, so the
file format records coordinates. Nothing that cannot hold a mouse can author one.
Here the spec is a NETLIST — components and what connects to what — and placement
and routing are computed. That is the whole design:

  * You never type an x/y. Components declare a column, and the layout places them.
  * You never type a pin number for the ESP32. You name a firmware role and
    saw_config.h supplies the pin.
  * You never type a function tag. Espressif's headers supply those.
  * Every pin name is checked against the part library, so a typo is a build error
    rather than a wire drawn to nowhere.

A sheet is therefore ~30 lines of YAML, and a change is one line.

    python3 tools/cirkit.py parts                 # the vocabulary: parts and pins
    python3 tools/cirkit.py build                 # render every spec
    python3 tools/cirkit.py check                 # CI gate: nets resolve, SVGs current
"""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svgcanvas import Canvas, tw          # noqa: E402
import partlib                            # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SPEC_DIR = REPO / "hardware" / "circuits"
CONFIG_H = REPO / "firmware" / "include" / "saw_config.h"

INK, MUTE, RULE = "#16181D", "#6E7178", "#C7CAD1"
PAPER = "#FFFFFF"

WIRE = {
    "red": "#C0392B", "black": "#22262A", "orange": "#D98C1F", "purple": "#7A5EA8",
    "brown": "#8A5A3C", "blue": "#2E6DA4", "green": "#1E6B45", "yellow": "#D4B106",
    "white": "#B9BEC4", "grey": "#7A8087", "mains": "#B3261E",
}


def roles():
    pat = re.compile(r"^#define\s+(SAW_PIN_[A-Z0-9_]+)\s+(\d+)", re.M)
    return {m.group(1): int(m.group(2)) for m in pat.finditer(CONFIG_H.read_text())}


def resolve_endpoint(ep, comps, parts, rmap):
    """'U1.GPIO26' or 'U1.@SAW_PIN_HOLD' -> (ref, pin name). The @ form is checked
    against the firmware, so a diagram cannot name a pin the firmware moved."""
    if "." not in ep:
        raise SystemExit(f"cirkit: endpoint {ep!r} must be REF.PIN")
    ref, pin = ep.split(".", 1)
    if ref not in comps:
        raise SystemExit(f"cirkit: {ep!r} names component {ref!r}, which is not declared.\n"
                         f"        declared: {', '.join(sorted(comps))}")
    part = parts[comps[ref]["part"]]
    if pin.startswith("@"):
        role = pin[1:]
        if role not in rmap:
            raise SystemExit(f"cirkit: {ep!r} names firmware role {role!r}, not in "
                             f"{CONFIG_H.relative_to(REPO)}.\n"
                             f"        known: {', '.join(sorted(rmap))}")
        pin = f"GPIO{rmap[role]}"
    if pin not in part.pins:
        raise SystemExit(
            f"cirkit: {ep!r} — part {comps[ref]['part']!r} has no pin {pin!r}.\n"
            f"        it has: {', '.join(sorted(part.pins))}\n"
            f"        (run `python3 tools/cirkit.py parts` for the full vocabulary)")
    return ref, pin


def layout(spec, parts):
    """Columns, not coordinates. `col` is left / centre / right; order within a
    column is declaration order. Everything else is arithmetic."""
    comps = spec["components"]
    cols = {"left": [], "centre": [], "right": []}
    for ref, c in comps.items():
        col = c.get("col", "left")
        if col not in cols:
            raise SystemExit(f"cirkit: {ref}: col must be left/centre/right, got {col!r}")
        cols[col].append(ref)

    GAP_Y, COL_GAP, MARGIN, TOP = 46, 150, 48, 132
    placed, widths = {}, {}
    for name, refs in cols.items():
        widths[name] = max([parts[comps[r]["part"]].w for r in refs], default=0)

    x = MARGIN
    xs = {}
    for name in ("left", "centre", "right"):
        xs[name] = x
        if cols[name]:
            x += widths[name] + COL_GAP
    total_w = max(x - COL_GAP + MARGIN, 900)

    heights = {}
    for name, refs in cols.items():
        hs = [parts[comps[r]["part"]].h for r in refs]
        heights[name] = sum(hs) + GAP_Y * max(len(refs) - 1, 0)
    content_h = max(heights.values(), default=0)

    for name, refs in cols.items():
        y = TOP + (content_h - heights[name]) / 2
        for r in refs:
            p = parts[comps[r]["part"]]
            # centre each part within its column so wires leave from a tidy edge
            placed[r] = (xs[name] + (widths[name] - p.w) / 2, y)
            y += p.h + GAP_Y

    return placed, total_w, TOP + content_h


def route(c, a, b, colour, sw=2.6):
    """Orthogonal, with a mid-channel dogleg. Straight where it can be."""
    (x1, y1), (x2, y2) = a, b
    if abs(y1 - y2) < 1.5:
        c.line(x1, y1, x2, y2, colour, sw)
    else:
        mx = (x1 + x2) / 2
        r = min(9, abs(y2 - y1) / 2, max(abs(mx - x1), 1))
        sy = 1 if y2 > y1 else -1
        sx = 1 if x2 > x1 else -1
        c.path(
            f"M{x1:.1f} {y1:.1f} H{mx - r * sx:.1f} "
            f"Q{mx:.1f} {y1:.1f} {mx:.1f} {y1 + r * sy:.1f} "
            f"V{y2 - r * sy:.1f} Q{mx:.1f} {y2:.1f} {mx + r * sx:.1f} {y2:.1f} "
            f"H{x2:.1f}",
            colour, sw)
    for (px, py) in (a, b):
        c.circle(px, py, 3.4, colour)


def render(spec, parts, rmap):
    comps = spec["components"]
    nets = spec.get("nets", [])

    # Which board pins are in play, so the board can highlight them.
    used = set()
    for n in nets:
        for ep in (n["from"], n["to"]):
            ref, pin = ep.split(".", 1)
            if pin.startswith("@") and pin[1:] in rmap:
                pin = f"GPIO{rmap[pin[1:]]}"
            used.add(pin)
    board = partlib.Esp32DevKitC(used=used)
    parts = dict(parts)
    parts[board.id] = board

    placed, W, bottom = layout(spec, parts)
    legend_y = bottom + 66
    H = legend_y + 96

    c = Canvas(W, H)
    c.rect(0, 0, W, H, PAPER)

    c.text(40, 52, spec.get("title", "Circuit"), 26, INK, weight="700")
    if spec.get("subtitle"):
        c.text(40, 77, spec["subtitle"], 14, MUTE)
    c.line(40, 97, W - 40, 97, RULE, 1)

    # wires first so parts sit on top of their own pads
    for n in nets:
        fr, fp = resolve_endpoint(n["from"], comps, parts, rmap)
        to, tp = resolve_endpoint(n["to"], comps, parts, rmap)
        colour = WIRE.get(n.get("color", "grey"), n.get("color", "#7A8087"))
        a = parts[comps[fr]["part"]].pin_at(fp, *placed[fr])
        b = parts[comps[to]["part"]].pin_at(tp, *placed[to])
        route(c, a, b, colour, 3.2 if n.get("mains") else 2.6)
        if n.get("label"):
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            s = n["label"]
            w = tw(s, 10.5) + 12
            c.rect(mx - w / 2, my - 9, w, 17, PAPER, r=3, stroke=colour, sw=1)
            c.text(mx, my + 3.5, s, 10.5, INK, anchor="middle")

    for ref, cd in comps.items():
        p = parts[cd["part"]]
        ox, oy = placed[ref]
        p.draw(c, ox, oy)
        cap = cd.get("label") or p.title
        c.text(ox + p.w / 2, oy + p.h + 17, f"{ref}  {cap}", 12, INK,
               anchor="middle", weight="600")
        if cd.get("note"):
            c.text(ox + p.w / 2, oy + p.h + 32, cd["note"], 10.5, MUTE, anchor="middle")

    # legend of wire colours actually used
    c.line(40, legend_y - 24, W - 40, legend_y - 24, RULE, 1)
    x = 40
    seen = []
    for n in nets:
        k = n.get("color", "grey")
        if k not in seen:
            seen.append(k)
    for k in seen:
        col = WIRE.get(k, k)
        c.line(x, legend_y, x + 26, legend_y, col, 3.2)
        lbl = next((n.get("label") or k for n in nets if n.get("color") == k), k)
        c.text(x + 33, legend_y + 4, k, 11.5, INK)
        x += 33 + tw(k, 11.5) + 30

    c.text(40, H - 38,
           "Pins from firmware/include/saw_config.h; ESP32 function warnings from "
           "Espressif ESP-IDF. Discrete part art © Uri Shaked, MIT (@wokwi/elements).",
           10.5, MUTE)
    c.text(40, H - 23,
           "! strapping or flash-reserved   < input-only. "
           "DevKitC header order is transcribed by hand — check it against the board. "
           "Regenerate: python3 tools/cirkit.py build",
           10.5, MUTE)
    return c.render()


def rel(p):
    """Display path. A spec given by absolute path outside the repo is a legitimate
    thing to render (a scratch sheet), so this must not raise."""
    try:
        return p.relative_to(REPO)
    except ValueError:
        return p


def specs(one=None):
    if one:
        p = Path(one)
        return [p if p.exists() else SPEC_DIR / one]
    return sorted(SPEC_DIR.glob("*.yml")) if SPEC_DIR.exists() else []


def cmd_build(args):
    parts, rmap = partlib.load_all(), roles()
    found = specs(args.spec)
    if not found:
        raise SystemExit(f"cirkit: no specs in {SPEC_DIR.relative_to(REPO)}")
    for s in found:
        spec = yaml.safe_load(s.read_text())
        out = s.with_suffix(".svg")
        out.write_text(render(spec, parts, rmap))
        print(f"  {rel(out)}  "
              f"({len(spec['components'])} parts, {len(spec.get('nets', []))} nets)")
    print(f"OK — {len(found)} sheet(s)")


def cmd_check(args):
    parts, rmap = partlib.load_all(), roles()
    stale = []
    for s in specs(None):
        spec = yaml.safe_load(s.read_text())
        want = render(spec, parts, rmap)      # raises on any unresolvable endpoint
        out = s.with_suffix(".svg")
        if not out.exists() or out.read_text() != want:
            stale.append(rel(out))
    if stale:
        print("cirkit: these sheets are stale:", file=sys.stderr)
        for p in stale:
            print(f"  {p}", file=sys.stderr)
        print("run: python3 tools/cirkit.py build", file=sys.stderr)
        return 1
    print("OK — every circuit sheet matches its spec, the part library and saw_config.h")
    return 0


def cmd_parts(args):
    d = partlib.describe()
    if args.json:
        print(json.dumps(d, indent=1))
        return 0
    for p in d:
        print(f"\n{p['id']}  [{p['origin']}]  {p['title']}  "
              f"{p['size'][0]:.0f}x{p['size'][1]:.0f}")
        for pin in p["pins"]:
            print(f"    {pin['name']:<12} {pin['description']}")
    print(f"\n{len(d)} parts. Endpoints are REF.PIN; on the board you may also write "
          f"REF.@SAW_PIN_HOLD to let saw_config.h supply the number.")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("spec", nargs="?")
    sub.add_parser("check")
    pp = sub.add_parser("parts"); pp.add_argument("--json", action="store_true")
    args = ap.parse_args()
    fn = {"build": cmd_build, "check": cmd_check, "parts": cmd_parts}[args.cmd]
    sys.exit(fn(args) or 0)


if __name__ == "__main__":
    main()
