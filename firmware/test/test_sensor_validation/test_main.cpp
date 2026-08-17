/*
 * SR-5: "Open sensor, shorted sensor, out-of-range reading, stale reading, CRC /
 * communication failure — all trip. Never fall back to last known good or assume
 * ambient."
 *
 * Every one of those gets a case here, plus the E02 / E03 split that decides which
 * hardware the operator is sent to look at.
 */
#include <unity.h>

#include <math.h>

#include "saw_sensor.h"

static const SawSensorLimits LIM = {
    -20.0f,     /* min_c      */
    400.0f,     /* max_c      */
    50.0f,      /* max_jump_c */
    3000UL,     /* timeout_ms */
};

void setUp(void) {}
void tearDown(void) {}

static SawReading good(float c)
{
    SawReading r;
    r.answered = true;
    r.celsius = c;
    return r;
}

/* Validate with a reference established 250 ms ago at `last_c`. */
static SawVerdict check(const SawReading &r, float last_c = 50.0f)
{
    return saw_validate(r, LIM, true, last_c, 1000250, 1000000);
}

static void test_a_normal_reading_is_valid(void)
{
    TEST_ASSERT_EQUAL(SAW_VERDICT_VALID, check(good(55.0f)));
}

static void test_open_circuit_is_a_fault(void)
{
    SawReading r = good(55.0f);
    r.fault_open = true;
    TEST_ASSERT_EQUAL(SAW_VERDICT_FAULT, check(r));
}

static void test_short_to_ground_is_a_fault(void)
{
    SawReading r = good(55.0f);
    r.fault_short_gnd = true;
    TEST_ASSERT_EQUAL(SAW_VERDICT_FAULT, check(r));
}

static void test_short_to_vcc_is_a_fault(void)
{
    SawReading r = good(55.0f);
    r.fault_short_vcc = true;
    TEST_ASSERT_EQUAL(SAW_VERDICT_FAULT, check(r));
}

static void test_raw_out_of_band_is_a_fault(void)
{
    SawReading r = good(55.0f);
    r.raw_out_of_band = true;
    TEST_ASSERT_EQUAL(SAW_VERDICT_FAULT, check(r));
}

static void test_out_of_range_temperatures_are_faults(void)
{
    TEST_ASSERT_EQUAL(SAW_VERDICT_FAULT, check(good(-21.0f), -20.0f));
    TEST_ASSERT_EQUAL(SAW_VERDICT_FAULT, check(good(401.0f), 390.0f));
    /* The bounds themselves are inside the believable band. */
    TEST_ASSERT_EQUAL(SAW_VERDICT_VALID, check(good(-20.0f), -20.0f));
    TEST_ASSERT_EQUAL(SAW_VERDICT_VALID, check(good(400.0f), 390.0f));
}

static void test_nan_is_a_fault_rather_than_a_number(void)
{
    /* Every comparison against NaN is false, so a naive range check would pass it
     * straight through as a temperature. That would be a supervisor happily reporting
     * "not a number" degrees while a motor cooks. */
    TEST_ASSERT_EQUAL(SAW_VERDICT_FAULT, check(good(NAN)));
}

static void test_no_answer_inside_the_window_is_a_fault(void)
{
    SawReading r;
    r.answered = false;
    TEST_ASSERT_EQUAL(SAW_VERDICT_FAULT, check(r));
}

static void test_no_answer_past_the_window_is_a_timeout(void)
{
    SawReading r;
    r.answered = false;
    /* Last good reading 3.5 s ago: E03, and the operator is sent to the SPI bus and the
     * amplifier rather than to the probe. */
    TEST_ASSERT_EQUAL(SAW_VERDICT_TIMEOUT,
                      saw_validate(r, LIM, true, 50.0f, 1003500, 1000000));
}

static void test_an_answered_but_unbelievable_reading_stays_a_fault_forever(void)
{
    SawReading r = good(55.0f);
    r.fault_open = true;
    /* An amplifier that keeps reporting an open thermocouple is answering. That is E02 no
     * matter how long it goes on: the fault is in the probe, not in the bus, and
     * escalating it to E03 would send the operator to the wrong hardware. */
    TEST_ASSERT_EQUAL(SAW_VERDICT_FAULT,
                      saw_validate(r, LIM, true, 50.0f, 1060000, 1000000));
}

static void test_implausible_jump_is_a_fault(void)
{
    TEST_ASSERT_EQUAL(SAW_VERDICT_FAULT, check(good(120.0f), 50.0f));
    TEST_ASSERT_EQUAL(SAW_VERDICT_FAULT, check(good(-10.0f), 50.0f));
    /* Exactly at the limit is still believable; beyond it is not. */
    TEST_ASSERT_EQUAL(SAW_VERDICT_VALID, check(good(100.0f), 50.0f));
    TEST_ASSERT_EQUAL(SAW_VERDICT_FAULT, check(good(100.1f), 50.0f));
}

static void test_a_stalled_loop_reports_a_timeout_even_with_a_good_reading(void)
{
    /* SENSOR_TIMEOUT exists because running blind is not allowed. A loop that lost four
     * seconds was blind for the same interval a dead bus would have been, so the good
     * reading that arrives afterwards does not erase it. */
    TEST_ASSERT_EQUAL(SAW_VERDICT_TIMEOUT,
                      saw_validate(good(52.0f), LIM, true, 50.0f, 1004000, 1000000));
}

static void test_first_reading_of_a_session_has_no_jump_reference(void)
{
    /* have_reference false: no last value to compare against, and no staleness window to
     * have exceeded. A believable reading is valid. */
    TEST_ASSERT_EQUAL(SAW_VERDICT_VALID,
                      saw_validate(good(300.0f), LIM, false, 0.0f, 5000000, 0));
    /* But an unbelievable one is still a fault, not a timeout. */
    SawReading r;
    r.answered = false;
    TEST_ASSERT_EQUAL(SAW_VERDICT_FAULT,
                      saw_validate(r, LIM, false, 0.0f, 5000000, 0));
}

static void test_believable_ignores_history(void)
{
    TEST_ASSERT_TRUE(saw_reading_believable(good(55.0f), LIM));
    /* The boot self-test counts good reads with this, before any reference exists, so a
     * 300 °C jump from nothing must not disqualify a read. */
    TEST_ASSERT_TRUE(saw_reading_believable(good(399.0f), LIM));
    TEST_ASSERT_FALSE(saw_reading_believable(good(401.0f), LIM));
}

static void test_millis_rollover_does_not_fake_a_timeout(void)
{
    SawReading r;
    r.answered = false;
    uint32_t last = 0xFFFFF000u;
    uint32_t now = last + 500u;    /* wraps through zero */
    TEST_ASSERT_EQUAL(SAW_VERDICT_FAULT, saw_validate(r, LIM, true, 50.0f, now, last));
    TEST_ASSERT_EQUAL(SAW_VERDICT_TIMEOUT,
                      saw_validate(r, LIM, true, 50.0f, last + 4000u, last));
}

int main(int, char **)
{
    UNITY_BEGIN();
    RUN_TEST(test_a_normal_reading_is_valid);
    RUN_TEST(test_open_circuit_is_a_fault);
    RUN_TEST(test_short_to_ground_is_a_fault);
    RUN_TEST(test_short_to_vcc_is_a_fault);
    RUN_TEST(test_raw_out_of_band_is_a_fault);
    RUN_TEST(test_out_of_range_temperatures_are_faults);
    RUN_TEST(test_nan_is_a_fault_rather_than_a_number);
    RUN_TEST(test_no_answer_inside_the_window_is_a_fault);
    RUN_TEST(test_no_answer_past_the_window_is_a_timeout);
    RUN_TEST(test_an_answered_but_unbelievable_reading_stays_a_fault_forever);
    RUN_TEST(test_implausible_jump_is_a_fault);
    RUN_TEST(test_a_stalled_loop_reports_a_timeout_even_with_a_good_reading);
    RUN_TEST(test_first_reading_of_a_session_has_no_jump_reference);
    RUN_TEST(test_believable_ignores_history);
    RUN_TEST(test_millis_rollover_does_not_fake_a_timeout);
    return UNITY_END();
}
