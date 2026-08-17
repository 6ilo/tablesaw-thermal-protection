/*
 * Rolling-window trip counter — ARCHITECTURE.md § State machine, chatter suppression.
 */
#include <unity.h>

#include "saw_trip_counter.h"

#define MAX_TRIPS   3
#define WINDOW_MS   600000UL   /* 10 minutes */

void setUp(void) {}
void tearDown(void) {}

static void test_third_trip_inside_the_window_escalates(void)
{
    SawTripCounter t;
    TEST_ASSERT_FALSE(t.record(1000, MAX_TRIPS, WINDOW_MS));
    TEST_ASSERT_FALSE(t.record(60000, MAX_TRIPS, WINDOW_MS));
    TEST_ASSERT_TRUE(t.record(120000, MAX_TRIPS, WINDOW_MS));
    TEST_ASSERT_EQUAL(3, t.count());
}

static void test_window_is_anchored_to_the_first_trip_not_to_boot(void)
{
    SawTripCounter t;
    /* The reference pseudocode leaves first_trip_ms at 0 until the window lapses, which
     * measures the first burst from power-up. A trip at 9 minutes of uptime followed by
     * two more at 15 and 16 minutes is three trips in eight minutes and must lock out;
     * anchored at boot it would look like two separate windows. */
    TEST_ASSERT_FALSE(t.record(540000, MAX_TRIPS, WINDOW_MS));   /*  9:00 */
    TEST_ASSERT_FALSE(t.record(900000, MAX_TRIPS, WINDOW_MS));   /* 15:00 */
    TEST_ASSERT_TRUE(t.record(960000, MAX_TRIPS, WINDOW_MS));    /* 16:00 */
}

static void test_a_lapsed_window_restarts_the_count(void)
{
    SawTripCounter t;
    t.record(1000, MAX_TRIPS, WINDOW_MS);
    t.record(2000, MAX_TRIPS, WINDOW_MS);
    TEST_ASSERT_EQUAL(2, t.count());

    /* Just past the window: this is the first trip of a new burst. */
    TEST_ASSERT_FALSE(t.record(1000 + WINDOW_MS + 1, MAX_TRIPS, WINDOW_MS));
    TEST_ASSERT_EQUAL(1, t.count());
}

static void test_trips_exactly_on_the_window_boundary_still_count(void)
{
    SawTripCounter t;
    t.record(0, MAX_TRIPS, WINDOW_MS);
    t.record(WINDOW_MS / 2, MAX_TRIPS, WINDOW_MS);
    /* Exactly at the boundary is inside it — the comparison is strictly greater-than. */
    TEST_ASSERT_TRUE(t.record(WINDOW_MS, MAX_TRIPS, WINDOW_MS));
}

static void test_reset_clears_the_window(void)
{
    SawTripCounter t;
    t.record(1000, MAX_TRIPS, WINDOW_MS);
    t.record(2000, MAX_TRIPS, WINDOW_MS);
    t.reset();
    TEST_ASSERT_EQUAL(0, t.count());
    TEST_ASSERT_FALSE(t.window_open());
    TEST_ASSERT_FALSE(t.record(3000, MAX_TRIPS, WINDOW_MS));
    TEST_ASSERT_EQUAL(1, t.count());
}

static void test_millis_rollover_does_not_lock_out_spuriously(void)
{
    SawTripCounter t;
    /* millis() wraps every 49.7 days. A supervisor left powered in a shop will see it, and
     * unsigned subtraction has to carry the arithmetic across the wrap. */
    uint32_t before = 0xFFFFFF00u;
    TEST_ASSERT_FALSE(t.record(before, MAX_TRIPS, WINDOW_MS));

    uint32_t after = before + 60000u;   /* wraps through zero */
    TEST_ASSERT_FALSE(t.record(after, MAX_TRIPS, WINDOW_MS));
    TEST_ASSERT_EQUAL(2, t.count());

    TEST_ASSERT_TRUE(t.record(after + 60000u, MAX_TRIPS, WINDOW_MS));
}

static void test_window_remaining_counts_down(void)
{
    SawTripCounter t;
    TEST_ASSERT_EQUAL(0, t.window_remaining_ms(0, WINDOW_MS));
    t.record(1000, MAX_TRIPS, WINDOW_MS);
    TEST_ASSERT_EQUAL(WINDOW_MS - 1000, t.window_remaining_ms(2000, WINDOW_MS));
    TEST_ASSERT_EQUAL(0, t.window_remaining_ms(1000 + WINDOW_MS, WINDOW_MS));
}

static void test_zero_max_trips_never_escalates(void)
{
    SawTripCounter t;
    for (int i = 0; i < 20; i++) {
        TEST_ASSERT_FALSE(t.record(1000u * (uint32_t)i, 0, WINDOW_MS));
    }
}

int main(int, char **)
{
    UNITY_BEGIN();
    RUN_TEST(test_third_trip_inside_the_window_escalates);
    RUN_TEST(test_window_is_anchored_to_the_first_trip_not_to_boot);
    RUN_TEST(test_a_lapsed_window_restarts_the_count);
    RUN_TEST(test_trips_exactly_on_the_window_boundary_still_count);
    RUN_TEST(test_reset_clears_the_window);
    RUN_TEST(test_millis_rollover_does_not_lock_out_spuriously);
    RUN_TEST(test_window_remaining_counts_down);
    RUN_TEST(test_zero_max_trips_never_escalates);
    return UNITY_END();
}
