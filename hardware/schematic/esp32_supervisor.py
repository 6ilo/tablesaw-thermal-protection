#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["schemdraw>=0.19"]
# ///
"""
ESP32 supervisor — low-voltage side schematic.

Board-level view of the enclosure interior: isolated 5 V rail feeding
the ESP32, MAX31855 SPI thermocouple front-end, NTC frame-temperature
divider, opto-isolated relay module driving the contactor coil circuit,
local ack button, onboard status LED.

Nothing on this drawing sits at mains potential. Isolation boundaries
are external to the sheet: reinforced-isolation AC-DC PSU, AlN
substrate at the winding, opto-input / contact-gap output on the
relay module.

Regenerate with:  uv run hardware/schematic/esp32_supervisor.py
"""

from pathlib import Path
import schemdraw
import schemdraw.elements as e

HERE = Path(__file__).parent

# Uniform pin pitch so ICs align cleanly with L-shape wires.
PITCH = 1.0

with schemdraw.Drawing(show=False) as d:
    d.config(fontsize=10, unit=2.0)

    # ============================================================
    # ESP32
    # ============================================================
    esp = e.Ic(
        pins=[
            # left: power
            e.IcPin(name='VIN',  side='L', pin='+5V'),
            e.IcPin(name='GND1', side='L', pin='GND'),
            e.IcPin(name='V33',  side='L', pin='3V3'),
            e.IcPin(name='GND2', side='L', pin='GND'),
            # right: signals
            e.IcPin(name='SCK',  side='R', pin='GPIO18'),
            e.IcPin(name='MISO', side='R', pin='GPIO19'),
            e.IcPin(name='CS',   side='R', pin='GPIO5'),
            e.IcPin(name='ADC',  side='R', pin='GPIO34'),
            e.IcPin(name='RLY',  side='R', pin='GPIO26'),
            e.IcPin(name='ACK',  side='R', pin='GPIO27'),
            e.IcPin(name='LED',  side='R', pin='GPIO2'),
        ],
        edgepadW=0.5,
        edgepadH=0.5,
        pinspacing=PITCH,
        w=4.5,
        label='ESP32-\nDevKitC-32E',
    ).at((3, 0)).anchor('VIN')
    d += esp

    # +5V feed to ESP32 VIN (short stub with label)
    d += e.Line().at(esp.VIN).left().length(2.0)
    d += e.Label().label('+5V (isolated PSU)', loc='left')
    d += e.Dot().at(esp.VIN)

    # ESP32 grounds → common ground
    d += e.Line().at(esp.GND1).left().length(1.0)
    d += e.Line().down().toy(esp.GND2.y)
    d += e.Line().right().tox(esp.GND2.x)
    d += e.Dot().at(esp.GND2)
    d += e.Line().at(esp.GND1).left().length(1.0)  # re-anchor to draw ground symbol
    gnd_pos = (esp.GND1.x - 1.0, esp.GND1.y)
    d += e.Ground().at(gnd_pos)

    # 3V3 rail — short stub, we'll tap it from two consumers via labels
    d += e.Line().at(esp.V33).left().length(1.2)
    d += e.Label().label('3V3', loc='left')
    d += e.Dot().at(esp.V33)

    # ============================================================
    # MAX31855 — SPI thermocouple front-end
    # ============================================================
    mx = e.Ic(
        pins=[
            e.IcPin(name='SCK', side='L', pin='SCK'),
            e.IcPin(name='DO',  side='L', pin='DO'),
            e.IcPin(name='CS',  side='L', pin='CS'),
            e.IcPin(name='VCC', side='T', pin='VCC'),
            e.IcPin(name='GND', side='B', pin='GND'),
            e.IcPin(name='TP',  side='R', pin='T+'),
            e.IcPin(name='TM',  side='R', pin='T-'),
        ],
        edgepadW=0.5,
        edgepadH=0.5,
        pinspacing=PITCH,
        w=3.0,
        label='MAX31855',
    ).at((esp.SCK.x + 4, esp.SCK.y)).anchor('SCK')
    d += mx

    # SPI: all three ESP32 pins are at the same pitch as MAX31855, so
    # ESP32.SCK <-> MX.SCK is a straight horizontal line, MISO <-> DO
    # is one pitch below (straight), CS <-> CS two pitches (straight).
    d += e.Line().at(esp.SCK).to(mx.SCK)
    d += e.Line().at(esp.MISO).to(mx.DO)
    d += e.Line().at(esp.CS).to(mx.CS)

    # MAX31855 3V3 supply (label rather than a long wire)
    d += e.Line().at(mx.VCC).up().length(1.0)
    d += e.Label().label('3V3', loc='top')

    d += e.Line().at(mx.GND).down().length(1.0)
    d += e.Ground()

    # Thermocouple leads → external winding pigtail
    d += e.Line().at(mx.TP).right().length(2.0)
    d += e.Label().label('TC+ (yellow)\nto winding K-type', loc='right')
    d += e.Line().at(mx.TM).right().length(2.0)
    d += e.Label().label('TC- (red)\nto winding K-type', loc='right')

    # ============================================================
    # NTC frame divider: 3V3 → 10k → GPIO34 → NTC 10k → GND
    # ============================================================
    d += e.Dot().at(esp.ADC)
    # Pullup: from GPIO34 upward to a 3V3 label
    d += e.Resistor().at(esp.ADC).up().length(2.0).label('10k 1%', loc='right')
    d += e.Line().up().length(0.6)
    d += e.Label().label('3V3', loc='top')

    # NTC leg: from GPIO34 right to an intermediate node, then down through
    # the thermistor to ground. Keeps the NTC clear of the pullup drawing.
    d += e.Line().at(esp.ADC).right().length(1.5)
    d += e.Thermistor().down().length(2.0).label('NTC 10k\nB3950\n(frame)', loc='right')
    d += e.Line().down().length(0.5)
    d += e.Ground()

    # ============================================================
    # Relay module (opto-isolated, active-HIGH), 10k pulldown on IN
    # ============================================================
    d += e.Line().at(esp.RLY).right().length(2.5)
    d += e.Dot()
    branch_x = esp.RLY.x + 2.5

    # 10k pulldown from GPIO26-branch to GND
    d += e.Resistor().down().length(2.0).label('10k\npulldown', loc='right')
    d += e.Ground()

    # Continue right into the relay IN
    relay = e.Ic(
        pins=[
            e.IcPin(name='IN',  side='L', pin='IN'),
            e.IcPin(name='VCC', side='T', pin='VCC'),
            e.IcPin(name='GND', side='B', pin='GND'),
            e.IcPin(name='COM', side='R', pin='COM'),
            e.IcPin(name='NO',  side='R', pin='NO'),
            e.IcPin(name='NC',  side='R', pin='NC'),
        ],
        edgepadW=0.5,
        edgepadH=0.5,
        pinspacing=PITCH,
        w=3.5,
        label='Relay module\nopto-isolated\nactive-HIGH\nN.O.',
    ).at((branch_x + 2.0, esp.RLY.y)).anchor('IN')
    d += relay

    # Wire from the branch point to relay.IN
    d += e.Line().at((branch_x, esp.RLY.y)).to(relay.IN)

    # Relay VCC/GND
    d += e.Line().at(relay.VCC).up().length(1.0)
    d += e.Label().label('+5V', loc='top')
    d += e.Line().at(relay.GND).down().length(1.0)
    d += e.Ground()

    # Relay contacts → external mains-side terminals
    d += e.Line().at(relay.COM).right().length(2.0)
    d += e.Label().label('COM →\nthermostat NC contact', loc='right')
    d += e.Line().at(relay.NO).right().length(2.0)
    d += e.Label().label('NO →\ncontactor coil', loc='right')
    d += e.Line().at(relay.NC).right().length(2.0)
    d += e.Label().label('(NC — leave open)', loc='right')

    # ============================================================
    # Ack button — GPIO27 to GND, firmware enables internal pullup
    # ============================================================
    d += e.Line().at(esp.ACK).right().length(2.5)
    d += e.Button().down().length(1.5).label('ACK\nbutton', loc='right')
    d += e.Ground()

    # ============================================================
    # Status LED — GPIO2 onboard on DevKitC
    # ============================================================
    d += e.Line().at(esp.LED).right().length(2.5)
    d += e.Label().label('→ onboard blue LED (DevKitC)', loc='right')

    # ============================================================
    # Sheet notes — plain text block below the schematic
    # ============================================================
    d += e.Label().label(
        'Table saw thermal supervisor — low-voltage side (5 V / 3.3 V)\n\n'
        'Isolation boundaries external to this sheet:\n'
        '  - AC-DC PSU input: reinforced isolation (Mean Well IRM-05-5 or equivalent)\n'
        '  - Thermocouple:  AlN substrate at winding, dielectric to line potential\n'
        '  - Relay:         opto-input / contact-gap output\n\n'
        'SR-1: relay is NO, energized-to-close. Floating GPIO26 = relay open.\n'
        'SR-3: passive thermostat is in series ahead of the relay COM (mains side).\n\n'
        'Not shown: mains coil circuit (see hardware/harness/mains_and_coil.svg).'
    ).at((esp.GND2.x - 2, esp.GND2.y - 5)).left()

    out_svg = HERE / 'esp32_supervisor.svg'
    d.save(str(out_svg))
    print(f'wrote {out_svg}')
