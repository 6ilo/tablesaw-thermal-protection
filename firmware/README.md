# Firmware

ESP32 supervisor code. Currently a stub — source lands here when the paper design in [`../ARCHITECTURE.md § Reference pseudocode`](../ARCHITECTURE.md#reference-pseudocode) becomes real ESP-IDF or Arduino-ESP32 code.

## Intended structure

```
firmware/
├── platformio.ini             or CMakeLists.txt for ESP-IDF native
├── src/
│   ├── main.cpp               setup() + task startup
│   ├── protection_loop.cpp    core-0 loop: read → validate → trip → LED → WDT
│   ├── trip.cpp               record_trip() with rolling-window escalation
│   ├── state_machine.h        BOOT/ARMED/TRIPPED/COOLDOWN/MANUAL_LOCKOUT
│   ├── led.cpp                non-blocking pattern engine (6 patterns)
│   ├── sensor_kthermo.cpp     MAX31855 SPI + validation (Path B)
│   ├── sensor_ntc.cpp         ADC + oversample + β-equation (frame / BUILD-TONIGHT)
│   ├── nvs_state.cpp          persist last_state, load on boot
│   ├── network.cpp            core-1 Wi-Fi + HTTP dashboard (advisory only)
│   ├── calibration.h          R_FIXED_ACTUAL, β_actual, offsets (per-unit)
│   └── config.h               pin map + thresholds
├── test/
│   ├── test_trip_counter.cpp        rolling-window → MANUAL_LOCKOUT
│   ├── test_state_machine.cpp       transitions match the state diagram
│   ├── test_sensor_validation.cpp   out-of-range / stale / jump all trip
│   └── test_ntc_math.cpp            β-equation against known R/T pairs
└── docs/
    └── (calibration procedure lives in ../ARCHITECTURE.md until code exists)
```

## Where the design currently lives

Until source exists here, the reference of record is:

- [`../ARCHITECTURE.md § Software architecture`](../ARCHITECTURE.md#software-architecture) — task layout, state machine, thresholds, logging, dashboard, LED patterns, probe self-verification, ack button behavior
- [`../ARCHITECTURE.md § Reference pseudocode`](../ARCHITECTURE.md#reference-pseudocode) — `setup()`, `protection_loop()`, `trip()`, `network_task()`, rate-of-rise
- [`../ARCHITECTURE.md § Sensor calibration`](../ARCHITECTURE.md#sensor-calibration) — two-point procedure for K-type and NTC
- [`../BUILD-TONIGHT.md § 5`](../BUILD-TONIGHT.md) — same-day expedient build (frame-temperature NTC, RF heartbeat)

When code lands, treat `ARCHITECTURE.md` as the spec and the code as the implementation. Any divergence should be resolved by updating the spec first, then the code.

## Non-negotiables

The eight safety requirements in [`../ARCHITECTURE.md § Safety requirements`](../ARCHITECTURE.md#safety-requirements) are enforced by topology *and* by firmware structure. The protection loop must:

- Not depend on Wi-Fi, NTP, filesystem, or the web server
- Feed the watchdog only on a complete successful cycle
- Trip on any sensor doubt (SR-5) — no "last known good" fallbacks
- Drive the relay via a topology where floating GPIOs = relay open
- Persist trip and lockout state to NVS so power cycles cannot clear them

Any change that appears to violate one of these is wrong until proven otherwise.
