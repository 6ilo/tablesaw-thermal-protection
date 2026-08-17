/*
 * Board-level I/O. Everything that touches a pin lives behind this header so the
 * protection loop reads the same on either build path.
 */
#pragma once

#include <stdint.h>

#include "saw_led.h"
#include "saw_sensor.h"

/* --------------------------------------------------------------------------- */
/* The hold line — GPIO26                                                      */
/* --------------------------------------------------------------------------- */

/*
 * Path A: drives the 433 MHz fob's ON pad through a level shifter. HIGH = transmitting =
 *         the receiver's momentary contact is held closed.
 * Path B: drives a wired opto-isolated active-HIGH relay module. HIGH = contact closed.
 *
 * Either way: HIGH means the contactor coil circuit may be closed, and the pin is driven
 * LOW before anything else in setup(). An external 10 kΩ pulldown makes "floating" mean
 * LOW during boot, after a crash and through a brown-out.
 */
void saw_hold_init(void);
void saw_hold_write(bool closed);
bool saw_hold_is_closed(void);

/* --------------------------------------------------------------------------- */
/* Status LED — GPIO2                                                          */
/* --------------------------------------------------------------------------- */

void saw_led_init(void);
/* Non-blocking. Call once per protection cycle; tracks its own pattern start time. */
void saw_led_apply(SawLedPattern pattern, uint32_t now_ms);
SawLedPattern saw_led_current(void);

/* --------------------------------------------------------------------------- */
/* Ack button — GPIO27 to GND, internal pullup                                 */
/* --------------------------------------------------------------------------- */

enum SawAckEvent {
    SAW_ACK_NONE = 0,
    SAW_ACK_SHORT_PRESS,   /* released before 2 s  */
    SAW_ACK_LONG_PRESS,    /* held 3 s or more     */
};

void saw_ack_init(void);
/* Debounced. Returns an event once per press, on release (or when a long hold matures). */
SawAckEvent saw_ack_poll(uint32_t now_ms);

/* --------------------------------------------------------------------------- */
/* Sensors                                                                     */
/* --------------------------------------------------------------------------- */

/* The trip source: MAX31855 at the winding on Path B, frame NTC on Path A. */
bool        saw_primary_begin(void);
SawReading  saw_primary_read(void);
const char *saw_primary_name(void);

/* Advisory frame sensor. Path B only; Path A's frame NTC is already the primary, so
 * saw_frame_available() is false and the delta is not meaningful. */
bool  saw_frame_available(void);
float saw_frame_celsius(void);   /* NAN when unavailable or faulted */

/* Raw ADC + implied resistance, for the calibration procedure's serial output. */
int32_t saw_ntc_last_raw(void);
float   saw_ntc_last_resistance(void);
