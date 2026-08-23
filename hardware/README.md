# Hardware

Physical build artifacts for the retrofit.

**Every diagram here is drawn for the hardware actually on hand.** The
end-state design — K-type + MAX31855, a GPIO-driven relay, a passive
thermostat, an isolated PSU module — lives in
[`../ARCHITECTURE.md`](../ARCHITECTURE.md) as prose and open TASKs. It
is deliberately not drawn, because a sheet full of parts nobody owns is
how a builder ends up wiring the wrong thing.

## Contents

| Path | Contents |
|---|---|
| [`schematic/`](schematic/) | Signal schematic, pictorial, coil-circuit ladder, mains one-line, and [`WIRING.md`](schematic/WIRING.md) — the pin-to-pin table. CircuiTikZ source + rendered SVGs. |
| [`harness/`](harness/) | Cable and mains-interconnect diagrams. Wireviz YAML source; render locally per the harness README. |
| [`photos/`](photos/) | As-built photographs, captioned. What is physically there, as opposed to what is drawn. |
| [`BOM.csv`](BOM.csv) | **The parts list.** ASINs, specs, purchase status, and which sheet each part appears on. Single source — the diagrams and prose reference it rather than restating it. |

## Where to start

| If you are… | Read |
|---|---|
| Wiring the board on the bench | [`schematic/WIRING.md`](schematic/WIRING.md), then [`schematic/esp32_pictorial.svg`](schematic/esp32_pictorial.svg) |
| Reviewing the safety logic | [`schematic/ladder_coil_circuit.svg`](schematic/ladder_coil_circuit.svg) |
| Working inside the starter enclosure | [`schematic/oneline_mains.svg`](schematic/oneline_mains.svg) + [`harness/fob_and_receiver.yml`](harness/fob_and_receiver.yml) |
| Mounting the probe | [`../archive/BUILD-TONIGHT.md § 6`](../archive/BUILD-TONIGHT.md) + [`harness/frame_probe.yml`](harness/frame_probe.yml) |
| Asking "what do we actually have?" | [`BOM.csv`](BOM.csv) |
| Asking "what is actually built?" | [`../BUILD-LOG.md`](../BUILD-LOG.md) + [`photos/`](photos/) |

## Three things the drawings exist to get right

1. **The board is powered over USB-C.** No VIN wire and no PSU module,
   so the only shared buses are 3V3 and GND — there is no 5 V rail.
   The USB charger is the isolation barrier, and it is fed from a wall
   outlet, not from the machine. Opening the machine disconnect
   therefore does *not* de-energise the supervisor.
2. **The NTC is the trip source, not an advisory sensor.** There is no
   K-type. Its 125 °C ceiling and PVC lead are why it lives on the
   motor frame rather than at the winding, and why thresholds come
   from an observed baseline instead of the 110 °C winding figure.
3. **The RF switch is line-powered and has no dry contact.** Four
   terminals as `AC IN L`/`N` + `AC OUT L`/`N`; the relay switches L
   only, so `AC IN L` is both the supply and the line side of the
   contact and has to stay permanently live. It sits at the head of
   the rung, not between the seal-in and the coil.

## Two traps the drawings exist to stop

- **Do not copy the VONVOFF's own wiring diagram onto the saw.** It
  runs the receiver's output straight to a contactor's coil terminals,
  which bypasses the 3-wire seal-in and lets the saw restart by itself
  when the RF link recovers. SR-4 forbids it. See the legend on
  `ladder_coil_circuit.svg`.
- **Do not trust the listing's "Contact Type: Normally Closed."**
  Settle it by observation during the momentary-mode check. A contact
  closed while nothing is transmitting inverts the entire fail-safe
  premise.

## Where the sheets are behind the build

The drawings are the design; [`../BUILD-LOG.md`](../BUILD-LOG.md) is the build. Three
things exist on the bench that no sheet shows yet, listed here so nobody reads a sheet as
current:

1. **The accessory 240 V receptacle.** Added off the incoming supply, deliberately outside
   the protected path. `oneline_mains.tex` does not have it. It also reopens the
   supervisor-supply question the same sheet currently answers — the legend says the ESP32
   is fed from a *separate wall outlet*, and if the charger moves to the new receptacle
   that legend becomes wrong in the one direction that matters, because it is the sentence
   telling a servicer whether the disconnect kills the supervisor.
2. **The connectorised probe.** The frame probe's factory JST now has its mate, so
   `frame_probe.yml`'s "cut it off and solder to the extension" note is stale as an
   instruction and survives only as history.
3. **The pigtailed fob.** Six conductors out of the fob board to a connector, both pads of
   each button among them. `fob_and_receiver.yml` still draws a single ON-pad and a fob
   ground, which is the harder version of the same thing.

Items 2 and 3 are corrected in the harness sources' prose already; item 1 needs a redraw,
and it should wait until the supply decision is made rather than being drawn twice.

One more, smaller: `esp32_supervisor.tex` now cites
[`../archive/BUILD-TONIGHT.md`](../archive/BUILD-TONIGHT.md) where that document moved, but
the committed `esp32_supervisor.svg` still carries the old path in its legend text. The
source is correct and the render is one `make` behind it — regenerate with the redraw
above rather than on its own.

## Open question the drawings flag rather than answer

**The A202C's coil voltage has not been read off the coil label.** It
decides what the control rails are and what the receiver's supply is
tapped from. The ladder and one-line say "control circuit hot /
return" rather than asserting a number. The receiver accepts AC
100–240 V single phase, so either answer works — the tap just has to
match.

## Intended structure (not yet created)

| Path | Purpose |
|---|---|
| `enclosure/` | 3D-printable brackets, panel cutouts, mounting fixtures — lands here when a physical build exists |
| `datasheets/` | PDF copies of datasheets for parts that get hard to find later — Marathon motor plate, Gould A202C wiring diagram, chosen thermostat |

[`photos/`](photos/) now exists and holds the first set. Still wanted there: the A202C
terminal block with the retrofit taps marked, the probe clamped in a fin channel, and the
enclosure interior once it is insulated, torqued and in its final location.

## Safety

Every wiring section in the design docs applies to any work in this
directory. See the DANGER block at the top of
[`../ARCHITECTURE.md`](../ARCHITECTURE.md) and
[`../archive/BUILD-TONIGHT.md § 3`](../archive/BUILD-TONIGHT.md).
