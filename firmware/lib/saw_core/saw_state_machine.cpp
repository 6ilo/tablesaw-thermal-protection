#include "saw_state_machine.h"

#include "saw_led.h"

SawContext::SawContext()
    : state(SAW_BOOT),
      cause(SAW_CAUSE_NONE),
      hold_closed(false),
      boot_failed(false),
      cooldown_start_ms(0),
      trips(),
      last_valid_c(0.0f),
      last_valid_ms(0),
      have_reference(false),
      session_baseline_c(0.0f),
      have_baseline(false),
      probe_verified(false),
      armed_ms(0),
      detach_alert_raised(false),
      alerts(0),
      warn_latched(false),
      last_step_ms(0),
      have_step_time(false),
      trips_lifetime(0)
{
}

static void emit(SawEventSink sink, void *ctx, SawEvent ev, float value, int32_t detail)
{
    if (sink) {
        sink(ctx, ev, value, detail);
    }
}

/* The single point where hold_closed is written. Anything that changes state must go
 * through here afterwards so the invariant cannot drift. */
static void apply_hold(SawContext &c)
{
    c.hold_closed = (c.state == SAW_ARMED);
}

void saw_raise_alert(SawContext &c, uint32_t alert)
{
    c.alerts |= alert;
}

void saw_clear_alerts(SawContext &c)
{
    c.alerts = 0;
}

/*
 * Record a trip. Called on the *edge* into TRIPPED, not once per cycle — see
 * saw_trip_counter.h for why.
 *
 * hold_closed goes false before any of the bookkeeping below can fail or branch: the
 * relay decision is never downstream of a log write or a counter update. The caller
 * additionally drops the physical pin before calling saw_step() at all when the sensor
 * verdict is not VALID, so the hardware leads the state machine rather than trailing it.
 */
static void do_trip(SawContext &c, const SawLimits &lim, SawCause cause,
                    uint32_t now_ms, SawEventSink sink, void *sink_ctx)
{
    c.hold_closed = false;

    if (c.state == SAW_MANUAL_LOCKOUT) {
        /* Already locked out. Do not cascade, do not re-count. */
        apply_hold(c);
        return;
    }

    bool entering = (c.state != SAW_TRIPPED);
    SawCause previous = c.cause;
    c.cause = cause;

    if (entering) {
        c.state = SAW_TRIPPED;
        bool escalate = c.trips.record(now_ms, lim.max_consecutive_trips,
                                       lim.trip_window_ms);
        if (c.trips_lifetime < 0xFFFFFFFFu) {
            c.trips_lifetime++;
        }
        emit(sink, sink_ctx, saw_cause_to_event(cause), c.last_valid_c,
             (int32_t)c.trips.count());

        if (escalate) {
            c.state = SAW_MANUAL_LOCKOUT;
            emit(sink, sink_ctx, SAW_EV_MANUAL_LOCKOUT_ENTERED, c.last_valid_c,
                 (int32_t)c.trips.count());
        }
    } else if (cause != previous) {
        /* Already tripped, but the diagnosis changed — a sensor fault that has gone
         * from "answered badly" to "stopped answering" is E02 followed by E03, and the
         * operator needs both lines to know which hardware to look at. Not a new trip. */
        emit(sink, sink_ctx, saw_cause_to_event(cause), c.last_valid_c,
             (int32_t)c.trips.count());
    }

    apply_hold(c);
}

void saw_boot(SawContext &c, const SawLimits &lim,
              SawState persisted, bool self_test_passed, float boot_c,
              uint32_t now_ms, SawEventSink sink, void *sink_ctx)
{
    c.hold_closed = false;
    c.alerts = 0;
    c.trips.reset();
    c.warn_latched = false;
    c.have_step_time = false;
    c.last_step_ms = now_ms;
    c.armed_ms = 0;
    c.probe_verified = false;
    c.detach_alert_raised = false;

    c.boot_failed = !self_test_passed;

    if (!self_test_passed) {
        c.state = SAW_TRIPPED;
        c.cause = SAW_CAUSE_BOOT_SENSOR_FAIL;
        c.have_reference = false;
        c.last_valid_c = 0.0f;
        c.last_valid_ms = now_ms;
        c.have_baseline = false;
        c.session_baseline_c = 0.0f;
        emit(sink, sink_ctx, SAW_EV_BOOT_SENSOR_FAIL, 0.0f, 0);
        apply_hold(c);
        return;
    }

    /* Prime the running-loop guards from the self-test result so the implausible-jump
     * and staleness checks have a valid reference on the very first cycle. */
    c.have_reference = true;
    c.last_valid_c = boot_c;
    c.last_valid_ms = now_ms;
    c.session_baseline_c = boot_c;
    c.have_baseline = true;

    if (persisted == SAW_TRIPPED && boot_c >= lim.reset_c) {
        /* A hot power-cycle does not clear a trip. */
        c.state = SAW_TRIPPED;
        c.cause = SAW_CAUSE_BOOT_HOT_HOLD;
        emit(sink, sink_ctx, SAW_EV_BOOT_HOT_HOLD, boot_c, 0);
    } else {
        c.state = SAW_COOLDOWN;
        c.cause = SAW_CAUSE_NONE;
        c.cooldown_start_ms = now_ms;
    }

    /* A persisted lockout overrides the temperature-based decision above. Power-cycling
     * is not a way out of MANUAL_LOCKOUT. */
    if (persisted == SAW_MANUAL_LOCKOUT) {
        c.state = SAW_MANUAL_LOCKOUT;
        emit(sink, sink_ctx, SAW_EV_BOOT_INTO_LOCKOUT, boot_c, 0);
    }

    apply_hold(c);
}

void saw_step(SawContext &c, const SawLimits &lim,
              SawVerdict verdict, float celsius, uint32_t now_ms,
              bool ack_pressed, SawEventSink sink, void *sink_ctx)
{
    uint32_t dt_ms = 0;
    if (c.have_step_time) {
        dt_ms = (uint32_t)(now_ms - c.last_step_ms);
        /* A stall longer than a couple of seconds is already a SENSOR_TIMEOUT; do not
         * let it inflate the ARMED-time accumulator too. */
        if (dt_ms > 2000u) {
            dt_ms = 2000u;
        }
    }
    c.last_step_ms = now_ms;
    c.have_step_time = true;

    if (verdict != SAW_VERDICT_VALID) {
        SawCause cause = (verdict == SAW_VERDICT_TIMEOUT) ? SAW_CAUSE_SENSOR_TIMEOUT
                                                          : SAW_CAUSE_SENSOR_FAULT;
        do_trip(c, lim, cause, now_ms, sink, sink_ctx);
        return;
    }

    bool recovering = (c.cause == SAW_CAUSE_SENSOR_FAULT ||
                       c.cause == SAW_CAUSE_SENSOR_TIMEOUT ||
                       c.cause == SAW_CAUSE_BOOT_SENSOR_FAIL);
    if (recovering) {
        emit(sink, sink_ctx, SAW_EV_SENSOR_RECOVERED, celsius, 0);
        c.cause = SAW_CAUSE_NONE;
    }

    c.last_valid_c = celsius;
    c.last_valid_ms = now_ms;
    c.have_reference = true;
    if (!c.have_baseline) {
        /* A failed boot self-test leaves no baseline. Adopt the first good reading so
         * probe verification still has something to measure a rise against. */
        c.session_baseline_c = celsius;
        c.have_baseline = true;
    }

    switch (c.state) {
    case SAW_ARMED:
        c.armed_ms += dt_ms;
        if (celsius >= lim.trip_c) {
            do_trip(c, lim, SAW_CAUSE_OVERTEMP, now_ms, sink, sink_ctx);
            return;
        }
        if (celsius >= lim.warn_c) {
            if (!c.warn_latched) {
                c.warn_latched = true;
                saw_raise_alert(c, SAW_ALERT_APPROACHING_TRIP);
                emit(sink, sink_ctx, SAW_EV_APPROACHING_TRIP, celsius, 0);
            }
        } else if (celsius < lim.warn_c - lim.warn_clear_hysteresis_c) {
            c.warn_latched = false;
            c.alerts &= ~(uint32_t)SAW_ALERT_APPROACHING_TRIP;
        }
        break;

    case SAW_TRIPPED:
        /* E05 clears by power cycle, not by the sensor coming back. A supervisor that
         * could not prove its sensor at boot does not get to arm this session. */
        if (!c.boot_failed && celsius < lim.reset_c) {
            c.state = SAW_COOLDOWN;
            c.cooldown_start_ms = now_ms;
            emit(sink, sink_ctx, SAW_EV_COOLDOWN, celsius, 0);
        }
        break;

    case SAW_COOLDOWN:
        if (celsius >= lim.reset_c) {
            /* Re-heated during the hold. Back to TRIPPED and restart the hold. Not a
             * new trip: the relay never re-closed, so nothing chattered. */
            c.state = SAW_TRIPPED;
            if (c.cause == SAW_CAUSE_NONE) {
                c.cause = SAW_CAUSE_OVERTEMP;
            }
        } else if ((uint32_t)(now_ms - c.cooldown_start_ms) > lim.cooldown_hold_ms) {
            c.state = SAW_ARMED;
            c.cause = SAW_CAUSE_NONE;
            c.warn_latched = false;
            emit(sink, sink_ctx, SAW_EV_ARMED, celsius, 0);
            /* SR-4: closing the contact does NOT start the saw. The starter's 3-wire
             * seal-in requires a physical press of the Start button. */
        }
        break;

    case SAW_MANUAL_LOCKOUT:
        if (ack_pressed) {
            if (celsius < lim.reset_c) {
                c.state = SAW_COOLDOWN;
                c.cooldown_start_ms = now_ms;
                c.cause = SAW_CAUSE_NONE;
                c.trips.reset();
                saw_clear_alerts(c);
                emit(sink, sink_ctx, SAW_EV_LOCKOUT_CLEARED_BY_ACK, celsius, 0);
            } else {
                emit(sink, sink_ctx, SAW_EV_ACK_REJECTED_HOT, celsius, 0);
            }
        }
        break;

    case SAW_BOOT:
    default:
        /* saw_boot() always leaves a definite state. Reaching here means the context
         * was never initialised, so hold the contact open and say so. */
        do_trip(c, lim, SAW_CAUSE_BOOT_SENSOR_FAIL, now_ms, sink, sink_ctx);
        return;
    }

    /* Probe self-verification — advisory only, never trips. Once verified it stays
     * verified: a probe that has warmed once is attached. */
    if (!c.probe_verified) {
        if ((celsius - c.session_baseline_c) >= lim.detach_min_rise_c) {
            c.probe_verified = true;
            c.alerts &= ~(uint32_t)SAW_ALERT_PROBE_UNVERIFIED;
            emit(sink, sink_ctx, SAW_EV_PROBE_VERIFIED,
                 celsius - c.session_baseline_c, 0);
        } else if (!c.detach_alert_raised && c.armed_ms > lim.detach_alert_ms) {
            c.detach_alert_raised = true;
            saw_raise_alert(c, SAW_ALERT_PROBE_UNVERIFIED);
            emit(sink, sink_ctx, SAW_EV_PROBE_UNVERIFIED_AT_ARMED_TIME,
                 celsius - c.session_baseline_c, 0);
        }
    }

    apply_hold(c);
}

SawLedPattern saw_led_for(const SawContext &c)
{
    if (c.boot_failed) {
        return SAW_LED_SOS;
    }
    switch (c.state) {
    case SAW_ARMED:
        return SAW_LED_SOLID;
    case SAW_COOLDOWN:
        return SAW_LED_SLOW_BLINK;
    case SAW_TRIPPED:
        if (c.cause == SAW_CAUSE_SENSOR_FAULT || c.cause == SAW_CAUSE_SENSOR_TIMEOUT) {
            return SAW_LED_DOUBLE_BLINK;
        }
        if (c.cause == SAW_CAUSE_BOOT_SENSOR_FAIL) {
            return SAW_LED_SOS;
        }
        return SAW_LED_FAST_BLINK;
    case SAW_MANUAL_LOCKOUT:
        return SAW_LED_TRIPLE_BLINK;
    case SAW_BOOT:
    default:
        return SAW_LED_SOS;
    }
}
