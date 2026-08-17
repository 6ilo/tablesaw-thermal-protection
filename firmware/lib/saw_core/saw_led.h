/*
 * Status LED pattern engine — ARCHITECTURE.md § Status LED patterns.
 *
 * The LED is the operator's primary indicator at the machine, because the dashboard is
 * on a phone that may be in another room. Seven distinguishable patterns:
 *
 *   Solid ON                     ARMED                    Ready. Press Start.
 *   Slow blink (1 Hz)            COOLDOWN                 Wait for solid.
 *   Fast blink (5 Hz)            TRIPPED — thermal        Motor overtemperature.
 *   Double-blink then pause      TRIPPED — sensor fault   Check sensor / wiring.
 *   Triple-blink then long pause MANUAL_LOCKOUT           Too many trips.
 *   SOS pattern                  Boot self-test failed    Do not use. Power-cycle.
 *   Off                          unpowered / pre-boot     Do not use.
 *
 * saw_led_output() is a pure function of the pattern and how long that pattern has been
 * showing, so it cannot stall the safety loop the way a delay()-based blinker would,
 * and the whole engine is testable on the host.
 */
#pragma once

#include <stdint.h>

enum SawLedPattern {
    SAW_LED_OFF = 0,
    SAW_LED_SOLID,
    SAW_LED_SLOW_BLINK,
    SAW_LED_FAST_BLINK,
    SAW_LED_DOUBLE_BLINK,
    SAW_LED_TRIPLE_BLINK,
    SAW_LED_SOS,
};

/* True when the LED should be lit, `elapsed_ms` into the pattern. */
bool saw_led_output(SawLedPattern pattern, uint32_t elapsed_ms);

/* Full cycle length of a pattern in ms; 0 for the two static patterns. */
uint32_t saw_led_period_ms(SawLedPattern pattern);

const char *saw_led_name(SawLedPattern pattern);
