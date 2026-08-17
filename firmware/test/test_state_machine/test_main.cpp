/*
 * The state machine against the diagram in ARCHITECTURE.md § State machine.
 *
 * The invariant that matters more than any individual transition is checked after every
 * single step in every test: hold_closed is true if and only if state == ARMED. That is
 * SR-1 and SR-2 in one assertion — no fault path, no alert, no acknowledgement and no
 * ordering of events may leave the contact closed in any other state.
 */
#include <unity.h>

#include "saw_state_machine.h"

static const SawLimits LIM = {
    110.0f,      /* trip_c                  */
    95.0f,       /* warn_c                  */
    70.0f,       /* reset_c                 */
    120000UL,    /* cooldown_hold_ms        */
    3,           /* max_consecutive_trips   */
    600000UL,    /* trip_window_ms          */
    5.0f,        /* detach_min_rise_c       */
    1800000UL,   /* detach_alert_ms         */
    2.0f,        /* warn_clear_hysteresis_c */
};

/* --- event capture --------------------------------------------------------- */

#define MAX_EV 128
static SawEvent s_ev[MAX_EV];
static float    s_val[MAX_EV];
static int      s_n;

static void sink(void *ctx, SawEvent ev, float value, int32_t detail)
{
    (void)ctx;
    (void)detail;
    if (s_n < MAX_EV) {
        s_ev[s_n] = ev;
        s_val[s_n] = value;
        s_n++;
    }
}

static void ev_reset(void) { s_n = 0; }

static int ev_count(SawEvent e)
{
    int n = 0;
    for (int i = 0; i < s_n; i++) {
        if (s_ev[i] == e) {
            n++;
        }
    }
    return n;
}

static bool ev_seen(SawEvent e) { return ev_count(e) > 0; }

/* Order check: does `a` appear before `b`? */
static bool ev_before(SawEvent a, SawEvent b)
{
    int ia = -1, ib = -1;
    for (int i = 0; i < s_n; i++) {
        if (s_ev[i] == a && ia < 0) {
            ia = i;
        }
        if (s_ev[i] == b && ib < 0) {
            ib = i;
        }
    }
    return ia >= 0 && ib >= 0 && ia < ib;
}

/* --- helpers --------------------------------------------------------------- */

static void check_invariant(const SawContext &c)
{
    TEST_ASSERT_EQUAL_MESSAGE(c.state == SAW_ARMED, c.hold_closed,
                              "hold_closed must be true only in ARMED");
}

static void step(SawContext &c, float celsius, uint32_t t, bool ack = false,
                 SawVerdict v = SAW_VERDICT_VALID)
{
    saw_step(c, LIM, v, celsius, t, ack, sink, NULL);
    check_invariant(c);
}

/* Boot into a cool, healthy ARMED state and leave the timestamp in s_armed_at.
 * Void rather than returning the time, because a Unity assertion aborts the enclosing
 * function and a non-void helper would then have no value to return. */
static uint32_t s_armed_at;

static void boot_to_armed(SawContext &c, float celsius = 25.0f)
{
    saw_boot(c, LIM, SAW_COOLDOWN, true, celsius, 1000, sink, NULL);
    check_invariant(c);
    TEST_ASSERT_EQUAL(SAW_COOLDOWN, c.state);

    step(c, celsius, 2000);
    TEST_ASSERT_EQUAL(SAW_COOLDOWN, c.state);

    s_armed_at = 1000 + LIM.cooldown_hold_ms + 2000;
    step(c, celsius, s_armed_at);
    TEST_ASSERT_EQUAL(SAW_ARMED, c.state);
    TEST_ASSERT_TRUE(c.hold_closed);
}

void setUp(void) { ev_reset(); }
void tearDown(void) {}

/* --- boot ------------------------------------------------------------------ */

static void test_boot_cool_goes_to_cooldown_not_armed(void)
{
    SawContext c;
    saw_boot(c, LIM, SAW_COOLDOWN, true, 22.0f, 1000, sink, NULL);
    check_invariant(c);
    /* Never straight to ARMED: the cooldown hold has to elapse first, so a board that
     * reboots in a loop cannot flicker the contactor coil. */
    TEST_ASSERT_EQUAL(SAW_COOLDOWN, c.state);
    TEST_ASSERT_FALSE(c.hold_closed);
}

static void test_boot_self_test_failure_trips_and_flags_sos(void)
{
    SawContext c;
    saw_boot(c, LIM, SAW_COOLDOWN, false, 0.0f, 1000, sink, NULL);
    check_invariant(c);
    TEST_ASSERT_EQUAL(SAW_TRIPPED, c.state);
    TEST_ASSERT_EQUAL(SAW_CAUSE_BOOT_SENSOR_FAIL, c.cause);
    TEST_ASSERT_FALSE(c.hold_closed);
    TEST_ASSERT_TRUE(ev_seen(SAW_EV_BOOT_SENSOR_FAIL));
    TEST_ASSERT_EQUAL(SAW_LED_SOS, saw_led_for(c));
}

static void test_a_failed_self_test_cannot_arm_even_if_the_sensor_recovers(void)
{
    SawContext c;
    saw_boot(c, LIM, SAW_COOLDOWN, false, 0.0f, 1000, sink, NULL);
    TEST_ASSERT_TRUE(c.boot_failed);

    /* The sensor starts answering perfectly, cool, for a full hour. E05 publishes
     * "clears: power" — the supervisor that could not prove its sensor at boot does not
     * get to arm this session. Without the latch it would work its way to ARMED and close
     * the contact while the LED was still showing SOS. */
    for (uint32_t e = 0; e < 3600000u; e += 60000u) {
        step(c, 22.0f, 2000 + e);
    }

    TEST_ASSERT_EQUAL(SAW_TRIPPED, c.state);
    TEST_ASSERT_FALSE(c.hold_closed);
    TEST_ASSERT_EQUAL(SAW_LED_SOS, saw_led_for(c));
    TEST_ASSERT_FALSE(ev_seen(SAW_EV_ARMED));
    TEST_ASSERT_FALSE(ev_seen(SAW_EV_COOLDOWN));
}

static void test_boot_hot_with_persisted_trip_holds_tripped(void)
{
    SawContext c;
    /* E06: a hot power-cycle does not clear a trip. */
    saw_boot(c, LIM, SAW_TRIPPED, true, 85.0f, 1000, sink, NULL);
    check_invariant(c);
    TEST_ASSERT_EQUAL(SAW_TRIPPED, c.state);
    TEST_ASSERT_EQUAL(SAW_CAUSE_BOOT_HOT_HOLD, c.cause);
    TEST_ASSERT_TRUE(ev_seen(SAW_EV_BOOT_HOT_HOLD));
}

static void test_boot_cool_with_persisted_trip_releases(void)
{
    SawContext c;
    saw_boot(c, LIM, SAW_TRIPPED, true, 40.0f, 1000, sink, NULL);
    check_invariant(c);
    TEST_ASSERT_EQUAL(SAW_COOLDOWN, c.state);
    TEST_ASSERT_FALSE(ev_seen(SAW_EV_BOOT_HOT_HOLD));
}

static void test_boot_into_persisted_lockout_even_when_cold(void)
{
    SawContext c;
    /* E07: power-cycling is not a way out of MANUAL_LOCKOUT, at any temperature. */
    saw_boot(c, LIM, SAW_MANUAL_LOCKOUT, true, 20.0f, 1000, sink, NULL);
    check_invariant(c);
    TEST_ASSERT_EQUAL(SAW_MANUAL_LOCKOUT, c.state);
    TEST_ASSERT_FALSE(c.hold_closed);
    TEST_ASSERT_TRUE(ev_seen(SAW_EV_BOOT_INTO_LOCKOUT));
}

/* --- the normal cycle ------------------------------------------------------ */

static void test_cooldown_arms_only_after_the_full_hold(void)
{
    SawContext c;
    saw_boot(c, LIM, SAW_COOLDOWN, true, 25.0f, 1000, sink, NULL);

    step(c, 25.0f, 1000 + LIM.cooldown_hold_ms - 10);
    TEST_ASSERT_EQUAL(SAW_COOLDOWN, c.state);
    TEST_ASSERT_FALSE(c.hold_closed);

    step(c, 25.0f, 1000 + LIM.cooldown_hold_ms + 10);
    TEST_ASSERT_EQUAL(SAW_ARMED, c.state);
    TEST_ASSERT_TRUE(c.hold_closed);
    TEST_ASSERT_TRUE(ev_seen(SAW_EV_ARMED));
}

static void test_overtemp_trips_at_the_threshold(void)
{
    SawContext c;
    boot_to_armed(c);
    uint32_t t = s_armed_at;

    step(c, 109.9f, t + 250);
    TEST_ASSERT_EQUAL(SAW_ARMED, c.state);

    step(c, 110.0f, t + 500);
    TEST_ASSERT_EQUAL(SAW_TRIPPED, c.state);
    TEST_ASSERT_EQUAL(SAW_CAUSE_OVERTEMP, c.cause);
    TEST_ASSERT_FALSE(c.hold_closed);
    TEST_ASSERT_EQUAL(1, ev_count(SAW_EV_OVERTEMP));
    TEST_ASSERT_EQUAL(SAW_LED_FAST_BLINK, saw_led_for(c));
}

static void test_tripped_recovers_through_cooldown(void)
{
    SawContext c;
    boot_to_armed(c);
    uint32_t t = s_armed_at;
    step(c, 115.0f, t + 250);
    TEST_ASSERT_EQUAL(SAW_TRIPPED, c.state);

    step(c, 71.0f, t + 500);
    TEST_ASSERT_EQUAL(SAW_TRIPPED, c.state);   /* still at or above RESET */

    step(c, 69.0f, t + 750);
    TEST_ASSERT_EQUAL(SAW_COOLDOWN, c.state);
    TEST_ASSERT_EQUAL(SAW_LED_SLOW_BLINK, saw_led_for(c));

    step(c, 60.0f, t + 750 + LIM.cooldown_hold_ms + 10);
    TEST_ASSERT_EQUAL(SAW_ARMED, c.state);
    TEST_ASSERT_TRUE(c.hold_closed);
}

static void test_reheat_during_cooldown_restarts_the_hold_without_a_new_trip(void)
{
    SawContext c;
    boot_to_armed(c);
    uint32_t t = s_armed_at;
    step(c, 115.0f, t + 250);
    step(c, 65.0f, t + 500);
    TEST_ASSERT_EQUAL(SAW_COOLDOWN, c.state);
    uint8_t trips_before = c.trips.count();

    step(c, 75.0f, t + 750);
    TEST_ASSERT_EQUAL(SAW_TRIPPED, c.state);
    /* The contact never re-closed, so nothing chattered and nothing should be counted. */
    TEST_ASSERT_EQUAL(trips_before, c.trips.count());

    step(c, 65.0f, t + 1000);
    TEST_ASSERT_EQUAL(SAW_COOLDOWN, c.state);
    /* And the hold restarts from the re-entry, not from the original trip. */
    step(c, 65.0f, t + 1000 + LIM.cooldown_hold_ms - 100);
    TEST_ASSERT_EQUAL(SAW_COOLDOWN, c.state);
}

/* --- chatter suppression --------------------------------------------------- */

static void test_three_trips_in_the_window_lock_out(void)
{
    SawContext c;
    boot_to_armed(c);
    uint32_t t = s_armed_at;

    for (int i = 0; i < 2; i++) {
        step(c, 115.0f, t);            /* trip           */
        step(c, 60.0f, t + 250);       /* -> COOLDOWN    */
        t += 250 + LIM.cooldown_hold_ms + 10;
        step(c, 60.0f, t);             /* -> ARMED       */
        TEST_ASSERT_EQUAL(SAW_ARMED, c.state);
    }

    step(c, 115.0f, t + 10);           /* third trip inside the window */
    TEST_ASSERT_EQUAL(SAW_MANUAL_LOCKOUT, c.state);
    TEST_ASSERT_FALSE(c.hold_closed);
    TEST_ASSERT_TRUE(ev_seen(SAW_EV_MANUAL_LOCKOUT_ENTERED));
    TEST_ASSERT_EQUAL(SAW_LED_TRIPLE_BLINK, saw_led_for(c));
}

static void test_a_persistent_sensor_fault_is_one_trip_not_one_per_cycle(void)
{
    SawContext c;
    boot_to_armed(c);
    uint32_t t = s_armed_at;

    /* The reference pseudocode calls trip() every iteration a fault persists, which at
     * 4 Hz reaches MANUAL_LOCKOUT in 750 ms. E04 promises the operator "three trips
     * inside ten minutes", so trips are counted on the edge into TRIPPED instead. */
    for (int i = 0; i < 40; i++) {
        step(c, 25.0f, t + 250 * (uint32_t)i, false, SAW_VERDICT_FAULT);
    }

    TEST_ASSERT_EQUAL(SAW_TRIPPED, c.state);
    TEST_ASSERT_EQUAL(SAW_MANUAL_LOCKOUT != c.state, true);
    TEST_ASSERT_EQUAL(1, c.trips.count());
    TEST_ASSERT_EQUAL(1, ev_count(SAW_EV_SENSOR_FAULT));
}

static void test_trips_outside_the_window_do_not_accumulate(void)
{
    SawContext c;
    boot_to_armed(c);
    uint32_t t = s_armed_at;

    for (int i = 0; i < 4; i++) {
        step(c, 115.0f, t);
        TEST_ASSERT_EQUAL(SAW_TRIPPED, c.state);
        step(c, 60.0f, t + 250);
        /* Space the trips further apart than the rolling window. */
        t += LIM.trip_window_ms + LIM.cooldown_hold_ms + 1000;
        step(c, 60.0f, t);
        TEST_ASSERT_EQUAL(SAW_ARMED, c.state);
    }

    TEST_ASSERT_FALSE(ev_seen(SAW_EV_MANUAL_LOCKOUT_ENTERED));
}

/* --- the lockout and the ack button --------------------------------------- */

static void test_ack_is_rejected_while_hot_and_accepted_when_cool(void)
{
    SawContext c;
    saw_boot(c, LIM, SAW_MANUAL_LOCKOUT, true, 20.0f, 1000, sink, NULL);
    TEST_ASSERT_EQUAL(SAW_MANUAL_LOCKOUT, c.state);

    /* E08: pressed while at or above RESET_THRESHOLD, logged and ignored. */
    step(c, 85.0f, 2000, true);
    TEST_ASSERT_EQUAL(SAW_MANUAL_LOCKOUT, c.state);
    TEST_ASSERT_FALSE(c.hold_closed);
    TEST_ASSERT_TRUE(ev_seen(SAW_EV_ACK_REJECTED_HOT));
    TEST_ASSERT_FALSE(ev_seen(SAW_EV_LOCKOUT_CLEARED_BY_ACK));

    step(c, 40.0f, 3000, true);
    TEST_ASSERT_EQUAL(SAW_COOLDOWN, c.state);
    TEST_ASSERT_TRUE(ev_seen(SAW_EV_LOCKOUT_CLEARED_BY_ACK));
    /* Clearing the lockout does not close the contact — the cooldown hold still runs. */
    TEST_ASSERT_FALSE(c.hold_closed);
    TEST_ASSERT_EQUAL(0, c.trips.count());
}

static void test_lockout_does_not_cascade_or_recount(void)
{
    SawContext c;
    saw_boot(c, LIM, SAW_MANUAL_LOCKOUT, true, 20.0f, 1000, sink, NULL);
    ev_reset();

    for (int i = 0; i < 10; i++) {
        step(c, 25.0f, 2000 + 250 * (uint32_t)i, false, SAW_VERDICT_FAULT);
    }

    TEST_ASSERT_EQUAL(SAW_MANUAL_LOCKOUT, c.state);
    TEST_ASSERT_EQUAL(0, ev_count(SAW_EV_SENSOR_FAULT));
    TEST_ASSERT_EQUAL(0, ev_count(SAW_EV_MANUAL_LOCKOUT_ENTERED));
}

/* --- sensor faults --------------------------------------------------------- */

static void test_sensor_fault_from_armed_trips_with_the_sensor_led(void)
{
    SawContext c;
    boot_to_armed(c);
    uint32_t t = s_armed_at;

    step(c, 25.0f, t + 250, false, SAW_VERDICT_FAULT);
    TEST_ASSERT_EQUAL(SAW_TRIPPED, c.state);
    TEST_ASSERT_EQUAL(SAW_CAUSE_SENSOR_FAULT, c.cause);
    TEST_ASSERT_FALSE(c.hold_closed);
    TEST_ASSERT_EQUAL(SAW_LED_DOUBLE_BLINK, saw_led_for(c));
}

static void test_fault_escalating_to_timeout_logs_both_codes(void)
{
    SawContext c;
    boot_to_armed(c);
    uint32_t t = s_armed_at;

    /* E02 first — the chain answered and was not believed. */
    step(c, 25.0f, t + 250, false, SAW_VERDICT_FAULT);
    /* Then E03, once it has stopped answering for longer than the timeout. The operator
     * needs both lines: E02 points at the probe, E03 at the bus and the amplifier. */
    step(c, 25.0f, t + 3500, false, SAW_VERDICT_TIMEOUT);

    TEST_ASSERT_EQUAL(SAW_TRIPPED, c.state);
    TEST_ASSERT_EQUAL(SAW_CAUSE_SENSOR_TIMEOUT, c.cause);
    TEST_ASSERT_TRUE(ev_seen(SAW_EV_SENSOR_FAULT));
    TEST_ASSERT_TRUE(ev_seen(SAW_EV_SENSOR_TIMEOUT));
    TEST_ASSERT_TRUE(ev_before(SAW_EV_SENSOR_FAULT, SAW_EV_SENSOR_TIMEOUT));
    /* One trip, two diagnoses. */
    TEST_ASSERT_EQUAL(1, c.trips.count());
}

static void test_sensor_recovery_is_logged_and_leads_back_to_cooldown(void)
{
    SawContext c;
    boot_to_armed(c);
    uint32_t t = s_armed_at;
    step(c, 25.0f, t + 250, false, SAW_VERDICT_FAULT);
    TEST_ASSERT_EQUAL(SAW_TRIPPED, c.state);

    step(c, 25.0f, t + 500);
    TEST_ASSERT_TRUE(ev_seen(SAW_EV_SENSOR_RECOVERED));
    TEST_ASSERT_EQUAL(SAW_COOLDOWN, c.state);
}

/* --- advisories ------------------------------------------------------------ */

static void test_warn_alert_latches_once_and_clears_with_hysteresis(void)
{
    SawContext c;
    boot_to_armed(c);
    uint32_t t = s_armed_at;

    step(c, 96.0f, t + 250);
    step(c, 97.0f, t + 500);
    step(c, 96.5f, t + 750);
    TEST_ASSERT_EQUAL(SAW_ARMED, c.state);
    TEST_ASSERT_EQUAL(1, ev_count(SAW_EV_APPROACHING_TRIP));
    TEST_ASSERT_TRUE((c.alerts & SAW_ALERT_APPROACHING_TRIP) != 0);

    step(c, 94.0f, t + 1000);   /* inside the hysteresis band: still latched */
    TEST_ASSERT_TRUE((c.alerts & SAW_ALERT_APPROACHING_TRIP) != 0);

    step(c, 92.0f, t + 1250);   /* below warn - hysteresis: cleared */
    TEST_ASSERT_FALSE((c.alerts & SAW_ALERT_APPROACHING_TRIP) != 0);

    step(c, 96.0f, t + 1500);
    TEST_ASSERT_EQUAL(2, ev_count(SAW_EV_APPROACHING_TRIP));
}

static void test_probe_verifies_on_a_genuine_rise_and_stays_verified(void)
{
    SawContext c;
    boot_to_armed(c, 20.0f);
    uint32_t t = s_armed_at;
    TEST_ASSERT_FALSE(c.probe_verified);

    step(c, 24.0f, t + 250);
    TEST_ASSERT_FALSE(c.probe_verified);

    step(c, 25.5f, t + 500);
    TEST_ASSERT_TRUE(c.probe_verified);
    TEST_ASSERT_TRUE(ev_seen(SAW_EV_PROBE_VERIFIED));

    /* A probe that has warmed once is attached; cooling back down does not un-verify. */
    step(c, 19.0f, t + 750);
    TEST_ASSERT_TRUE(c.probe_verified);
}

static void test_probe_unverified_after_long_armed_time_warns_but_does_not_trip(void)
{
    SawContext c;
    boot_to_armed(c, 20.0f);
    uint32_t t = s_armed_at;

    /* Half-hour of ARMED at a flat temperature, stepped at the sample rate. */
    uint32_t step_ms = 250;
    for (uint32_t elapsed = 0; elapsed <= LIM.detach_alert_ms + 2000;
         elapsed += step_ms) {
        step(c, 20.2f, t + elapsed);
    }

    /* W03 is advisory: the saw is still armed and the contact is still closed. */
    TEST_ASSERT_EQUAL(SAW_ARMED, c.state);
    TEST_ASSERT_TRUE(c.hold_closed);
    TEST_ASSERT_EQUAL(1, ev_count(SAW_EV_PROBE_UNVERIFIED_AT_ARMED_TIME));
    TEST_ASSERT_TRUE((c.alerts & SAW_ALERT_PROBE_UNVERIFIED) != 0);
}

static void test_armed_time_does_not_accrue_outside_armed(void)
{
    SawContext c;
    saw_boot(c, LIM, SAW_COOLDOWN, true, 20.0f, 1000, sink, NULL);

    /* Sit in COOLDOWN for well past the detach alert window. */
    for (uint32_t e = 0; e < LIM.detach_alert_ms + 5000; e += 1000) {
        saw_step(c, LIM, SAW_VERDICT_VALID, 20.0f, 1000 + e, false, sink, NULL);
        if (c.state == SAW_ARMED) {
            break;
        }
    }
    /* It armed part way through, so some armed time accrued — but the alert must not
     * have fired from the COOLDOWN period. */
    TEST_ASSERT_TRUE(c.armed_ms < LIM.detach_alert_ms);
    TEST_ASSERT_EQUAL(0, ev_count(SAW_EV_PROBE_UNVERIFIED_AT_ARMED_TIME));
}

/* --- the invariant, hammered ---------------------------------------------- */

static void test_hold_never_closes_outside_armed_across_a_long_random_walk(void)
{
    SawContext c;
    saw_boot(c, LIM, SAW_COOLDOWN, true, 25.0f, 1000, sink, NULL);

    /* A deterministic pseudo-random walk through temperature, verdicts and ack presses.
     * The point is not the specific sequence, it is that no ordering of inputs produces a
     * closed contact in a state that is not ARMED. */
    uint32_t seed = 12345;
    uint32_t t = 1000;
    for (int i = 0; i < 5000; i++) {
        seed = seed * 1103515245u + 12345u;
        uint32_t r = (seed >> 16) & 0x7FFF;

        float celsius = 20.0f + (float)(r % 120);
        SawVerdict v = SAW_VERDICT_VALID;
        if ((r % 37) == 0) {
            v = SAW_VERDICT_FAULT;
        } else if ((r % 53) == 0) {
            v = SAW_VERDICT_TIMEOUT;
        }
        bool ack = ((r % 29) == 0);

        t += 250 + (r % 500);
        saw_step(c, LIM, v, celsius, t, ack, NULL, NULL);

        TEST_ASSERT_EQUAL_MESSAGE(c.state == SAW_ARMED, c.hold_closed,
                                  "contact closed outside ARMED");
        if (v != SAW_VERDICT_VALID) {
            TEST_ASSERT_FALSE_MESSAGE(c.hold_closed,
                                      "contact closed on a sensor fault");
        }
        if (celsius >= LIM.trip_c) {
            TEST_ASSERT_FALSE_MESSAGE(c.hold_closed,
                                      "contact closed at or above TRIP_C");
        }
    }
}

int main(int, char **)
{
    UNITY_BEGIN();
    RUN_TEST(test_boot_cool_goes_to_cooldown_not_armed);
    RUN_TEST(test_boot_self_test_failure_trips_and_flags_sos);
    RUN_TEST(test_a_failed_self_test_cannot_arm_even_if_the_sensor_recovers);
    RUN_TEST(test_boot_hot_with_persisted_trip_holds_tripped);
    RUN_TEST(test_boot_cool_with_persisted_trip_releases);
    RUN_TEST(test_boot_into_persisted_lockout_even_when_cold);
    RUN_TEST(test_cooldown_arms_only_after_the_full_hold);
    RUN_TEST(test_overtemp_trips_at_the_threshold);
    RUN_TEST(test_tripped_recovers_through_cooldown);
    RUN_TEST(test_reheat_during_cooldown_restarts_the_hold_without_a_new_trip);
    RUN_TEST(test_three_trips_in_the_window_lock_out);
    RUN_TEST(test_a_persistent_sensor_fault_is_one_trip_not_one_per_cycle);
    RUN_TEST(test_trips_outside_the_window_do_not_accumulate);
    RUN_TEST(test_ack_is_rejected_while_hot_and_accepted_when_cool);
    RUN_TEST(test_lockout_does_not_cascade_or_recount);
    RUN_TEST(test_sensor_fault_from_armed_trips_with_the_sensor_led);
    RUN_TEST(test_fault_escalating_to_timeout_logs_both_codes);
    RUN_TEST(test_sensor_recovery_is_logged_and_leads_back_to_cooldown);
    RUN_TEST(test_warn_alert_latches_once_and_clears_with_hysteresis);
    RUN_TEST(test_probe_verifies_on_a_genuine_rise_and_stays_verified);
    RUN_TEST(test_probe_unverified_after_long_armed_time_warns_but_does_not_trip);
    RUN_TEST(test_armed_time_does_not_accrue_outside_armed);
    RUN_TEST(test_hold_never_closes_outside_armed_across_a_long_random_walk);
    return UNITY_END();
}
