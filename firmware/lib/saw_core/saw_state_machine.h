/*
 * The protection state machine — ARCHITECTURE.md § State machine.
 *
 *   [*]            -> BOOT
 *   BOOT           -> ARMED           sensor OK, temp < RESET
 *   BOOT           -> TRIPPED         sensor fail, or persisted TRIPPED and still hot
 *   ARMED          -> TRIPPED         temp >= TRIP, or any SR-5 sensor doubt
 *   TRIPPED        -> COOLDOWN        temp < RESET
 *   TRIPPED        -> MANUAL_LOCKOUT  MAX_CONSECUTIVE_TRIPS inside TRIP_WINDOW
 *   COOLDOWN       -> ARMED           sustained below RESET for COOLDOWN_HOLD
 *   COOLDOWN       -> TRIPPED         re-heated above RESET, or any fault
 *   MANUAL_LOCKOUT -> COOLDOWN        ack pressed while temp < RESET
 *
 * No Arduino, no I/O, no clock of its own: the caller supplies the reading, the
 * verdict, the millisecond timestamp and the ack state, and gets back a context whose
 * `hold_closed` field is the only thing the relay driver is allowed to look at.
 *
 * `hold_closed` is true if and only if state == ARMED. Nothing else can close the
 * contact — not an alert acknowledgement, not a web request, not a threshold edit.
 * That is SR-1 and SR-2 expressed as a single invariant, and test_state_machine
 * asserts it after every transition.
 */
#pragma once

#include "saw_led.h"
#include "saw_sensor.h"
#include "saw_trip_counter.h"
#include "saw_types.h"

struct SawLimits {
    float    trip_c;
    float    warn_c;
    float    reset_c;
    uint32_t cooldown_hold_ms;
    uint8_t  max_consecutive_trips;
    uint32_t trip_window_ms;
    float    detach_min_rise_c;
    uint32_t detach_alert_ms;
    float    warn_clear_hysteresis_c;
};

/* Everything the protection loop carries between cycles. Owned by the protection task
 * on core 0; the network task only ever reads a copy. */
struct SawContext {
    SawState state;
    SawCause cause;                 /* cause of the trip currently in effect     */

    bool     hold_closed;           /* THE output. true = coil circuit permitted */

    /*
     * Latched by a failed boot self-test and cleared only by a power cycle, which is what
     * E05 publishes ("clears: power", "the supervisor refused to arm"). Without the latch a
     * board whose sensor came back to life mid-session would work its way to ARMED and
     * close the contact while the LED was still showing SOS — the contact and the
     * indicator saying opposite things, which is the one combination an operator must
     * never be shown.
     */
    bool     boot_failed;

    uint32_t cooldown_start_ms;
    SawTripCounter trips;

    float    last_valid_c;
    uint32_t last_valid_ms;
    bool     have_reference;

    /* Probe self-verification — ARCHITECTURE.md § Probe self-verification. */
    float    session_baseline_c;
    bool     have_baseline;
    bool     probe_verified;
    uint32_t armed_ms;
    bool     detach_alert_raised;

    uint32_t alerts;                /* bitmask of SawAlert                       */
    bool     warn_latched;          /* W01 raised for the current excursion      */

    uint32_t last_step_ms;
    bool     have_step_time;

    uint32_t trips_lifetime;        /* survives reboots, for the dashboard       */

    SawContext();
};

/* Sink for anything worth logging. Kept as a function pointer so the core stays free
 * of std::function and of any allocation. */
typedef void (*SawEventSink)(void *ctx, SawEvent ev, float value, int32_t detail);

/* One protection cycle. Call at SAMPLE_HZ with a fresh reading and its verdict. */
void saw_step(SawContext &c, const SawLimits &lim,
              SawVerdict verdict, float celsius, uint32_t now_ms,
              bool ack_pressed, SawEventSink sink, void *sink_ctx);

/* Boot decision — ARCHITECTURE.md § Boot. `persisted` is the state read from NVS.
 * `self_test_passed` is the result of the N-of-M sensor self-test, `boot_c` its last
 * valid reading (ignored when the self-test failed). */
void saw_boot(SawContext &c, const SawLimits &lim,
              SawState persisted, bool self_test_passed, float boot_c,
              uint32_t now_ms, SawEventSink sink, void *sink_ctx);

/* Raise / clear advisory alerts. Never touches state or hold_closed. */
void saw_raise_alert(SawContext &c, uint32_t alert);
void saw_clear_alerts(SawContext &c);

/* Which LED pattern the current context should show. */
SawLedPattern saw_led_for(const SawContext &c);
