/*
 * NTC thermistor maths — the β-parameter equation and the two-point calibration solve.
 *
 * Divider topology (hardware/schematic/WIRING.md):
 *
 *     3V3 --[ R_FIXED ]--+-- GPIO34 (ADC1)
 *                        |
 *                     [ NTC ]
 *                        |
 *                       GND
 *
 * So the NTC sits on the *low* side and its resistance falls as it heats, which means
 * the ADC code falls as temperature rises. Getting that backwards is the classic way to
 * build a supervisor that trips on a cold motor and runs a hot one, so
 * test_ntc_math pins the direction as well as the values.
 *
 * The ESP32's ADC is nonlinear and noisy. That is absorbed by oversampling in the
 * driver and by the mandatory two-point calibration in ARCHITECTURE.md § Sensor
 * calibration, not by anything in here — this file only implements the equation the
 * calibration procedure is written against.
 */
#pragma once

#include <stdint.h>

struct SawNtcParams {
    float r_fixed_ohms;    /* MEASURED value of the divider resistor, not nominal */
    float r_nominal_ohms;  /* NTC resistance at t_nominal_c, typically 10000       */
    float t_nominal_c;     /* typically 25                                        */
    float beta;            /* B3950 part -> 3950 until calibration says otherwise */
    float vref_v;          /* divider supply, 3.3                                 */
    float adc_full_scale;  /* 4095 for the ESP32's 12-bit ADC                     */
    float offset_c;        /* additive correction from two-point calibration      */
};

/* NTC resistance implied by an ADC code. Returns a negative value if the code is at a
 * rail, where the divider equation has no meaningful solution. */
float saw_ntc_resistance(float adc_code, const SawNtcParams &p);

/* Temperature for an ADC code, including offset_c. NaN if the code is unusable. */
float saw_ntc_celsius(float adc_code, const SawNtcParams &p);

/* Temperature for a known resistance, excluding offset_c. */
float saw_ntc_celsius_from_r(float r_ntc_ohms, const SawNtcParams &p);

/*
 * Solve for the actual β from two measured (resistance, temperature) points — step 6 of
 * the NTC calibration procedure, for when the ice-bath and boiling readings are off in
 * opposite directions. Returns 0 on degenerate input.
 */
float saw_ntc_solve_beta(float r_cold_ohms, float t_cold_c,
                         float r_hot_ohms, float t_hot_c);
