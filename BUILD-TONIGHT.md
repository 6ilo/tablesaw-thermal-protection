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
PIN_LED   = 2

// FRAME temperature, not winding. Provisional — tune in §7.
TRIP_C     = 90
WARN_C     = 78
RESET_C    = 55
COOLDOWN_HOLD_S = 120
SAMPLE_HZ  = 4
WDT_TIMEOUT_MS = 5000
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

    watchdog_enable(WDT_TIMEOUT_MS)
```

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
            if state != TRIPPED:
                state = TRIPPED
                nvs_write("last_state", TRIPPED)
            log("SENSOR_FAULT", raw, c)
            feed_watchdog()
            continue

        last_c = c

        switch state:
            case ARMED:
                if c >= TRIP_C:
                    digitalWrite(PIN_TX, LOW)
                    state = TRIPPED
                    nvs_write("last_state", TRIPPED)
                    log("OVERTEMP", c)
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
Sanity-check against a known temperature — ice water reads 0 °C, boiling reads 100 °C. Two points is enough to catch a wiring or math error.

### Skip tonight
Wi-Fi, web dashboard, flash logging. They are not protection. Get the cutout working; add them later. If you want live numbers during commissioning, serial output is enough.

---

## 6. Sensor mounting

Position matters more than anything else here.

1. **Location:** seat the probe in a fin channel on the motor frame, as close to the drive end as you can reach. That end runs hottest.
2. **Contact:** AlN between probe and frame. The probe is cylindrical, so bed it — the goal is maximum contact area, not a neat appearance.
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

**The one gap this build does have:** an ESP32 that is running fine but reading a *detached* probe. It would report cool air and keep transmitting. The implausibility checks catch a fully open probe, not one that has fallen off but still reads ambient. Clamp it properly, and during the first few sessions confirm the temperature actually rises when you cut.

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

Fallback: leave the fob's ON button mechanically held closed and switch the fob's **battery** with a small relay or reed switch driven from the ESP32. Same heartbeat behavior — power the fob to transmit, cut power to stop. Uglier and needs a relay you may not have, but it is the same logic.

If neither works, do not improvise a bypass. A saw with no thermal protection is how you got here. Leave it down until you're back.
