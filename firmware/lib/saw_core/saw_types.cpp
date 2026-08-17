#include "saw_types.h"

static const char *const STATE_NAMES[] = {
    "BOOT", "ARMED", "TRIPPED", "COOLDOWN", "MANUAL_LOCKOUT",
};

/* Order must track enum SawEvent exactly. */
static const char *const EVENT_NAMES[SAW_EV_COUNT] = {
    "BOOT",
    "ARMED",
    "COOLDOWN",
    "OVERTEMP",
    "SENSOR_FAULT",
    "SENSOR_TIMEOUT",
    "SENSOR_RECOVERED",
    "MANUAL_LOCKOUT_ENTERED",
    "LOCKOUT_CLEARED_BY_ACK",
    "ACK_REJECTED_HOT",
    "BOOT_SENSOR_FAIL",
    "BOOT_HOT_HOLD",
    "BOOT_INTO_LOCKOUT",
    "APPROACHING_TRIP",
    "HEATING_FASTER_THAN_BASELINE",
    "PROBE_VERIFIED",
    "PROBE_UNVERIFIED_AT_ARMED_TIME",
    "ALERT_ACKED",
    "UNCALIBRATED_BUILD",
};

const char *saw_state_name(SawState s)
{
    if (s < SAW_BOOT || s > SAW_MANUAL_LOCKOUT) {
        return "?";
    }
    return STATE_NAMES[s];
}

const char *saw_event_name(SawEvent e)
{
    if (e < 0 || e >= SAW_EV_COUNT) {
        return "?";
    }
    return EVENT_NAMES[e];
}

SawEvent saw_cause_to_event(SawCause c)
{
    switch (c) {
    case SAW_CAUSE_OVERTEMP:         return SAW_EV_OVERTEMP;
    case SAW_CAUSE_SENSOR_FAULT:     return SAW_EV_SENSOR_FAULT;
    case SAW_CAUSE_SENSOR_TIMEOUT:   return SAW_EV_SENSOR_TIMEOUT;
    case SAW_CAUSE_BOOT_SENSOR_FAIL: return SAW_EV_BOOT_SENSOR_FAIL;
    case SAW_CAUSE_BOOT_HOT_HOLD:    return SAW_EV_BOOT_HOT_HOLD;
    case SAW_CAUSE_NONE:
    default:                         return SAW_EV_BOOT;
    }
}

const char *saw_cause_event(SawCause c)
{
    if (c == SAW_CAUSE_NONE) {
        return "";
    }
    return saw_event_name(saw_cause_to_event(c));
}
