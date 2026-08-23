---
name: flash-esp32
description: Build, flash, and verify the table saw thermal supervisor firmware onto an ESP32 over USB from the terminal on macOS. Use when the user asks to flash, upload, reflash, program, or burn firmware to the ESP32 or "the board"; to run the firmware's tests; to watch the serial log or boot banner; to retune trip thresholds after a commissioning run; to pull the temperature log off the device; or to diagnose a board that will not connect, will not boot, or shows no serial port.
---

# Flashing the thermal supervisor

You are flashing firmware onto a device whose job is to stop a 3 HP table saw when its
motor overheats. Treat a bad flash as a safety event, not an inconvenience. The whole
procedure is `firmware/scripts/flash.sh`; your job is to run it, read what it says, and
diagnose anything it cannot.

**Everything here happens in the terminal.** No IDE, no Arduino app, no board manager.

## Before you touch the board

Work through these in order. Do not skip to flashing.

1. **Establish where the board is.** The board must be plugged into *this* machine over
   USB. If you are running anywhere other than the user's own Mac with the board attached,
   say so and stop — you cannot flash a board you are not physically connected to.

2. **Ask about mains, once, and only if it is not already settled.** Flashing resets the
   ESP32 and leaves GPIO26 floating during the upload. The mandatory 10 kΩ pulldown makes
   that safe (floating = not transmitting = contactor coil circuit open). So:

   - If the board is on the bench, unwired: flash away, no question needed.
   - If the board is installed in the saw's enclosure: confirm with `AskUserQuestion`
     that either the GPIO26 pulldown is fitted and verified, or the machine disconnect is
     locked out. Do not assume. `hardware/schematic/WIRING.md` § *Sanity checklist* is the
     reference.
   - Either way the saw must not be in use — the supervisor protects nothing while it is
     being written.

3. **Run the host tests.** They need no hardware and take about a second:

   ```bash
   cd firmware && ./scripts/flash.sh test
   ```

   76 tests over the state machine, the trip counter, the SR-5 sensor-validation rules,
   the NTC maths, the rate-of-rise fit and the LED patterns. **If any of them fail, stop
   and fix the cause. Do not flash a red build onto a saw.**

## Flashing

```bash
cd firmware
./scripts/flash.sh doctor      # toolchain, port, chip, flash size, chosen environment
./scripts/flash.sh flash       # build and upload
./scripts/flash.sh monitor     # watch the boot banner (ctrl-] to exit)
```

`./scripts/flash.sh all` chains doctor → test → flash. The script installs PlatformIO
via pipx if it is missing, finds the serial port, reads the real flash size off the chip
with esptool, and picks the matching partition table. Prefer it over raw `pio` commands —
it carries the safety confirmation and the port and partition logic.

### Choosing the build

Two hardware paths, and they are not interchangeable:

| Environment | When | Sensor | Output | Thresholds |
|---|---|---|---|---|
| `path_a` *(default)* | The hardware that exists today | DROK NTC on the motor **frame** | 433 MHz fob heartbeat into a receiver in momentary mode | 90 / 78 / 55 °C |
| `path_b` | Only once the MAX31855 + K-type, the wired opto-isolated relay and the thermostat are actually fitted | K-type at the **winding** | GPIO-driven wired relay | 110 / 95 / 70 °C |

`hardware/BOM.csv` records the Path B parts as **NOT PURCHASED**. Default to `path_a` and
only use `path_b` if the user states the parts are installed. Pass `--env path_b` to
choose. Flashing a Path B build onto Path A hardware produces a supervisor that reports a
sensor fault forever, because there is no MAX31855 on the SPI bus to answer.

### After flashing, read the boot banner

`monitor` prints it. Check four things and report them:

- **`self-test: N/10 valid reads (need 8)`** — fewer than 8 means the probe is not working
  and the firmware refused to arm. That is `E05`, and the LED will be showing SOS.
- **`reset reason`** — `power-on` after a flash is expected. `TASK WATCHDOG` or
  `panic / exception` on a *later* boot is a real defect worth chasing.
- **`calibration`** — a `*** DEFAULTS IN USE ***` line means the two-point calibration has
  not been done on this unit. The device works, but its temperatures are unverified. Say so
  plainly; do not let it pass silently.
- **The state transition to `ARMED`** — takes `COOLDOWN_HOLD` (120 s) from boot. Watch for
  the `[---] ARMED` line. Before that the contact is open, which is correct.

Log lines carry the error code from the registry in brackets, e.g.
`1234.567 [E01] OVERTEMP 111.25C n=1`. `docs/codes/E01.md` is the operator page for it.

## Other jobs this skill covers

**Retuning thresholds after the commissioning baseline run** (archive/BUILD-TONIGHT.md § 7 step 9).
Never edit the tracked defaults for a per-unit number; pass them at build time:

```bash
./scripts/flash.sh flash --trip 95 --warn 85 --reset 65
```

**The offline error-code pages**, served from the device so the operator's phone can read
remediation with no internet:

```bash
./scripts/flash.sh fs
```

**The dashboard**, from the terminal, once the Mac has joined the `ALN Table Saw` network:

```bash
curl -s http://saw.local/api/state | python3 -m json.tool
curl -s http://saw.local/api/events
./scripts/flash.sh logs              # pulls the 30-day CSV log
```

**Per-unit calibration** — `include/saw_calibration.h` is the only file that should be
edited for one physical board. `scripts/solve_beta.py` turns two bath readings into the
constants to put in it.

## When it goes wrong

| Symptom | Cause and fix |
|---|---|
| `No ESP32 serial port found` | Data cable, not charge-only. `ls /dev/cu.*` before and after plugging in. If nothing appears, the USB-UART chip needs a driver: identify it with `system_profiler SPUSBDataType`, then `brew install --cask silicon-labs-vcp-driver` (CP210x) or `wch-ch34x-usb-serial-driver` (CH34x/CH9102). Driver installs need a reboot and an approval in System Settings → Privacy & Security. |
| `Failed to connect to ESP32: Timed out waiting for packet header` | The board is not in download mode. Hold **BOOT**, tap **EN**, release BOOT, retry. Also try `--port` explicitly, and a different USB port or cable. |
| `Could not open /dev/cu.usbserial-…, the port is busy` | A monitor or another terminal still owns it. Close it — the script's `monitor` holds the port. |
| `A fatal error occurred: MD5 of file does not match` | Bad cable or an underpowered hub. Try a different cable and a direct port, and let the script lower `upload_speed` by passing `--env` with a slower environment if it persists. |
| Board boots, then reboots in a loop | Almost always an 8 MB partition table on a 4 MB chip. Run `doctor` to see the real size, then flash with `--env path_a` (the 4 MB layout, which is safe on both). |
| `Error: Please specify SAW_PATH_A or SAW_PATH_B` | Built without an environment. Use `-e path_a`, or just use the script. |
| `region 'iram0_2_seg' overflowed` / app too large | The binary outgrew a 1.5 MB OTA slot. Do not fix this by deleting protection code; report it. |
| Serial shows nothing at all | Wrong baud (it is 115200), or the board is not running. Check for the SOS LED pattern, which means the boot self-test failed. |
| Repeated `[E02] SENSOR_FAULT` on Path A | The NTC divider. Check GPIO34 is on ADC1, the divider resistor value in `saw_calibration.h`, and the probe connector. `docs/codes/E02.md`. |

## Rules

- **Never disable a safety check to make a build pass.** Not the watchdog, not the boot
  self-test, not the SR-5 sensor validation, not the `static_assert`s in `saw_config.h`.
  If one of them is in the way, the build is telling you something true.
- **Never raise `SAW_TRIP_C` to stop nuisance trips.** Repeated trips mean the fan shroud is
  packed with sawdust — the root cause of the original failure this project exists to
  address. `docs/codes/E01.md` explains why the threshold is where it is.
- **Never hand-edit `firmware/generated/error_codes.h`.** It is generated from `docs/codes/`
  by `tools/codedocs.py build`, and CI fails if it is stale.
- **Report what actually happened**, including a failed self-test or an uncalibrated build.
  A supervisor that is silently not protecting is worse than one that is obviously broken.
