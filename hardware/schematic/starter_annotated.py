#!/usr/bin/env python3
"""Render starter_annotated.svg — where the receiver wires land, drawn on a
photo of the open Gould/ITE A202C starter enclosure.

The other four sheets in this directory are CircuiTikZ. This one is a
photo overlay registered to pixel coordinates, which TikZ is the wrong
tool for, so it is generated here instead. The photograph is embedded as
a data URI: an SVG that references an external image renders blank on
GitHub and inside an <img> tag, and a sheet that only works when opened
as a local file is not much of a sheet.

    make starter_annotated.svg      # or: python3 starter_annotated.py

Companion to ladder_coil_circuit.svg, which has the topology. This sheet
answers the other question — which screw. Coordinates are raw photo
pixels (1125 x 1500), read off the photograph at 3x magnification.
Anything asserted here is legible in the image; everything else is
deferred to a meter, which is the point of the procedure panel.
"""

import base64
import pathlib

HERE = pathlib.Path(__file__).parent
PHOTO = HERE / "starter_photo.jpg"
OUT = HERE / "starter_annotated.svg"

PW, PH = 1125, 1500                 # photo pixels
POX, POY = 30, 30                   # photo pane origin on the canvas
PX, PY = 1190, 30                   # panel origin
PANW, PANH = 700, 1560              # panel runs a little taller than the photo
CW, CH = 1920, 1620                 # canvas

INK, MUTE, RULE = "#16181D", "#6E7178", "#C7CAD1"
MAINS, SAFE, AMBER = "#B3261E", "#1E6B45", "#8A6A12"
RED, GRN, AMB = "#FF4438", "#22C97F", "#FFD166"

# ---------------------------------------------------------------- features
# Read off the photograph at 3x. The moulded numerals are the only
# markings legible enough to assert; the screws are located but NOT
# identified, which is why they get letters rather than names.
NUM = {"2": (477, 402), "3": (595, 402), "?": (716, 400)}
SCREWS = [("A", 438, 320), ("B", 418, 410), ("C", 593, 350),
          ("D", 695, 316), ("E", 768, 412)]
STRIP = (380, 278, 428, 176)        # control terminal strip
BODY = (398, 448, 444, 428)         # contactor body: coil, aux, OL inside
BUNDLE = (400, 40, 430, 248)        # control wires leaving the enclosure
HUB_L, HUB_R = (392, 1172, 48), (583, 1178, 52)
T2, GNDSCREW, OLRESET = (808, 1032), (487, 952), (820, 930)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def lines(x, y, rows, size=15, fill=MUTE, lh=19, weight=None, anchor=None):
    """A run of text lines sharing a left edge."""
    w = f' font-weight="{weight}"' if weight else ""
    a = f' text-anchor="{anchor}"' if anchor else ""
    out = [f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}"{w}{a}>']
    for i, r in enumerate(rows):
        dy = 0 if i == 0 else lh
        out.append(f'<tspan x="{x}" dy="{dy}">{esc(r)}</tspan>')
    out.append("</text>")
    return "".join(out)


def pill(x, y, w, text, stroke, fg, size=17, h=34):
    """Dark rounded label, legible over any part of the photograph."""
    return (f'<g><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h/2}" '
            f'fill="#0B0D10" fill-opacity="0.88" stroke="{stroke}" stroke-width="2"/>'
            f'<text x="{x+15}" y="{y+h/2+6}" font-size="{size}" font-weight="600" '
            f'fill="{fg}">{esc(text)}</text></g>')


def leader(x1, y1, x2, y2, color, dash="6 5", w=2.4):
    return (f'<path d="M{x1},{y1} L{x2},{y2}" fill="none" stroke="{color}" '
            f'stroke-width="{w}" stroke-dasharray="{dash}" opacity="0.95"/>')


# ================================================================== photo
def photo_layer():
    b64 = base64.b64encode(PHOTO.read_bytes()).decode("ascii")
    s = [f'<g transform="translate({POX},{POY})">',
         f'<rect x="-1" y="-1" width="{PW+2}" height="{PH+2}" fill="#1A1C21" '
         f'stroke="{RULE}" stroke-width="1"/>',
         '<g clip-path="url(#photoclip)">',
         f'<image x="0" y="0" width="{PW}" height="{PH}" '
         f'xlink:href="data:image/jpeg;base64,{b64}"/>',
         # Dim everything, then lift the terminal strip back out. The strip
         # is the only place a wire actually lands, so it gets the light.
         f'<rect x="0" y="0" width="{PW}" height="{PH}" fill="#05070A" opacity="0.46"/>']

    sx, sy, sw, sh = STRIP
    s.append(f'<rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" rx="8" '
             f'fill="#FFFFFF" fill-opacity="0.16"/>')

    # --- the contactor's internals: nothing lands here -------------------
    bx, by, bw, bh = BODY
    s.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="9" '
             f'fill="#05070A" fill-opacity="0.34" stroke="#9AA0AA" '
             f'stroke-width="2" stroke-dasharray="9 7"/>')
    s.append(lines(bx + bw / 2, 792, ["INSIDE THE STARTER"], 20, "#DDE1E8",
                   weight="700", anchor="middle"))
    s.append(lines(bx + bw / 2, 820,
                   ["coil · seal-in aux · OL contact — all factory-wired.",
                    "No receiver conductor lands in here."],
                   15, "#AEB4BD", lh=20, anchor="middle"))

    # --- control wires leaving the box -----------------------------------
    ux, uy, uw, uh = BUNDLE
    s.append(f'<rect x="{ux}" y="{uy}" width="{uw}" height="{uh}" rx="9" '
             f'fill="{RED}" fill-opacity="0.10" stroke="{RED}" stroke-width="2.5" '
             f'stroke-opacity="0.8" stroke-dasharray="9 6"/>')
    s.append(pill(400, 8, 372, "control wiring → START / STOP station", RED, "#FF9A92"))

    # --- the strip, spotlit ----------------------------------------------
    s.append(f'<rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" rx="8" '
             f'fill="none" stroke="{AMB}" stroke-width="3.5"/>')
    s.append(pill(842, 296, 268, "EVERY receiver wire", AMB, AMB, 17))
    s.append(pill(842, 336, 268, "lands on this strip", AMB, AMB, 17))
    s.append(leader(842, 330, 812, 346, AMB, "7 5"))

    # --- located but unidentified screws ---------------------------------
    for letter, x, y in SCREWS:
        s.append(f'<circle cx="{x}" cy="{y}" r="19" fill="none" stroke="#FFFFFF" '
                 f'stroke-width="2.4" stroke-dasharray="5 4" opacity="0.9"/>')
        s.append(f'<circle cx="{x+17}" cy="{y-16}" r="11" fill="#0B0D10" '
                 f'fill-opacity="0.9" stroke="#FFFFFF" stroke-width="1.4"/>')
        s.append(f'<text x="{x+17}" y="{y-11}" font-size="14" font-weight="700" '
                 f'fill="#FFFFFF" text-anchor="middle">{letter}</text>')

    # --- the moulded numerals: the one certain identification ------------
    for label, (x, y) in NUM.items():
        s.append(f'<rect x="{x-29}" y="{y-29}" width="58" height="58" rx="7" '
                 f'fill="none" stroke="{AMB}" stroke-width="3.5"/>')
        # the inverted third numeral is labelled lower, to clear "TERM 3"
        end = f"L{x},{y+66} L730,{y+88}" if label == "?" else f"L{x},{y+62}"
        s.append(f'<path d="M{x},{y+31} {end}" stroke="{AMB}" '
                 f'stroke-width="2.4" stroke-dasharray="5 4" fill="none"/>')
    for label, tx, ty in (("TERM 2", 477, 482), ("TERM 3", 595, 482),
                          ("3rd numeral,", 730, 506), ("reads inverted", 730, 526)):
        s.append(lines(tx, ty, [label], 16, AMB, weight="700", anchor="middle"))

    # --- the cut: control L1, ahead of STOP ------------------------------
    s.append(f'<circle cx="470" cy="152" r="26" fill="{GRN}" stroke="#FFFFFF" '
             f'stroke-width="3.5"/>')
    s.append('<path d="M458,140 L474,149 L461,155 L481,165" fill="none" '
             'stroke="#08120D" stroke-width="3.6" stroke-linecap="round" '
             'stroke-linejoin="round"/>')
    s.append(pill(38, 88, 372, "CUT HERE — control L1, ahead of STOP", GRN, GRN, 18, 38))
    s.append(lines(53, 150, ["The receiver goes in this gap. Its line side",
                             "must stay permanently live, so it sits at the",
                             "head of the rung — never past the seal-in."],
                   15, "#8FE8C0", lh=19))
    s.append(leader(410, 112, 446, 142, GRN, "7 5"))

    # --- hubs the new leads travel through -------------------------------
    for cx, cy, r in (HUB_L, HUB_R):
        s.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{GRN}" '
                 f'stroke-width="4"/>')
    s.append(pill(150, 1216, 432, "three conductors travel through these hubs",
                  GRN, GRN))
    s.append(leader(350, 1216, 386, 1224, GRN, "7 5"))
    s.append(leader(470, 1216, 566, 1232, GRN, "7 5"))

    # --- the receiver, drawn outside the enclosure where it lives --------
    s.append(f'<rect x="150" y="1284" width="500" height="196" rx="12" '
             f'fill="#0B0D10" fill-opacity="0.86" stroke="{GRN}" stroke-width="2.5"/>')
    s.append(lines(400, 1310, ["VONVOFF RX — LINE-POWERED, NOT A DRY CONTACT"],
                   14, GRN, weight="700", anchor="middle"))
    for ty, term, dest in (
            (1344, "AC IN L", "control L1 — the line side of your cut"),
            (1378, "AC OUT L", "STOP — the lifted feed"),
            (1412, "AC OUT N", "control L2 / return"),
            (1446, "AC IN N", "bonded to AC OUT N inside; use either")):
        s.append(lines(172, ty, [term], 16, GRN, weight="700"))
        s.append(lines(300, ty, [dest], 14, "#8FE8C0"))

    # --- quiet orientation tags ------------------------------------------
    for tx, ty, lx, ly, lw, txt in (
            (T2[0] + 22, T2[1], 858, 1014, 232, "T2 — motor load"),
            (OLRESET[0] + 20, OLRESET[1] - 4, 858, 900, 232, "OL reset (manual)"),
            (GNDSCREW[0] - 20, GNDSCREW[1], 196, 1006, 190, "PE ground")):
        s.append(pill(lx, ly, lw, txt, "#C7CAD1", "#DDE1E8", 16, 32))
        s.append(leader(lx if lx > tx else lx + lw, ly + 16, tx, ty, "#C7CAD1", "5 5", 2))

    s.append("</g></g>")
    return "".join(s)


# ================================================================== panel
def panel():
    s = [f'<g transform="translate({PX},{PY})">',
         f'<rect x="0" y="0" width="{PANW}" height="{PANH}" rx="4" fill="#FFFFFF" '
         f'stroke="{RULE}" stroke-width="1"/>']

    s.append(lines(26, 52, ["Where the receiver wires land"], 28, INK, weight="700"))
    s.append(lines(26, 78, ["Gould / ITE A202C · NEMA Size 1 · 2-pole · VONVOFF B07CTL3TG6",
                            "Table-saw thermal protection retrofit"], 15, MUTE, lh=20))
    s.append(f'<line x1="26" y1="112" x2="{PANW-26}" y2="112" stroke="{RULE}"/>')

    # -- why the head of the rung ----------------------------------------
    s.append(f'<rect x="26" y="128" width="{PANW-52}" height="212" rx="6" '
             f'fill="#FFF8E6" stroke="{AMBER}" stroke-width="1.6"/>')
    s.append(lines(44, 154, ["WHY THE RECEIVER GOES AT THE HEAD OF THE RUNG"], 15,
                   AMBER, weight="700"))
    s.append(lines(44, 180, [
        "Two independent reasons, either one sufficient:"], 15, "#6B551A"))
    s.append(lines(44, 206, [
        "1.  It is line-powered. AC IN L is both its supply and the line",
        "     side of its relay. Fed from past the seal-in it is dead when",
        "     START is pressed, so the coil never latches."], 15, "#6B551A", lh=19))
    s.append(lines(44, 274, [
        "2.  The seal-in aux bridges terminals 2 and 3, so a break inside",
        "     that span is shorted out the moment the contactor pulls in."],
        15, "#6B551A", lh=19))
    for cx, lab in ((330, "2"), (462, "3")):
        s.append(f'<rect x="{cx-16}" y="304" width="32" height="30" rx="5" '
                 f'fill="#FFFFFF" stroke="{AMBER}" stroke-width="2.2"/>')
        s.append(f'<text x="{cx}" y="326" font-size="17" font-weight="700" '
                 f'fill="{AMBER}" text-anchor="middle">{lab}</text>')
    s.append(f'<path d="M346,319 L446,319" stroke="{AMBER}" stroke-width="2.2"/>')
    s.append(f'<path d="M384,307 L408,331 M408,307 L384,331" stroke="{MAINS}" '
             f'stroke-width="3.2" stroke-linecap="round"/>')
    s.append(lines(488, 325, ["dead zone"], 14, MAINS, weight="700"))

    # -- the four terminals ----------------------------------------------
    s.append(lines(26, 372, ["THE FOUR TERMINALS"], 15, INK, weight="700"))
    s.append(f'<rect x="26" y="386" width="{PANW-52}" height="146" rx="6" '
             f'fill="#F2FAF6" stroke="{SAFE}" stroke-width="1.8"/>')
    for ty, term, dest in (
            (416, "AC IN L", "Control-circuit L1, ahead of STOP and the seal-in."),
            (446, "AC OUT L", "STOP, then the rest of the rung. Switched AC IN L."),
            (476, "AC OUT N", "Control-circuit L2 / return."),
            (506, "AC IN N", "Bonded to AC OUT N internally. Use either.")):
        s.append(lines(44, ty, [term], 15, SAFE, weight="700"))
        s.append(lines(158, ty, [dest], 15, "#3E6B56"))
    s.append(lines(26, 558, [
        "There is no dry contact to relocate and no jumper to fit. One L pair",
        "carries the rung, the N pair carries the return."], 15, MUTE, lh=19))

    # -- procedure -------------------------------------------------------
    s.append(f'<line x1="26" y1="598" x2="{PANW-26}" y2="598" stroke="{RULE}"/>')
    s.append(lines(26, 626, ["PROCEDURE"], 15, INK, weight="700"))
    steps = [
        ("Lock out the disconnect.",
         ["Prove dead at the line lugs with a meter you have first",
          "tested on a known-live circuit."]),
        ("Find the control feed.",
         ["Ohms from each strip screw to the L2 line lug. Tens to a few",
          "hundred Ω is the coil seen through the rung — that screw is on",
          "the control circuit. Open circuit means a power lug; leave it."]),
        ("Confirm the aux span.",
         ["Terminal 2 to terminal 3 reads open at rest, and ≈0 Ω when",
          "you press the armature closed by hand. Your cut stays outside",
          "that span."]),
        ("Lift the L1 feed into STOP.",
         ["Tag it. This is the one conductor the receiver interrupts."]),
        ("Land the four terminals.",
         ["L1 screw → AC IN L · lifted STOP feed → AC OUT L ·",
          "control L2 → AC OUT N. Three runs through the conduit hubs",
          "in 14 AWG mains-rated wire."]),
        ("Prove the inversion before re-energising.",
         ["Hold a fob button: the contact must close. Release it: the",
          "contact must open. If it is closed with nothing transmitting,",
          "stop — the fail-safe this design rests on is not there."]),
    ]
    y = 652
    for i, (head, body) in enumerate(steps, 1):
        s.append(f'<circle cx="44" cy="{y-5}" r="14" fill="{INK}"/>'
                 f'<text x="44" y="{y+1}" font-size="15" font-weight="700" '
                 f'fill="#FFF" text-anchor="middle">{i}</text>')
        s.append(lines(70, y, [head], 16, INK, weight="700"))
        s.append(lines(70, y + 22, body, 15, MUTE, lh=19))
        y += 30 + 19 * len(body) + 14

    # -- the honest bit --------------------------------------------------
    s.append(f'<rect x="26" y="{y-4}" width="{PANW-52}" height="132" rx="6" '
             f'fill="#FDF2F1" stroke="{MAINS}" stroke-width="1.6"/>')
    s.append(lines(44, y + 22, ["WHAT THIS PHOTOGRAPH CANNOT TELL YOU"], 15,
                   MAINS, weight="700"))
    s.append(lines(44, y + 48, [
        "Only the moulded numerals are legible. Which brass screw each numeral",
        "serves, where the coil terminals sit, and whether the two side blocks",
        "are aux contacts are all unresolved from a photo. The white rings mark",
        "screws that exist, not screws identified — step 2 settles that."],
        15, "#7A2A24", lh=19))
    y += 150

    # -- the rung as it ends up wired ------------------------------------
    s.append(lines(26, y, ["THE RUNG, AS WIRED"], 15, INK, weight="700"))
    rung = "L1 → RX → STOP → [2] → START ∥ aux → [3] → coil → OL → L2"
    s.append(f'<text x="26" y="{y+28}" font-size="14" font-family="Menlo, '
             f'Consolas, monospace" fill="{INK}">{esc(rung)}</text>')
    # Menlo advances 0.6em, so char n starts at 26 + 8.4n at font-size 14.
    a0, a1 = 26 + 5 * 8.4, 26 + 7 * 8.4            # spans "RX"
    s.append(f'<path d="M{a0},{y+38} L{a0},{y+48} L{a1},{y+48} L{a1},{y+38}" '
             f'fill="none" stroke="{SAFE}" stroke-width="2.4"/>')
    s.append(lines(26, y + 66, ["RX is the one thing added"], 14, SAFE,
                   weight="700"))

    s.append(lines(26, PANH - 62, [
        "Topology: ladder_coil_circuit.svg · Terminals: WIRING.md § Receiver",
        "Aux span: ARCHITECTURE.md § Control topology",
        "Photo overlay generated by starter_annotated.py"],
        13, MUTE, lh=16))
    s.append("</g>")
    return "".join(s)


def main():
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" width="{CW}" height="{CH}" '
        f'viewBox="0 0 {CW} {CH}" font-family="Helvetica Neue, Helvetica, Arial, '
        f'sans-serif">',
        '<!-- GENERATED by starter_annotated.py - do not edit -->',
        f'<defs><clipPath id="photoclip"><rect x="0" y="0" width="{PW}" '
        f'height="{PH}"/></clipPath></defs>',
        f'<rect width="{CW}" height="{CH}" fill="#F5F6F7"/>',
        photo_layer(), panel(), '</svg>']
    OUT.write_text("".join(svg))
    print(f"wrote {OUT.name}  ({OUT.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
