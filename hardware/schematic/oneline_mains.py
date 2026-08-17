#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["schemdraw>=0.19"]
# ///
"""
One-line diagram — mains power distribution after retrofit.

Utility 240 V single-phase feeds the wall disconnect. Downstream:

  1. Motor branch:
       DISC -> 30 A fuses/breaker -> M1 contactor (Size 1) -> OL heater
            -> motor (3 HP, 145TC TEFC, Class F, 14.4 A FLA)

  2. Control-supply branch (RETROFIT ADDITION):
       tap after DISC -> 250 mA fuse -> isolated AC-DC PSU
                       -> 5 V SELV rail to ESP32 supervisor

The control branch is tapped on the load side of the DISC and the
line side of M1, so the ESP32 stays powered even when the motor coil
drops. That is intentional: the ESP32 must remain alive to log the
trip and hold the coil open until the operator acks.

Regenerate with:  uv run hardware/schematic/oneline_mains.py
"""

from pathlib import Path
import schemdraw
import schemdraw.elements as e

HERE = Path(__file__).parent


with schemdraw.Drawing(show=False) as d:
    d.config(fontsize=10, unit=2.0)

    # Layout constants (schemdraw units)
    MAIN_Y = 0.0                 # motor-branch horizontal
    CONTROL_Y = -4.0             # control-supply branch (below main)
    RETURN_Y = -7.5              # L2 return conductor
    NOTE_Y = -10.5               # notes block

    # Element x positions on the main line
    X_SRC = 0.0
    X_DISC_L = 2.5
    X_DISC_R = 4.5
    X_TAP = 6.0                  # control-branch tap point
    X_FUSE_L = 7.5
    X_FUSE_R = 9.5
    X_M1_L = 11.0
    X_M1_R = 13.0
    X_OL_L = 14.5
    X_OL_R = 16.5
    X_MOTOR = 18.5               # centre of motor circle

    # ---------------------------------------------------------
    # Utility source
    # ---------------------------------------------------------
    d.add(e.Label().at((X_SRC - 0.3, MAIN_Y + 0.5)).label('Utility\n240 V, 1Φ', loc='left'))
    d.add(e.Line().at((X_SRC, MAIN_Y)).to((X_DISC_L, MAIN_Y)).linewidth(2))

    # ---------------------------------------------------------
    # DISC — fused disconnect
    # ---------------------------------------------------------
    d.add(e.Switch().at((X_DISC_L, MAIN_Y)).to((X_DISC_R, MAIN_Y)).right())
    d.add(e.Label().at(((X_DISC_L + X_DISC_R) / 2, MAIN_Y + 1.4)).label(
        'DISC\n(fused disconnect,\nlockable)', loc='center'))

    # Main line continues to the tap
    d.add(e.Line().at((X_DISC_R, MAIN_Y)).to((X_TAP, MAIN_Y)).linewidth(2))
    d.add(e.Dot().at((X_TAP, MAIN_Y)))
    d.add(e.Label().at((X_TAP, MAIN_Y + 1.4)).label(
        'retrofit tap\n(load side of DISC,\nline side of M1)',
        loc='center', color='#666'))

    # Continue main line to fuse
    d.add(e.Line().at((X_TAP, MAIN_Y)).to((X_FUSE_L, MAIN_Y)).linewidth(2))

    # ---------------------------------------------------------
    # 30 A motor-branch fuse
    # ---------------------------------------------------------
    d.add(e.Fuse().at((X_FUSE_L, MAIN_Y)).to((X_FUSE_R, MAIN_Y)).right())
    d.add(e.Label().at(((X_FUSE_L + X_FUSE_R) / 2, MAIN_Y + 1.2)).label(
        '30 A\n(motor branch)', loc='center'))

    d.add(e.Line().at((X_FUSE_R, MAIN_Y)).to((X_M1_L, MAIN_Y)).linewidth(2))

    # ---------------------------------------------------------
    # M1 contactor
    # ---------------------------------------------------------
    d.add(e.Switch().at((X_M1_L, MAIN_Y)).to((X_M1_R, MAIN_Y)).right())
    d.add(e.Label().at(((X_M1_L + X_M1_R) / 2, MAIN_Y + 1.4)).label(
        'M1\n(contactor,\nNEMA Size 1)', loc='center'))
    d.add(e.Label().at(((X_M1_L + X_M1_R) / 2, MAIN_Y - 1.2)).label(
        '(driven by coil circuit)', loc='center', color='#666'))

    d.add(e.Line().at((X_M1_R, MAIN_Y)).to((X_OL_L, MAIN_Y)).linewidth(2))

    # ---------------------------------------------------------
    # OL heater (drawn as a resistor)
    # ---------------------------------------------------------
    d.add(e.Resistor().at((X_OL_L, MAIN_Y)).to((X_OL_R, MAIN_Y)).right())
    d.add(e.Label().at(((X_OL_L + X_OL_R) / 2, MAIN_Y + 1.2)).label(
        'OL\n(overload heater)', loc='center'))

    d.add(e.Line().at((X_OL_R, MAIN_Y)).to((X_MOTOR - 0.5, MAIN_Y)).linewidth(2))

    # ---------------------------------------------------------
    # Motor
    # ---------------------------------------------------------
    d.add(e.Motor().at((X_MOTOR - 0.5, MAIN_Y)).right().label(
        'M\n3 HP  14.4 A\n145TC TEFC\nClass F', loc='right'))

    # ---------------------------------------------------------
    # Control-supply branch (retrofit) — tap down to CONTROL_Y
    # ---------------------------------------------------------
    d.add(e.Line().at((X_TAP, MAIN_Y)).to((X_TAP, CONTROL_Y)).linewidth(2))

    # 250 mA fuse on the control branch
    X_CTRL_FUSE_L = X_TAP + 0.5
    X_CTRL_FUSE_R = X_CTRL_FUSE_L + 2.0
    d.add(e.Line().at((X_TAP, CONTROL_Y)).to((X_CTRL_FUSE_L, CONTROL_Y)).linewidth(2))
    d.add(e.Fuse().at((X_CTRL_FUSE_L, CONTROL_Y)).to((X_CTRL_FUSE_R, CONTROL_Y)).right())
    d.add(e.Label().at(((X_CTRL_FUSE_L + X_CTRL_FUSE_R) / 2, CONTROL_Y + 1.0)).label(
        '250 mA\n(control fuse)', loc='center'))

    # Isolated PSU
    X_PSU_L = X_CTRL_FUSE_R + 0.5
    X_PSU_R = X_PSU_L + 3.5
    d.add(e.Line().at((X_CTRL_FUSE_R, CONTROL_Y)).to((X_PSU_L, CONTROL_Y)).linewidth(2))
    d.add(e.RBox().at((X_PSU_L, CONTROL_Y)).to((X_PSU_R, CONTROL_Y)).right().label(
        'Isolated AC-DC PSU\n120 V AC → 5 V DC\n(Mean Well IRM-05-5\nor Recom RAC03-05SK)',
        loc='bottom'))

    # 5V rail out to ESP32 (draw in red to signal SELV)
    d.add(e.Line().at((X_PSU_R, CONTROL_Y)).to((X_PSU_R + 2.5, CONTROL_Y)).color('#d62728').linewidth(2))
    d.add(e.Label().at((X_PSU_R + 2.6, CONTROL_Y)).label(
        '+5V DC\n(SELV)\n=> ESP32 supervisor',
        loc='right', color='#d62728'))

    # ---------------------------------------------------------
    # L2 return — bottom horizontal back to source
    # ---------------------------------------------------------
    # Motor L2 out and down
    d.add(e.Line().at((X_MOTOR + 0.5, MAIN_Y)).to((X_MOTOR + 0.5, RETURN_Y)).linewidth(2))
    d.add(e.Line().at((X_MOTOR + 0.5, RETURN_Y)).to((X_SRC, RETURN_Y)).linewidth(2))
    d.add(e.Line().at((X_SRC, RETURN_Y)).to((X_SRC, MAIN_Y)).linewidth(2))
    d.add(e.Label().at(((X_MOTOR + X_SRC) / 2, RETURN_Y - 0.4)).label('L2', loc='center'))

    # Control return joins the same L2
    d.add(e.Line().at((X_PSU_R - 1.0, CONTROL_Y - 0.3)).to((X_PSU_R - 1.0, RETURN_Y)).linewidth(2))
    d.add(e.Dot().at((X_PSU_R - 1.0, RETURN_Y)))

    # ---------------------------------------------------------
    # Legend / notes — well below all the drawn geometry
    # ---------------------------------------------------------
    d.add(e.Label().at((X_SRC, NOTE_Y)).label(
        'What changed vs. OEM Powermatic:\n'
        '  • Klixon BEC2921 removed from motor internal circuit\n'
        '      (was: manual-reset thermal in series with winding lead)\n'
        '  • Passive bimetallic thermostat  → wired into coil circuit  (see ladder_coil_circuit.svg)\n'
        '  • ESP32 supervisor relay (KA)    → wired into coil circuit in series with the thermostat\n'
        '  • Control-supply tap             → 250 mA fuse + isolated AC-DC PSU feeds the ESP32 at 5 V DC\n\n'
        'Isolation:\n'
        '  • PSU input:     reinforced (UL 61010 / IEC 60950 rated part)\n'
        '  • PSU output:    SELV; ESP32 side referenced to enclosure ground\n'
        '  • ESP32 → coil:  opto-input + contact-gap on the relay module (double isolation)\n'
        '  • TC at winding: AlN dielectric substrate\n\n'
        'Not shown on this drawing:\n'
        '  • 3-wire seal-in start/stop network        → ladder_coil_circuit.svg\n'
        '  • ESP32 board-level wiring                 → esp32_supervisor.svg\n'
        '  • Motor-side sensor pigtail (TC + TSTAT)   → ../harness/motor_pigtail.yml\n'
        '  • Enclosure interior wiring                → ../harness/mains_and_coil.yml',
        loc='right', halign='left', color='#333',
    ))

    out_svg = HERE / 'oneline_mains.svg'
    d.save(str(out_svg))
    print(f'wrote {out_svg}')
