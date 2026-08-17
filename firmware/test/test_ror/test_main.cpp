/*
 * Rate-of-rise tracking — the input to W02, HEATING_FASTER_THAN_BASELINE.
 *
 * This is the one advisory that is supposed to tell the operator to clean the shroud
 * *before* a trip, so a slope that is wrong by a factor of 60 (per second instead of per
 * minute) or that swings on a single noisy sample would either cry wolf constantly or
 * never fire.
 */
#include <unity.h>

#include "saw_ror.h"

void setUp(void) {}
void tearDown(void) {}

static void test_a_flat_trace_has_no_slope(void)
{
    SawRor r;
    for (uint32_t t = 0; t <= 60000; t += 1000) {
        r.push(t, 55.0f);
    }
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.0f, r.slope_c_per_min(60000, 60000));
}

static void test_a_known_ramp_reads_back_in_degrees_per_minute(void)
{
    SawRor r;
    /* 2 °C per minute, sampled once a second for a minute. */
    for (uint32_t t = 0; t <= 60000; t += 1000) {
        r.push(t, 40.0f + 2.0f * (float)t / 60000.0f);
    }
    TEST_ASSERT_FLOAT_WITHIN(0.05f, 2.0f, r.slope_c_per_min(60000, 60000));
}

static void test_a_falling_trace_reads_negative(void)
{
    SawRor r;
    for (uint32_t t = 0; t <= 60000; t += 1000) {
        r.push(t, 80.0f - 5.0f * (float)t / 60000.0f);
    }
    TEST_ASSERT_FLOAT_WITHIN(0.05f, -5.0f, r.slope_c_per_min(60000, 60000));
}

static void test_one_noisy_sample_does_not_dominate(void)
{
    SawRor clean, noisy;
    for (uint32_t t = 0; t <= 60000; t += 1000) {
        float c = 50.0f + 1.0f * (float)t / 60000.0f;
        clean.push(t, c);
        /* Same ramp, but the newest sample is 3 °C high — exactly the case a
         * (last − first) / dt calculation would report as a 4 °C/min excursion. */
        noisy.push(t, t == 60000 ? c + 3.0f : c);
    }
    float a = clean.slope_c_per_min(60000, 60000);
    float b = noisy.slope_c_per_min(60000, 60000);
    TEST_ASSERT_FLOAT_WITHIN(0.05f, 1.0f, a);
    TEST_ASSERT_TRUE_MESSAGE(b < 2.5f, "a single outlier swung the fit too far");
}

static void test_the_window_excludes_older_samples(void)
{
    SawRor r;
    /* Ten minutes of flat, then one minute rising at 6 °C/min. */
    for (uint32_t t = 0; t < 600000; t += 1000) {
        r.push(t, 50.0f);
    }
    for (uint32_t t = 600000; t <= 660000; t += 1000) {
        r.push(t, 50.0f + 6.0f * (float)(t - 600000) / 60000.0f);
    }
    /* A 60 s window sees only the ramp. */
    TEST_ASSERT_FLOAT_WITHIN(0.2f, 6.0f, r.slope_c_per_min(660000, 60000));
}

static void test_rate_limiting_keeps_the_buffer_covering_the_window(void)
{
    SawRor r;
    int taken = 0;
    /* A 4 Hz protection loop pushing every cycle: only one in four is kept, which is what
     * lets a 96-deep buffer cover a 60-second window. */
    for (uint32_t t = 0; t < 10000; t += 250) {
        if (r.push(t, 50.0f)) {
            taken++;
        }
    }
    TEST_ASSERT_INT_WITHIN(2, 10, taken);
    TEST_ASSERT_INT_WITHIN(2, 10, (int)r.samples_in_window(10000, 60000));
}

static void test_too_few_samples_reports_no_slope_rather_than_a_guess(void)
{
    SawRor r;
    TEST_ASSERT_EQUAL_FLOAT(0.0f, r.slope_c_per_min(0, 60000));
    r.push(0, 50.0f);
    TEST_ASSERT_EQUAL_FLOAT(0.0f, r.slope_c_per_min(0, 60000));
    r.push(1000, 51.0f);
    TEST_ASSERT_EQUAL_FLOAT(0.0f, r.slope_c_per_min(1000, 60000));
    r.push(2000, 52.0f);
    TEST_ASSERT_TRUE(r.slope_c_per_min(2000, 60000) > 10.0f);
}

static void test_reset_empties_the_buffer(void)
{
    SawRor r;
    for (uint32_t t = 0; t <= 10000; t += 1000) {
        r.push(t, 50.0f + (float)t / 1000.0f);
    }
    r.reset();
    TEST_ASSERT_EQUAL(0, r.samples_in_window(10000, 60000));
    TEST_ASSERT_EQUAL_FLOAT(0.0f, r.slope_c_per_min(10000, 60000));
}

static void test_buffer_overrun_keeps_the_newest_samples(void)
{
    SawRor r;
    /* Push far more than the capacity and confirm the fit still describes the recent
     * ramp rather than the ancient one. */
    for (uint32_t t = 0; t < 400000; t += 1000) {
        r.push(t, 20.0f);
    }
    for (uint32_t t = 400000; t <= 460000; t += 1000) {
        r.push(t, 20.0f + 3.0f * (float)(t - 400000) / 60000.0f);
    }
    TEST_ASSERT_FLOAT_WITHIN(0.2f, 3.0f, r.slope_c_per_min(460000, 60000));
}

int main(int, char **)
{
    UNITY_BEGIN();
    RUN_TEST(test_a_flat_trace_has_no_slope);
    RUN_TEST(test_a_known_ramp_reads_back_in_degrees_per_minute);
    RUN_TEST(test_a_falling_trace_reads_negative);
    RUN_TEST(test_one_noisy_sample_does_not_dominate);
    RUN_TEST(test_the_window_excludes_older_samples);
    RUN_TEST(test_rate_limiting_keeps_the_buffer_covering_the_window);
    RUN_TEST(test_too_few_samples_reports_no_slope_rather_than_a_guess);
    RUN_TEST(test_reset_empties_the_buffer);
    RUN_TEST(test_buffer_overrun_keeps_the_newest_samples);
    return UNITY_END();
}
