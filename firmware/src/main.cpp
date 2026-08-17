/*
 * Table saw thermal protection supervisor — ESP32.
 *
 * Design of record: ARCHITECTURE.md (Path B) and BUILD-TONIGHT.md (Path A).
 * Operator-facing fault codes: docs/codes/, compiled in via generated/error_codes.h.
 *
 * The first executable statement in setup() drives the hold line low. Everything else —
 * the serial port, the log, the state machine, the network — happens after the coil
 * circuit is known to be open. That ordering is SR-1 and it is not negotiable: a board
 * that has just been powered, or has just crashed and restarted, must not be able to
 * close a contactor coil circuit while it works out what is going on.
 */
#include <Arduino.h>
#include <esp_system.h>

#include "error_codes.h"
#include "saw_calibration.h"
#include "saw_config.h"
#include "saw_hw.h"
#include "saw_net.h"
#include "saw_protection.h"
#include "saw_runtime.h"
#include "saw_store.h"

static const char *reset_reason_name(void)
{
    switch (esp_reset_reason()) {
    case ESP_RST_POWERON:  return "power-on";
    case ESP_RST_EXT:      return "external reset";
    case ESP_RST_SW:       return "software reset";
    case ESP_RST_PANIC:    return "panic / exception";
    case ESP_RST_INT_WDT:  return "interrupt watchdog";
    case ESP_RST_TASK_WDT: return "TASK WATCHDOG";
    case ESP_RST_WDT:      return "other watchdog";
    case ESP_RST_BROWNOUT: return "brown-out";
    case ESP_RST_SDIO:     return "SDIO";
    default:               return "unknown";
    }
}

static void banner(void)
{
    Serial.println();
    Serial.println("=== table saw thermal supervisor ===");
    Serial.printf("path            %s\n", SAW_PATH_NAME);
    Serial.printf("primary sensor  %s\n", saw_primary_name());
    Serial.printf("trip / warn / reset   %.1f / %.1f / %.1f C (%s temperature)\n",
                  (double)SAW_TRIP_C, (double)SAW_WARN_C, (double)SAW_RESET_C,
                  SAW_SENSOR_LOCATION);
    Serial.printf("cooldown hold   %d s\n", (int)SAW_COOLDOWN_HOLD_S);
    Serial.printf("sensor timeout  %d ms   loop %d Hz   wdt %d ms\n",
                  (int)SAW_SENSOR_TIMEOUT_MS, (int)SAW_SAMPLE_HZ,
                  (int)SAW_WDT_TIMEOUT_MS);
    Serial.printf("lockout after   %d trips in %d min\n",
                  (int)SAW_MAX_CONSECUTIVE_TRIPS, (int)SAW_TRIP_WINDOW_MIN);
    Serial.printf("hold pin        GPIO%d (active HIGH, needs a 10k pulldown to GND)\n",
                  (int)SAW_PIN_HOLD);
    Serial.printf("led / ack       GPIO%d / GPIO%d%s\n", (int)SAW_PIN_LED,
                  (int)SAW_PIN_ACK, SAW_HAS_ACK_BUTTON ? "" : " (no ack button)");
    Serial.printf("code registry   %s, %d codes\n", SAW_REGISTRY_VERSION,
                  (int)SAW_CODE_COUNT);
    Serial.printf("reset reason    %s\n", reset_reason_name());
    Serial.printf("log             %s, %lu h ring at %d s/record\n",
                  saw_store_fs_ok() ? "ok" : "UNAVAILABLE",
                  (unsigned long)saw_store_retention_hours(), (int)SAW_LOG_PERIOD_S);
    Serial.printf("session         %lu\n", (unsigned long)saw_store_session());
#if SAW_CALIBRATED == 0
    Serial.println("calibration     *** DEFAULTS IN USE — run the two-point procedure "
                   "in ARCHITECTURE.md and set SAW_CALIBRATED to 1 ***");
#else
    Serial.printf("calibration     r_fixed %.0f ohm, beta %.0f, offset %+.2f C\n",
                  (double)SAW_NTC_R_FIXED_OHMS, (double)SAW_NTC_BETA,
                  (double)SAW_NTC_OFFSET_C);
#endif
    Serial.println("the contact is open until the state machine says otherwise");
    Serial.println();
}

void setup()
{
    /* FIRST. Contact open before anything else runs. */
    saw_hold_init();
    saw_led_init();
    saw_ack_init();

    Serial.begin(SAW_SERIAL_BAUD);
    /* Bounded wait: a supervisor must not sit here forever because nobody has a terminal
     * open. 600 ms is enough for the USB-serial bridge to come up on a Mac. */
    uint32_t t0 = millis();
    while (!Serial && (millis() - t0) < 600u) {
        delay(10);
    }

    saw_runtime_init();
    saw_store_begin();

    banner();

    /* Runs the boot self-test, decides BOOT -> ARMED / TRIPPED / MANUAL_LOCKOUT, and
     * starts the core-0 protection task. Its return value is advisory here: on a failed
     * self-test the task still runs, with the contact held open and the LED on SOS, so
     * the supervisor recovers on its own if the sensor does. */
    bool ok = saw_protection_begin();
    if (!ok) {
        Serial.println("BOOT SELF-TEST FAILED — see docs/codes/E05.md. Contact stays "
                       "open; the saw cannot start.");
    }

    /* Advisory only, on core 1, and started last so a Wi-Fi stall cannot delay any of
     * the above. SR-8. */
    saw_net_begin();
}

void loop()
{
    /*
     * Nothing runs here. Protection is a pinned core-0 task and the dashboard is a
     * pinned core-1 task, so the Arduino loop task has no work — and giving it any would
     * put code on the same task as the framework's own housekeeping, which is exactly the
     * coupling the two-task layout exists to avoid.
     */
    vTaskDelay(pdMS_TO_TICKS(1000));
}
