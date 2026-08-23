# Changelog

Notable changes to this project, newest first. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## What the version number covers

[`VERSION`](VERSION) is the **error code registry** version, not a hardware or firmware
release. It exists because three artifacts have to agree with each other — the pages on
GitHub, the offline copies bundled into the ESP32, and the card printed and taped inside
the cabinet door — and a version number is how you tell whether they do.

| Bump | When |
|---|---|
| **Major** | A published code changes meaning, or is retired. This should never happen. Codes are append-only precisely so that a card printed two years ago is still correct. |
| **Minor** | New codes added, or a new required front-matter field. Existing codes keep their meaning; an old printed card is incomplete but not wrong. |
| **Patch** | Wording, corrections, tooling. No change to what any code means. |

Hardware and firmware changes that do not touch the registry are recorded here without a
version bump.

---

## [Unreleased]

No registry version bump: no code changes meaning, and no code is added or retired. The
firmware landing and the hardware progress below are hardware/firmware changes, and the two
operator-page edits are corrections to text that described a firmware limitation that no
longer exists.

### Added

- **[`BUILD-LOG.md`](BUILD-LOG.md) — the as-built record.** The repository had five
  documents describing intended states and none describing the built one, which is how a
  reader ends up assuming a part is fitted because it is drawn. The log carries what is
  actually installed, the next steps, the measurements each one is waiting on, and the
  safety gates still open. Every other document now defers to it on build state, and
  [`CLAUDE.md`](CLAUDE.md) says so first.
- **[`hardware/photos/`](hardware/photos/)** — captioned photographs, the directory
  `hardware/README.md` had listed as intended. Starter enclosure, and the fob board before
  and after it was pigtailed.
- **Hardware progress recorded:** the `A202C` starter is installed and wired in its
  enclosure; an accessory 240 V receptacle has been added off the incoming supply,
  deliberately outside the protected path; and the frame probe and the RF fob are both
  connectorised so the ESP32 can be wired, unwired and re-flashed without unsoldering
  anything. Nothing is flashed, nothing is commissioned.
- **The accessory receptacle is documented as unprotected** in
  [`ARCHITECTURE.md § Power supply`](ARCHITECTURE.md#power-supply), in the README's operator
  section, and as `X1` in [`BOM.csv`](hardware/BOM.csv). It does not close TASK-2 and it is
  not the supervisor supply — but it *could* be, and that decision now sits in the open
  questions rather than being made silently by whichever outlet is nearest.
- **[`firmware/`](firmware/) — the ESP32 supervisor, written.** Arduino-ESP32 under
  PlatformIO, with two build environments matching the project's two hardware paths:
  `path_a` (frame NTC + 433 MHz heartbeat, per [`BUILD-TONIGHT.md`](BUILD-TONIGHT.md)) and
  `path_b` (winding K-type via MAX31855 + wired relay, per
  [`ARCHITECTURE.md`](ARCHITECTURE.md)). One state machine and one output pin serve both;
  GPIO26 means "the coil circuit may be closed" in either case.
- **Protection logic as a host-testable core.** Everything that decides whether the saw
  stops lives in `firmware/lib/saw_core/` as pure C++ with no Arduino dependency — the state
  machine, the SR-5 validation rules, the rolling-window trip counter, the β-equation, the
  rate-of-rise fit and the LED pattern engine. 76 unit tests run on a laptop in about a
  second via `pio test -e native`, including a 5000-step pseudo-random walk that asserts the
  contact is closed **only** in `ARMED`, and a check that every published error code is
  reachable from an event name the firmware can actually emit.
- **One-command flashing from a terminal.** `firmware/scripts/flash.sh` installs
  PlatformIO if absent, finds the serial port, reads the board's real flash size with
  esptool, picks the matching partition table, runs the tests, and uploads. Companion
  [`flash-esp32`](.claude/skills/flash-esp32/SKILL.md) skill and [`CLAUDE.md`](CLAUDE.md) so
  the whole procedure can be driven by asking for it.
- **Local dashboard and log.** An `ALN Table Saw` access point serving live state, a
  20-minute chart, the event log and the offline error-code bundle, plus a rotating flash
  ring holding 30 days of aggregated samples and a streamable CSV export. Advisory only:
  `POST /api/ack` clears alert bits and is the only mutating endpoint in the firmware.
- **[`.github/workflows/firmware.yml`](.github/workflows/firmware.yml)** — host tests plus a
  real compile of all four board environments on every change, and a staleness gate on the
  generated header.

### Changed

- **The fob's "12 V A23 cell" is withdrawn, not corrected.**
  [`fob_and_receiver.yml`](hardware/harness/fob_and_receiver.yml) asserted a rail voltage
  that came from the general class of part rather than from this one; the fob on the bench
  carries a coin-cell holder. Nothing about the design changes — an optocoupler is right at
  any rail voltage — but an unverified number that a GPIO could be wired to should not be
  sitting in a harness source, so it is marked unmeasured in the harness file,
  [`WIRING.md`](hardware/schematic/WIRING.md), `BUILD-TONIGHT.md § 2` and the BOM, with the
  "no GPIO touches a fob pad" rule restated on the honest grounds: not that 12 V is certain,
  but that the number is unknown.
- **"Cut the probe's JST off" is no longer the instruction.** The mate is fitted.
  `BUILD-TONIGHT.md § 3`, `WIRING.md` and
  [`frame_probe.yml`](hardware/harness/frame_probe.yml) updated; the old note survives as
  history rather than as a step.
- **The fob pigtail brings out both pads of each button**, so the level shifter needs no
  ESP32-to-fob ground tie at all. The optocoupler and NPN tables in `WIRING.md` and
  `BUILD-TONIGHT.md § 3` are rewritten around the pair, with the single-pad wiring kept as
  the fallback it now is.
- **The sheets are marked as behind the build** rather than silently stale.
  [`hardware/README.md`](hardware/README.md) lists the three things on the bench that no
  sheet shows, and `oneline_mains.svg`'s "separate wall outlet" legend is flagged in
  [`schematic/README.md`](hardware/schematic/README.md) as the sentence that goes wrong if
  the charger moves to the new receptacle. The redraw waits on the supply decision, so the
  sheet is drawn once rather than twice.
- **`error_codes.h` is now committed at
  [`firmware/generated/`](firmware/generated/error_codes.h)** rather than written into the
  gitignored `build/`. The firmware has to compile on a machine that has PlatformIO and no
  Python doc toolchain — that is the premise of "plug the board in and flash it" — so the
  header is generated deterministically and CI fails if it drifts, exactly as
  `docs/codes/README.md` already did.
- **`E03` is now reachable.** The 1.0.0 notes recorded that the reference pseudocode routed
  the staleness check through the same `trip("SENSOR_FAULT")` call as every other sensor
  fault, so `E02` and `E03` could not be told apart. The firmware splits them on whether the
  sensing chain *answered*: an amplifier reporting an open-circuit flag answers every cycle
  and stays `E02`, while a bus silent for `SENSOR_TIMEOUT` becomes `E03`. `ARCHITECTURE.md`'s
  pseudocode and [`E03.md`](docs/codes/E03.md)'s firmware note are updated to match.
- **The ack button is fitted on both build paths.** `BUILD-TONIGHT.md` § 5 claimed a Path A
  lockout "clears only by power-cycling the ESP32" while its own `setup()` pseudocode
  honoured a persisted `MANUAL_LOCKOUT` across reboots — a contradiction, and `E07`
  publishes the stricter reading. Honouring the persisted lockout is the safe behaviour, so
  a build with no ack input would have no way out of lockout at all. `BUILD-TONIGHT.md` and
  [`WIRING.md`](hardware/schematic/WIRING.md) now describe the GPIO27 input, which on Path A
  can be any scrounged momentary switch or a bare wire touched to GND.
- **The registry index now flags the Path A / Path B threshold difference.** The code pages
  quote the winding figures; a Path A unit measures the frame at lower, provisional numbers,
  and prints what it is really running in its boot log and on its dashboard.

## [1.0.0] — 2026-08-17

First versioned release of the error code registry. Establishes
[`docs/codes/`](docs/codes/) as the single source for every operator-facing fault
message, and a build pipeline that makes "never hand-copied" enforceable rather than
aspirational. Implements the documentation half of
[#1](https://github.com/6ilo/tablesaw-thermal-protection/issues/1).

### Added

- **Error code registry** — eleven codes covering every fault, lockout, and advisory the
  supervisor can report:
  - `E01` motor overtemperature, `E02` sensor fault, `E03` sensor timeout,
    `E04` manual lockout, `E05` boot self-test failure, `E06` boot hot hold,
    `E07` boot into lockout, `E08` ack rejected while hot
  - `W01` approaching trip, `W02` heating faster than baseline,
    `W03` probe unverified at armed time
  - Each carries operator remediation written to be read on a phone, at the machine,
    with no internet — not a description of the fault, but what to do about it.
- **[`tools/codedocs.py`](tools/codedocs.py)** — generates three artifacts from that one
  source: the browsable index, the offline HTML bundle for the ESP32, and
  `error_codes.h` so the device's code table cannot drift from the docs.
- **Validation gate** (`codedocs.py check`, wired to CI). Beyond schema and cross-link
  checking, it parses the thresholds and LED patterns out of
  [`ARCHITECTURE.md`](ARCHITECTURE.md) and fails the build if any operator doc quotes a
  value that disagrees with the design of record. Twenty-four constants and seven LED
  patterns are cross-checked on every run.
- **Offline-first page rendering** — self-contained HTML, inline CSS, no JavaScript, no
  external requests, light and dark themes, gzip-precompressed with a manifest. QR codes
  are generated on-device-build with [segno](https://pypi.org/project/segno/), because a
  phone joined to the saw's access point has no route to github.com.
- **Lockout callouts rendered inline.** Every code whose remediation requires locking out
  the disconnect restates that requirement in the page itself rather than linking to it —
  the `README`'s warnings do not travel with the operator. Codes where a lockout would be
  actively *wrong* say so instead: clearing a lockout needs the disconnect **on**, because
  the supervisor is powered from downstream of it and a locked-out supervisor cannot see
  the ack press.
- **[`.github/workflows/error-codes.yml`](.github/workflows/error-codes.yml)** — runs the
  gate, proves the bundle builds, verifies the committed index is current, and enforces a
  100 KiB gzipped flash budget so the docs cannot quietly grow into the log ring buffer's
  30-day retention or the OTA app slots.
- **[`VERSION`](VERSION)** and this changelog.

### Notes for implementers

Two things the registry assumes that the reference pseudocode does not yet do:

- **`E02` and `E03` are not currently distinguishable.** The protection loop routes the
  staleness check through the same `trip("SENSOR_FAULT")` call as open-circuit, short,
  out-of-range, and implausible-jump faults. The registry treats a stale reading as a
  separate code because it points at different hardware — the SPI bus and amplifier
  rather than the thermocouple. The timeout branch needs to emit its own cause before
  `E03` can ever appear.
- **Warnings have no LED.** `W01`, `W02`, and `W03` all leave the status LED solid, by
  design — the saw is still running. They are visible only on the web page, which is the
  argument for the page existing at all.

### Prior history

Work before this release is in the git log and was not versioned: initial design docs,
BOM verification against actual purchases, the same-day
[`BUILD-TONIGHT.md`](BUILD-TONIGHT.md) path, the isolated power supply section, and the
`hardware/` schematic and harness sources.
