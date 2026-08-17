#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["schemdraw>=0.19"]
# ///
"""
ESP32 supervisor — block-and-wire pictorial.

Deliberately simpler than the signal-level schematic
(esp32_supervisor.svg) and complementary to WIRING.md. The value
of this drawing is spatial: where each module sits relative to the
ESP32, and which colours of wire go where. The pin-level truth
lives in the schematic and the wiring table.

Regenerate with:  uv run hardware/schematic/esp32_pictorial.py
"""

from pathlib import Path
import schemdraw
import schemdraw.elements as e
from schemdraw.segments import Segment

HERE = Path(__file__).parent

RED    = '#d62728'
ORANGE = '#ff7f0e'
BLACK  = '#000000'
YELLOW = '#bcbd22'
GREEN  = '#2ca02c'
BLUE   = '#1f77b4'
PURPLE = '#9467bd'
BROWN  = '#8c564b'
GREY   = '#7f7f7f'


class Wire(e.Element):
    """Coloured polyline between arbitrary points — bypasses SchemDraw
    flow-based orientation so wires never rotate unexpectedly."""
    def __init__(self, points, color=BLACK, linewidth=2, dashed=False, **kwargs):
        super().__init__(**kwargs)
        seg = Segment(points)
        if dashed:
            seg.ls = '--'
        seg.lw = linewidth
        seg.color = color
        self.segments.append(seg)
        self.anchors['start'] = points[0]
        self.anchors['end'] = points[-1]


def block(d, x, y, w, h, label, color='#f7f7f7', edgecolor='black'):
    """Draw a filled labelled rectangle at (x, y) with corner at bottom-left."""
    seg = Segment([(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)])
    seg.fill = color
    seg.color = edgecolor
    seg.lw = 1.5
    el = e.Element()
    el.segments.append(seg)
    d.add(el)
    d.add(e.Label().at((x + w / 2, y + h / 2)).label(label, loc='center'))


with schemdraw.Drawing(show=False) as d:
    d.config(fontsize=10, unit=1.0)

    # =============================================================
    # Layout: ESP32 in the centre. Each external module has a
    # comfortable clear zone around it. Coordinates are in schemdraw
    # units, no overlaps by construction.
    # =============================================================

    # ESP32 module
    ESP_X, ESP_Y, ESP_W, ESP_H = -3.5, -3.5, 7.0, 7.0
    block(d, ESP_X, ESP_Y, ESP_W, ESP_H,
          'ESP32-DevKitC-32E\n\n(pin map: see WIRING.md\nand esp32_supervisor.svg)')

    # Labelled "port" anchors on the ESP32 edges — the physical pin
    # locations that connect out to the external modules.
    port_TC_out       = (ESP_X + ESP_W, ESP_Y + ESP_H - 1.0)  # right side, upper
    port_5V_in        = (ESP_X + ESP_W, ESP_Y + ESP_H - 2.5)  # right side, mid-upper
    port_3V3_out      = (ESP_X + ESP_W, ESP_Y + ESP_H - 4.0)  # right side, mid
    port_GND_R        = (ESP_X + ESP_W, ESP_Y + 1.0)          # right side, bottom
    port_NTC_in       = (ESP_X, ESP_Y + ESP_H - 1.0)          # left side, upper
    port_RLY_out      = (ESP_X, ESP_Y + ESP_H - 3.0)          # left side, mid
    port_ACK_in       = (ESP_X, ESP_Y + 1.5)                  # left side, bottom

    # Label the ports on the ESP32 boundary
    for pt, txt, col in [
        (port_TC_out,  '(SPI:\n GPIO18/19/5)', GREY),
        (port_5V_in,   '(VIN)',                 GREY),
        (port_3V3_out, '(3V3)',                 GREY),
        (port_GND_R,   '(GND)',                 GREY),
        (port_NTC_in,  '(GPIO34)',              GREY),
        (port_RLY_out, '(GPIO26)',              GREY),
        (port_ACK_in,  '(GPIO27)',              GREY),
    ]:
        d.add(e.Dot().at(pt))
        d.add(e.Label().at((pt[0] + (0.15 if pt[0] > 0 else -0.15), pt[1])).label(
            txt, loc='right' if pt[0] > 0 else 'left', fontsize=8, color=col))

    # ----- MAX31855 breakout (upper right)
    MX_X, MX_Y, MX_W, MX_H = 7.0, 3.0, 5.0, 2.5
    block(d, MX_X, MX_Y, MX_W, MX_H,
          'MAX31855\nK-type breakout\n(3V3, SPI)',
          color='#fef7ea')
    mx_spi_in = (MX_X, MX_Y + MX_H / 2)
    mx_tc_out = (MX_X + MX_W, MX_Y + MX_H / 2)

    # ----- Isolated PSU (upper far right, feeds +5V to ESP32)
    PSU_X, PSU_Y, PSU_W, PSU_H = 7.0, -0.5, 5.0, 2.0
    block(d, PSU_X, PSU_Y, PSU_W, PSU_H,
          'Isolated AC-DC PSU\n5 V SELV\n(Mean Well IRM-05-5)',
          color='#fdecea')
    psu_5v_out = (PSU_X, PSU_Y + PSU_H / 2)

    # ----- Relay module (lower right)
    RLY_X, RLY_Y, RLY_W, RLY_H = 7.0, -6.0, 5.0, 4.0
    block(d, RLY_X, RLY_Y, RLY_W, RLY_H,
          'Relay module\n(opto-isolated,\nactive-HIGH, NO)\n\n=> coil circuit',
          color='#eaf4fb')
    rly_in    = (RLY_X, RLY_Y + RLY_H - 1.0)
    rly_5v    = (RLY_X, RLY_Y + RLY_H - 2.0)
    rly_gnd   = (RLY_X, RLY_Y + RLY_H - 3.0)
    rly_contacts_out = (RLY_X + RLY_W, RLY_Y + RLY_H / 2)

    d.add(e.Label().at((RLY_X + RLY_W + 0.2, rly_contacts_out[1])).label(
        'COM, NO\n=> thermostat + M1 coil',
        loc='right', fontsize=8))

    # ----- NTC frame divider (upper left)
    NTC_X, NTC_Y, NTC_W, NTC_H = -12.0, 2.5, 5.0, 3.5
    block(d, NTC_X, NTC_Y, NTC_W, NTC_H,
          'NTC frame divider\n3V3 - 10k pullup - node\n              - NTC - GND\n(node = GPIO34)',
          color='#f4eafb')
    ntc_out_3v3 = (NTC_X + NTC_W, NTC_Y + NTC_H - 0.7)  # right side, upper (3V3 in)
    ntc_out_gpio = (NTC_X + NTC_W, NTC_Y + 0.7)         # right side, lower (signal out)

    # ----- Ack button (lower left)
    BTN_X, BTN_Y, BTN_W, BTN_H = -10.0, -6.0, 4.0, 2.0
    block(d, BTN_X, BTN_Y, BTN_W, BTN_H,
          'ACK button\n(momentary,\nto GND)',
          color='#eeeeee')
    btn_out = (BTN_X + BTN_W, BTN_Y + BTN_H / 2)

    # =============================================================
    # Wires — colour-coded, generously routed to avoid crossings
    # =============================================================

    # +5V from PSU to ESP32 VIN
    d.add(Wire([psu_5v_out, ((psu_5v_out[0] + port_5V_in[0]) / 2, psu_5v_out[1]),
                ((psu_5v_out[0] + port_5V_in[0]) / 2, port_5V_in[1]),
                port_5V_in],
               color=RED, linewidth=3))
    d.add(e.Label().at((port_5V_in[0] + 1.0, port_5V_in[1] - 0.3)).label(
        '+5V (red)', loc='right', color=RED, fontsize=8))

    # 3V3 from ESP32 to MAX31855 (VCC) and to NTC divider (top)
    # First to a junction, then to both consumers.
    junction_3v3 = (port_3V3_out[0] + 2.0, port_3V3_out[1] + 1.0)
    d.add(Wire([port_3V3_out, junction_3v3,
                (junction_3v3[0], mx_spi_in[1] + 0.5),
                (mx_spi_in[0] - 0.5, mx_spi_in[1] + 0.5),
                (mx_spi_in[0] - 0.5, mx_spi_in[1] + 0.3),
                mx_spi_in],
               color=ORANGE, linewidth=2))
    d.add(e.Dot().at(junction_3v3))
    # Second branch: back across to NTC divider top-right (crosses over the ESP32)
    d.add(Wire([junction_3v3,
                (junction_3v3[0], NTC_Y + NTC_H + 1.0),
                (ntc_out_3v3[0] + 0.3, NTC_Y + NTC_H + 1.0),
                ntc_out_3v3],
               color=ORANGE, linewidth=2))
    d.add(e.Label().at((junction_3v3[0] + 0.1, junction_3v3[1] + 0.3)).label(
        '3V3 (orange)', loc='right', color=ORANGE, fontsize=8))

    # GND common bus — from ESP32 right-side GND, split down to PSU and Relay
    d.add(Wire([port_GND_R, (port_GND_R[0] + 1.0, port_GND_R[1]),
                (port_GND_R[0] + 1.0, rly_gnd[1]),
                rly_gnd],
               color=BLACK, linewidth=2))
    d.add(e.Label().at((port_GND_R[0] + 1.1, port_GND_R[1] - 0.3)).label(
        'GND common (black)', loc='right', color=BLACK, fontsize=8))

    # SPI: from ESP32 TC-out port bundle to MAX31855 left side
    d.add(Wire([port_TC_out, ((port_TC_out[0] + mx_spi_in[0]) / 2, port_TC_out[1]),
                ((port_TC_out[0] + mx_spi_in[0]) / 2, mx_spi_in[1]),
                mx_spi_in],
               color=YELLOW, linewidth=2))
    d.add(e.Label().at((port_TC_out[0] + 1.5, port_TC_out[1] + 0.3)).label(
        'SPI bundle:\n SCK (yellow)\n MISO (green)\n CS (blue)',
        loc='right', halign='left', fontsize=8))

    # Thermocouple leads out of MAX31855 to the winding pigtail
    d.add(Wire([mx_tc_out, (mx_tc_out[0] + 2.0, mx_tc_out[1])],
               color=YELLOW, linewidth=2))
    d.add(e.Label().at((mx_tc_out[0] + 2.1, mx_tc_out[1])).label(
        'TC+ / TC- =>\nwinding K-type\n(via harness)',
        loc='right', fontsize=8))

    # NTC divider signal to ESP32 GPIO34 (dashed purple — via the divider node)
    d.add(Wire([ntc_out_gpio, ((ntc_out_gpio[0] + port_NTC_in[0]) / 2, ntc_out_gpio[1]),
                ((ntc_out_gpio[0] + port_NTC_in[0]) / 2, port_NTC_in[1]),
                port_NTC_in],
               color=PURPLE, linewidth=2, dashed=True))
    d.add(e.Label().at((ntc_out_gpio[0] + 0.2, ntc_out_gpio[1] + 0.3)).label(
        'GPIO34 (purple,\ndashed = via divider)',
        loc='right', color=PURPLE, fontsize=8))

    # Relay drive: GPIO26 -> relay IN (with pulldown noted)
    d.add(Wire([port_RLY_out, (port_RLY_out[0] - 1.5, port_RLY_out[1]),
                (port_RLY_out[0] - 1.5, rly_in[1] - 0.5),
                (rly_in[0] - 1.0, rly_in[1] - 0.5),
                (rly_in[0] - 1.0, rly_in[1]),
                rly_in],
               color=BROWN, linewidth=2))
    # Route the relay-drive brown wire under/around the ESP32 body
    d.add(Wire([(port_RLY_out[0] - 1.5, rly_in[1] - 0.5),
                (rly_in[0] - 1.0, rly_in[1] - 0.5)],
               color=BROWN, linewidth=2))
    d.add(e.Label().at((rly_in[0] - 1.0, rly_in[1] + 0.6)).label(
        'GPIO26 (brown)\n+ 10k pulldown\n at relay IN',
        loc='center', color=BROWN, fontsize=8))

    # Relay +5V feed (from same +5V bus)
    d.add(Wire([(port_5V_in[0] + 0.7, port_5V_in[1]),
                (port_5V_in[0] + 0.7, rly_5v[1]),
                rly_5v],
               color=RED, linewidth=2))

    # Ack button wire from GPIO27 to button
    d.add(Wire([port_ACK_in, (port_ACK_in[0] - 0.5, port_ACK_in[1]),
                (port_ACK_in[0] - 0.5, btn_out[1]),
                btn_out],
               color=GREY, linewidth=2))
    d.add(e.Label().at((port_ACK_in[0] - 0.6, port_ACK_in[1] - 0.3)).label(
        'GPIO27\n(grey)', loc='left', color=GREY, fontsize=8))

    # =============================================================
    # Legend + notes
    # =============================================================
    NOTES_Y = -10.5
    d.add(e.Label().at((NTC_X, NOTES_Y)).label(
        'Wire colour code (breadboard convention)\n\n'
        '  red     +5 V rail from PSU\n'
        '  orange  3V3 rail (regulated on the DevKitC)\n'
        '  black   GND / common bus\n'
        '  yellow  SPI SCK  (and MAX31855 TC leads)\n'
        '  green   SPI MISO\n'
        '  blue    SPI CS\n'
        '  purple  ADC1 input (GPIO34, dashed = via divider)\n'
        '  brown   relay drive (GPIO26)\n'
        '  grey    ack button, LED annotation',
        loc='right', halign='left', color='#333',
    ))

    d.add(e.Label().at((0.0, NOTES_Y)).label(
        'Physical build notes\n\n'
        '  * Full pin table is in WIRING.md (same directory).\n'
        '  * GPIO34 is INPUT-ONLY; do not use it for outputs.\n'
        '  * ADC2 pins (GPIO0/2/4/12-15/25-27) are unusable while Wi-Fi\n'
        '    is active. The NTC MUST be on ADC1 (GPIO32-39).\n'
        '  * GPIO26 needs an external 10 kOhm pulldown at the relay IN pin\n'
        '    so a floating GPIO (boot, crash, brown-out) equals relay OPEN.\n'
        '  * GND is a common bus: tie both ESP32 GND pins together, join\n'
        '    to PSU return, MAX31855 GND, and relay GND.\n\n'
        'Cross-references\n'
        '  Design-of-record schematic:  esp32_supervisor.svg\n'
        '  Coil-circuit ladder:         ladder_coil_circuit.svg\n'
        '  Mains one-line:              oneline_mains.svg\n'
        '  Full wiring table:           WIRING.md\n'
        '  Cable harness YAMLs:         ../harness/*.yml',
        loc='right', halign='left', color='#333',
    ))

    out_svg = HERE / 'esp32_pictorial.svg'
    d.save(str(out_svg))
    print(f'wrote {out_svg}')
