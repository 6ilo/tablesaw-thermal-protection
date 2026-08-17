#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["schemdraw>=0.19"]
# ///
"""
Ladder logic — coil circuit after retrofit.

3-wire seal-in with the retrofit interposed between the seal-in
network and the overload / coil. Reading left-to-right on the rung:

    L1 rail
      -> STOP  (NC pushbutton)
      -> START (NO pushbutton) || M1 aux (NO)     <-- seal-in parallel
      -> TSTAT (NC thermostat — passive layer)
      -> KA    (NO contact from ESP32 relay module — supervisor layer)
      -> OL    (NC contact from overload relay)
      -> M1    (contactor coil)
    L2 rail

Fail-safe topology: every element between the rails is either
NC-that-opens-on-fault (STOP, TSTAT, OL) or NO-that-must-be-actively-
held-closed (START/seal, KA). Any wire break, sensor failure, or loss
of ESP32 supply drops the coil.

Regenerate with:  uv run hardware/schematic/ladder_coil_circuit.py
"""

from pathlib import Path
import schemdraw
import schemdraw.elements as e
from schemdraw.segments import Segment, SegmentCircle

HERE = Path(__file__).parent


# ---------------------------------------------------------------
# Ladder-logic symbol primitives.
# SchemDraw ships general-purpose electrical symbols (Switch, Fuse,
# etc.) but not the IEC/NEMA ladder shapes. Build them from Segments.
# All shapes are horizontal (start=(0,0), end=(W,0)) and get placed
# with an explicit .right() so SchemDraw's current-direction state
# never rotates them.
# ---------------------------------------------------------------

CONTACT_W = 1.5   # element length in schemdraw units
CONTACT_GAP = 0.35
BAR_H = 0.6


class NOContact(e.Element):
    """Ladder NO contact:  ─| |─  (two short vertical bars, gap between)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        mid = CONTACT_W / 2
        self.segments.append(Segment([(0, 0), (mid - CONTACT_GAP / 2, 0)]))
        self.segments.append(Segment([(mid + CONTACT_GAP / 2, 0), (CONTACT_W, 0)]))
        self.segments.append(Segment([(mid - CONTACT_GAP / 2, -BAR_H / 2),
                                      (mid - CONTACT_GAP / 2, BAR_H / 2)]))
        self.segments.append(Segment([(mid + CONTACT_GAP / 2, -BAR_H / 2),
                                      (mid + CONTACT_GAP / 2, BAR_H / 2)]))
        self.params['drop'] = (CONTACT_W, 0)
        self.anchors['start'] = (0, 0)
        self.anchors['end'] = (CONTACT_W, 0)
        self.anchors['center'] = (mid, 0)


class NCContact(e.Element):
    """Ladder NC contact:  ─|/|─  (NO contact with diagonal slash)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        mid = CONTACT_W / 2
        self.segments.append(Segment([(0, 0), (mid - CONTACT_GAP / 2, 0)]))
        self.segments.append(Segment([(mid + CONTACT_GAP / 2, 0), (CONTACT_W, 0)]))
        self.segments.append(Segment([(mid - CONTACT_GAP / 2, -BAR_H / 2),
                                      (mid - CONTACT_GAP / 2, BAR_H / 2)]))
        self.segments.append(Segment([(mid + CONTACT_GAP / 2, -BAR_H / 2),
                                      (mid + CONTACT_GAP / 2, BAR_H / 2)]))
        # diagonal slash across the contact
        self.segments.append(Segment([(mid - CONTACT_GAP, -BAR_H / 2 - 0.1),
                                      (mid + CONTACT_GAP, BAR_H / 2 + 0.1)]))
        self.params['drop'] = (CONTACT_W, 0)
        self.anchors['start'] = (0, 0)
        self.anchors['end'] = (CONTACT_W, 0)
        self.anchors['center'] = (mid, 0)


COIL_W = 1.6
COIL_R = 0.45


class Coil(e.Element):
    """Ladder coil:  ─O─  (circle in the middle of the wire)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        mid = COIL_W / 2
        self.segments.append(Segment([(0, 0), (mid - COIL_R, 0)]))
        self.segments.append(Segment([(mid + COIL_R, 0), (COIL_W, 0)]))
        self.segments.append(SegmentCircle((mid, 0), COIL_R))
        self.params['drop'] = (COIL_W, 0)
        self.anchors['start'] = (0, 0)
        self.anchors['end'] = (COIL_W, 0)
        self.anchors['center'] = (mid, 0)


# ---------------------------------------------------------------
# Drawing — everything at absolute coordinates so element order
# does not affect layout.
# ---------------------------------------------------------------

with schemdraw.Drawing(show=False) as d:
    d.config(fontsize=11, unit=1.0)

    # -------- Layout constants
    RUNG_Y = 0.0
    RAIL_TOP_Y = 2.0
    BRANCH_Y = -3.0                # seal-in loop below the main rung
    RAIL_BOT_Y = -5.0

    LEFT_RAIL_X = 0.0
    STOP_X = 2.0                    # start x of STOP
    SEAL_LEFT_X = STOP_X + CONTACT_W + 1.0    # 4.5 — start of the seal-in parallel network
    START_X = SEAL_LEFT_X + 1.5    # 6.0 — start x of START (centered in seal region)
    SEAL_RIGHT_X = SEAL_LEFT_X + 6.0           # 10.5 — right side of seal-in network
    TSTAT_X = SEAL_RIGHT_X + 1.5   # 12.0
    KA_X = TSTAT_X + CONTACT_W + 1.5           # 15.0
    OL_X = KA_X + CONTACT_W + 1.5              # 18.0
    M1_X = OL_X + CONTACT_W + 1.5              # 21.0
    RIGHT_RAIL_X = M1_X + COIL_W + 2.0         # 24.6

    def horiz_wire(x1, x2, y):
        d.add(e.Line().at((x1, y)).to((x2, y)))

    def vert_wire(x, y1, y2):
        d.add(e.Line().at((x, y1)).to((x, y2)))

    def contact_label(x, y_offset_top, y_offset_bot, top_text, bot_text):
        """Center a two-line label above and below a contact/coil."""
        d.add(e.Label().at((x, RUNG_Y + y_offset_top)).label(top_text, loc='center'))
        d.add(e.Label().at((x, RUNG_Y + y_offset_bot)).label(bot_text, loc='center'))

    # -------- Rails
    d.add(e.Line().at((LEFT_RAIL_X, RAIL_TOP_Y)).to((LEFT_RAIL_X, RAIL_BOT_Y)).linewidth(2))
    d.add(e.Label().at((LEFT_RAIL_X, RAIL_TOP_Y + 0.3)).label('L1  (120 V hot)', loc='top'))

    d.add(e.Line().at((RIGHT_RAIL_X, RAIL_TOP_Y)).to((RIGHT_RAIL_X, RAIL_BOT_Y)).linewidth(2))
    d.add(e.Label().at((RIGHT_RAIL_X, RAIL_TOP_Y + 0.3)).label(
        'L2  (neutral / return)', loc='top'))

    # -------- Rung wires (fill in the horizontal segments between elements)
    horiz_wire(LEFT_RAIL_X, STOP_X, RUNG_Y)
    horiz_wire(STOP_X + CONTACT_W, SEAL_LEFT_X, RUNG_Y)
    horiz_wire(SEAL_LEFT_X, SEAL_RIGHT_X, RUNG_Y)   # top of seal-in parallel = also main rung passes through START
    horiz_wire(SEAL_RIGHT_X, TSTAT_X, RUNG_Y)
    horiz_wire(TSTAT_X + CONTACT_W, KA_X, RUNG_Y)
    horiz_wire(KA_X + CONTACT_W, OL_X, RUNG_Y)
    horiz_wire(OL_X + CONTACT_W, M1_X, RUNG_Y)
    horiz_wire(M1_X + COIL_W, RIGHT_RAIL_X, RUNG_Y)

    # -------- STOP (NC)
    d.add(NCContact().at((STOP_X, RUNG_Y)).right())
    contact_label(STOP_X + CONTACT_W / 2, 1.0, -1.0, 'STOP', '(NC pushbutton)')

    # -------- START (NO) on the main rung, inside the seal-in span
    d.add(NOContact().at((START_X, RUNG_Y)).right())
    contact_label(START_X + CONTACT_W / 2, 1.0, -1.0, 'START', '(NO pushbutton)')

    # -------- M1 aux (NO) in parallel with START — branch below
    aux_x = START_X   # align with START
    vert_wire(SEAL_LEFT_X, RUNG_Y, BRANCH_Y)
    vert_wire(SEAL_RIGHT_X, RUNG_Y, BRANCH_Y)
    horiz_wire(SEAL_LEFT_X, aux_x, BRANCH_Y)
    horiz_wire(aux_x + CONTACT_W, SEAL_RIGHT_X, BRANCH_Y)
    d.add(NOContact().at((aux_x, BRANCH_Y)).right())
    d.add(e.Label().at((aux_x + CONTACT_W / 2, BRANCH_Y + 1.0)).label('M1 aux', loc='center'))
    d.add(e.Label().at((aux_x + CONTACT_W / 2, BRANCH_Y - 1.0)).label(
        '(NO, seal-in)', loc='center'))
    d.add(e.Dot().at((SEAL_LEFT_X, RUNG_Y)))
    d.add(e.Dot().at((SEAL_RIGHT_X, RUNG_Y)))

    # -------- TSTAT (NC, passive thermostat — the retrofit)
    d.add(NCContact().at((TSTAT_X, RUNG_Y)).right())
    contact_label(TSTAT_X + CONTACT_W / 2, 1.0, -1.2, 'TSTAT',
                  '(NC, opens ~110°C)')

    # -------- KA (NO, ESP32 relay contact — the supervisor)
    d.add(NOContact().at((KA_X, RUNG_Y)).right())
    contact_label(KA_X + CONTACT_W / 2, 1.0, -1.2, 'KA',
                  '(ESP32 relay NO,\nactive-HIGH)')

    # -------- OL (NC, overload)
    d.add(NCContact().at((OL_X, RUNG_Y)).right())
    contact_label(OL_X + CONTACT_W / 2, 1.0, -1.0, 'OL', '(NC, overload)')

    # -------- M1 coil
    d.add(Coil().at((M1_X, RUNG_Y)).right())
    contact_label(M1_X + COIL_W / 2, 1.0, -1.0, 'M1', '(contactor coil)')

    # -------- Rung label on the left margin
    d.add(e.Label().at((LEFT_RAIL_X - 1.5, RUNG_Y)).label('Rung 1', loc='center'))

    # -------- Legend / notes below the ladder
    note_y = RAIL_BOT_Y - 2.5
    d.add(e.Label().at((LEFT_RAIL_X, note_y)).label(
        'Fail-safe topology — after retrofit\n\n'
        '  STOP (NC pb)  — opens rung on operator command  '
        '(fail-safe: broken wire = open = stopped)\n'
        '  START (NO pb) — momentary; must be held until M1 aux seals it in\n'
        '  M1 aux (NO)   — auxiliary contact on M1 contactor; carries the seal after START releases\n'
        '                  (loss of coil power breaks the seal — motor cannot restart on its own)\n'
        '  TSTAT (NC)    — passive bimetallic snap-action on winding; opens ~110°C, autoresets ~70°C\n'
        '                  Wired IN SERIES with the rung — cuts coil independent of the ESP32.\n'
        '  KA (NO)       — normally-open contact on the ESP32 relay module (opto-isolated, active-HIGH)\n'
        '                  ESP32 must actively drive GPIO26 HIGH to close KA. Any of:\n'
        '                    - ESP32 crash / brown-out / power loss  -> GPIO26 floats -> 10k pulldown -> KA opens\n'
        '                    - Firmware trip on winding overtemp     -> firmware drives GPIO26 LOW  -> KA opens\n'
        '                    - Loss of thermocouple                  -> firmware trips              -> KA opens\n'
        '                  Any KA-open drops the coil.\n'
        '  OL (NC)       — overload relay auxiliary; opens on sustained overcurrent, drops coil\n'
        '  M1            — Gould/ITE A202C NEMA Size 1 contactor coil, 120 V\n\n'
        'SR-3: TSTAT and KA are IN SERIES. Either one open == coil de-energized == motor stopped.\n'
        'SR-4: No autonomous restart. After the coil drops, the seal-in is broken; a human must press START.',
        loc='right', halign='left', color='#333',
    ))

    out_svg = HERE / 'ladder_coil_circuit.svg'
    d.save(str(out_svg))
    print(f'wrote {out_svg}')
