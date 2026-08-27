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

ROUTING

Placement is columns and arithmetic; routing is a search. Each wire proposes every
route it could take — a straight run, a dog-leg through one channel, or a lap out
past the end of a part and back — and the cheapest one that is READABLE wins.
Readable is not a matter of taste here, it is two arithmetic properties:

  * no conductor runs under a component (`buried`), and
  * no conductor runs along another (`overlap_px`),

both of which are also what `check` asserts, using the same functions on the same
planned routes. The router cannot draw a route the checker would reject, because
passing the checker is how a route gets chosen.

    python3 tools/cirkit.py parts                 # the vocabulary: parts and pins
    python3 tools/cirkit.py build                 # render every spec
    python3 tools/cirkit.py check                 # CI gate: nets resolve, SVGs current
    python3 tools/cirkit.py selftest              # prove those checks can fail
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

# How close two parallel conductors may run before they stop reading as two. A
# stroke is 2.6 px wide, so this is a little over four times a stroke: enough white
# between them to be unambiguous at the size these sheets are actually read at.
NEAR = 11.0

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


def legs(pts):
    """A route as ('h'|'v', fixed, from, to) legs.

    Zero-length legs are dropped. A route whose channel lands exactly on a pin has
    one, and counting it would make the overlap arithmetic report a wire lying on
    top of itself.
    """
    out = []
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if abs(x1 - x2) < 0.05 and abs(y1 - y2) < 0.05:
            continue
        out.append(("h", y1, x1, x2) if abs(y1 - y2) < 0.05 else ("v", x1, y1, y2))
    return out


# Parts are treated as 2 px larger than they draw. A conductor run along a
# component's edge is not "clear of" it: the DevKitC's header pads sit exactly on
# its bounding box, so a wire at that x is drawn over the gold, and a rule that
# measures the box exactly calls that clean.
GIRTH = 2.0


def _seg_hits(seg, box, grow=GIRTH):
    bx0, by0, bx1, by1 = box
    bx0, by0, bx1, by1 = bx0 - grow, by0 - grow, bx1 + grow, by1 + grow
    kind, fixed, p0, p1 = seg
    lo, hi = sorted((p0, p1))
    if kind == "h":
        return by0 < fixed < by1 and hi > bx0 and lo < bx1
    return bx0 < fixed < bx1 and hi > by0 and lo < by1


def pin_edge(p, bx):
    """Which edge of its own part a pin sits on."""
    d = {"L": p[0] - bx[0], "R": bx[2] - p[0], "T": p[1] - bx[1], "B": bx[3] - p[1]}
    return min(("L", "R", "T", "B"), key=lambda k: round(d[k], 3))


def arriving(seg, bx, p, edge):
    """Is this leg the wire ARRIVING at its pin, or is it running under the part?

    A pin sits a few pixels inside its part's bounding box, because the box includes
    the leads — the optocoupler's legs stop 8 px in from a 120 px box. So the last
    few pixels of every wire are legitimately inside the component and a rule that
    forbids that forbids every route there is.

    What is never legitimate is continuing PAST the pin into the body. That is the
    difference between a wire landing on a leg and a wire disappearing under a black
    DIP package, and it is the whole test: along the pin's own edge normal, ending
    on the pin, never reaching beyond it.
    """
    kind, fixed, q0, q1 = seg
    lo, hi = sorted((q0, q1))
    if edge in ("L", "R"):
        if kind != "h" or abs(fixed - p[1]) > 0.6:
            return False
        if min(abs(q0 - p[0]), abs(q1 - p[0])) > 0.6:
            return False
        i0, i1 = max(lo, bx[0] - GIRTH), min(hi, bx[2] + GIRTH)
        return i1 <= i0 or (i1 <= p[0] + 1 if edge == "L" else i0 >= p[0] - 1)
    if kind != "v" or abs(fixed - p[0]) > 0.6:
        return False
    if min(abs(q0 - p[1]), abs(q1 - p[1])) > 0.6:
        return False
    i0, i1 = max(lo, bx[1] - GIRTH), min(hi, bx[3] + GIRTH)
    return i1 <= i0 or (i1 <= p[1] + 1 if edge == "T" else i0 >= p[1] - 1)


def buried(pts, box, term):
    """The parts this route runs under, by ref.

    ONE rule, used by the router to choose a route and by the checker to complain
    about one. They must agree: a checker with a laxer rule cannot see the defect
    the router exists to prevent, which is exactly what happened when the checker
    skipped every part a wire terminates on — a conductor could vanish behind the
    whole board and be reported clean.
    """
    ls = legs(pts)
    out = []
    for ref in sorted(box):
        bx = box[ref]
        p = term.get(ref)
        edge = pin_edge(p, bx) if p is not None else None
        for sg in ls:
            if not _seg_hits(sg, bx):
                continue
            if p is not None and arriving(sg, bx, p, edge):
                continue
            out.append(ref)
            break
    return out


def overlap_px(ls, laid, mine, near=None, taper=True):
    """How much of this route lies ON another conductor rather than crossing it.

    Crossings are unavoidable and readable; a shared stretch is not, because the
    wire drawn second simply deletes the first. 112 px of the fob's brown ON-pad
    conductor were hidden under the black one this way, and nothing in the sheet
    said so.

    Wires that share an endpoint are exempt: two branches of the same bus leave
    their junction together by construction, and that fork is the notation, not a
    collision.
    """
    near = NEAR if near is None else near
    tot = 0.0
    for owner, og in laid:
        if owner & mine:
            continue
        for sg in ls:
            if sg[0] != og[0]:
                continue
            gap = abs(sg[1] - og[1])
            if gap >= near:
                continue
            lo1, hi1 = sorted(sg[2:])
            lo2, hi2 = sorted(og[2:])
            # Weighted by separation rather than counted at zero. Two conductors
            # 3 px apart are not "clear" — at 2.6 px wide they are one thick line
            # with a seam — so the cost fades out over a stroke's worth of space
            # instead of switching off, which is also what gives the router a
            # gradient to follow when it has to fit one more wire into a full
            # gutter.
            run = max(0.0, min(hi1, hi2) - max(lo1, lo2))
            tot += run * (1.0 - gap / near) if taper else run
    return tot


PAD_OUT = (14, 22, 30, 40, 52, 68)


def _exits(p, bx):
    """x values just outside a part, on the side its pin is on.

    Several offsets rather than one, because the useful one is whichever is not
    already occupied: the left gutter of the Path A sheet carries nine vertical
    runs, and a single offset means the last wire routed has nowhere to sit. A pin
    on a top or bottom edge is reached vertically, so its own x is the exit.

    Nothing here checks that an exit is sensible — leaving a pin on the wrong side
    is a route that runs under its own part, which `buried` disqualifies, and
    leaving one so close to the part that it lies on the bus trunk is a cost.
    """
    edge = pin_edge(p, bx)
    if edge == "L":
        return [bx[0] - k for k in PAD_OUT]
    if edge == "R":
        return [bx[2] + k for k in PAD_OUT]
    return [p[0]]


def _transit_ys(obst, x0, x1, y1, y2, top, bot, keep=12):
    """Candidate heights for a lap's crossing run.

    The middle of every horizontal strip that is clear all the way from x0 to x1 —
    the same idea as `corridors`, turned ninety degrees and restricted to the span
    the wire actually crosses. Deriving them instead of offsetting from the nearest
    part is what finds the 10 px of white between the probe's caption and the
    resistor above it; offsets found only heights that ran through one or the other,
    and the 3V3 conductor spent its crossing run inside the words "clamps to the
    motor frame".

    A strip narrower than a wire plus its clearance is not a route, so bands are
    filtered by width — otherwise the 2 px between the board's silkscreen and its
    caption reads as the cheapest crossing on the sheet. The floor is 9 px, which
    is a 2.6 px conductor with 3 px either side: tight, but it is the gap between a
    caption and the part below it, and it is where a crossing run belongs.
    """
    LEAST = 9
    x0, x1 = sorted((x0, x1))
    spans = sorted((by0, by1) for bx0, by0, bx1, by1 in obst if bx1 > x0 and bx0 < x1)
    merged = []
    for lo, hi in spans:
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    ys, cursor = [], top
    for lo, hi in merged:
        if lo - cursor >= LEAST:
            ys.append((cursor + lo) / 2)
        cursor = max(cursor, hi)
    if bot - cursor >= LEAST:
        ys.append((cursor + bot) / 2)
    # Fallback heights, for a span with no clear strip at all: hugging a part is
    # ugly but it is a route, and having none means the wire goes back to crossing
    # something solid. Only these are capped — every clear band is kept, because
    # capping the list by cost dropped the two clean ways round the board in favour
    # of twelve cheap ways straight across it.
    near = sorted({round(y, 2) for _, by0, _, by1 in obst for y in (by0 - 13, by1 + 13)
                   if top <= y <= bot},
                  key=lambda y: (round(abs(y1 - y) + abs(y2 - y), 3), y))
    ys = sorted({round(y, 2) for y in ys if top <= y <= bot} | set(near[:keep]))
    ys.sort(key=lambda y: (round(abs(y1 - y) + abs(y2 - y), 3), y))
    return ys


def routes(a, b, chan, ba, bb, obst, gaps, top, bot, xlo, xhi):
    """Every route this wire could take, in preference order.

    Three shapes, cheapest first:

      * a straight run, where the two pins already line up;
      * a dog-leg through one channel — the normal case;
      * a lap: out past the end of a part, along a clear band, and back.

    The lap exists for the one thing a dog-leg cannot do, which is reach a pin on
    the far side of its own component from everything it connects to. R3 is the
    example: both of its leads connect to things on its left, so one of them has to
    come round the end rather than across the body.

    This function only proposes. Nothing here knows what is in the way — the caller
    scores each candidate with the same `buried` rule the CI check uses, so a route
    the checker would complain about cannot be the route the renderer draws.
    """
    (x1, y1), (x2, y2) = a, b
    out = []
    if abs(y1 - y2) < 1.5 or abs(x1 - x2) < 1.5:
        out.append([a, b])

    lo, hi = sorted((x1, x2))
    cxs = ([chan] if chan is not None else [])
    cxs += [lo + (hi - lo) * f for f in (0.5, 0.32, 0.68, 0.16, 0.84)]
    cxs += [(g0 + g1) / 2 for g0, g1 in gaps]
    cxs += _exits(a, ba) + _exits(b, bb)
    cxs = [x for x in cxs if xlo <= x <= xhi]
    seen = set()
    for cx in cxs:
        if round(cx, 1) in seen:
            continue
        seen.add(round(cx, 1))
        out.append([a, (cx, y1), (cx, y2), b])

    ylo, yhi = sorted((y1, y2))
    for f in (0.5, 0.3, 0.7):
        cy = ylo + (yhi - ylo) * f
        out.append([a, (x1, cy), (x2, cy), b])

    for ca in (x for x in _exits(a, ba) if xlo <= x <= xhi):
        for cb in (x for x in _exits(b, bb) if xlo <= x <= xhi):
            for yd in _transit_ys(obst, ca, cb, y1, y2, top, bot):
                out.append([a, (ca, y1), (ca, yd), (cb, yd), (cb, y2), b])
    return out


def path_len(pts):
    return sum(abs(x1 - x2) + abs(y1 - y2)
               for (x1, y1), (x2, y2) in zip(pts, pts[1:]))


def choose(cands, box, term, caps, laid, mine):
    """The best of the proposed routes, and whether it is actually clean.

    Lexicographic on purpose. Running under a part is disqualifying — length can
    never buy it back — and everything below that is a cost in pixels, so a lap is
    taken only when the shorter routes are genuinely blocked. Ties go to the
    earliest candidate, which is what keeps the output byte-identical from run to
    run.
    """
    best = None
    for i, pts in enumerate(cands):
        ls = legs(pts)
        hard = buried(pts, box, term)
        soft = sum(1 for cb in caps if any(_seg_hits(sg, cb) for sg in ls))
        cost = path_len(pts) + 80 * soft + 6 * overlap_px(ls, laid, mine)
        score = (len(hard), round(cost, 3), i)
        if best is None or score < best[0]:
            best = (score, pts, hard)
    return best[1], best[2]


def _sign(v):
    return 1 if v > 0 else -1 if v < 0 else 0


def draw_path(c, pts, colour, sw):
    """A polyline with rounded corners, which is what a dressed wire looks like."""
    pts = [p for i, p in enumerate(pts)
           if i == 0 or abs(p[0] - pts[i - 1][0]) > 0.05 or abs(p[1] - pts[i - 1][1]) > 0.05]
    if len(pts) < 2:
        return
    if len(pts) == 2:
        c.line(pts[0][0], pts[0][1], pts[1][0], pts[1][1], colour, sw)
        return
    d = [f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"]
    for i in range(1, len(pts) - 1):
        (px, py), (cx, cy), (nx, ny) = pts[i - 1], pts[i], pts[i + 1]
        r = min(9, (abs(cx - px) + abs(cy - py)) / 2, (abs(nx - cx) + abs(ny - cy)) / 2)
        d.append(f"L{cx - _sign(cx - px) * r:.1f} {cy - _sign(cy - py) * r:.1f} "
                 f"Q{cx:.1f} {cy:.1f} "
                 f"{cx + _sign(nx - cx) * r:.1f} {cy + _sign(ny - cy) * r:.1f}")
    d.append(f"L{pts[-1][0]:.1f} {pts[-1][1]:.1f}")
    c.path(" ".join(d), colour, sw)


def place_label(c, a, b, colour, s, hard, soft, bounds, size=10.5):
    """Put a net label on its wire's first horizontal run, clear of everything.

    The old rule was "draw it at the midpoint of the straight line between the two
    pins", which is not a place the wire necessarily goes and not a place anything
    else necessarily is not: on this sheet it put "USB-C" across a bundle of four
    other conductors and "divider junction" over a component caption.

    A label belongs where the wire LEAVES A PIN, because that is what it names, and
    that is also the one stretch of a wire guaranteed to be a clean horizontal run.
    Candidates around both pins are scored on how far they sit from the pin and how
    much they cover, in the same units, and the best wins. Everything is ordered, so
    the choice is deterministic.
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
    cands = sorted(cands, key=lambda t: (round(t[0], 3), round(t[1], 2), round(t[2], 2)))
    cands.append((260.0, (x1 + x2) / 2 - w / 2, (y1 + y2) / 2 - h / 2))

    # A candidate off the edge of the sheet is not a candidate. The widening search
    # will happily walk a label past the right margin, where it renders half-cut and
    # looks like a rendering bug rather than a placement one.
    bx0, by0, bx1, by1 = bounds
    inb = [c for c in cands
           if bx0 <= c[1] and by0 <= c[2] and c[1] + w <= bx1 and c[2] + h <= by1]

    # Ranked by how much they cover, not by the first that covers nothing.
    # Conductors are a SOFT constraint: crossing somebody else's wire is untidy, but
    # landing on a component is worse. A clear spot still wins — it scores zero, and
    # the list is ordered nearest-first — but where nothing is clear this settles for
    # the least-covered spot instead of falling through to the midpoint of a straight
    # line between the pins. That fallback is what put "fob ON pad" squarely across
    # the sentence explaining why the fob has no shared ground: in that corner every
    # candidate overlaps something, and the midpoint was the one place guaranteed to
    # be worst.
    def covered(r, boxes):
        ax0, ay0, ax1, ay1 = r
        return sum(max(0, min(ax1, bx1) - max(ax0, bx0)) *
                   max(0, min(ay1, by1) - max(ay0, by0))
                   for bx0, by0, bx1, by1 in boxes)

    best = None
    for rank, (dist, lx, ly) in enumerate(inb or cands):
        r = (lx, ly, lx + w, ly + h)
        # Distance and coverage in the same currency, so the choice between them is
        # explicit: sitting squarely on a component costs about 95, which is 95 px
        # of walking away from the pin it names, while crossing one conductor costs
        # about 3. That exchange rate is the whole behaviour. Coverage first and
        # distance only as a tiebreak sent "divider junction" 100 px from its own
        # wire to reach clear paper, where it reads as the name of whatever
        # conductor it happens to be nearest; the other way round parks it on the fob.
        score = ((3 * covered(r, hard) + covered(r, soft)) / 40.0 + dist, rank)
        if best is None or score < best[0]:
            best = (score, (lx, ly))
    lx, ly = best[1]
    # Grown by 3 px before it becomes an obstacle for the next label, so two of them
    # keep a hair of white between rather than sharing an edge.
    hard.append((lx - 3, ly - 3, lx + w + 3, ly + h + 3))
    c.rect(lx, ly, w, h, PAPER, r=3, stroke=colour, sw=1)
    c.text(lx + w / 2, ly + 12.5, s, size, INK, anchor="middle")


def render(spec, parts, rmap):
    comps = spec["components"]
    nets = spec.get("nets", [])

    pl = plan_sheet(spec, parts, rmap)
    parts, W, bottom = pl["parts"], pl["W"], pl["bottom"]
    placed, groups, eff = pl["placed"], pl["groups"], pl["eff"]
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
        draw_path(c, pl["paths"][i], colour, sw)
        for (px, py) in (a, b):
            c.circle(px, py, 3.4, colour)
        # A thin box per leg, so labels can be kept off conductors they do not name.
        lg = []
        for kind, fixed, p0, p1 in legs(pl["paths"][i]):
            lo, hi = sorted((p0, p1))
            lg.append((lo - 2, fixed - 3, hi + 2, fixed + 3) if kind == "h"
                      else (fixed - 3, lo - 2, fixed + 3, hi + 2))
        wire_boxes.append(lg)
        if label:
            pending.append((i, a, b, colour, label))

    for ref, cd in comps.items():
        p = parts[cd["part"]]
        ox, oy = placed[ref]
        p.draw(c, ox, oy)
        cap = cd.get("label") or p.title
        c.text(ox + p.w / 2, oy + p.h + 17, f"{ref}  {cap}", 12, INK,
               anchor="middle", weight="600")
        if cd.get("note"):
            c.text(ox + p.w / 2, oy + p.h + 32, cd["note"], 10.5, MUTE, anchor="middle")
    obstacles = list(pl["obstacles"])

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

    wires, owners, own_ref = [], {}, []
    for n in spec.get("nets", []):
        fr, fp = resolve_endpoint(n["from"], comps, parts, rmap)
        to, tp = resolve_endpoint(n["to"], comps, parts, rmap)
        a = parts[comps[fr]["part"]].pin_at(fp, *placed[fr])
        b = parts[comps[to]["part"]].pin_at(tp, *placed[to])
        colour = WIRE.get(n.get("color", "grey"), n.get("color", "#7A8087"))
        wires.append((a, b, colour, 3.2 if n.get("mains") else 2.6, n.get("label")))
        owners[(round(a[0], 1), round(a[1], 1))] = box[fr]
        owners[(round(b[0], 1), round(b[1], 1))] = box[to]
        own_ref.append((fr, to))

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

    # Two boxes per part. `obstacles` is the art plus its caption lines, which is
    # what a net label must stay off. `caps` is the caption text alone, which a
    # conductor should prefer to miss but may cross if the alternative is a lap
    # round the sheet. Both must be as wide as the TEXT, not as wide as the part: a
    # note like "no shared ground with the fob" is three times the width of the
    # optocoupler it sits under.
    obstacles, caps = [], []
    for ref, cd in comps.items():
        p = parts[cd["part"]]
        ox, oy = placed[ref]
        cap = cd.get("label") or p.title
        span = max(p.w, tw(f"{ref}  {cap}", 12),
                   tw(cd["note"], 10.5) if cd.get("note") else 0)
        cx, deep = ox + p.w / 2, oy + p.h + (36 if cd.get("note") else 22)
        obstacles.append((cx - span / 2, oy, cx + span / 2, deep))
        caps.append((cx - span / 2, oy + p.h + 5, cx + span / 2, deep))

    # Conductors already on the sheet, so each route can be scored against what is
    # actually there. Trunks go down first: nothing should be routed along one.
    laid = [(frozenset({g["pt"]}),
             ("h", g["pt"][1], g["pt"][0], g["pt"][0] + g["dir"] * TRUNK))
            for g in groups.values()]

    cand, term, ends = [], [], []
    for i, (a, b, *_r) in enumerate(eff):
        fr, to = own_ref[i]
        cand.append(routes(a, b, chan.get(i), box[fr], box[to], boxes + caps, gaps,
                           108, bottom + 24, 16, W - 16))
        # The pins, not the effective endpoints: a bus member starts at its junction,
        # and only a leg that ends on the actual pin can be the wire arriving at it.
        term.append({fr: wires[i][0], to: wires[i][1]})
        ends.append(frozenset({a, b}))

    def sheet_so_far(paths, skip):
        out = list(laid)
        for j, pts in enumerate(paths):
            if j == skip or pts is None:
                continue
            out += [(ends[j], sg) for sg in legs(pts)]
        return out

    # Three passes, not one. A single greedy pass gives each wire only the wires
    # laid before it, so the last one routed has to fit through whatever everything
    # else already took — on this sheet that left the GPIO26 pulldown conductor
    # lying along 102 px of the acknowledge button's ground. Re-routing every wire
    # against the FINISHED sheet lets an early wire move over for a late one, which
    # is what a person does when they dress a loom and find the last conductor has
    # nowhere to sit. It settles in two; the third is there to prove it.
    paths, hard_of = [None] * len(eff), [[]] * len(eff)
    for _ in range(3):
        moved = False
        for i in range(len(eff)):
            pts, hard = choose(cand[i], box, term[i], caps,
                               sheet_so_far(paths, i), ends[i])
            moved = moved or paths[i] != pts
            paths[i], hard_of[i] = pts, hard
        if not moved:
            break
    stuck = [(i, h) for i, h in enumerate(hard_of) if h]

    return dict(parts=parts, placed=placed, W=W, bottom=bottom, box=box, boxes=boxes,
                wires=wires, eff=eff, chan=chan, groups=groups, paths=paths,
                stuck=stuck, obstacles=obstacles, caps=caps, own_ref=own_ref,
                trunk=TRUNK)


def crossings(spec, parts, rmap):
    """Every way a conductor can be made unreadable: under a part, or under another
    conductor.

    Both are re-derived from the planned routes with the same functions the router
    scored them with, so this cannot pass by looking at a path that is not the one
    drawn. It is worth asserting even though the router avoids both by construction,
    because that is a property of the search, and a future change to placement,
    channel allocation or part art could quietly lose it.
    """
    pl = plan_sheet(spec, parts, rmap)
    nets = spec["nets"]
    paths, eff = pl["paths"], pl["eff"]

    def who(i):
        n = nets[i]
        return (f"net {i} ({n.get('label') or n.get('color', '?')}: "
                f"{n['from']} -> {n['to']})")

    bad = [f"{who(i)} runs under {', '.join(refs)}" for i, refs in pl["stuck"]]

    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            if {eff[i][0], eff[i][1]} & {eff[j][0], eff[j][1]}:
                continue              # two branches of one bus: a fork, not a collision
            # The router's cost tapers with separation, because two conductors
            # 8 px apart are worth nudging but are perfectly readable. The CHECK is
            # the untapered thing it is there to prevent: one conductor drawn on
            # top of another, where the second simply deletes the first.
            ov = overlap_px(legs(paths[i]),
                            [(frozenset(), sg) for sg in legs(paths[j])],
                            frozenset(), near=3.5, taper=False)
            if ov > 6:
                bad.append(f"{who(i)} lies on {who(j)} for {ov:.0f} px")
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
        print("cirkit: these conductors cannot be followed on the sheet:",
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


def cmd_selftest(args):
    """Make each readability check fail on purpose, and confirm it notices.

    A gate nobody has ever seen fail is a gate nobody should trust. Every check in
    this repository that was written and believed turned out to need correcting —
    four were too strict and condemned correct work, one passed while looking at the
    wrong thing — so a check is worth having only once it has been disbelieved.

    Each case here disables exactly one thing the router does to keep conductors
    followable and asserts that `check` complains. If a case stops producing
    complaints, either the router got better in a way that makes the case
    meaningless, or the check went blind. Both are worth a person looking.
    """
    parts, rmap = partlib.load_all(), roles()
    spec = yaml.safe_load(specs(None)[0].read_text())
    saved = (routes, overlap_px, arriving)
    cases, bad = [], []
    try:
        # 1. Only dog-legs. Wires whose pin is on the far side of their own part
        #    have nowhere to go but across it.
        globals()["routes"] = lambda *a, **k: [p for p in saved[0](*a, **k) if len(p) <= 4]
        cases.append(("no lap shape", "runs under", crossings(spec, parts, rmap)))
        globals()["routes"] = saved[0]

        # 2. The router stops caring what is already on the sheet.
        globals()["overlap_px"] = (
            lambda ls, laid, mine, near=None, taper=True:
            0.0 if taper else saved[1](ls, laid, mine, near, taper))
        cases.append(("no overlap cost", "lies on", crossings(spec, parts, rmap)))
        globals()["overlap_px"] = saved[1]

        # 3. No stub excusal, so every wire is guilty of touching its own part.
        globals()["arriving"] = lambda *a: False
        cases.append(("no arriving-stub rule", "runs under", crossings(spec, parts, rmap)))
    finally:
        globals()["routes"], globals()["overlap_px"], globals()["arriving"] = saved

    for name, want, found in cases:
        hits = [c for c in found if want in c]
        print(f"  {name:<24} {len(hits)} × {want!r}")
        for c in hits[:4]:
            print(f"      {c}")
        if not hits:
            bad.append(f"{name}: expected at least one {want!r}, got none")

    if crossings(spec, parts, rmap):
        bad.append("the sheet as built is not clean")
    if bad:
        print("cirkit selftest: the checks are not doing what they claim",
              file=sys.stderr)
        for b in bad:
            print(f"  {b}", file=sys.stderr)
        return 1
    print("OK — every readability check fails when the thing it guards is removed")
    return 0


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
    sub.add_parser("selftest", help="prove the readability checks can fail")
    sub.add_parser("catalogue", help="render every part on one sheet, pins marked")
    pp = sub.add_parser("parts"); pp.add_argument("--json", action="store_true")
    args = ap.parse_args()
    fn = {"build": cmd_build, "check": cmd_check, "parts": cmd_parts,
          "lint": cmd_lint, "catalogue": cmd_catalogue, "selftest": cmd_selftest}[args.cmd]
    sys.exit(fn(args) or 0)


if __name__ == "__main__":
    main()
