/*
 * The protection loop — core 0, highest priority, no dependency on Wi-Fi, NTP, the
 * filesystem or the web server.
 *
 * ARCHITECTURE.md § Protection loop, and the eight safety requirements in
 * ARCHITECTURE.md § Safety requirements. The two structural rules that shape this file:
 *
 *   SR-6  the watchdog is fed only after a complete successful cycle. Every early exit
 *         in this loop feeds it *after* driving the hold line low, so a starved loop
 *         reboots into the fail-safe boot path rather than being papered over.
 *
 *   SR-1  the hold line is written from this task and nowhere else. It is driven low
 *         before the state machine runs whenever the sensor verdict is not VALID, so the
 *         hardware leads the bookkeeping.
 */
#include <Arduino.h>
#include <esp_idf_version.h>
#include <esp_task_wdt.h>
#include <math.h>
#include <stdint.h>

#include "error_codes.h"
#include "saw_calibration.h"
#include "saw_config.h"
#include "saw_hw.h"
#include "saw_protection.h"
#include "saw_ror.h"
#include "saw_runtime.h"
#include "saw_store.h"

static SawContext s_ctx;
static SawRor     s_ror;
static uint32_t   s_state_entered_ms = 0;
static uint32_t   s_last_flush_ms = 0;
static float      s_sample_sum = 0.0f;
static uint32_t   s_sample_n = 0;
static float      s_frame_sum = 0.0f;
static uint32_t   s_frame_n = 0;
static bool       s_ror_alert_latched = false;

static const SawLimits LIMITS = {
    SAW_TRIP_C,
    SAW_WARN_C,
    SAW_RESET_C,
    SAW_COOLDOWN_HOLD_MS,
    SAW_MAX_CONSECUTIVE_TRIPS,
    SAW_TRIP_WINDOW_MS,
    SAW_DETACH_MIN_RISE_C,
    SAW_DETACH_ALERT_MS,
    SAW_WARN_HYSTERESIS_C,
};

static const SawSensorLimits SENSOR_LIMITS = {
    SAW_SENSOR_MIN_C,
    SAW_SENSOR_MAX_C,
    SAW_MAX_JUMP_C,
    SAW_SENSOR_TIMEOUT_MS,
};

const SawLimits &saw_protection_limits(void)
{
    return LIMITS;
}

/* --------------------------------------------------------------------------- */
/* Logging                                                                     */
/* --------------------------------------------------------------------------- */

/*
 * One formatter for serial, the flash event log and the dashboard, so the three can
 * never disagree about what happened. The error code comes from the generated registry
 * table rather than from a string in this file: saw_code_by_event() looks the event name
 * up in generated/error_codes.h, which is built from docs/codes/. If a code's meaning
 * changes in the operator documentation, this line changes with it on the next build.
 */
static void log_event(void *unused, SawEvent ev, float value, int32_t detail)
{
    (void)unused;

    const char *name = saw_event_name(ev);
    const saw_code_t *code = saw_code_by_event(name);

    char line[SAW_EVENT_LINE_MAX];
    unsigned long t = millis();
    if (isnan(value)) {
        snprintf(line, sizeof(line), "%lu.%03lu [%s] %s n=%ld",
                 t / 1000UL, t % 1000UL, code ? code->code : "---", name, (long)detail);
    } else {
        snprintf(line, sizeof(line), "%lu.%03lu [%s] %s %.2fC n=%ld",
                 t / 1000UL, t % 1000UL, code ? code->code : "---", name,
                 (double)value, (long)detail);
    }

    Serial.println(line);
    saw_runtime_push_event(line);
    saw_store_log_event(line);
}

/* --------------------------------------------------------------------------- */
/* Watchdog                                                                    */
/* --------------------------------------------------------------------------- */

static void wdt_begin(void)
{
    /* The API changed between ESP-IDF 4.x (Arduino core 2.x) and 5.x (Arduino core 3.x).
     * Support both so the build does not silently lose its watchdog on a platform bump —
     * and SR-6 is not a requirement to leave at the mercy of a version pin. */
#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(5, 0, 0)
    esp_task_wdt_config_t cfg = {};
    cfg.timeout_ms = SAW_WDT_TIMEOUT_MS;
    cfg.idle_core_mask = 0;
    cfg.trigger_panic = true;
    esp_err_t err = esp_task_wdt_init(&cfg);
    if (err == ESP_ERR_INVALID_STATE) {
        esp_task_wdt_reconfigure(&cfg);
    }
#else
    esp_task_wdt_init(SAW_WDT_TIMEOUT_MS / 1000, true);
#endif
    esp_task_wdt_add(NULL);
}

static inline void wdt_feed(void)
{
    esp_task_wdt_reset();
}

/* --------------------------------------------------------------------------- */
/* Boot                                                                        */
/* --------------------------------------------------------------------------- */

bool saw_protection_begin(void)
{
    if (!saw_primary_begin()) {
        Serial.println("primary sensor failed to initialise");
    }

    /*
     * Self-test: N valid reads out of M before arming is even considered. Track the last
     * *valid* reading rather than the last reading, because the final read of the loop
     * may well be the failure that ends it.
     */
    int   valid = 0;
    bool  have_valid = false;
    float last_valid_c = 0.0f;

    for (int i = 0; i < SAW_SELFTEST_READS; i++) {
        SawReading r = saw_primary_read();
        if (saw_reading_believable(r, SENSOR_LIMITS)) {
            valid++;
            have_valid = true;
            last_valid_c = r.celsius;
        }
        delay(SAW_SELFTEST_GAP_MS);
    }

    /* saw_boot() latches the failure into the context as boot_failed, which is what holds
     * the LED on SOS and keeps the state machine out of ARMED for the rest of this
     * session. E05 clears by power cycle, not by the sensor recovering. */
    bool passed = (valid >= SAW_SELFTEST_REQUIRED) && have_valid;

    Serial.printf("self-test: %d/%d valid reads (need %d)\n",
                  valid, (int)SAW_SELFTEST_READS, (int)SAW_SELFTEST_REQUIRED);

    saw_boot(s_ctx, LIMITS, saw_store_last_state(), passed, last_valid_c, millis(),
             log_event, NULL);
    s_ctx.trips_lifetime = saw_store_trips_lifetime();

    /* The state machine has decided; make the pin agree before anything else runs. */
    saw_hold_write(s_ctx.hold_closed);
    saw_store_set_last_state(s_ctx.state);
    s_state_entered_ms = millis();

#if SAW_CALIBRATED == 0
    saw_raise_alert(s_ctx, SAW_ALERT_UNCALIBRATED);
    log_event(NULL, SAW_EV_UNCALIBRATED_BUILD, NAN, 0);
#endif

    xTaskCreatePinnedToCore(saw_protection_task, "saw_protect", 4096, NULL,
                            configMAX_PRIORITIES - 2, NULL, 0);
    return passed;
}

/* --------------------------------------------------------------------------- */
/* Loop                                                                        */
/* --------------------------------------------------------------------------- */

static void publish(uint32_t now_ms, const SawReading &r, float frame_c, float ror)
{
    SawSnapshot s;
    s.state = (uint8_t)s_ctx.state;
    s.cause = (uint8_t)s_ctx.cause;
    s.led = (uint8_t)saw_led_for(s_ctx);
    s.hold_closed = s_ctx.hold_closed;
    s.celsius = s_ctx.have_reference ? s_ctx.last_valid_c : NAN;
    s.frame_c = frame_c;
    s.delta_c = (isnan(frame_c) || !s_ctx.have_reference) ? NAN
                                                         : s_ctx.last_valid_c - frame_c;
    /* MAX31855 cold-junction temperature. Useful during commissioning: a CJC reading
     * that drifts with a draft on the amplifier is the documented cause of both
     * calibration points being offset the same way. NAN on Path A. */
    s.internal_c = r.internal_c;
    s.ror_c_per_min = ror;
    s.ntc_raw = saw_ntc_last_raw();
    s.ntc_resistance = saw_ntc_last_resistance();
    s.alerts = s_ctx.alerts;
    s.uptime_ms = now_ms;
    s.state_ms = (uint32_t)(now_ms - s_state_entered_ms);
    s.cooldown_remaining_ms = 0;
    if (s_ctx.state == SAW_COOLDOWN) {
        uint32_t elapsed = (uint32_t)(now_ms - s_ctx.cooldown_start_ms);
        s.cooldown_remaining_ms =
            elapsed >= SAW_COOLDOWN_HOLD_MS ? 0 : SAW_COOLDOWN_HOLD_MS - elapsed;
    }
    s.sensor_age_ms = s_ctx.have_reference ? (uint32_t)(now_ms - s_ctx.last_valid_ms) : 0;
    s.trip_count = s_ctx.trips.count();
    s.trips_lifetime = s_ctx.trips_lifetime;
    s.session = saw_store_session();
    s.probe_verified = s_ctx.probe_verified;
    s.calibrated = (SAW_CALIBRATED != 0);
    s.fs_ok = saw_store_fs_ok();

    saw_runtime_publish(s);
}

void saw_protection_task(void *arg)
{
    (void)arg;

    wdt_begin();

    uint32_t last_hist_ms = 0;
    TickType_t last_wake = xTaskGetTickCount();

    for (;;) {
        uint32_t now = millis();

        SawReading r = saw_primary_read();
        SawVerdict verdict = saw_validate(r, SENSOR_LIMITS, s_ctx.have_reference,
                                          s_ctx.last_valid_c, now, s_ctx.last_valid_ms);

        /* SR-1, hardware first: any doubt at all drops the hold line before the state
         * machine, the log, or anything else gets a chance to run long. */
        if (verdict != SAW_VERDICT_VALID) {
            saw_hold_write(false);
        }

        SawState before = s_ctx.state;

        /* The web dashboard may acknowledge an alert. It may not do anything else — see
         * saw_runtime.h. Consumed here so the flag cannot accumulate. */
        if (saw_runtime_take_alert_clear()) {
            s_ctx.alerts = 0;
            s_ror_alert_latched = false;
            log_event(NULL, SAW_EV_ALERT_ACKED, NAN, 0);
        }

        SawAckEvent ack = saw_ack_poll(now);
        bool ack_for_lockout = (ack == SAW_ACK_SHORT_PRESS || ack == SAW_ACK_LONG_PRESS);
        if (ack == SAW_ACK_SHORT_PRESS && s_ctx.state != SAW_MANUAL_LOCKOUT) {
            /* Outside lockout the button only clears the alert banner. It cannot arm the
             * relay, lower a threshold, or bypass an active fault. */
            s_ctx.alerts = 0;
            s_ror_alert_latched = false;
            log_event(NULL, SAW_EV_ALERT_ACKED, NAN, 0);
        }

        saw_step(s_ctx, LIMITS, verdict, r.celsius, now, ack_for_lockout,
                 log_event, NULL);

        /* The only other place the hold line is written. */
        saw_hold_write(s_ctx.hold_closed);

        if (s_ctx.state != before) {
            s_state_entered_ms = now;
            /* Persist TRIPPED and MANUAL_LOCKOUT so a power cycle cannot clear them. */
            saw_store_set_last_state(s_ctx.state);
        }
        saw_store_set_trips_lifetime(s_ctx.trips_lifetime);

        /* --- advisory work, none of which can affect the hold line ------------- */

        float frame_c = NAN;
#if SAW_HAS_FRAME_NTC
        if (saw_frame_available()) {
            frame_c = saw_frame_celsius();
        }
#endif

        float ror = 0.0f;
        if (verdict == SAW_VERDICT_VALID) {
            s_ror.push(now, r.celsius);
            ror = s_ror.slope_c_per_min(now, SAW_ROR_WINDOW_MS);

            /* W02 needs a baseline from commissioning step 10. Without one there is
             * nothing to be faster than, so the alert stays off rather than guessing. */
            if (SAW_ROR_BASELINE_C_PER_MIN > 0.0f && s_ctx.state == SAW_ARMED) {
                if (ror > SAW_ROR_BASELINE_C_PER_MIN * SAW_ROR_ALERT_FACTOR) {
                    if (!s_ror_alert_latched) {
                        s_ror_alert_latched = true;
                        saw_raise_alert(s_ctx, SAW_ALERT_HEATING_FAST);
                        log_event(NULL, SAW_EV_HEATING_FASTER_THAN_BASELINE, ror, 0);
                    }
                } else if (ror < SAW_ROR_BASELINE_C_PER_MIN) {
                    s_ror_alert_latched = false;
                    s_ctx.alerts &= ~(uint32_t)SAW_ALERT_HEATING_FAST;
                }
            }

            s_sample_sum += r.celsius;
            s_sample_n++;
            if (!isnan(frame_c)) {
                s_frame_sum += frame_c;
                s_frame_n++;
            }
        }

        publish(now, r, frame_c, ror);

        /* Dashboard chart resolution: one point every 5 s covers 20 minutes in
         * SAW_LOG_RAM_SAMPLES without touching flash. */
        if (last_hist_ms == 0 || (uint32_t)(now - last_hist_ms) >= 5000u) {
            last_hist_ms = now;
            saw_runtime_push_history(now / 1000u,
                                     s_ctx.have_reference ? s_ctx.last_valid_c : NAN,
                                     frame_c, (uint8_t)s_ctx.state);
        }

        /* Long-term log: one aggregated record per SAW_LOG_PERIOD_S. */
        if (s_last_flush_ms == 0) {
            s_last_flush_ms = now;
        } else if ((uint32_t)(now - s_last_flush_ms) >=
                   (uint32_t)SAW_LOG_PERIOD_S * 1000UL) {
            s_last_flush_ms = now;
            SawSampleRecord rec;
            rec.session = saw_store_session();
            rec.uptime_s = now / 1000u;
            rec.c_x10 = s_sample_n
                            ? (int16_t)lroundf(s_sample_sum / (float)s_sample_n * 10.0f)
                            : INT16_MIN;
            rec.frame_x10 = s_frame_n
                                ? (int16_t)lroundf(s_frame_sum / (float)s_frame_n * 10.0f)
                                : INT16_MIN;
            rec.state = (uint8_t)s_ctx.state;
            rec.flags = (uint8_t)(s_ctx.alerts & 0xFFu);
            rec.crc = 0;
            saw_store_log_sample(rec);
            s_sample_sum = 0.0f;
            s_sample_n = 0;
            s_frame_sum = 0.0f;
            s_frame_n = 0;
        }

        saw_led_apply(saw_led_for(s_ctx), now);

        /* SR-6. Only reached on a complete cycle. */
        wdt_feed();

        /* vTaskDelayUntil rather than delay() so a slow flash write does not stretch the
         * sample interval and drift the loop away from SAW_SAMPLE_HZ. */
        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(SAW_LOOP_PERIOD_MS));
    }
}
