# Build log

The as-built record. [`README.md`](README.md) is the *why*, [`ARCHITECTURE.md`](ARCHITECTURE.md)
is the end-state design, [`NEXT-STEPS.md`](NEXT-STEPS.md) is the procedure being followed
and [`archive/BUILD-TONIGHT.md`](archive/BUILD-TONIGHT.md) is the reasoning behind it. Every one of those
describes an *intended* state. **This file is the only place that says how far along the
physical build actually is**, and nothing in the other documents should be read as a claim
that a part is fitted.

> **Nothing here has been commissioned.** No firmware has been flashed, no fault test has
> been run, and no threshold has been set from a measurement. Neither
> [ARCHITECTURE.md § Commissioning](ARCHITECTURE.md#commissioning) nor
> [BUILD-TONIGHT.md § 7](archive/BUILD-TONIGHT.md) has been performed. **Do not cut wood.**

---

## Status at a glance

Last updated **2026-08-26**.

| Subsystem | State | Detail |
|---|---|---|
| Starter / contactor (Gould ITE `A202C`) | **Installed and wired** in its enclosure | Terminations not yet insulated or torqued to the label figure. Not in its final location |
| Accessory 240 V outlet | **Installed**, fed from the incoming 220 V | Deliberately **outside** the protected path — see [below](#the-accessory-outlet-is-outside-the-protection) |
| Frame probe (DROK NTC, `RT1`) | **Connectorised** — mating JST fitted | Not mounted on the motor. Not calibrated |
| RF fob (`KA1`, remote half) | **Opened and pigtailed** to a connector | Level shifter not fitted. Battery rail not metered |
| RF receiver (`KA1`, mains half) | Not recorded here yet | Momentary-mode programming ([BUILD-TONIGHT.md § 4](archive/BUILD-TONIGHT.md)) is the gate before it goes near the coil rung |
| ESP32 (`U1`) | On the bench, unflashed, unwired | |
| Level shifter (`Q1`) and the three resistors (`R1`, `R2`, `R3`) | **Not on the bench** | Logged "to scrounge" in [`BOM.csv`](hardware/BOM.csv) and still unscrounged. **This blocks all of Path A's wiring** — see [below](#2026-08-26--the-path-a-passives-are-not-on-the-bench) |
| Firmware | Written; host tests pass in CI | **Never run on hardware.** [`firmware/README.md`](firmware/README.md) |
| Passive thermostat (`TS1`) | Not purchased — TASK-6 | **SR-3 is unmet.** Everything protective on the coil rung depends on the ESP32 |
| Winding sensor (`TC1`), GPIO relay (`KA2`), isolated PSU (`PSU1`) | Not purchased — TASK-1 / TASK-3 / TASK-2 | Path B is not startable |
| Fan shroud cleaned | Not recorded | Prerequisite, [README § Prerequisite work](README.md#prerequisite-work) |
| Overload heaters verified ≤ 16.5 A | Not recorded | Prerequisite, same section |

Purchase status for every part is in [`hardware/BOM.csv`](hardware/BOM.csv); this table is
about what is *fitted*, which is a different question.

---

## 2026-08-26 — the Path A passives are not on the bench

The three purchased assemblies — ESP32, frame probe, fob — are all on the bench. What is
not on the bench is `Q1`, `R1`, `R2` and `R3`, and each of Path A's three circuits is
blocked on one of them. `BOM.csv` has said "to scrounge" since it was written; this entry
records that the scrounging has not happened, because "to scrounge" reads as a formality
and these four are not one.

| Ref | Blocks | Why there is no way round it |
|---|---|---|
| `R1` | The entire sensing chain | A thermistor is a variable resistor, not a source. With no fixed resistor above it there is no divider and `GPIO34` has nothing to read. Nothing on-chip substitutes: `GPIO34` is input-only, and `GPIO34`–`GPIO39` have no internal pull resistors. `GPIO32`/`GPIO33` do, but a loosely specified, temperature-dependent internal pullup as the reference for the trip source defeats both the measured-`R1` requirement and the two-point calibration |
| `R2` | `GPIO26` | The mandatory pulldown. [`WIRING.md`](hardware/schematic/WIRING.md) § *Mandatory on every version* |
| `Q1`, `R3` | The fob drive | No GPIO touches a fob pad directly, and the rail voltage is still unmetered |

So the buildable work today is flashing, which needs only the board and a laptop.
Everything in [NEXT-STEPS.md](NEXT-STEPS.md) Step 3 waits on four cheap parts.

Nothing was built or unbuilt today. This entry exists because the parts list said
"to scrounge" and the bench says otherwise, and the gap between those two was not
written down anywhere.

---

## 2026-08-23 — starter installed, accessory outlet added, probe and fob connectorised

Photos: [`hardware/photos/`](hardware/photos/).

### The starter is installed

The `A202C` is mounted in its enclosure with the line, load and bonding conductors landed
on insulated terminals and the flexible entries made up. It is wired, not finished — the
builder's own next pass is to insulate the exposed terminations and torque every screw,
and the assembly still has to move to its final location.

The retrofit does not change any of this wiring. The coil rung it interposes into is
unchanged and undisturbed so far: [ARCHITECTURE.md § Control topology](ARCHITECTURE.md#control-topology)
describes what is there now, and [`hardware/schematic/ladder_coil_circuit.svg`](hardware/schematic/ladder_coil_circuit.svg)
describes what it becomes.

### The accessory outlet is outside the protection

A receptacle has been added off the incoming 220 V, deliberately **unprotected** — nothing
plugged into it is stopped by the overload relay, the supervisor, or the thermostat that
TASK-6 will add. That is a legitimate thing to want in a machine enclosure and a dangerous
thing to leave undocumented, because a receptacle bolted to a saw reads to everyone else as
part of the saw.

Two consequences that have to be settled before the ESP32 is wired:

1. **Label it, at the outlet.** Anything fed from it is running with no thermal protection
   and no contactor between it and the mains. It is not a place to plug in the dust
   collector and assume the saw's protection covers it.
2. **Decide whether the supervisor is fed from it.** Right now every drawing and every
   document says the ESP32's USB charger comes from a *separate wall outlet*, which means
   opening the machine disconnect leaves the supervisor powered — see
   [`hardware/schematic/README.md`](hardware/schematic/README.md) on `oneline_mains.svg`,
   and the `PS1` note in [`BOM.csv`](hardware/BOM.csv). Feeding the charger from this new
   outlet instead is what [ARCHITECTURE.md § Power supply](ARCHITECTURE.md#power-supply)
   asks for — supervisor power tied to the machine disconnect, one enclosure, nothing to
   unplug by accident — and it brings that section's tap requirements with it, the
   fuse included. Either answer is defensible. **What is not defensible is drawings that
   say one thing and an enclosure that does the other**, so whichever is built gets
   recorded here and the sheets get redrawn to match.

Neither the outlet nor its feed appears on any sheet in
[`hardware/schematic/`](hardware/schematic/) yet.

### The probe and the fob now plug in

Both low-voltage assemblies were connectorised so the ESP32 can be wired, unwired and
re-flashed without unsoldering anything:

- **Frame probe.** The DROK probe's factory JST XH 2.54 mm 2-pin lead now has its mate, so
  the earlier instruction to cut the connector off and solder to hookup wire no longer
  applies. [`WIRING.md`](hardware/schematic/WIRING.md) and
  [`frame_probe.yml`](hardware/harness/frame_probe.yml) are updated.
- **Fob.** The fob is open and its board — silkscreened `CYS02-E2` — is pigtailed out to a
  connector on six conductors: red and black at the cell holder, and a pair at each of the
  two button positions — yellow and orange at one, blue and green at the other. Bringing out
  *both* pads of a button is better than the single-pad-plus-shared-ground arrangement the
  documents assumed: a level shifter can sit straight across one button's pair with no
  common reference at all.

  **Nothing is proven about that pigtail until it is metered.** The colour-to-pad map above
  is read off photographs, and the fob's rail voltage is unknown — the harness file asserted
  a 12 V A23 cell and the board on the bench carries a coin-cell holder instead. Both facts
  go in [`WIRING.md`](hardware/schematic/WIRING.md) once measured, and until then the rule
  from [BUILD-TONIGHT.md § 3](archive/BUILD-TONIGHT.md) stands unchanged: **no GPIO touches a fob
  pad directly.**

---

## Next steps

**The procedure is [`NEXT-STEPS.md`](NEXT-STEPS.md)** — written for the people doing the
work, who are not electrically trained and are being guided through it on a call. It
carries annotated photographs, plain-language steps and stop conditions.

This table is the same six steps mapped to the reference document behind each, for anyone
who wants the underlying detail.

| # | Step | Follow |
|---|---|---|
| 1 | Insulate the exposed terminations and torque every screw | A202C label figure (#14–#10 at 35 in-lb). Lock out the disconnect first, and note that the accessory outlet is fed ahead of everything protective — dropping the contactor does not make that part of the enclosure dead |
| 2 | Flash the firmware | [`firmware/README.md`](firmware/README.md) — `./scripts/flash.sh all`, default environment `path_a` |
| 3 | Wire everything to the ESP32 | [`WIRING.md`](hardware/schematic/WIRING.md), then its sanity checklist. The 10 kΩ pulldown on GPIO26 is the one item with no substitute |
| 4 | Prove the firmware does what it claims | [BUILD-TONIGHT.md § 7](archive/BUILD-TONIGHT.md) bench tests, all of them, before anything goes on the motor. Plain-language version in [NEXT-STEPS.md](NEXT-STEPS.md) |
| 5 | Install everything in its final place | [ARCHITECTURE.md TASK-5](ARCHITECTURE.md#task-5--enclosure-placement) — out of the dust stream, not obstructing cooling airflow |
| 6 | Final insulation and tightening pass | Then re-run the § 7 fault tests, because the wiring moved |

Steps 2 and 3 are listed in the builder's order, and flashing first is fine: the board is
on the bench, and a flashed board is what step 3 needs. Once the board is *in* the
enclosure, the order inverts — see the warning at the top of
[`firmware/README.md`](firmware/README.md) about flashing an installed board.

---

## To confirm and record

Measurements and identifications the build cannot be finished without. Each one lands in
the document named beside it, not in this list.

| What | Blocks | Goes in |
|---|---|---|
| `A202C` coil voltage, off the coil label | The receiver's supply tap | [`hardware/README.md`](hardware/README.md) open question |
| Measured value of the divider resistor `R1` | Every temperature the board reports | `firmware/include/saw_calibration.h` |
| Two-point calibration of the frame probe | Thresholds meaning anything | Same file; `scripts/solve_beta.py` does the arithmetic |
| Fob rail voltage, and the pad map for the six pigtail conductors | Choosing and wiring the level shifter | [`WIRING.md`](hardware/schematic/WIRING.md) |
| Receiver momentary-mode hold time | The heartbeat's timing budget | [BUILD-TONIGHT.md § 4](archive/BUILD-TONIGHT.md) step 5 |
| Whether the receiver's contact is open with nothing transmitting | The entire fail-safe premise | Same step. If it is closed, **stop** |
| Accessory outlet: receptacle type and rating, conductor size, overcurrent protection, and whether it sits upstream or downstream of the machine disconnect | Its own safety, and the supervisor-supply decision | This file, then `oneline_mains.tex` |
| Which supply feeds the ESP32 — the new outlet or a separate wall outlet | [ARCHITECTURE.md § Power supply](ARCHITECTURE.md#power-supply) compliance | This file, then the sheets |
| Identity of the LED-bearing module visible in the enclosure photo | Nothing yet — but an as-built record with an unidentified powered device in it is not an as-built record | This file |
| Fan shroud cleaned; overload heaters ≤ 16.5 A | Every number the baseline run produces | This file |

---

## Safety gates still open

- **SR-3 is unmet.** No passive thermostat is fitted (TASK-6), so there is no protection
  that survives the ESP32 being unplugged. Until that part is in, the supervisor is not a
  supervisor — it is the only layer.
- **No commissioning has been performed.** Not one fault test, on either path.
- **The firmware has never run on hardware.** CI proves it compiles and that the state
  machine behaves; it proves nothing about this motor, this probe, or this receiver.
- **Thresholds are provisional.** The Path A numbers are placeholders until the baseline
  run sets them — [BUILD-TONIGHT.md § 7](archive/BUILD-TONIGHT.md) steps 8–9.
