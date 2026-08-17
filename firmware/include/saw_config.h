/*
 * Pin map, thresholds and build-variant selection.
 *
 * Exactly one of SAW_PATH_A / SAW_PATH_B must be defined; platformio.ini does that per
 * environment. The two variants are the two build paths in the project README:
 *
 *   Path A  BUILD-TONIGHT.md — parts on hand. DROK NTC on the motor FRAME is the trip
 *           source, and the "relay" is a 433 MHz fob held transmitting through a level
 *           shifter into a receiver programmed to momentary mode. Loss of transmission
 *           opens the receiver contact.
 *
 *   Path B  ARCHITECTURE.md — end state. K-type thermocouple at the WINDING through a
 *           MAX31855 is the trip source, the NTC is demoted to advisory frame
 *           monitoring, and GPIO26 drives a wired opto-isolated active-HIGH relay.
 *
 * Both variants drive GPIO26 with identical semantics: HIGH means "the coil circuit may
 * be closed", LOW means "open it". Everything downstream of that pin differs; nothing
 * upstream of it does. That is why there is one state machine and not two.
 *
 * Every value below is overridable from build_flags, so commissioning step 9 in
 * BUILD-TONIGHT.md ("set TRIP_C = baseline + 20 ... reflash") does not require editing
 * tracked source:
 *
 *     pio run -e path_a -t upload --build-flag="-DSAW_TRIP_C=95.0f"
 */
#pragma once

#if !defined(SAW_PATH_A) && !defined(SAW_PATH_B)
#error "Define SAW_PATH_A or SAW_PATH_B (platformio.ini sets one per environment)"
#endif
#if defined(SAW_PATH_A) && defined(SAW_PATH_B)
#error "SAW_PATH_A and SAW_PATH_B are mutually exclusive"
#endif

/* --------------------------------------------------------------------------- */
/* Variant features                                                            */
/* --------------------------------------------------------------------------- */

#ifdef SAW_PATH_B
#define SAW_PATH_NAME        "B (winding K-type, wired relay)"
#define SAW_HAS_MAX31855     1
#define SAW_PRIMARY_IS_NTC   0
#define SAW_HAS_FRAME_NTC    1   /* NTC demoted to advisory frame monitoring   */
#define SAW_OUTPUT_IS_RF     0
#define SAW_SENSOR_LOCATION  "winding"
#else
#define SAW_PATH_NAME        "A (frame NTC, RF heartbeat)"
#define SAW_HAS_MAX31855     0
#define SAW_PRIMARY_IS_NTC   1
#define SAW_HAS_FRAME_NTC    0   /* the frame NTC *is* the primary here        */
#define SAW_OUTPUT_IS_RF     1
#define SAW_SENSOR_LOCATION  "frame"
#endif

/*
 * The ack button is fitted on BOTH paths, which is a deliberate deviation from
 * BUILD-TONIGHT.md § 5 — see firmware/README.md § Deviations. Short version: E07 tells
 * the operator that power-cycling does not clear a lockout, and honouring a persisted
 * MANUAL_LOCKOUT is the safe behaviour, so a build with no ack input would have no way
 * out of lockout at all. On a Path A build the "button" can be a scrounged momentary
 * switch or a bare wire touched from GPIO27 to GND.
 */
#ifndef SAW_HAS_ACK_BUTTON
#define SAW_HAS_ACK_BUTTON 1
#endif

/* --------------------------------------------------------------------------- */
/* Pin map — ARCHITECTURE.md § Pin assignments, hardware/schematic/WIRING.md   */
/* --------------------------------------------------------------------------- */

/* THE output. Active-HIGH. Needs a 10 kΩ pulldown to GND so that a floating pin during
 * boot, after a crash, or through a brown-out means "open the coil circuit".
 * Mandatory, not optional — WIRING.md § Mandatory on every version. */
#ifndef SAW_PIN_HOLD
#define SAW_PIN_HOLD    26
#endif

#ifndef SAW_PIN_LED
#define SAW_PIN_LED     2
#endif

#ifndef SAW_PIN_ACK
#define SAW_PIN_ACK     27      /* to GND, internal pullup */
#endif

/* NTC divider midpoint. MUST be an ADC1 pin: ADC2 is unusable while Wi-Fi is up. */
#ifndef SAW_PIN_NTC
#define SAW_PIN_NTC     34
#endif

/* MAX31855 — read-only device, so there is no MOSI. */
#ifndef SAW_PIN_TC_SCK
#define SAW_PIN_TC_SCK  18
#endif
#ifndef SAW_PIN_TC_DO
#define SAW_PIN_TC_DO   19
#endif
#ifndef SAW_PIN_TC_CS
#define SAW_PIN_TC_CS   5
#endif

/* --------------------------------------------------------------------------- */
/* Thresholds                                                                  */
/* --------------------------------------------------------------------------- */

#ifdef SAW_PATH_B
/* ARCHITECTURE.md § Thresholds. Winding temperature. TRIP_C sits meaningfully below the
 * bimetallic thermostat's 120–130 °C so the supervisor acts first and logs the trip. */
#ifndef SAW_TRIP_C
#define SAW_TRIP_C      110.0f
#endif
#ifndef SAW_WARN_C
#define SAW_WARN_C      95.0f
#endif
#ifndef SAW_RESET_C
#define SAW_RESET_C     70.0f
#endif
/* Believable band for a K-type at a motor winding. */
#ifndef SAW_SENSOR_MIN_C
#define SAW_SENSOR_MIN_C  -20.0f
#endif
#ifndef SAW_SENSOR_MAX_C
#define SAW_SENSOR_MAX_C  400.0f
#endif
#ifndef SAW_MAX_JUMP_C
#define SAW_MAX_JUMP_C    50.0f
#endif

#else
/* BUILD-TONIGHT.md § 5. FRAME temperature, not winding — the numbers are lower because
 * the frame runs cooler than the winding, and they are PROVISIONAL until the baseline run
 * in BUILD-TONIGHT.md § 7 steps 8–9 replaces them with baseline+20 / +10 / −10.
 *
 * Note for anyone reading the error-code pages against a Path A build: docs/codes/
 * quotes the Path B winding figures (110 / 95 / 70 °C). The dashboard and the boot log
 * print the thresholds this unit is actually running. */
#ifndef SAW_TRIP_C
#define SAW_TRIP_C      90.0f
#endif
#ifndef SAW_WARN_C
#define SAW_WARN_C      78.0f
#endif
#ifndef SAW_RESET_C
#define SAW_RESET_C     55.0f
#endif
/* The DROK probe is specified −25 to +125 °C, so 150 is already past the part's range;
 * anything above it is a wiring or maths fault rather than a hot motor. */
#ifndef SAW_SENSOR_MIN_C
#define SAW_SENSOR_MIN_C  -20.0f
#endif
#ifndef SAW_SENSOR_MAX_C
#define SAW_SENSOR_MAX_C  150.0f
#endif
#ifndef SAW_MAX_JUMP_C
#define SAW_MAX_JUMP_C    30.0f
#endif
#endif

#ifndef SAW_COOLDOWN_HOLD_S
#define SAW_COOLDOWN_HOLD_S     120
#endif
#ifndef SAW_SENSOR_TIMEOUT_MS
#define SAW_SENSOR_TIMEOUT_MS   3000
#endif
#ifndef SAW_SAMPLE_HZ
#define SAW_SAMPLE_HZ           4
#endif
#ifndef SAW_WDT_TIMEOUT_MS
#define SAW_WDT_TIMEOUT_MS      5000
#endif
#ifndef SAW_MAX_CONSECUTIVE_TRIPS
#define SAW_MAX_CONSECUTIVE_TRIPS 3
#endif
#ifndef SAW_TRIP_WINDOW_MIN
#define SAW_TRIP_WINDOW_MIN     10
#endif
#ifndef SAW_DETACH_MIN_RISE_C
#define SAW_DETACH_MIN_RISE_C   5.0f
#endif
#ifndef SAW_DETACH_ALERT_MIN
#define SAW_DETACH_ALERT_MIN    30
#endif
#ifndef SAW_ACK_DEBOUNCE_MS
#define SAW_ACK_DEBOUNCE_MS     30
#endif
/* W01 clears this far below WARN_C, so a reading sitting on the threshold does not
 * raise and clear the alert every cycle. */
#ifndef SAW_WARN_HYSTERESIS_C
#define SAW_WARN_HYSTERESIS_C   2.0f
#endif

/* --------------------------------------------------------------------------- */
/* Boot self-test — ARCHITECTURE.md § Boot                                     */
/* --------------------------------------------------------------------------- */

#ifndef SAW_SELFTEST_READS
#define SAW_SELFTEST_READS      10
#endif
#ifndef SAW_SELFTEST_REQUIRED
#define SAW_SELFTEST_REQUIRED   8
#endif
#ifndef SAW_SELFTEST_GAP_MS
#define SAW_SELFTEST_GAP_MS     100
#endif

/* --------------------------------------------------------------------------- */
/* Sensor front end                                                            */
/* --------------------------------------------------------------------------- */

/* Electrically plausible ADC band. Below the low bound the probe looks shorted to GND,
 * above the high bound it looks open. Kept separate from the temperature range check so
 * a genuinely hot motor is never confused with a short. */
#ifndef SAW_NTC_RAW_MIN
#define SAW_NTC_RAW_MIN         20
#endif
#ifndef SAW_NTC_RAW_MAX
#define SAW_NTC_RAW_MAX         4090
#endif
#ifndef SAW_NTC_OVERSAMPLE
#define SAW_NTC_OVERSAMPLE      16
#endif

/* --------------------------------------------------------------------------- */
/* Rate of rise                                                                */
/* --------------------------------------------------------------------------- */

#ifndef SAW_ROR_WINDOW_S
#define SAW_ROR_WINDOW_S        60
#endif
/* W02 fires above baseline × this. */
#ifndef SAW_ROR_ALERT_FACTOR
#define SAW_ROR_ALERT_FACTOR    1.5f
#endif

/* --------------------------------------------------------------------------- */
/* Logging                                                                     */
/* --------------------------------------------------------------------------- */

/* One aggregated sample record per period. The flash budget below is what sets the
 * retention: records = SAW_LOG_RING_BYTES / sizeof(SawSampleRecord). */
#ifndef SAW_LOG_PERIOD_S
#define SAW_LOG_PERIOD_S        120
#endif
#ifndef SAW_LOG_RING_BYTES
#define SAW_LOG_RING_BYTES      360000UL
#endif
#ifndef SAW_LOG_EVENT_BYTES
#define SAW_LOG_EVENT_BYTES     98304UL
#endif
/* In-RAM history the dashboard charts without touching flash. */
#ifndef SAW_LOG_RAM_SAMPLES
#define SAW_LOG_RAM_SAMPLES     240
#endif

/* --------------------------------------------------------------------------- */
/* Network — advisory only (SR-8)                                              */
/* --------------------------------------------------------------------------- */

#ifndef SAW_NET_ENABLED
#define SAW_NET_ENABLED         1
#endif
/* The access point the operator's phone joins to read the dashboard and the offline
 * error-code bundle. Named in docs/codes/README.md. */
#ifndef SAW_AP_SSID
#define SAW_AP_SSID             "ALN Table Saw"
#endif
/* WPA2 needs 8 characters minimum. Change it per install; nothing behind it can alter
 * protection, so this guards against nuisance rather than against attack. */
#ifndef SAW_AP_PASSWORD
#define SAW_AP_PASSWORD         "tablesaw"
#endif
#ifndef SAW_MDNS_HOST
#define SAW_MDNS_HOST           "saw"
#endif
#ifndef SAW_HTTP_PORT
#define SAW_HTTP_PORT           80
#endif

/* Over-the-air update, so thresholds can be retuned without opening the starter
 * enclosure. Deliberately only serviced while the saw is NOT armed — see saw_net.cpp. */
#ifndef SAW_OTA_ENABLED
#define SAW_OTA_ENABLED         1
#endif
#ifndef SAW_OTA_HOSTNAME
#define SAW_OTA_HOSTNAME        "tablesaw-supervisor"
#endif
#ifndef SAW_OTA_PASSWORD
#define SAW_OTA_PASSWORD        "tablesaw-ota"
#endif

#ifndef SAW_SERIAL_BAUD
#define SAW_SERIAL_BAUD         115200
#endif

/* --------------------------------------------------------------------------- */
/* Derived                                                                     */
/* --------------------------------------------------------------------------- */

#define SAW_LOOP_PERIOD_MS   (1000 / (SAW_SAMPLE_HZ))
#define SAW_COOLDOWN_HOLD_MS ((uint32_t)(SAW_COOLDOWN_HOLD_S) * 1000UL)
#define SAW_TRIP_WINDOW_MS   ((uint32_t)(SAW_TRIP_WINDOW_MIN) * 60000UL)
#define SAW_DETACH_ALERT_MS  ((uint32_t)(SAW_DETACH_ALERT_MIN) * 60000UL)
#define SAW_ROR_WINDOW_MS    ((uint32_t)(SAW_ROR_WINDOW_S) * 1000UL)

/* Threshold sanity, checked at compile time. static_assert rather than #if because the
 * preprocessor cannot evaluate floating-point constants — `#if SAW_TRIP_C <= SAW_RESET_C`
 * is a hard error, not a silently skipped check. */
#ifdef __cplusplus
static_assert(SAW_TRIP_C > SAW_RESET_C,
              "SAW_TRIP_C must be above SAW_RESET_C or the supervisor can never recover");
static_assert(SAW_WARN_C < SAW_TRIP_C,
              "SAW_WARN_C must be below SAW_TRIP_C to be a warning at all");
static_assert(SAW_SENSOR_MAX_C > SAW_TRIP_C,
              "the believable sensor band must extend above SAW_TRIP_C, or a real "
              "overtemperature is rejected as an implausible reading and logged as E02");
#endif

/* Integers, so the preprocessor can do this one. */
#if SAW_WDT_TIMEOUT_MS <= SAW_SENSOR_TIMEOUT_MS
#error "The watchdog must outlast SAW_SENSOR_TIMEOUT_MS, or a stale sensor reboots the board instead of tripping and logging E03"
#endif
#if SAW_SELFTEST_REQUIRED > SAW_SELFTEST_READS
#error "SAW_SELFTEST_REQUIRED cannot exceed SAW_SELFTEST_READS — the self-test could never pass"
#endif
