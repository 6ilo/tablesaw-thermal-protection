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

Nothing yet.

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
- **Lockout callouts rendered inline.** Any code whose remediation means reaching into
  the fan shroud or opening the starter enclosure restates the lockout requirement in
  the page itself. The `README`'s warnings do not travel with the operator.
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
