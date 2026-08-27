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


def corridors(boxes, W, pad=8):
    """The vertical strips of the sheet no part occupies.

    Channels are cut from these, so a wire's vertical run is in clear space by
    construction rather than by luck. Deriving them from the part boxes means the
    board needs no special case: it is simply the widest obstacle, and wires route
    around it because there is no corridor through it.
    """
    spans = sorted((x0 - pad, x1 + pad) for x0, _, x1, _ in boxes)
    merged = []
    for lo, hi in spans:
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    gaps, cursor = [], 0.0
    for lo, hi in merged:
        if lo - cursor > 24:
            gaps.append((cursor, lo))
        cursor = max(cursor, hi)
    if W - cursor > 24:
        gaps.append((cursor, W))
    return gaps


def plan_channels(wires, boxes, W):
    """Give every dog-legged wire its own vertical track.

    Previously every wire turned at the midpoint of its own straight line. Since a
    whole column of parts sits at roughly one x, their midpoints coincided and four
    or five conductors collapsed onto one track, which is most of what made the
    sheet unreadable.

    Allocation, all deterministic:
      1. Pick the corridor with the widest overlap of the wire's x-span; ties go to
         the leftmost corridor.
      2. Within a corridor, order wires by the y they are heading TO, then by
         declaration index. Ordering by destination keeps the second horizontal legs
         from interleaving, which is where crossings actually come from.
      3. Spread the tracks evenly across the corridor's usable width.
    """
    want = {}
    for i, (a, b, *_rest) in enumerate(wires):
        if abs(a[1] - b[1]) < 1.5:
            continue                                  # straight run, no turn needed
        lo, hi = sorted((a[0], b[0]))
        best, best_overlap = None, 0
        for gi, (g0, g1) in enumerate(corridors(boxes, W)):
            ov = min(hi, g1) - max(lo, g0)
            if ov > best_overlap + 0.01:
                best, best_overlap = gi, ov
        if best is not None and best_overlap > 12:
            want.setdefault(best, []).append(i)

    gaps = corridors(boxes, W)
    chan = {}
    for gi, idxs in want.items():
        g0, g1 = gaps[gi]
        usable = max(g1 - g0 - 28, 12)
        order = sorted(idxs, key=lambda i: (round(wires[i][1][1], 2), i))
        n = len(order)
        for k, i in enumerate(order):
            frac = (k + 1) / (n + 1)
            chan[i] = g0 + 14 + usable * frac
    return chan


def bus_groups(wires, owners):
    """Endpoints shared by two or more wires of the same colour.

    Three black conductors landing on one GND pin are electrically ONE node, and
    drawing them as three independent lines that happen to converge makes them read
    as a tangle. Drawn as a trunk with a junction dot and branches, they read as
    what they are.

    Same colour is required. A junction whose trunk had to pick between a brown and
    a black conductor would be asserting something about the circuit that the
    netlist does not say, so mixed-colour convergences are left as separate wires.
    """
    from collections import defaultdict
    at = defaultdict(list)
    for i, (a, b, colour, _sw, _lab) in enumerate(wires):
        at[(round(a[0], 1), round(a[1], 1))].append((i, 0, colour))
        at[(round(b[0], 1), round(b[1], 1))].append((i, 1, colour))

    groups = {}
    for key in sorted(at):
        members = at[key]
        if len(members) < 2:
            continue
        if len({m[2] for m in members}) != 1:
            continue
        px, py = key
        # Trunk direction: away from the OWNING part, not toward the far endpoints.
        # Inferring it from the far ends put GPIO26's junction 24 px inside the
        # board, because that pin is on the board's left header while everything it
        # drives sits in the right column. Which side of its own part a pin is on is
        # the only thing that decides where its trunk can go.
        ox0, _, ox1, _ = owners[key]
        d = -1 if px < (ox0 + ox1) / 2 else 1
        groups[key] = {"pt": (px, py), "dir": d, "colour": members[0][2],
                       "members": [(i, end) for i, end, _ in members]}
    return groups


def path_segments(a, b, channel):
    """The three legs a normal dog-leg route actually draws."""
    (x1, y1), (x2, y2) = a, b
    if abs(y1 - y2) < 1.5:
        return [("h", y1, x1, x2)]
    mx = channel if channel is not None else (x1 + x2) / 2
    return [("h", y1, x1, mx), ("v", mx, y1, y2), ("h", y2, mx, x2)]


def _seg_hits(seg, box, inset=3):
    bx0, by0, bx1, by1 = box
    bx0, by0, bx1, by1 = bx0 + inset, by0 + inset, bx1 - inset, by1 - inset
    kind, fixed, p0, p1 = seg
    lo, hi = sorted((p0, p1))
    if kind == "h":
        return by0 < fixed < by1 and hi > bx0 and lo < bx1
    return bx0 < fixed < bx1 and hi > by0 and lo < by1


def blocking(segs, bx, own):
    """Is this box a real obstruction for these segments?

    One rule, used by the router to decide on a detour and by the checker to decide
    on a complaint. They must agree: a checker with a laxer rule cannot see the
    defect the router exists to prevent, which is exactly what happened when the
    checker simply skipped every part a wire terminates on — the GPIO26 conductor
    could vanish behind the whole board and be reported clean.
    """
    if not any(_seg_hits(sg, bx) for sg in segs):
        return False
    if bx not in own:
        return True                       # an unrelated part is never acceptable
    if bx[2] - bx[0] < 100:
        return False                      # lying along a small part reads fine
    span = 0.0
    for kind, fixed, p0, p1 in segs:
        if kind != "h":
            continue
        lo, hi = sorted((p0, p1))
        span = max(span, min(hi, bx[2]) - max(lo, bx[0]))
    return span >= 0.5 * (bx[2] - bx[0])


def needs_detour(a, b, channel, boxes, own=()):
    """The part a wire's ACTUAL path would run through, if any.

    An earlier version asked whether a box merely sat inside the wire's bounding
    region, which fired on wires that route cleanly past it — the 3V3 conductor was
    sent on a lap of the sheet to avoid a probe its channel already cleared by
    40 px. Testing the three legs the router really draws is both correct and
    cheaper to reason about.

    Endpoint parts are NOT exempt. A pin can sit on the far side of its own
    component from everything it connects to (GPIO26 is on the DevKitC's left
    header while the fob chain is in the right column), and that wire has to go
    around the board rather than across its face.
    """
    segs = path_segments(a, b, channel)
    worst, worst_w = None, 0
    for bx in boxes:
        if blocking(segs, bx, own) and bx[2] - bx[0] > worst_w:
            worst, worst_w = bx, bx[2] - bx[0]
    return worst


def route_around(c, a, b, colour, sw, obstacle, ca, cb, sheet_h):
    """Two channels and a transit above or below the obstacle.

    pin -> channel -> transit -> channel -> pin. The side is whichever gives the
    shorter path, so a wire to a part near the top goes over and one to a part near
    the bottom goes under.
    """
    (x1, y1), (x2, y2) = a, b
    _, by0, _, by1 = obstacle
    over, under = by0 - 22, by1 + 22
    cost_o = abs(y1 - over) + abs(y2 - over)
    cost_u = abs(y1 - under) + abs(y2 - under)
    yd = over if cost_o <= cost_u else under
    yd = min(max(yd, 108), sheet_h - 40)

    r = 8
    def h(x_from, x_to, y):
        c.line(x_from, y, x_to, y, colour, sw)
    def v(x, y_from, y_to):
        c.line(x, y_from, x, y_to, colour, sw)
    h(x1, ca, y1); v(ca, y1, yd); h(ca, cb, yd); v(cb, yd, y2); h(cb, x2, y2)
    for (px, py) in (a, b):
        c.circle(px, py, 3.4, colour)


def route(c, a, b, colour, sw=2.6, channel=None):
    """Orthogonal, with a mid-channel dogleg. Straight where it can be."""
    (x1, y1), (x2, y2) = a, b
    if abs(y1 - y2) < 1.5:
        c.line(x1, y1, x2, y2, colour, sw)
    else:
        mx = channel if channel is not None else (x1 + x2) / 2
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


def place_label(c, a, b, colour, s, hard, soft, bounds, size=10.5):
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
    inb = [(lx, ly) for lx, ly in cands
           if bx0 <= lx and by0 <= ly and lx + w <= bx1 and ly + h <= by1]

    # Two passes. Conductors are a SOFT constraint: crossing somebody else's wire is
    # untidy, but landing on a component is worse, and treating wires as hard
    # obstacles over-constrained the sheet enough to push a label onto the fob.
    # Prefer a spot clear of everything; settle for one clear of the parts.
    chosen = None
    for avoid in (hard + soft, hard):
        for lx, ly in inb:
            if not _overlaps((lx, ly, lx + w, ly + h), avoid):
                chosen = (lx, ly)
                break
        if chosen:
            break
    lx, ly = chosen or cands[-1]
    hard.append((lx, ly, lx + w, ly + h))
    c.rect(lx, ly, w, h, PAPER, r=3, stroke=colour, sw=1)
    c.text(lx + w / 2, ly + 12.5, s, size, INK, anchor="middle")


def render(spec, parts, rmap):
    comps = spec["components"]
    nets = spec.get("nets", [])

    pl = plan_sheet(spec, parts, rmap)
    parts, placed, W, bottom = pl["parts"], pl["placed"], pl["W"], pl["bottom"]
    boxes, wires, eff = pl["boxes"], pl["wires"], pl["eff"]
    chan, groups, detour = pl["chan"], pl["groups"], pl["detour"]
    legend_y = bottom + 66
    H = legend_y + 96

    c = Canvas(W, H)
    c.rect(0, 0, W, H, PAPER)

    c.text(40, 52, spec.get("title", "Circuit"), 26, INK, weight="700")
    if spec.get("subtitle"):
        c.text(40, 77, spec["subtitle"], 14, MUTE)
    c.line(40, 97, W - 40, 97, RULE, 1)

    # Trunks and junction dots first, so branches leave from a drawn node.
    for g in groups.values():
        px, py = g["pt"]
        jx = px + g["dir"] * pl["trunk"]
        c.line(px, py, jx, py, g["colour"], 3.0)
        c.circle(jx, py, 4.6, g["colour"])

    pending, wire_boxes = [], []
    for i, (a, b, colour, sw, label) in enumerate(eff):
        if i in detour:
            block, ca, cb = detour[i]
            route_around(c, a, b, colour, sw, block, ca, cb, H)
            segs = [("h", a[1], a[0], ca), ("v", ca, a[1], b[1]),
                    ("v", cb, a[1], b[1]), ("h", b[1], cb, b[0])]
        else:
            route(c, a, b, colour, sw, chan.get(i))
            segs = path_segments(a, b, chan.get(i))
        # A thin box per leg, so labels can be kept off conductors they do not name.
        legs = []
        for kind, fixed, p0, p1 in segs:
            lo, hi = sorted((p0, p1))
            legs.append((lo - 2, fixed - 3, hi + 2, fixed + 3) if kind == "h"
                        else (fixed - 3, lo - 2, fixed + 3, hi + 2))
        wire_boxes.append(legs)
        if label:
            pending.append((i, a, b, colour, label))

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
    for i, a, b, colour, s in pending:
        # Every conductor except this label's own is an obstacle. A label sitting on
        # the wire it names is legible and expected; one sitting on somebody else's
        # is the clutter being removed.
        others = [bx for j, legs in enumerate(wire_boxes) if j != i for bx in legs]
        place_label(c, a, b, colour, s, obstacles, others, label_bounds)

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


def plan_sheet(spec, parts, rmap):
    """Everything decided before a single shape is drawn.

    Shared by render() and crossings() ON PURPOSE. They diverged once already: the
    checker recomputed plain dog-leg paths while the renderer had learned to detour
    around the board and to start wires at bus junctions, so it was validating
    routes that were no longer drawn — a check that passes by looking at the wrong
    thing is worse than no check.
    """
    comps = spec["components"]
    nets = spec.get("nets", [])

    # Which BOARD pins are in play, so the board can highlight them. This lives here
    # rather than in render() because the board instance it produces is part of the
    # plan: building it without `used` in the planner silently dropped every pin
    # highlight from the sheet while every check still passed.
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

    box = {r: (placed[r][0], placed[r][1],
               placed[r][0] + parts[cd["part"]].w,
               placed[r][1] + parts[cd["part"]].h)
           for r, cd in comps.items()}
    boxes = list(box.values())

    wires, owners, own_of = [], {}, []
    for n in spec.get("nets", []):
        fr, fp = resolve_endpoint(n["from"], comps, parts, rmap)
        to, tp = resolve_endpoint(n["to"], comps, parts, rmap)
        a = parts[comps[fr]["part"]].pin_at(fp, *placed[fr])
        b = parts[comps[to]["part"]].pin_at(tp, *placed[to])
        colour = WIRE.get(n.get("color", "grey"), n.get("color", "#7A8087"))
        wires.append((a, b, colour, 3.2 if n.get("mains") else 2.6, n.get("label")))
        owners[(round(a[0], 1), round(a[1], 1))] = box[fr]
        owners[(round(b[0], 1), round(b[1], 1))] = box[to]
        own_of.append((box[fr], box[to]))

    TRUNK = 24
    groups = bus_groups(wires, owners)
    start = {}
    for g in groups.values():
        jx = g["pt"][0] + g["dir"] * TRUNK
        for i, end in g["members"]:
            start[(i, end)] = (jx, g["pt"][1])
    eff = [(start.get((i, 0), a), start.get((i, 1), b), col, sw, lab)
           for i, (a, b, col, sw, lab) in enumerate(wires)]

    chan = plan_channels(eff, boxes, W)
    gaps = corridors(boxes, W)

    def near_channel(x, avoid):
        ax0, _, ax1, _ = avoid
        best = None
        for g0, g1 in gaps:
            if g1 <= ax0 + 1 or g0 >= ax1 - 1:
                cx = (g0 + g1) / 2
                if best is None or abs(cx - x) < abs(best - x):
                    best = cx
        return best if best is not None else x

    detour = {}
    for i, (a, b, *_r) in enumerate(eff):
        blk = needs_detour(a, b, chan.get(i), boxes, own_of[i])
        if blk is not None:
            detour[i] = (blk, near_channel(a[0], blk), near_channel(b[0], blk))

    return dict(parts=parts, placed=placed, W=W, bottom=bottom, box=box, boxes=boxes,
                wires=wires, eff=eff, chan=chan, groups=groups, detour=detour,
                own_of=own_of, trunk=TRUNK)


def crossings(spec, parts, rmap):
    """Wires whose path runs under a part they do not connect to.

    Corridors make this impossible by construction today, which is exactly why it
    is worth asserting: the property is a consequence of the routing design, so a
    future change to placement or allocation could quietly lose it, and a wire that
    disappears under a component is unreadable in the one way that matters.
    """
    pl = plan_sheet(spec, parts, rmap)
    box, eff, chan, detour, own_of = (pl["box"], pl["eff"], pl["chan"],
                                      pl["detour"], pl["own_of"])
    bad = []
    for i, (a, b, *_r) in enumerate(eff):
        if i in detour:
            blk, ca, cb = detour[i]
            segs = [("h", a[1], a[0], ca), ("v", ca, a[1], b[1]),
                    ("v", cb, a[1], b[1]), ("h", b[1], cb, b[0])]
        else:
            segs = path_segments(a, b, chan.get(i))
        for r, bx in box.items():
            if blocking(segs, bx, own_of[i]):
                net = spec["nets"][i]
                bad.append(f"net {i} ({net.get('label') or net.get('color', '?')}: "
                           f"{net['from']} -> {net['to']}) runs under {r}")
    return bad


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
    stale, buried = [], []
    for s in specs(None):
        spec = yaml.safe_load(s.read_text())
        buried += crossings(spec, parts, rmap)
        want = render(spec, parts, rmap)      # raises on any unresolvable endpoint
        out = s.with_suffix(".svg")
        if not out.exists() or out.read_text() != want:
            stale.append(rel(out))
    if buried:
        print("cirkit: these wires run under a part they do not connect to:",
              file=sys.stderr)
        for b in buried:
            print(f"  {b}", file=sys.stderr)
        return 1
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
