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


def _overlaps(r, others, pad=3):
    ax0, ay0, ax1, ay1 = r
    for bx0, by0, bx1, by1 in others:
        if ax0 < bx1 + pad and bx0 < ax1 + pad and ay0 < by1 + pad and by0 < ay1 + pad:
            return True
    return False


def place_label(c, a, b, colour, s, obstacles, bounds, size=10.5):
    """Put a net label on its wire's first horizontal run, clear of everything.

    The old rule was "draw it at the midpoint of the straight line between the two
    pins", which is not a place the wire necessarily goes and not a place anything
    else necessarily is not: on this sheet it put "USB-C" across a bundle of four
    other conductors and "divider junction" over a component caption.

    A label belongs where the wire LEAVES A PIN, because that is what it names, and
    that is also the one stretch of a wire guaranteed to be a clean horizontal run.
    Candidates are tried nearest-first and the first clear one wins; if the wire's
    own side is full the far side is tried, then vertical offsets. Everything is
    ordered, so the choice is deterministic.
    """
    (x1, y1), (x2, y2) = a, b
    w, h = tw(s, size) + 12, 17
    reach = abs(x2 - x1)

    # Candidates: a grid around each endpoint, ordered by how far they sit from the
    # pin being named, so the nearest clear spot always wins. Hand-listing offsets
    # was tried first and was too sparse — in a crowded corner every listed position
    # collided and the label fell through to the midpoint, which is the thing this
    # function exists to avoid.
    cands = []
    for (px, py), (qx, _) in ((a, b), (b, a)):
        d = 1 if qx > px else -1
        for dy in range(-108, 112, 13):
            for dx in (14, 34, 56, 84, 116):
                lx = px + d * dx - (w if d < 0 else 0)
                ly = py + dy - h / 2
                cands.append((abs(dy) + dx * 0.55, lx, ly))
    # Deterministic: sorted by distance, ties broken by the generated order.
    cands = [(lx, ly) for _, lx, ly in
             sorted((c for c in cands), key=lambda t: (round(t[0], 3), round(t[1], 2), round(t[2], 2)))]
    cands.append(((x1 + x2) / 2 - w / 2, (y1 + y2) / 2 - h / 2))

    # A candidate off the edge of the sheet is not a candidate. The widening search
    # will happily walk a label past the right margin, where it renders half-cut and
    # looks like a rendering bug rather than a placement one.
    bx0, by0, bx1, by1 = bounds
    for lx, ly in cands:
        if lx < bx0 or ly < by0 or lx + w > bx1 or ly + h > by1:
            continue
        if not _overlaps((lx, ly, lx + w, ly + h), obstacles):
            break
    else:
        lx, ly = cands[-1]                    # nothing fits; the midpoint it is
    obstacles.append((lx, ly, lx + w, ly + h))
    c.rect(lx, ly, w, h, PAPER, r=3, stroke=colour, sw=1)
    c.text(lx + w / 2, ly + 12.5, s, size, INK, anchor="middle")


def render(spec, parts, rmap):
    comps = spec["components"]
    nets = spec.get("nets", [])

    # Which BOARD pins are in play, so the board can highlight them.
    #
    # Scoped to endpoints that actually land on the board. Collecting every pin
    # name from every net highlighted any header pin that happened to share a name
    # with a pin on another part — the charger's "5V" lit up the board's 5V header,
    # which nothing in this circuit connects to. A highlight that marks an unused
    # pin is worse than no highlight, because it is read as "wire here".
    board_refs = {r for r, cd in comps.items() if cd["part"] == "esp32-devkitc-38"}
    used = set()
    for n in nets:
        for ep in (n["from"], n["to"]):
            ref, pin = ep.split(".", 1)
            if ref not in board_refs:
                continue
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

    # Wires, then parts, then labels. The order matters: labels used to be drawn
    # with the wires and were painted over by any part that followed, so the fix
    # for "you cannot read it" could not simply be "move it somewhere clearer".
    pending = []
    for n in nets:
        fr, fp = resolve_endpoint(n["from"], comps, parts, rmap)
        to, tp = resolve_endpoint(n["to"], comps, parts, rmap)
        colour = WIRE.get(n.get("color", "grey"), n.get("color", "#7A8087"))
        a = parts[comps[fr]["part"]].pin_at(fp, *placed[fr])
        b = parts[comps[to]["part"]].pin_at(tp, *placed[to])
        route(c, a, b, colour, 3.2 if n.get("mains") else 2.6)
        if n.get("label"):
            pending.append((a, b, colour, n["label"]))

    obstacles = []
    for ref, cd in comps.items():
        p = parts[cd["part"]]
        ox, oy = placed[ref]
        p.draw(c, ox, oy)
        cap = cd.get("label") or p.title
        c.text(ox + p.w / 2, oy + p.h + 17, f"{ref}  {cap}", 12, INK,
               anchor="middle", weight="600")
        if cd.get("note"):
            c.text(ox + p.w / 2, oy + p.h + 32, cd["note"], 10.5, MUTE, anchor="middle")
        # The art plus its caption lines. The box must be as wide as the TEXT, not
        # as wide as the part: a note like "no shared ground with the fob — that is
        # the point" is three times the width of the optocoupler it sits under, and
        # measuring the part instead let a label land squarely on it.
        cap_w = tw(f"{ref}  {cap}", 12)
        note_w = tw(cd["note"], 10.5) if cd.get("note") else 0
        span = max(p.w, cap_w, note_w)
        cx = ox + p.w / 2
        obstacles.append((cx - span / 2, oy, cx + span / 2,
                          oy + p.h + (36 if cd.get("note") else 22)))

    label_bounds = (40, 108, W - 40, bottom + 30)
    for a, b, colour, s in pending:
        place_label(c, a, b, colour, s, obstacles, label_bounds)

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
    # The catalogue has no spec of its own, so `check` cannot notice it going stale.
    # Building it here puts it under CI's re-render-must-produce-no-diff step, which
    # is the only thing that would catch a part changing shape without it updating.
    if not args.spec:
        cmd_catalogue(args)
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


# The palette local parts may draw from. Shared with hardware/parts/local/README.md
# and with the brief the parts were drawn to. An off-palette colour is not a crime,
# but a library where every part invents its own greys stops looking like one library.
PALETTE = {
    "#2A2E33", "#D8DCE0", "#1E5E3A", "#9AA0A6", "#B0B6BC", "#C08A4A",
    "#B3261E", "#15607A", "#1E6B45", "#16181D", "#6E7178", "#FFFFFF",
    "#E4E6E2", "#C7CAD1", "#3A3F45", "#D4B106", "#8A6716",
}


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def palette_distance(c):
    """Distance from the nearest allowed colour.

    Identity was the wrong test. The brief that produced these parts asked for the
    fob pigtail in its REAL conductor colours, and shading a moulded body is normal
    draughtsmanship — so an exact-match palette flags correct art and teaches people
    to ignore the linter. What matters is that nothing wanders to a foreign hue.
    """
    allowed = PALETTE | {v.upper() for v in WIRE.values()}
    r, g, b = _rgb(c.upper())
    return min(((r - x) ** 2 + (g - y) ** 2 + (b - z) ** 2) ** 0.5
               for x, y, z in (_rgb(a) for a in allowed))


def _lum(hexc):
    """WCAG relative luminance."""
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hexc[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(fg, bg):
    a, b = _lum(fg), _lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def _bg_behind(shapes, upto, x, y):
    """Fill of the last filled shape painted before `upto` that covers (x, y).

    Paint order is declaration order, so the nearest enclosing earlier shape is
    what a reader actually sees behind the text. Falls back to paper.
    """
    bg = "#FFFFFF"
    for sh in shapes[:upto]:
        f = sh.get("fill")
        if not f or f == "none" or not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(f)):
            continue
        if sh.get("t") == "rect":
            if sh["x"] <= x <= sh["x"] + sh["w"] and sh["y"] - 10 <= y <= sh["y"] + sh["h"]:
                bg = f
        elif sh.get("t") == "circle":
            if (x - sh["cx"]) ** 2 + (y - sh["cy"]) ** 2 <= sh["r"] ** 2:
                bg = f
        elif sh.get("t") == "path":
            # Crude bbox from the numbers in `d`. Parts draw moulded bodies as
            # filled paths — the TO-92 half-cylinder is one — and ignoring those
            # made every marking on them look like text floating on white paper.
            nums = [float(n) for n in re.findall(r"-?\d+\.?\d*", sh["d"])]
            pts = list(zip(nums[0::2], nums[1::2]))
            if pts:
                xs, ys = [q[0] for q in pts], [q[1] for q in pts]
                if min(xs) <= x <= max(xs) and min(ys) - 10 <= y <= max(ys):
                    bg = f
    return bg


SHAPE_FIELDS = {
    "rect": {"x", "y", "w", "h"},
    "circle": {"cx", "cy", "r"},
    "line": {"x1", "y1", "x2", "y2"},
    "path": {"d"},
    "text": {"x", "y", "s"},
}


def cmd_lint(args):
    """Mechanical checks on the part library.

    These are geometry facts, so they are arithmetic rather than judgement: a pin
    that sits inside a body is a wire that vanishes under a component, and no
    amount of reading the JSON catches it as reliably as computing it.
    """
    import partlib as pl
    problems = []
    for pid, part in sorted(pl.load_all().items()):
        if not isinstance(part, pl.LocalPart):
            continue                      # imported and procedural parts are not ours to lint

        for sh in part.shapes:
            t = sh.get("t")
            if t not in SHAPE_FIELDS:
                problems.append(f"{pid}: unknown shape type {t!r}")
                continue
            missing = SHAPE_FIELDS[t] - set(sh)
            if missing:
                problems.append(f"{pid}: {t} missing {sorted(missing)}")
            for k, v in sh.items():
                if k in ("fill", "stroke") and v not in ("none", None):
                    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(v)):
                        problems.append(f"{pid}: {t}.{k}={v!r} is not #RRGGBB")
                    elif palette_distance(str(v)) > 70:
                        problems.append(
                            f"{pid}: {t}.{k}={v} is off-palette "
                            f"({palette_distance(str(v)):.0f} from the nearest allowed colour)")

        # Text contrast. A part's markings are what tell somebody which leg a wire
        # lands on, so they are held to the WCAG 4.5:1 floor against whatever is
        # actually painted behind them.
        for i, sh in enumerate(part.shapes):
            if sh.get("t") != "text":
                continue
            fg = str(sh.get("fill", "#16181D"))
            if not re.fullmatch(r"#[0-9A-Fa-f]{6}", fg):
                continue
            bg = _bg_behind(part.shapes, i, sh["x"], sh["y"])
            ratio = contrast(fg.upper(), bg.upper())
            if ratio < 4.5:
                problems.append(
                    f"{pid}: text {sh['s']!r} is {fg} on {bg} — {ratio:.2f}:1, "
                    f"below the 4.5:1 floor")

        # A pin must be reachable: near an edge, not stranded in the middle of the
        # art, or a wire routed to it runs underneath the component.
        #
        # The tolerance is deliberately loose. The bounding box includes the part's
        # LEADS, so a pin legitimately terminates a few pixels inside it — the
        # optocoupler's legs stop 8 px in from a 120 px box, and the probe's JST
        # contacts 4 px in from 180 px. Both are on the edge in every sense that
        # matters. A tight tolerance flags those and teaches everyone to ignore the
        # linter, which is worse than not having one. What this must catch is a pin
        # at the CENTRE of a part, and it still does.
        TOL = max(10.0, 0.08 * min(part.w, part.h))
        for name, pin in part.pins.items():
            x, y, w, h = pin["x"], pin["y"], part.w, part.h
            inside = (TOL < x < w - TOL) and (TOL < y < h - TOL)
            if inside:
                problems.append(
                    f"{pid}: pin {name!r} at ({x:.0f},{y:.0f}) is inside the "
                    f"{w:.0f}x{h:.0f} body — a wire to it would run under the part")
            if not (-TOL <= x <= w + TOL and -TOL <= y <= h + TOL):
                problems.append(
                    f"{pid}: pin {name!r} at ({x:.0f},{y:.0f}) is outside the "
                    f"{w:.0f}x{h:.0f} bounding box")
            if not pin.get("description"):
                problems.append(f"{pid}: pin {name!r} has no description")

    if problems:
        print(f"cirkit lint: {len(problems)} problem(s)", file=sys.stderr)
        for pr in problems:
            print(f"  {pr}", file=sys.stderr)
        return 1
    n = sum(1 for p in pl.load_all().values() if isinstance(p, pl.LocalPart))
    print(f"OK — {n} local parts: every pin reachable, every shape well formed")
    return 0


def cmd_catalogue(args):
    """Render every part on one sheet, with its pins marked.

    `parts` prints the vocabulary; this shows it. Two things are only visible in a
    picture: whether a part is recognisable as the real component, which no
    mechanical check can express, and whether its pins are where its art implies —
    a coordinate can pass the linter by sitting on the bounding box and still be at
    the wrong end of the part.
    """
    import partlib as pl
    parts = pl.load_all()
    order = sorted(parts.items(), key=lambda kv: (kv[1].w * kv[1].h))
    COLS, CELL_W, PAD, TOP = 4, 250, 30, 120
    rows = (len(order) + COLS - 1) // COLS

    # rows size to their tallest part rather than to a constant
    heights, grid = [], []
    for r in range(rows):
        chunk = order[r * COLS:(r + 1) * COLS]
        grid.append(chunk)
        heights.append(max(p.h for _, p in chunk) + 86)

    W = PAD * 2 + COLS * CELL_W
    H = TOP + sum(heights) + 40
    c = Canvas(W, H)
    c.rect(0, 0, W, H, PAPER)
    c.text(PAD, 52, "Part library", 26, INK, weight="700")
    c.text(PAD, 77, f"{len(order)} parts — imported art, local drawings and the board, "
                    f"all in one pin format", 14, MUTE)
    c.line(PAD, 97, W - PAD, 97, RULE, 1)

    y = TOP
    for r, chunk in enumerate(grid):
        for i, (pid, part) in enumerate(chunk):
            x = PAD + i * CELL_W + (CELL_W - part.w) / 2
            part.draw(c, x, y)
            # Name every pin on a small part; on a dense one the names collide into
            # noise and the dots alone carry what this sheet is for — showing that a
            # pin sits where the art implies. The board's own silkscreen names it.
            label_pins = len(part.pins) <= 12
            for name, pin in part.pins.items():
                px, py = x + pin["x"], y + pin["y"]
                c.circle(px, py, 3 if label_pins else 2, "#B3261E")
                if label_pins:
                    c.text(px, py - 6, name, 7, "#B3261E", anchor="middle", mono=True)
            origin = ("wokwi" if isinstance(part, pl.ImportedPart)
                      else "board" if isinstance(part, pl.Esp32DevKitC) else "local")
            base = y + max(p.h for _, p in chunk)
            c.text(PAD + i * CELL_W + CELL_W / 2, base + 26, pid, 11.5, INK,
                   anchor="middle", weight="600", mono=True)
            c.text(PAD + i * CELL_W + CELL_W / 2, base + 42,
                   f"{origin} · {len(part.pins)} pins", 10, MUTE, anchor="middle")
        y += heights[r]

    out = SPEC_DIR / "_catalogue.svg"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(c.render())
    print(f"  {rel(out)}  ({len(order)} parts)")
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
    sub.add_parser("lint", help="mechanical geometry checks on local parts")
    sub.add_parser("catalogue", help="render every part on one sheet, pins marked")
    pp = sub.add_parser("parts"); pp.add_argument("--json", action="store_true")
    args = ap.parse_args()
    fn = {"build": cmd_build, "check": cmd_check, "parts": cmd_parts,
          "lint": cmd_lint, "catalogue": cmd_catalogue}[args.cmd]
    sys.exit(fn(args) or 0)


if __name__ == "__main__":
    main()
