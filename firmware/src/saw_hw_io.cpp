#include <Arduino.h>

#include "saw_config.h"
#include "saw_hw.h"

/* --------------------------------------------------------------------------- */
/* Hold line                                                                   */
/* --------------------------------------------------------------------------- */

static bool s_hold_closed = false;

void saw_hold_init(void)
{
    /* Order matters. Drive the level before enabling the output so the pin cannot glitch
     * high for the microseconds between pinMode() and the first write. */
    digitalWrite(SAW_PIN_HOLD, LOW);
    pinMode(SAW_PIN_HOLD, OUTPUT);
    digitalWrite(SAW_PIN_HOLD, LOW);
    s_hold_closed = false;
}

void saw_hold_write(bool closed)
{
    s_hold_closed = closed;
    digitalWrite(SAW_PIN_HOLD, closed ? HIGH : LOW);
}

bool saw_hold_is_closed(void)
{
    return s_hold_closed;
}

/* --------------------------------------------------------------------------- */
/* Status LED                                                                  */
/* --------------------------------------------------------------------------- */

static SawLedPattern s_pattern = SAW_LED_OFF;
static uint32_t      s_pattern_start_ms = 0;
static bool          s_led_lit = false;

void saw_led_init(void)
{
    pinMode(SAW_PIN_LED, OUTPUT);
    digitalWrite(SAW_PIN_LED, LOW);
    s_pattern = SAW_LED_OFF;
    s_pattern_start_ms = 0;
    s_led_lit = false;
}

void saw_led_apply(SawLedPattern pattern, uint32_t now_ms)
{
    if (pattern != s_pattern) {
        s_pattern = pattern;
        s_pattern_start_ms = now_ms;
    }

    bool lit = saw_led_output(s_pattern, (uint32_t)(now_ms - s_pattern_start_ms));
    if (lit != s_led_lit) {
        s_led_lit = lit;
        digitalWrite(SAW_PIN_LED, lit ? HIGH : LOW);
    }
}

SawLedPattern saw_led_current(void)
{
    return s_pattern;
}

/* --------------------------------------------------------------------------- */
/* Ack button                                                                  */
/* --------------------------------------------------------------------------- */

#define ACK_LONG_MS   3000
#define ACK_SHORT_MAX 2000

static bool     s_raw_last = false;
static bool     s_stable = false;
static uint32_t s_change_ms = 0;
static uint32_t s_press_start_ms = 0;
static bool     s_long_reported = false;

void saw_ack_init(void)
{
#if SAW_HAS_ACK_BUTTON
    pinMode(SAW_PIN_ACK, INPUT_PULLUP);
#endif
    s_raw_last = false;
    s_stable = false;
    s_change_ms = 0;
    s_press_start_ms = 0;
    s_long_reported = false;
}

SawAckEvent saw_ack_poll(uint32_t now_ms)
{
#if !SAW_HAS_ACK_BUTTON
    (void)now_ms;
    return SAW_ACK_NONE;
#else
    /* Pullup to 3V3, button to GND: LOW means pressed. */
    bool raw = (digitalRead(SAW_PIN_ACK) == LOW);

    if (raw != s_raw_last) {
        s_raw_last = raw;
        s_change_ms = now_ms;
        return SAW_ACK_NONE;
    }

    if ((uint32_t)(now_ms - s_change_ms) < SAW_ACK_DEBOUNCE_MS) {
        return SAW_ACK_NONE;   /* still bouncing */
    }

    if (raw == s_stable) {
        /* Held. Report a long press once, without waiting for release, so the operator
         * gets feedback while their finger is still on the button. */
        if (s_stable && !s_long_reported &&
            (uint32_t)(now_ms - s_press_start_ms) >= ACK_LONG_MS) {
            s_long_reported = true;
            return SAW_ACK_LONG_PRESS;
        }
        return SAW_ACK_NONE;
    }

    /* Debounced edge. */
    s_stable = raw;
    if (s_stable) {
        s_press_start_ms = now_ms;
        s_long_reported = false;
        return SAW_ACK_NONE;
    }

    /* Released. */
    uint32_t held = (uint32_t)(now_ms - s_press_start_ms);
    if (s_long_reported) {
        return SAW_ACK_NONE;   /* already reported as a long press */
    }
    if (held < ACK_SHORT_MAX) {
        return SAW_ACK_SHORT_PRESS;
    }
    /* Between 2 s and 3 s: neither, per the ack table in ARCHITECTURE.md. */
    return SAW_ACK_NONE;
#endif
}
