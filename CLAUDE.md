# Working in this repository

A retrofit that replaces a failed Klixon thermal protector on a Powermatic table saw with
a bimetallic thermostat plus an ESP32 supervisory monitor. Read [README.md](README.md) for
the why and [ARCHITECTURE.md](ARCHITECTURE.md) for the design of record.

**This is safety-critical code for a machine that can take a hand off.** The bias
throughout is toward stopping the saw when anything is uncertain. A nuisance stop is an
acceptable outcome; a saw running with protection silently disabled is not.

## The eight safety requirements are not negotiable

[ARCHITECTURE.md § Safety requirements](ARCHITECTURE.md#safety-requirements) — SR-1 to
SR-8. Any change that appears to violate one of them is wrong until proven otherwise. In
firmware terms, the ones that constrain code most often:

- **SR-1 / SR-2.** GPIO26 is closed if and only if the state machine is in `ARMED`. It is
  written from the core-0 protection task and nowhere else. There is no code path from an
  HTTP request, an alert acknowledgement, or a threshold to that pin.
- **SR-5.** Any sensor doubt is a trip. No "last known good", no "assume ambient", no
  clamping an out-of-range reading into range.
- **SR-6.** The watchdog is fed only at the end of a complete successful cycle. Do not move
  the feed earlier to quiet a reset.
- **SR-8.** The network is advisory. `POST /api/ack` clears alert bits and is the only
  mutating endpoint in the firmware. It cannot clear a `MANUAL_LOCKOUT` — that needs the
  physical button, by design.

If a change genuinely requires relaxing one of these, say so explicitly and stop. Do not
work around it quietly.

## Flashing and firmware work

Use the **`flash-esp32`** skill. Short version, from `firmware/`:

```bash
./scripts/flash.sh test      # 76 host unit tests, no hardware needed
./scripts/flash.sh doctor    # toolchain, port, chip, flash size, chosen environment
./scripts/flash.sh flash     # build and upload over USB
./scripts/flash.sh monitor   # serial log
```

Default environment is `path_a` — the build for the hardware that actually exists.
`path_b` needs the MAX31855, the wired relay and the thermostat, all recorded as **NOT
PURCHASED** in [hardware/BOM.csv](hardware/BOM.csv). Do not switch to `path_b` unless the
user says those parts are fitted.

Run the host tests before proposing any firmware change. They are fast and they cover the
logic that decides whether the saw stops.

## Two things are generated. Never edit them by hand

| File | Generated from | Regenerate with |
|---|---|---|
| `firmware/generated/error_codes.h` | `docs/codes/*.md` | `python3 tools/codedocs.py build` |
| `docs/codes/README.md` | `docs/codes/*.md` | `python3 tools/codedocs.py build` |

CI fails if either is stale. `python3 tools/codedocs.py check` is the gate, and it is
strict on purpose: it parses the thresholds and LED patterns out of `ARCHITECTURE.md` and
fails the build if any operator document quotes a number that disagrees. An operator
reading a stale threshold off a screen at a machine is the failure that pipeline exists to
prevent.

**Error codes are append-only.** A published code never changes meaning and is never
reused, because it may be printed on the card inside the cabinet door. Adding one is
documented in [docs/codes/README.md](docs/codes/README.md) § *Adding a code*.

## Where things live

| Path | What |
|---|---|
| `ARCHITECTURE.md` | Design of record — Path B, the end state |
| `BUILD-TONIGHT.md` | Path A, the same-day build from parts on hand |
| `firmware/lib/saw_core/` | Protection logic, pure C++, no Arduino. Host-testable |
| `firmware/src/` | Arduino glue — drivers, tasks, dashboard |
| `firmware/include/saw_config.h` | Pin map and thresholds, all `#ifndef`-guarded |
| `firmware/include/saw_calibration.h` | **Per-unit** values. The only file that is meant to differ between boards |
| `firmware/test/` | Host unit tests |
| `docs/codes/` | Operator-facing fault pages, single source for three artifacts |
| `hardware/` | Schematics, harnesses, BOM — drawn for the parts on hand |

Prefer putting new protection logic in `lib/saw_core/` with a test, not in `src/`. The
split exists so the decisions that stop the saw can be exercised without hardware.

## Documentation conventions

- `ARCHITECTURE.md` is the spec; the code is the implementation. Resolve any divergence by
  updating the spec first, then the code — and say which one you changed.
- Where the firmware deliberately departs from the reference pseudocode, it is recorded in
  [firmware/README.md § Deviations](firmware/README.md#deviations-from-the-reference-pseudocode)
  with the reasoning. Add to that list rather than leaving a silent difference.
- Never state a fact the repository does not establish. Several parts are unpurchased and
  several measurements unmade; write around that rather than inventing a number.
- Threshold values live in exactly one place per path. If you find yourself typing `110`
  into prose, link to the table instead.
