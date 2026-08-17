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
| [`BOM.csv`](BOM.csv) | **The parts list.** ASINs, specs, purchase status, and which sheet each part appears on. Single source — the diagrams and prose reference it rather than restating it. |

## Where to start

| If you are… | Read |
|---|---|
| Wiring the board on the bench | [`schematic/WIRING.md`](schematic/WIRING.md), then [`schematic/esp32_pictorial.svg`](schematic/esp32_pictorial.svg) |
| Reviewing the safety logic | [`schematic/ladder_coil_circuit.svg`](schematic/ladder_coil_circuit.svg) |
| Working inside the starter enclosure | [`schematic/oneline_mains.svg`](schematic/oneline_mains.svg) + [`harness/fob_and_receiver.yml`](harness/fob_and_receiver.yml) |
| Mounting the probe | [`../BUILD-TONIGHT.md § 6`](../BUILD-TONIGHT.md) + [`harness/frame_probe.yml`](harness/frame_probe.yml) |
| Asking "what do we actually have?" | [`BOM.csv`](BOM.csv) |

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
| `photos/` | Annotated photos of the built system (A202C terminal block with retrofit taps marked, probe clamped in a fin channel, enclosure interior) |
| `datasheets/` | PDF copies of datasheets for parts that get hard to find later — Marathon motor plate, Gould A202C wiring diagram, chosen thermostat |

## Safety

Every wiring section in the design docs applies to any work in this
directory. See the DANGER block at the top of
[`../ARCHITECTURE.md`](../ARCHITECTURE.md) and
[`../BUILD-TONIGHT.md § 3`](../BUILD-TONIGHT.md).
