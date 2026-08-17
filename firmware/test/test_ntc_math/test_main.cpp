/*
 * NTC β-equation against known resistance/temperature pairs, and the direction of the
 * divider.
 *
 * Reference values for a 10 kΩ B3950 part with the low-side topology in
 * hardware/schematic/WIRING.md, computed from R(T) = R25 · exp(β·(1/T − 1/298.15)):
 *
 *     0 °C    33 620 Ω     ADC code ≈ 3156
 *    25 °C    10 000 Ω     ADC code ≈ 2048
 *   100 °C       698 Ω     ADC code ≈  267
 */
#include <unity.h>

#include <math.h>

#include "saw_ntc.h"

static const SawNtcParams P = {
    10000.0f,   /* r_fixed_ohms   */
    10000.0f,   /* r_nominal_ohms */
    25.0f,      /* t_nominal_c    */
    3950.0f,    /* beta           */
    3.3f,       /* vref_v         */
    4095.0f,    /* adc_full_scale */
    0.0f,       /* offset_c       */
};

void setUp(void) {}
void tearDown(void) {}

/* Code that the divider produces for a given NTC resistance. */
static float code_for(float r_ntc)
{
    float v = P.vref_v * r_ntc / (P.r_fixed_ohms + r_ntc);
    return v / P.vref_v * P.adc_full_scale;
}

static void test_known_resistance_temperature_pairs(void)
{
    TEST_ASSERT_FLOAT_WITHIN(0.5f, 0.0f, saw_ntc_celsius_from_r(33620.0f, P));
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 25.0f, saw_ntc_celsius_from_r(10000.0f, P));
    TEST_ASSERT_FLOAT_WITHIN(0.5f, 100.0f, saw_ntc_celsius_from_r(698.0f, P));
}

static void test_round_trip_through_the_divider(void)
{
    TEST_ASSERT_FLOAT_WITHIN(0.6f, 0.0f, saw_ntc_celsius(code_for(33620.0f), P));
    TEST_ASSERT_FLOAT_WITHIN(0.2f, 25.0f, saw_ntc_celsius(code_for(10000.0f), P));
    TEST_ASSERT_FLOAT_WITHIN(0.6f, 100.0f, saw_ntc_celsius(code_for(698.0f), P));
}

static void test_the_ntc_is_on_the_low_side_so_hotter_reads_lower(void)
{
    /* Getting this backwards builds a supervisor that trips on a cold motor and runs a hot
     * one, which is the single worst outcome available. */
    float cold = saw_ntc_celsius(3156.0f, P);
    float warm = saw_ntc_celsius(2048.0f, P);
    float hot = saw_ntc_celsius(267.0f, P);
    TEST_ASSERT_TRUE(cold < warm);
    TEST_ASSERT_TRUE(warm < hot);
    TEST_ASSERT_FLOAT_WITHIN(1.0f, 25.0f, warm);
}

static void test_resistance_from_code(void)
{
    TEST_ASSERT_FLOAT_WITHIN(60.0f, 10000.0f, saw_ntc_resistance(2048.0f, P));
    TEST_ASSERT_FLOAT_WITHIN(200.0f, 33620.0f, saw_ntc_resistance(3156.0f, P));
}

static void test_rails_have_no_solution(void)
{
    /* At either rail the divider equation has nothing to say. The driver's raw-band check
     * catches these first; this is the second line. */
    TEST_ASSERT_TRUE(saw_ntc_resistance(0.0f, P) < 0.0f);
    TEST_ASSERT_TRUE(saw_ntc_resistance(4095.0f, P) < 0.0f);
    TEST_ASSERT_TRUE(isnan(saw_ntc_celsius(0.0f, P)));
    TEST_ASSERT_TRUE(isnan(saw_ntc_celsius(4095.0f, P)));
}

static void test_measured_divider_resistor_shifts_the_answer(void)
{
    /* Why "measure R_FIXED" is step 1 of the calibration and not a nicety: a 5% part
     * marked 10 kΩ reading 9500 Ω moves the computed temperature by a real amount. */
    SawNtcParams low = P;
    low.r_fixed_ohms = 9500.0f;
    float nominal = saw_ntc_celsius(2048.0f, P);
    float actual = saw_ntc_celsius(2048.0f, low);
    TEST_ASSERT_TRUE(fabsf(nominal - actual) > 0.3f);
}

static void test_offset_is_applied(void)
{
    SawNtcParams o = P;
    o.offset_c = -3.5f;
    TEST_ASSERT_FLOAT_WITHIN(0.01f, saw_ntc_celsius(2048.0f, P) - 3.5f,
                             saw_ntc_celsius(2048.0f, o));
}

static void test_solve_beta_recovers_the_curve(void)
{
    /* Calibration step 6: two points, off in opposite directions, solve for actual β. */
    float beta = saw_ntc_solve_beta(33620.0f, 0.0f, 698.0f, 100.0f);
    TEST_ASSERT_FLOAT_WITHIN(20.0f, 3950.0f, beta);

    /* And a part that really is off-curve is recovered too. */
    float r0 = 10000.0f * expf(3600.0f * (1.0f / 273.15f - 1.0f / 298.15f));
    float r100 = 10000.0f * expf(3600.0f * (1.0f / 373.15f - 1.0f / 298.15f));
    TEST_ASSERT_FLOAT_WITHIN(20.0f, 3600.0f,
                             saw_ntc_solve_beta(r0, 0.0f, r100, 100.0f));
}

static void test_solve_beta_rejects_degenerate_input(void)
{
    TEST_ASSERT_EQUAL_FLOAT(0.0f, saw_ntc_solve_beta(10000.0f, 25.0f, 10000.0f, 25.0f));
    TEST_ASSERT_EQUAL_FLOAT(0.0f, saw_ntc_solve_beta(0.0f, 0.0f, 698.0f, 100.0f));
    TEST_ASSERT_EQUAL_FLOAT(0.0f, saw_ntc_solve_beta(33620.0f, 0.0f, -1.0f, 100.0f));
}

static void test_the_probes_range_limits_land_inside_the_raw_band(void)
{
    /* The firmware's electrical band is codes 20..4090. The DROK part is specified
     * −25 to +125 °C; the whole usable span has to sit inside the band or a legitimate
     * temperature would read as a short or an open. */
    float r_minus20 = 10000.0f * expf(3950.0f * (1.0f / 253.15f - 1.0f / 298.15f));
    float r_150 = 10000.0f * expf(3950.0f * (1.0f / 423.15f - 1.0f / 298.15f));
    float code_cold = code_for(r_minus20);
    float code_hot = code_for(r_150);
    TEST_ASSERT_TRUE_MESSAGE(code_cold < 4090.0f, "-20 C reads as an open probe");
    TEST_ASSERT_TRUE_MESSAGE(code_hot > 20.0f, "150 C reads as a shorted probe");
}

int main(int, char **)
{
    UNITY_BEGIN();
    RUN_TEST(test_known_resistance_temperature_pairs);
    RUN_TEST(test_round_trip_through_the_divider);
    RUN_TEST(test_the_ntc_is_on_the_low_side_so_hotter_reads_lower);
    RUN_TEST(test_resistance_from_code);
    RUN_TEST(test_rails_have_no_solution);
    RUN_TEST(test_measured_divider_resistor_shifts_the_answer);
    RUN_TEST(test_offset_is_applied);
    RUN_TEST(test_solve_beta_recovers_the_curve);
    RUN_TEST(test_solve_beta_rejects_degenerate_input);
    RUN_TEST(test_the_probes_range_limits_land_inside_the_raw_band);
    return UNITY_END();
}
