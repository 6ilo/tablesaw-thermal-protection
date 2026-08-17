#include "saw_sensor.h"

#include <math.h>

bool saw_reading_believable(const SawReading &r, const SawSensorLimits &lim)
{
    if (!r.answered) {
        return false;
    }
    if (r.fault_open || r.fault_short_gnd || r.fault_short_vcc || r.raw_out_of_band) {
        return false;
    }
    /* NaN fails every comparison below, which is the intent: a NaN temperature is a
     * fault, not a number to reason about. */
    if (!(r.celsius >= lim.min_c) || !(r.celsius <= lim.max_c)) {
        return false;
    }
    return true;
}

SawVerdict saw_validate(const SawReading &r, const SawSensorLimits &lim,
                        bool have_reference, float last_valid_c,
                        uint32_t now_ms, uint32_t last_valid_ms)
{
    bool believable = saw_reading_believable(r, lim);

    if (believable && have_reference) {
        float jump = r.celsius - last_valid_c;
        if (jump < 0.0f) {
            jump = -jump;
        }
        if (jump > lim.max_jump_c) {
            believable = false;
        }
    }

    if (believable) {
        /* A believable reading that arrived after a long stall is still evidence the
         * loop lost time. Report the staleness rather than accept it silently — the
         * whole point of SENSOR_TIMEOUT is that running blind is not allowed, and a
         * stalled loop was blind for the same interval a dead bus would have been. */
        if (have_reference && (uint32_t)(now_ms - last_valid_ms) > lim.timeout_ms) {
            return SAW_VERDICT_TIMEOUT;
        }
        return SAW_VERDICT_VALID;
    }

    /* Nothing valid for longer than the timeout window, and the chain is not even
     * answering: that is E03, the bus rather than the probe. */
    if (!r.answered && have_reference &&
        (uint32_t)(now_ms - last_valid_ms) > lim.timeout_ms) {
        return SAW_VERDICT_TIMEOUT;
    }

    return SAW_VERDICT_FAULT;
}
