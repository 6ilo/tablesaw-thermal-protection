/*
 * Two things that are easy to break silently and impossible to notice at the machine.
 *
 * 1. The LED patterns. Seven of them, and the operator card in the cabinet door tells
 *    someone to distinguish a double-blink from a triple-blink from across a workshop.
 *    They have to be actually distinguishable, and the pattern names have to match the
 *    table in ARCHITECTURE.md § Status LED patterns, because that is where the error-code
 *    registry's `led` field is validated against.
 *
 * 2. The event-name-to-error-code mapping. Every operator-visible event the firmware can
 *    emit has to resolve to a published code through the generated registry table. A typo
 *    in an event name is invisible in testing — the trip still happens, the relay still
 *    opens — and shows up months later as a log line with no code beside it and an
 *    operator with no page to read.
 */
#include <unity.h>

#include <string.h>

#include "error_codes.h"
#include "saw_led.h"
#include "saw_types.h"

void setUp(void) {}
void tearDown(void) {}

/* --- LED patterns ---------------------------------------------------------- */

static void test_solid_and_off_are_static(void)
{
    for (uint32_t t = 0; t < 5000; t += 37) {
        TEST_ASSERT_TRUE(saw_led_output(SAW_LED_SOLID, t));
        TEST_ASSERT_FALSE(saw_led_output(SAW_LED_OFF, t));
    }
}

static void test_blink_rates_match_the_table(void)
{
    /* Slow blink is 1 Hz, 50% duty. */
    TEST_ASSERT_TRUE(saw_led_output(SAW_LED_SLOW_BLINK, 0));
    TEST_ASSERT_TRUE(saw_led_output(SAW_LED_SLOW_BLINK, 499));
    TEST_ASSERT_FALSE(saw_led_output(SAW_LED_SLOW_BLINK, 500));
    TEST_ASSERT_FALSE(saw_led_output(SAW_LED_SLOW_BLINK, 999));
    TEST_ASSERT_TRUE(saw_led_output(SAW_LED_SLOW_BLINK, 1000));
    TEST_ASSERT_EQUAL(1000, saw_led_period_ms(SAW_LED_SLOW_BLINK));

    /* Fast blink is 5 Hz. */
    TEST_ASSERT_TRUE(saw_led_output(SAW_LED_FAST_BLINK, 0));
    TEST_ASSERT_FALSE(saw_led_output(SAW_LED_FAST_BLINK, 100));
    TEST_ASSERT_TRUE(saw_led_output(SAW_LED_FAST_BLINK, 200));
    TEST_ASSERT_EQUAL(200, saw_led_period_ms(SAW_LED_FAST_BLINK));
}

/* Count rising edges in one full period. */
static int pulses_per_cycle(SawLedPattern p)
{
    uint32_t period = saw_led_period_ms(p);
    int pulses = 0;
    bool prev = saw_led_output(p, period - 1);
    for (uint32_t t = 0; t < period; t++) {
        bool now = saw_led_output(p, t);
        if (now && !prev) {
            pulses++;
        }
        prev = now;
    }
    return pulses;
}

static void test_double_and_triple_blink_have_the_right_pulse_counts(void)
{
    TEST_ASSERT_EQUAL_MESSAGE(2, pulses_per_cycle(SAW_LED_DOUBLE_BLINK),
                              "double-blink must show exactly two pulses per cycle");
    TEST_ASSERT_EQUAL_MESSAGE(3, pulses_per_cycle(SAW_LED_TRIPLE_BLINK),
                              "triple-blink must show exactly three pulses per cycle");
    /* 50-50-50-850 ms, per archive/BUILD-TONIGHT.md § 5. */
    TEST_ASSERT_EQUAL(1000, saw_led_period_ms(SAW_LED_DOUBLE_BLINK));
    /* The triple's pause has to be long enough to read as a pause and not as a fourth
     * blink, so the cycle is deliberately twice the double's. */
    TEST_ASSERT_TRUE(saw_led_period_ms(SAW_LED_TRIPLE_BLINK) >= 1800);
}

static void test_sos_is_nine_pulses(void)
{
    TEST_ASSERT_EQUAL(9, pulses_per_cycle(SAW_LED_SOS));
}

static void test_patterns_are_periodic(void)
{
    SawLedPattern all[] = {SAW_LED_SLOW_BLINK, SAW_LED_FAST_BLINK,
                           SAW_LED_DOUBLE_BLINK, SAW_LED_TRIPLE_BLINK, SAW_LED_SOS};
    for (unsigned i = 0; i < sizeof(all) / sizeof(all[0]); i++) {
        uint32_t p = saw_led_period_ms(all[i]);
        TEST_ASSERT_TRUE(p > 0);
        for (uint32_t t = 0; t < p; t += 7) {
            TEST_ASSERT_EQUAL(saw_led_output(all[i], t),
                              saw_led_output(all[i], t + p));
            TEST_ASSERT_EQUAL(saw_led_output(all[i], t),
                              saw_led_output(all[i], t + p * 1000u));
        }
    }
}

static void test_pattern_names_match_the_architecture_table(void)
{
    /* These strings are what the registry's `led` front-matter field is validated
     * against by tools/codedocs.py, so they are an interface, not a label. */
    TEST_ASSERT_EQUAL_STRING("Solid ON", saw_led_name(SAW_LED_SOLID));
    TEST_ASSERT_EQUAL_STRING("Slow blink (1 Hz)", saw_led_name(SAW_LED_SLOW_BLINK));
    TEST_ASSERT_EQUAL_STRING("Fast blink (5 Hz)", saw_led_name(SAW_LED_FAST_BLINK));
    TEST_ASSERT_EQUAL_STRING("Double-blink then pause",
                             saw_led_name(SAW_LED_DOUBLE_BLINK));
    TEST_ASSERT_EQUAL_STRING("Triple-blink then long pause",
                             saw_led_name(SAW_LED_TRIPLE_BLINK));
    TEST_ASSERT_EQUAL_STRING("SOS pattern", saw_led_name(SAW_LED_SOS));
    TEST_ASSERT_EQUAL_STRING("Off", saw_led_name(SAW_LED_OFF));
}

/* --- event / registry mapping --------------------------------------------- */

static void test_every_registry_code_is_reachable_from_an_event_name(void)
{
    for (int i = 0; i < SAW_CODE_COUNT; i++) {
        const saw_code_t *found = saw_code_by_event(SAW_CODES[i].event);
        TEST_ASSERT_NOT_NULL_MESSAGE(found, SAW_CODES[i].code);
        TEST_ASSERT_EQUAL_STRING(SAW_CODES[i].code, found->code);

        /* And the firmware can actually name that event. A published code the firmware
         * cannot emit is a page nobody will ever be sent to. */
        bool emitted_by_firmware = false;
        for (int e = 0; e < SAW_EV_COUNT; e++) {
            if (strcmp(saw_event_name((SawEvent)e), SAW_CODES[i].event) == 0) {
                emitted_by_firmware = true;
                break;
            }
        }
        TEST_ASSERT_TRUE_MESSAGE(emitted_by_firmware, SAW_CODES[i].code);
    }
}

static void test_trip_causes_all_map_to_published_codes(void)
{
    SawCause causes[] = {SAW_CAUSE_OVERTEMP, SAW_CAUSE_SENSOR_FAULT,
                         SAW_CAUSE_SENSOR_TIMEOUT, SAW_CAUSE_BOOT_SENSOR_FAIL,
                         SAW_CAUSE_BOOT_HOT_HOLD};
    const char *expect[] = {"E01", "E02", "E03", "E05", "E06"};

    for (unsigned i = 0; i < sizeof(causes) / sizeof(causes[0]); i++) {
        const saw_code_t *c = saw_code_by_event(saw_cause_event(causes[i]));
        TEST_ASSERT_NOT_NULL_MESSAGE(c, expect[i]);
        TEST_ASSERT_EQUAL_STRING(expect[i], c->code);
    }
}

static void test_event_names_are_unique_and_populated(void)
{
    for (int i = 0; i < SAW_EV_COUNT; i++) {
        const char *a = saw_event_name((SawEvent)i);
        TEST_ASSERT_TRUE(a != NULL && a[0] != '\0');
        /* "?" is the out-of-range fallback, so seeing it means the name table has fewer
         * entries than the enum — the classic way an added event ends up unnamed. */
        TEST_ASSERT_TRUE_MESSAGE(strcmp(a, "?") != 0, "event name table is short");
        for (int j = i + 1; j < SAW_EV_COUNT; j++) {
            TEST_ASSERT_TRUE_MESSAGE(strcmp(a, saw_event_name((SawEvent)j)) != 0,
                                     "duplicate event name");
        }
    }
}

static void test_unknown_events_resolve_to_nothing_rather_than_to_something_wrong(void)
{
    TEST_ASSERT_NULL(saw_code_by_event("NOT_A_REAL_EVENT"));
    TEST_ASSERT_NULL(saw_code_by_event(""));
    TEST_ASSERT_NULL(saw_code_by_event(NULL));
    /* Prefix and suffix must not match — the lookup compares whole strings. */
    TEST_ASSERT_NULL(saw_code_by_event("OVERTEMP_"));
    TEST_ASSERT_NULL(saw_code_by_event("OVERTEM"));
}

static void test_the_state_names_match_the_registry_vocabulary(void)
{
    TEST_ASSERT_EQUAL_STRING("BOOT", saw_state_name(SAW_BOOT));
    TEST_ASSERT_EQUAL_STRING("ARMED", saw_state_name(SAW_ARMED));
    TEST_ASSERT_EQUAL_STRING("TRIPPED", saw_state_name(SAW_TRIPPED));
    TEST_ASSERT_EQUAL_STRING("COOLDOWN", saw_state_name(SAW_COOLDOWN));
    TEST_ASSERT_EQUAL_STRING("MANUAL_LOCKOUT", saw_state_name(SAW_MANUAL_LOCKOUT));
}

int main(int, char **)
{
    UNITY_BEGIN();
    RUN_TEST(test_solid_and_off_are_static);
    RUN_TEST(test_blink_rates_match_the_table);
    RUN_TEST(test_double_and_triple_blink_have_the_right_pulse_counts);
    RUN_TEST(test_sos_is_nine_pulses);
    RUN_TEST(test_patterns_are_periodic);
    RUN_TEST(test_pattern_names_match_the_architecture_table);
    RUN_TEST(test_every_registry_code_is_reachable_from_an_event_name);
    RUN_TEST(test_trip_causes_all_map_to_published_codes);
    RUN_TEST(test_event_names_are_unique_and_populated);
    RUN_TEST(test_unknown_events_resolve_to_nothing_rather_than_to_something_wrong);
    RUN_TEST(test_the_state_names_match_the_registry_vocabulary);
    return UNITY_END();
}
