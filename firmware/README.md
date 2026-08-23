# Firmware

ESP32 supervisor for the table saw thermal protection retrofit. Arduino-ESP32 under
PlatformIO, two build variants matching the project's two hardware paths, and the
protection logic split into a pure C++ core that runs its tests on a laptop.

`../ARCHITECTURE.md` is the spec. This directory is the implementation. Where they differ
deliberately, it is written down in [Deviations](#deviations-from-the-reference-pseudocode).

---

## Flash it

On a Mac, with the board on USB, from this directory:

```bash
./scripts/flash.sh all
```

That installs PlatformIO if needed, runs the host tests, finds the serial port, reads the
board's real flash size, picks the matching partition table, and uploads. Then:

```bash
./scripts/flash.sh monitor
```

Or ask Claude — the [`flash-esp32`](../.claude/skills/flash-esp32/SKILL.md) skill drives
the same script, reads the boot banner back, and knows the failure modes.

> **Before flashing an installed board.** The upload resets the ESP32 and leaves GPIO26
> floating. The 10 kΩ pulldown required by
> [`WIRING.md`](../hardware/schematic/WIRING.md) is what makes that safe — floating means
> not transmitting means the coil circuit is open. **If the pulldown is not fitted, lock
> out the machine disconnect first.** The supervisor protects nothing while it is being
> written, so the saw must not be in use either way.

### Commands

| Command | Does |
|---|---|
| `./scripts/flash.sh doctor` | Toolchain, port, chip, flash size, which environment it would pick, safety reminders |
| `./scripts/flash.sh test` | 76 host unit tests. No board required |
| `./scripts/flash.sh build` | Compile only |
| `./scripts/flash.sh flash` | Compile and upload |
| `./scripts/flash.sh fs` | Build and upload the offline error-code bundle to LittleFS |
| `./scripts/flash.sh monitor` | Serial log at 115200 |
| `./scripts/flash.sh logs` | Pull the long-term CSV log off the running board over Wi-Fi |
| `./scripts/flash.sh clean` | Drop build artifacts |

Options: `--env`, `--port`, `--trip`, `--warn`, `--reset`, `--yes`.

---

## The two builds

One state machine, one output pin, two sets of hardware hanging off it. GPIO26 means the
same thing in both: HIGH is *the contactor coil circuit may be closed*.

| | `path_a` (default) | `path_b` |
|---|---|---|
| Reference | [`BUILD-TONIGHT.md`](../BUILD-TONIGHT.md) | [`ARCHITECTURE.md`](../ARCHITECTURE.md) |
| Trip source | DROK 10K NTC on the motor **frame**, ADC1 | K-type at the **winding** via MAX31855, SPI |
| Advisory sensor | — | the frame NTC, demoted |
| Output | 433 MHz fob held transmitting into a receiver in momentary mode | wired opto-isolated active-HIGH relay |
| Trip / warn / reset | 90 / 78 / 55 °C, **provisional** | 110 / 95 / 70 °C |
| Passive backstop | none yet (SR-3 unmet) | bimetallic thermostat, 120–130 °C |

`path_a` is the default because it is the build the hardware exists for.
[`BOM.csv`](../hardware/BOM.csv) records the MAX31855, the relay module, the thermostat and
the isolated supply as **NOT PURCHASED**.

Add `_8mb` to either environment for a board with 8 MB of flash — it doubles the log
resolution. The 4 MB layouts are the default because they boot on either part, and an 8 MB
partition table on a 4 MB chip does not boot at all. `doctor` reads the real size.

> **Path A thresholds versus the operator pages.** [`docs/codes/`](../docs/codes/) quotes
> the Path B winding figures, because that is the end-state design. On a Path A build the
> numbers that are actually in force are the frame-temperature ones, and they are
> provisional until the baseline run in BUILD-TONIGHT.md § 7 steps 8–9. The dashboard and
> the boot banner both print the thresholds this unit is really running — trust those over
> any number in prose.

---

## Layout

```
firmware/
├── platformio.ini              five environments: four boards, one host
├── partitions_4mb.csv          two OTA slots + 896 KB LittleFS
├── partitions_8mb.csv          two OTA slots + 3.9 MB LittleFS
├── generated/
│   └── error_codes.h           GENERATED from docs/codes/. Committed, never hand-edited
├── include/
│   ├── saw_config.h            pin map, thresholds, variant selection. All #ifndef-guarded
│   ├── saw_calibration.h       PER-UNIT values. The one file meant to differ per board
│   ├── saw_hw.h                board I/O behind one header
│   ├── saw_protection.h        the core-0 task
│   ├── saw_runtime.h           the core-0 / core-1 boundary
│   ├── saw_store.h             NVS + LittleFS
│   └── saw_net.h               the advisory network layer
├── lib/saw_core/               PURE C++, no Arduino. Everything that decides to stop the saw
│   ├── saw_types.{h,cpp}       states, causes, event names (match the code registry)
│   ├── saw_sensor.{h,cpp}      SR-5 validation, and the E02 / E03 split
│   ├── saw_trip_counter.{h,cpp} rolling-window chatter suppression
│   ├── saw_state_machine.{h,cpp} the state machine and the hold-line invariant
│   ├── saw_ntc.{h,cpp}         β-equation and the two-point calibration solve
│   ├── saw_ror.{h,cpp}         least-squares rate of rise
│   └── saw_led.{h,cpp}         seven non-blocking LED patterns
├── src/
│   ├── main.cpp                setup() — drives GPIO26 low as its first statement
│   ├── saw_protection.cpp      core-0 loop: read → validate → step → drive → feed WDT
│   ├── saw_hw_io.cpp           hold line, LED, debounced ack button
│   ├── saw_sensor_ntc.cpp      ADC oversampling, primary on Path A
│   ├── saw_sensor_max31855.cpp SPI, fault bits, Path B primary
│   ├── saw_store.cpp           persisted state and the rotating log ring
│   ├── saw_runtime.cpp         seqlock snapshot, non-blocking for core 0
│   └── saw_net.cpp             AP, dashboard, JSON API, guarded OTA
├── test/                       host unit tests, one directory per suite
└── scripts/
    ├── flash.sh                the whole build-and-flash procedure
    └── solve_beta.py           two bath readings → calibration constants
```

The `lib/saw_core` / `src` split is the important structural decision. Everything that
decides whether the saw stops is in `saw_core`, has no Arduino dependency, and is exercised
by `pio test -e native` in about a second. `src/` is drivers and plumbing.

---

## Tests

```bash
pio test -e native          # or ./scripts/flash.sh test
```

76 assertions-heavy tests across six suites:

| Suite | Covers |
|---|---|
| `test_state_machine` | Every transition in the diagram, plus a 5000-step pseudo-random walk asserting that the contact is closed **only** in `ARMED` |
| `test_trip_counter` | Rolling window, boundary conditions, `millis()` rollover |
| `test_sensor_validation` | Each SR-5 fault class, NaN, the E02/E03 split, rollover |
| `test_ntc_math` | Known R/T pairs, divider direction, rails, β solve |
| `test_ror` | Known ramps, outlier resistance, window edges |
| `test_led_and_registry` | Pulse counts per pattern, and that every published error code is reachable from an event name the firmware can actually emit |

The last one is worth calling out: it walks `SAW_CODES` from the generated header and
asserts each `event` string resolves both ways. A typo in an event name is otherwise
invisible — the trip still happens, the relay still opens — and surfaces months later as a
log line with no code beside it and an operator with no page to read.

---

## Configuration

Everything in `saw_config.h` is `#ifndef`-guarded, so nothing needs a source edit:

```bash
# commissioning step 9: set thresholds from the observed baseline
./scripts/flash.sh flash --trip 95 --warn 85 --reset 65

# or directly
SAW_EXTRA_FLAGS="-DSAW_TRIP_C=95 -DSAW_AP_SSID='\"Shop Saw\"'" pio run -e path_a -t upload
```

`saw_calibration.h` is the exception — per-unit values belong in the file, committed, so
the board in the enclosure and the source in the repository agree. Until `SAW_CALIBRATED`
is set to 1 the boot log carries `UNCALIBRATED_BUILD` and the dashboard shows a banner.

---

## The dashboard

Advisory only (SR-8). The ESP32 runs an access point named `ALN Table Saw`; join it and
open `http://saw.local/` or `http://192.168.4.1/`.

| Endpoint | Returns |
|---|---|
| `/` | Dashboard: state, temperature, thresholds, alerts, 20-minute chart, event log, code table |
| `/api/state` | Current state as JSON, including the thresholds this unit is running |
| `/api/history` | The in-RAM chart series |
| `/api/events` | Recent event lines, newest first |
| `/api/codes` | The compiled-in error-code registry |
| `/api/log.csv` | The long-term log, streamed |
| `/api/ack` | `POST`. Clears alert bits. **The only mutating endpoint** |
| `/codes/…` | Offline operator pages, if `flash.sh fs` has been run |

`POST /api/ack` cannot clear a `MANUAL_LOCKOUT`, change a threshold, or close the contact.
There is no code in `saw_net.cpp` that could — the protection context is not visible from
that translation unit at all.

OTA is enabled but only serviced while the state is **not** `ARMED`. An update reboots the
board, which opens the contact; that is fail-safe, but it would stop the motor mid-cut, and
a supervisor interruptible from the network during a cut is not a supervisor.

---

## Logging

Two artifacts on LittleFS, sized from the partition table:

- **Sample ring** — one 16-byte CRC'd record per `SAW_LOG_PERIOD_S`, across eight rotating
  segments. 30 days at 120 s on the 4 MB layout, 60 s on the 8 MB one. A segment boundary
  is the only time an index is rewritten, which keeps flash wear off the hot path.
- **Event log** — every state transition and trip, as text, rotating across two
  generations. Trip events are what a builder reads months later, so the newest lines are
  never the ones dropped.

Records torn by a power loss mid-write fail their CRC and are skipped on read rather than
decoded into a plausible temperature.

---

## Deviations from the reference pseudocode

`ARCHITECTURE.md § Reference pseudocode` says "structure only — not intended to compile".
Four places where the implementation deliberately differs, and why.

**1. Trips are counted on the edge into `TRIPPED`, not once per loop iteration.**
The pseudocode calls `trip()` every cycle a fault persists and increments the counter
inside it. At `SAMPLE_HZ = 4` a single stuck sensor would reach `MAX_CONSECUTIVE_TRIPS` in
750 ms and lock out almost instantly. `E04` tells the operator "three trips inside ten
minutes", and chatter suppression exists to stop the relay cycling *repeatedly* — so a
persistent fault is one trip, and three separate fault-and-recover cycles are three.

**2. `SENSOR_TIMEOUT` emits its own cause, so `E03` can appear.**
The pseudocode routes the staleness check through the same `trip("SENSOR_FAULT")` call as
every other sensor fault, which the changelog and `E03.md` both flag as a gap. The split is
now on whether the sensing chain *answered*: an amplifier that keeps reporting an
open-circuit flag is answering, and stays `E02` forever, because the fault is in the probe.
A bus that has gone silent for `SENSOR_TIMEOUT` becomes `E03`, because the fault is in the
SPI link or the amplifier. That is exactly the distinction the two operator pages draw.

**3. The rolling window is anchored to the first trip of a burst, not to boot.**
The pseudocode leaves `first_trip_ms` at 0 until the window lapses, which measures the
first burst from power-up rather than from the first trip.

**4. The ack button is fitted on both paths.**
`BUILD-TONIGHT.md § 5` says a Path A lockout "clears only by power-cycling the ESP32", but
its own `setup()` pseudocode honours a persisted `MANUAL_LOCKOUT` across reboots — the two
statements contradict each other, and `E07` publishes the stricter one ("Power-cycling does
not clear a lockout"). Honouring the persisted lockout is the safe reading, so a build with
no ack input would have no way out of lockout at all. `SAW_HAS_ACK_BUTTON` therefore
defaults to 1 on both paths. On Path A the "button" can be a scrounged momentary switch, or
a bare wire touched from GPIO27 to GND.

Smaller choices that are additions rather than departures: `W01` latches with 2 °C of
hysteresis so a reading sitting on the threshold does not raise and clear an alert every
cycle; `W02` stays off entirely until `SAW_ROR_BASELINE_C_PER_MIN` is set from
commissioning step 10, because there is no honest way to say "faster than baseline" before
a baseline exists; and a `MAX31855` register reading all-zeros or all-ones is treated as *no
answer* rather than as 0 °C.

---

## What this firmware does not do

- **It does not replace the passive layer.** SR-3 is unmet until the bimetallic thermostat
  (TASK-6) is fitted. On a Path A build every protective function on the coil rung depends
  on this firmware continuing to run.
- **It cannot detect a probe that has fallen off but still reads shop ambient.** The
  `probe_verified` latch and `W03` are a partial mitigation, not a solution — see
  `BUILD-TONIGHT.md § 9`.
- **It does not measure current.** The starter's overload heaters do that, and their sizing
  (16.5 A maximum for this motor) is a prerequisite this firmware cannot check.
- **It has not been run on hardware.** Everything here is verified by the host test suite
  and by compilation in CI. The commissioning procedures in `ARCHITECTURE.md § Commissioning`
  and `BUILD-TONIGHT.md § 7` are the acceptance tests, and none of them has been performed.
  **Do not cut wood until they have been.** [`../BUILD-LOG.md`](../BUILD-LOG.md) tracks that,
  along with the per-unit numbers this firmware is waiting on: the measured divider
  resistor, the two-point calibration, and the baseline that sets the thresholds.
