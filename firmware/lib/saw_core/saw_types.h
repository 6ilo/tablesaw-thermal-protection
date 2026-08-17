/*
 * Shared types for the protection core.
 *
 * Everything in lib/saw_core/ is pure C++ with no Arduino or ESP-IDF dependency, so
 * the state machine, the trip counter, the sensor validation rules, the NTC maths and
 * the LED pattern engine all compile and run on a host machine. `pio test -e native`
 * exercises them before anything is flashed. See firmware/README.md.
 *
 * Event names in this file are load-bearing: they are matched against the `event`
 * field of the error-code registry in docs/codes/ via saw_code_by_event() from the
 * generated generated/error_codes.h. Renaming one here silently de-links an operator
 * error code from the firmware that is supposed to raise it, so
 * test_event_registry checks every mapping.
 */
#pragma once

#include <stdint.h>

/* --------------------------------------------------------------------------- */
/* State machine — ARCHITECTURE.md § Software architecture                      */
/* --------------------------------------------------------------------------- */

enum SawState {
    SAW_BOOT           = 0,  /* relay open, self-test running                  */
    SAW_ARMED          = 1,  /* relay closed, saw may run                      */
    SAW_TRIPPED        = 2,  /* relay open, event logged                       */
    SAW_COOLDOWN       = 3,  /* relay open, anti-chatter hold running          */
    SAW_MANUAL_LOCKOUT = 4,  /* relay open, no auto-recovery                   */
};

/* Why the supervisor last opened the relay. Maps 1:1 onto a registry event so the
 * LED pattern and the logged error code cannot disagree. */
enum SawCause {
    SAW_CAUSE_NONE = 0,
    SAW_CAUSE_OVERTEMP,          /* E01 */
    SAW_CAUSE_SENSOR_FAULT,      /* E02 — got an answer, did not believe it    */
    SAW_CAUSE_SENSOR_TIMEOUT,    /* E03 — got no answer at all                 */
    SAW_CAUSE_BOOT_SENSOR_FAIL,  /* E05 */
    SAW_CAUSE_BOOT_HOT_HOLD,     /* E06 */
};

/* --------------------------------------------------------------------------- */
/* Log / alert events                                                          */
/* --------------------------------------------------------------------------- */

enum SawEvent {
    SAW_EV_BOOT = 0,
    SAW_EV_ARMED,
    SAW_EV_COOLDOWN,
    SAW_EV_OVERTEMP,
    SAW_EV_SENSOR_FAULT,
    SAW_EV_SENSOR_TIMEOUT,
    SAW_EV_SENSOR_RECOVERED,
    SAW_EV_MANUAL_LOCKOUT_ENTERED,
    SAW_EV_LOCKOUT_CLEARED_BY_ACK,
    SAW_EV_ACK_REJECTED_HOT,
    SAW_EV_BOOT_SENSOR_FAIL,
    SAW_EV_BOOT_HOT_HOLD,
    SAW_EV_BOOT_INTO_LOCKOUT,
    SAW_EV_APPROACHING_TRIP,
    SAW_EV_HEATING_FASTER_THAN_BASELINE,
    SAW_EV_PROBE_VERIFIED,
    SAW_EV_PROBE_UNVERIFIED_AT_ARMED_TIME,
    SAW_EV_ALERT_ACKED,
    SAW_EV_UNCALIBRATED_BUILD,
    SAW_EV_COUNT,
};

/* Dashboard alert flags. Advisory only — nothing here influences the relay. */
enum SawAlert {
    SAW_ALERT_APPROACHING_TRIP = 1u << 0,  /* W01 */
    SAW_ALERT_HEATING_FAST     = 1u << 1,  /* W02 */
    SAW_ALERT_PROBE_UNVERIFIED = 1u << 2,  /* W03 */
    SAW_ALERT_UNCALIBRATED     = 1u << 3,  /* build carries default calibration */
};

const char *saw_state_name(SawState s);
const char *saw_event_name(SawEvent e);

/* The registry event string for a trip cause, or "" for SAW_CAUSE_NONE. */
const char *saw_cause_event(SawCause c);

/* The event a cause should be logged as. */
SawEvent saw_cause_to_event(SawCause c);
