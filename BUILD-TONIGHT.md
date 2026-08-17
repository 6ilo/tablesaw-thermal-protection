# Build Tonight — Fail-Safe Thermal Cutout, Parts On Hand

**Constraint:** 9 hours. Parts are fixed. No shopping except one transistor.

**What this delivers:** a fail-safe overtemperature cutout on the table saw motor, using frame-temperature sensing and a heartbeat RF link. Every fault path stops the saw.

**What this defers:** winding-temperature sensing, passive thermostat backstop. See §9.

---

## 1. Architecture

```
NTC probe on motor frame
        │
        ▼
   ESP32  ──(transistor)──▶  433 MHz fob  ))) ▶  Receiver (MOMENTARY mode)
   in old switch compartment                          │
   powered by USB charger                             ▼
                                          relay contacts in series
                                          with contactor coil
```

**The fail-safe principle:** the receiver is programmed to **momentary** mode. Its relay is closed *only while receiving*. The ESP32 holds the fob button continuously while the motor is safe. Anything that stops transmission opens the relay.

| Fault | Result |
|---|---|
| ESP32 loses power | TX stops → relay opens → saw stops |
| Firmware hangs | Watchdog stops TX → relay opens → saw stops |
| Sensor fails/detaches | Firmware stops TX → relay opens → saw stops |
| Fob battery dies | TX stops → relay opens → saw stops |
| RF jammed or out of range | No signal → relay opens → saw stops |
| Overtemperature | Firmware stops TX → relay opens → saw stops |

There is no failure that leaves the saw running unprotected. Failures produce nuisance stops, which is the correct direction.

**Restart is always manual.** The A202C's 3-wire seal-in means the contactor stays dropped once released. Even when the relay re-closes, someone must press Start.

---

## 2. Resolve these first (30 min)

### Power — use a USB phone charger
Do not use the unverified "220 to 12 V buck converter." If it is non-isolated, the ESP32 ground sits at mains potential and the USB port becomes lethal.

A UL-listed USB wall charger is an isolated AC-DC supply with reinforced isolation. Plug it into a 120 V outlet, run USB to the ESP32. USB is SELV — the cable can be routed freely with no hazard. Zero cost, zero risk, available now.

### Transistor — the one scrounge item
Needed to let a 3.3 V GPIO switch the fob's button, which likely sits on a 12 V rail. Any of:
- Small-signal NPN: 2N3904, 2N2222, BC547, S8050
- Any optocoupler: 4N25, 4N35, PC817
- Salvage: old PC power supply, dead router, printer board, appliance control board

**Do not connect a GPIO directly to the fob button.** 12 V on a GPIO destroys the ESP32.

---

## 3. Wiring

> **DANGER — 240 VAC.** Before touching any of the wiring in this section or § 4:
> - Lock out and tag out the machine disconnect. If the disconnect is a breaker, physically lock it in the OFF position and keep the key on you.
> - With the disconnect open, verify the L1, L2, and coil-circuit terminals read 0 V with a multimeter that you have first tested on a known-live circuit.
> - Treat incoming L1 and L2 as live until proven otherwise — feedback through control transformers or shared neutrals is real.
> - If the starter enclosure is metal, confirm it is bonded to safety ground with a #10 or larger conductor terminated at the ground stud.
> - PPE: safety glasses. Insulated tools if you cannot fully de-energize.
> - Sensor mounting (§ 6) is on the motor frame and does not require mains work, but the belt and shaft still turn under gravity — chock the belt or remove it before reaching in.

### NTC divider
```
3V3 ──[10 kΩ]──┬── GPIO34
               │
             [NTC]
               │
              GND
```
- **GPIO34 only** (or any of 32–39). ADC2 is unusable once Wi-Fi is on.
- The 10 kΩ can be any resistor near 10 k — record the actual value for the math.
- No 10 k on hand? Use two of whatever you have in series/parallel and measure.
- NTC connector is JST XH 2.54 — cut it off and solder to scrap wire if you lack the mate.

### Fob drive (NPN version)
```
GPIO26 ──[1 kΩ]── B
                  C ── fob button pad (the side that goes to the encoder)
                  E ── fob GND (battery negative)
```
- Tie ESP32 GND to fob GND. This is the common reference — without it, nothing switches.
- GPIO26 HIGH = transistor conducts = button "pressed" = transmitting.
- Open the fob, find the ON button's two pads. One is GND, the other goes to the encoder IC. Meter to identify. Solder to the encoder side.
- No 1 kΩ? Anything 470 Ω–10 kΩ works.

### Optocoupler version (preferred if you have one)
```
GPIO26 ──[330 Ω]── anode | cathode ── GND
                   collector ── fob button pad
                   emitter   ── fob GND
```
Galvanic isolation between ESP32 and fob. No shared ground needed.

### Fail-safe pin discipline
- Fit a **10 kΩ pulldown from GPIO26 to GND.** ESP32 pins float during boot and after a crash; the pulldown guarantees floating = not transmitting = relay open.
- Verify: with the ESP32 unpowered, the fob must not transmit and the receiver relay must be open.

### Receiver into the coil circuit
```
… seal-in ──▶ Receiver COM/NO ──▶ Coil ──▶ OL ──▶ L2
```
- Use COM and NO only. Leave NC unconnected.
- 30 A contacts on a ~1 A coil load — enormous margin.
- Ring terminals on the coil-circuit taps, torqued per the A202C label (#14–#10 at 35 in-lb).

---

## 4. Program the receiver to MOMENTARY

**This is the single most important step. Get it wrong and the system is fail-dangerous.**

Per the manufacturer's scheme, learn-button presses select the mode:
- **1 press = momentary** ← required
- 2 presses = toggle (fail-dangerous — relay latches)
- 3 presses = latched (fail-dangerous)

Procedure:
1. Press learn 8 times to clear all paired codes and start clean.
2. Press learn **once** (LED flashes once, then goes steady).
3. Press the fob ON button to pair.
4. **Verify momentary behavior:** hold the fob button — relay closes. Release — relay opens within about a second. If the relay stays closed after release, you are in toggle or latched mode. Clear and redo.
5. **Measure the hold time.** Press and release the fob several times, timing from release to relay drop with a stopwatch or scope. This is the receiver's momentary decay period — typical 300–800 ms. Record the number; it is the timing budget the heartbeat must beat.

The heartbeat model relies on the 433 MHz encoder in the fob emitting continuous frames while its input pad is held HIGH (PT2262 / EV1527 style — frame period ~40–100 ms). The ESP32 drives that pad HIGH via the transistor whenever it is ARMED and does not have to explicitly re-trigger — the encoder produces the frame stream. The receiver's hold timer bridges gaps between decoded frames. All three windows (encoder frame period ≪ receiver hold time ≪ firmware loop period) must be true for the link to sustain without chatter, and are verified in § 7 step 1.

Do not proceed until momentary behavior and hold time are both confirmed by observation.

---

## 5. Firmware

Same structure as the full handoff, with these changes:

```
PIN_NTC   = 34          // ADC1
PIN_TX    = 26          // drives fob via transistor, 10k pulldown
PIN_LED   = 2           // onboard blue LED, active-HIGH

// FRAME temperature, not winding. Provisional — tune in §7.
TRIP_C     = 90
WARN_C     = 78
RESET_C    = 55
COOLDOWN_HOLD_S = 120
SAMPLE_HZ  = 4
WDT_TIMEOUT_MS = 5000

// Probe-attachment self-verification. The one gap the heartbeat design
// leaves is a probe that has fallen off but still reads shop ambient.
// If temperature never rises >= DETACH_MIN_RISE_C above cold-boot baseline
// within DETACH_ALERT_MIN minutes of ARMED time, raise an advisory alert.
DETACH_MIN_RISE_C = 5
DETACH_ALERT_MIN  = 30

// Chatter suppression. A glitchy NTC or loose connector will otherwise
// spin the receiver relay open/closed every few minutes, spamming logs
// and hiding the real problem. After MAX_CONSECUTIVE_TRIPS in
// TRIP_WINDOW_MIN, drop into MANUAL_LOCKOUT — receiver stays open,
// no auto-recovery. In this build (no ack button) the lockout clears
// only by power-cycling the ESP32.
MAX_CONSECUTIVE_TRIPS = 3
TRIP_WINDOW_MIN       = 10
```

### The inversion that matters

Transmission is **asserted only in ARMED**. Every other state, every fault, every early return leaves `PIN_TX` LOW. Write it so that doing nothing is safe. `setup()` must also refuse to arm without a proven-good sensor and must not clear a persisted TRIPPED state by power-cycling into a still-hot motor.

```
setup():
    pinMode(PIN_TX, OUTPUT)
    digitalWrite(PIN_TX, LOW)              // FIRST LINE. Not transmitting = relay open.

    pinMode(PIN_LED, OUTPUT)
    nvs_open()
    last_state = nvs_read("last_state", default=COOLDOWN)

    // Boot self-test: N consecutive valid reads before arming.
    // Any partial-failure result leaves state = TRIPPED and PIN_TX = LOW.
    valid = 0
    last_c_boot = null
    for i in 1..10:
        raw = analogRead_oversampled(PIN_NTC, 16)
        if raw > 20 and raw < 4090:        // separates shorted / open from valid range
            c = ntc_to_celsius(raw)
            if c > -20 and c < 150:
                valid += 1
                last_c_boot = c
        delay(100)

    if valid < 8 or last_c_boot == null:
        state = TRIPPED
        log("BOOT_SENSOR_FAIL")
        // PIN_TX stays LOW → no transmission → relay open. Fall through to loop.
    else if last_state == TRIPPED and last_c_boot >= RESET_C:
        state = TRIPPED                    // hot motor + persisted trip: hold
        log("BOOT_HOT_HOLD", last_c_boot)
    else:
        state = COOLDOWN
        cooldown_start = now()

    // Prime the running-loop guards from the self-test result so the
    // implausible-jump check has a valid reference on the very first cycle.
    last_c = (last_c_boot != null) ? last_c_boot : 25    // 25 = plausible ambient fallback

    // Probe-attachment tracking: baseline captured once at cold boot.
    // probe_verified flips true the first time we observe a genuine rise.
    session_baseline_c        = last_c
    probe_verified            = false
    armed_ms_at_session_start = 0
    detach_alert_raised       = false

    // Chatter suppression: rolling window of consecutive trips.
    consecutive_trips = 0
    first_trip_ms     = 0

    // Persisted MANUAL_LOCKOUT overrides the temperature-based decision.
    if last_state == MANUAL_LOCKOUT:
        state = MANUAL_LOCKOUT
        log("BOOT_INTO_LOCKOUT")

    watchdog_enable(WDT_TIMEOUT_MS)
```

### record_trip helper

Centralizes the trip-count bookkeeping and MANUAL_LOCKOUT escalation so both trip sources (SENSOR_FAULT, OVERTEMP) go through the same path.

```
record_trip(cause, raw, c):
    if state == MANUAL_LOCKOUT:
        return                                  // already locked; don't cascade

    now_ms = now()
    if (now_ms - first_trip_ms) > TRIP_WINDOW_MIN * 60_000:
        consecutive_trips = 0
        first_trip_ms = now_ms
    consecutive_trips += 1

    if state != TRIPPED:
        state = TRIPPED
        nvs_write("last_state", TRIPPED)
        log("TRIP", cause, c, consecutive_trips)

    if consecutive_trips >= MAX_CONSECUTIVE_TRIPS:
        state = MANUAL_LOCKOUT
        nvs_write("last_state", MANUAL_LOCKOUT)
        log("MANUAL_LOCKOUT_ENTERED", consecutive_trips, TRIP_WINDOW_MIN)
```

### LED status patterns

At the machine, without a dashboard, the LED is how the operator knows what state the supervisor is in. Six distinguishable patterns cover every state that matters:

| Pattern | State | Meaning to the operator |
|---|---|---|
| Solid ON | ARMED | Ready. Press Start. |
| Slow blink (1 Hz) | COOLDOWN | Wait for solid. |
| Fast blink (5 Hz) | TRIPPED — thermal | Motor is hot. Clean the fan shroud. |
| Double-blink then pause | TRIPPED — sensor fault | Do not use. Check probe wiring. |
| Triple-blink then long pause | MANUAL_LOCKOUT | Repeated tripping. Investigate root cause, then power-cycle the ESP32 to clear. |
| SOS (··· − − − ···) | Boot self-test failed | Do not use. Power-cycle. If it repeats, check wiring. |
| Off | ESP32 unpowered or crashed pre-boot | Do not use. Check the power. |

`Off` and `boot fail` are both fail-safe — the relay is open in both. The LED distinguishes them for troubleshooting.

```
update_led(state, cause):
    switch state:
        case BOOT:      led_pattern_sos()
        case ARMED:     led_on()
        case COOLDOWN:  led_blink(period_ms=1000)
        case TRIPPED:
            if cause == "SENSOR_FAULT":
                led_pattern_doubleblink()      // 50-50-50-850 ms
            else:
                led_blink(period_ms=200)
```

Call `update_led()` once per protection-loop iteration, after the state transition. The LED helpers are non-blocking (they toggle based on a millisecond counter, not `delay()`), so they never stall the safety loop.

```
protection_loop():
    loop forever:
        raw = analogRead_oversampled(PIN_NTC, 16)
        c   = ntc_to_celsius(raw)          // B3950 beta equation

        // Separate the electrical checks from the temperature range check.
        // raw < 20 catches a probe shorted to GND; raw > 4090 catches an
        // open probe. Legitimate high temperature is caught by c > 150
        // without conflating it with the short-check bound.
        if raw < 20 or raw > 4090
           or c < -20 or c > 150
           or abs(c - last_c) > 30:        // primed at boot; safe on first cycle
            digitalWrite(PIN_TX, LOW)
            record_trip("SENSOR_FAULT", raw, c)
            feed_watchdog()
            continue

        last_c = c

        switch state:
            case ARMED:
                if c >= TRIP_C:
                    digitalWrite(PIN_TX, LOW)
                    record_trip("OVERTEMP", raw, c)
                else:
                    digitalWrite(PIN_TX, HIGH)     // heartbeat continues
                    if c >= WARN_C: raise_alert("APPROACHING_TRIP")

            case TRIPPED:
                digitalWrite(PIN_TX, LOW)
                if c < RESET_C:
                    state = COOLDOWN
                    cooldown_start = now()

            case COOLDOWN:
                digitalWrite(PIN_TX, LOW)
                if c >= RESET_C:
                    state = TRIPPED
                else if now() - cooldown_start > COOLDOWN_HOLD_S:
                    state = ARMED
                    nvs_write("last_state", ARMED)
                    log("ARMED")
                    // Relay re-closing does NOT start the saw.
                    // Seal-in requires a physical Start press.

            case MANUAL_LOCKOUT:
                digitalWrite(PIN_TX, LOW)        // stays open, no auto-recovery
                // No ack button in this build: clear only by power-cycle.
                // Boot self-test will then land in COOLDOWN (or hold TRIPPED
                // if the motor is still hot per BOOT_HOT_HOLD).

        // Probe-attachment self-verification (advisory only, never trips).
        // Once verified, we never un-verify — a probe that has warmed once is on.
        if state == ARMED:
            armed_ms_at_session_start += 1000 / SAMPLE_HZ
        if not probe_verified and (c - session_baseline_c) >= DETACH_MIN_RISE_C:
            probe_verified = true
            log("PROBE_VERIFIED", c - session_baseline_c)
        else if not probe_verified and not detach_alert_raised
                and armed_ms_at_session_start > DETACH_ALERT_MIN * 60_000:
            log("PROBE_UNVERIFIED_AT_ARMED_TIME",
                minutes=DETACH_ALERT_MIN, rise=c - session_baseline_c)
            detach_alert_raised = true

        update_led(state, last_trip_cause)
        feed_watchdog()      // only reached on a complete cycle
        delay(1000 / SAMPLE_HZ)
```

### Beta equation
```
ntc_to_celsius(raw):
    v     = raw / 4095.0 * 3.3
    r_ntc = R_FIXED * v / (3.3 - v)
    inv_t = 1/298.15 + (1/3950.0) * ln(r_ntc / 10000.0)
    return (1 / inv_t) - 273.15
```

### Two-point calibration procedure

Ice water and boiling water give two known temperature points. This catches wiring errors, math bugs, and part tolerance in one procedure. Do it before mounting the probe on the motor.

1. **Measure `R_FIXED` with a meter.** Write that number into `ntc_to_celsius()` as the actual value, not the nominal 10000. A 5% carbon resistor labeled 10 kΩ can measure 9500–10500. This matters — every 1% off is a fraction of a degree of systematic error.
2. **Ice bath.** Container of crushed ice with just enough water to cover. Stir 30 seconds. Submerge probe — not touching the vessel wall or bottom. Wait 2 minutes for the mass to equilibrate. Log `raw` and computed °C.
3. **Boiling water.** Kettle-boil off the flame (avoids splash and steam artifacts). Submerge probe. Wait 30 seconds. Log `raw` and computed °C. Sea level = 100.0 °C; subtract ~1 °C per 300 m elevation.
4. **Interpret:**
    - **Both within ±2 °C of target →** you're done. Ship it.
    - **Both offset by the same amount →** sensor tolerance. Apply an offset (`c_calibrated = c_raw + offset`).
    - **Off in opposite directions →** β doesn't match the datasheet's 3950. Solve for the actual β:
      ```
      R_ntc_0C   = R_FIXED × V_0C   / (3.3 − V_0C)
      R_ntc_100C = R_FIXED × V_100C / (3.3 − V_100C)
      β_actual   = ln(R_ntc_100C / R_ntc_0C) / (1/373.15 − 1/273.15)
      ```
      Replace 3950 with `β_actual` in `ntc_to_celsius()`.
5. **Re-verify.** Back in ice water, should read 0.0 ± 0.5 °C. Body-heat the tip between fingers — should read 30–35 °C.

A miscalibrated probe reading 5 °C low means the operator sees "80 °C, healthy" when the frame is actually at 85 °C. Trip threshold effectively shifts up by the offset. Not catastrophic in this build (the receiver momentary-mode heartbeat is still fail-safe on power/firmware faults) but it defeats the whole point of having a temperature-based cutoff.

### Skip tonight
Wi-Fi, web dashboard, flash logging. They are not protection. Get the cutout working; add them later. If you want live numbers during commissioning, serial output is enough.

---

## 6. Sensor mounting

Position matters more than anything else here.

1. **Location:** seat the probe in a fin channel on the motor frame, as close to the drive end as you can reach. That end runs hottest.
2. **Contact:** **thermal grease** between the stainless probe body and the aluminum frame. Do **not** use the AlN substrate here — AlN was specified for the winding-side sensor where mains-potential isolation matters. The motor frame is bonded to safety ground, so no dielectric layer is needed on this side, and AlN's ceramic hardness works against contact area with a cylindrical probe. Save the AlN for Path B. Any silicone-based thermal paste (CPU-grade or better) is fine; a thin film only.
3. **Clamp:** hose clamp, zip tie through the fins, or a scrap-metal strap. It must not shift with vibration.
4. **Insulate:** thermal insulation over the outboard face so the probe reads the frame, not shop air. Skipping this is the most common way this project fails — you get plausible numbers that track nothing.
5. **Route:** cable clear of the belt, pulleys, and the fan shroud outlet. Do not obstruct airflow.

---

## 7. Commissioning — do not skip

### Bench first, motor disconnected
1. **Heartbeat timing baseline.** With ESP32 running ARMED (probe cold), watch the receiver relay for 60 seconds continuously. No drop-outs allowed. If you see chatter, the encoder is not producing a continuous frame stream — the fob wiring or transistor drive is wrong. Then time the drop by pulling ESP32 power: relay must open within one receiver hold period (the value recorded in § 4 step 5, typically 300–800 ms). If the drop is slower than that, something upstream is latching.
2. Heat the probe with a heat gun or hot water. Verify the reading tracks and that trip fires at `TRIP_C`.
3. **Pull ESP32 power while ARMED.** Relay must open within one hold period. Core safety claim — verify it by observation.
4. Disconnect the NTC while ARMED. Relay must open.
5. Force a crash (infinite loop). Watchdog must reset, relay must open. Worst-case latency: `WDT_TIMEOUT_MS` + reset (~200 ms) + receiver hold time.
6. **Persisted-trip test.** Force a trip. Immediately power-cycle the ESP32 while the probe is still above `RESET_C` (heat it and hold). Boot must resume in TRIPPED, not COOLDOWN — verify by log line `BOOT_HOT_HOLD`.

### Coil circuit, motor still disconnected
7. Press Start — contactor pulls in. Force a trip — contactor drops out. Clear the trip and confirm the contactor does **not** re-latch. Start must be pressed.

### Baseline run
8. Set `TRIP_C = 110` temporarily (still under the 125 °C sensor limit). Run normal cuts, watch the serial output, record steady-state frame temperature.
9. Set `TRIP_C = baseline + 20`, `WARN_C = baseline + 10`, `RESET_C = baseline − 10`. Reflash.

Typical healthy TEFC frame temperature is 60–75 °C, which puts trip around 85–95 °C. If your baseline is already above 90 °C, the shroud is still restricted — stop and clean it before setting thresholds around a bad number.

---

## 8. Before any of it

**Clean the fan shroud completely.** The motor failed because it could not shed heat. Ten minutes with compressed air. Everything else is instrumentation on top of an unfixed root cause, and your baseline numbers will be garbage.

Also verify the A202C's overload heaters are sized for 14.4 A FLA at SF 1.0 → **16.5 A maximum**. Oversized heaters mean no current protection, and this system only covers temperature.

---

## 9. Deferred — order when you're back

1. **Bimetallic thermostat, 120–130 °C NC.** Passive backstop, in series in the coil circuit. Independent of firmware entirely.
2. **K-type thermocouple + MAX31855.** Winding temperature instead of frame temperature. Faster, more direct, better data.
3. **Isolated AC-DC supply,** if you want to retire the phone charger.

None are needed tonight. The heartbeat design means the ESP32 cannot fail closed, which is what the thermostat mainly protects against.

**The one gap this build does have:** an ESP32 that is running fine but reading a *detached* probe. It would report cool air and keep transmitting. The implausibility checks catch a fully open probe, not one that has fallen off but still reads ambient. The `probe_verified` latch in the firmware is a partial mitigation — it will log `PROBE_UNVERIFIED_AT_ARMED_TIME` after 30 minutes ARMED without a rise. During the first few sessions, confirm the temperature actually rises when you cut and that `PROBE_VERIFIED` appears in the serial log.

### Note on FCC Part 15

Continuous 433 MHz transmission during ARMED sits outside the periodic-control-signal duty cycle expectations of 47 CFR § 15.231. For a private shop the point is entirely academic — nobody is coming for you, and the transmit power on these encoder modules is well under the field-strength limits. Flagging it here so that if this design is ever shared, re-published, or scaled up beyond a single benchtop, the RF path is understood to be a compliance conversation rather than a certified solution. Path B replaces the RF link with a directly wired opto-isolated relay, which sidesteps the question entirely.

---

## 10. Time budget

| | Task |
|---|---|
| 0:00–0:30 | Find charger and transistor. Clean the fan shroud. |
| 0:30–1:30 | Bench NTC + ESP32. Verify readings against ice water and boiling. |
| 1:30–2:30 | Solder transistor to fob. Program receiver to momentary. Verify drop-out. |
| 2:30–3:30 | Firmware. |
| 3:30–4:30 | Bench-test all four fault modes in §7. |
| 4:30–5:30 | Mount probe on frame. Mount ESP32 and charger in enclosure. |
| 5:30–6:30 | Wire receiver into coil circuit. |
| 6:30–7:30 | Commissioning §7 steps 5–6. |
| 7:30–8:30 | Baseline, tune thresholds, reflash. |
| 8:30–9:00 | Buffer. |

If you fall behind, cut in this order: web/Wi-Fi (already cut), flash logging, warning threshold, enclosure tidiness. **Never cut the §7 fault tests.** They are the only evidence the thing is fail-safe.

---

## 11. If the transistor doesn't turn up

Same underlying idea in every fallback: leave the fob's ON button mechanically held closed with tape or a solder bridge, and use the ESP32 to switch the fob's **power** instead of the button. Heartbeat behavior is identical — power the fob to transmit, cut power to stop.

### Fallback A — logic-level N-channel MOSFET (preferred)

Cheaper, cleaner, and often already in the ESP32 kit or on any dead motherboard.

```
GPIO26 ──[220 Ω]── G
                   D ── fob battery negative
                   S ── circuit ground
              +
GPIO26 ──[100 kΩ]── GND   (defined off-state)
GPIO26 ──[ 10 kΩ]── GND   (fail-safe pulldown, same as the transistor build)
```

- Any logic-level N-FET with Vgs(th) ≤ 2 V and Id ≥ 100 mA works: **2N7000, IRLML2502, AO3400, BSS138, IRLZ44N**. Pull one off a dead PC power supply, router, or LED strip driver if the parts drawer is bare.
- The 100 kΩ from gate to source guarantees the FET is off when the GPIO is floating during boot. The 10 kΩ pulldown on GPIO26 is still required — same fail-safe pin discipline as the transistor build.
- Wire the FET on the **low side** of the fob battery (source to ground, drain to battery negative). High-side switching an N-FET needs a level shifter and is not worth the complexity here.

### Fallback B — small reed relay

Uglier, slower, but works if no MOSFET is on hand.

- Reed relay coil driven by the same NPN-transistor circuit described in § 3, with a flyback diode across the coil.
- Contacts in series with the fob's battery positive lead (mechanical isolation is a small side benefit).
- Same fail-safe pin discipline on GPIO26.

### Commissioning still applies

Whichever fallback is used, the § 7 fault tests are the only evidence the assembly is fail-safe. Do not skip them because the parts are scrounged. In particular: **verify that pulling the ESP32's power drops the receiver relay within one hold period**. If it doesn't, you have a latent path around the intended cut and the whole design collapses.

If none of NPN, optocoupler, MOSFET, or reed relay turns up: do not improvise a bypass. A saw with no thermal protection is how you got here. Leave it down until you're back.
