/*
 * PER-UNIT CALIBRATION. Edit this file for the board in front of you.
 *
 * These are the only values in the firmware that are properties of one physical
 * assembly rather than of the design. ARCHITECTURE.md § Sensor calibration and
 * archive/BUILD-TONIGHT.md § 5 both describe the two-point procedure that produces them; do it
 * at the bench, before the probe is mounted on the motor.
 *
 *   1. Measure the divider resistor with a meter. Put the measured ohms in
 *      SAW_NTC_R_FIXED_OHMS. A 5% part marked 10 kΩ can read 9500–10500, and that error
 *      lands directly on the temperature.
 *   2. Ice bath: crushed ice, just enough water to cover, stirred 30 s, probe clear of
 *      the vessel walls, wait 2 minutes. Expect 0.0 °C.
 *   3. Boiling water off the flame, 30 s. Expect 100.0 °C at sea level; subtract about
 *      1 °C per 300 m of elevation.
 *   4. Both readings within ±2 °C  -> done.
 *      Both off by the same amount -> put the correction in SAW_NTC_OFFSET_C.
 *      Off in opposite directions  -> β is wrong. The serial log prints the measured
 *                                     resistance at each point; feed both to
 *                                     `python3 scripts/solve_beta.py` and put the answer
 *                                     in SAW_NTC_BETA.
 *
 * Then set SAW_CALIBRATED to 1. Until you do, the boot log carries UNCALIBRATED_BUILD
 * and the dashboard shows a banner — an uncalibrated probe reading 5 °C low is a trip
 * threshold 5 °C higher than the one written on the operator card.
 */
#pragma once

/* Set to 1 once the two-point procedure above has actually been run on this unit. */
#ifndef SAW_CALIBRATED
#define SAW_CALIBRATED              0
#endif

/* MEASURE THIS. Nominal 10 kΩ is a starting value, not an answer. */
#ifndef SAW_NTC_R_FIXED_OHMS
#define SAW_NTC_R_FIXED_OHMS        10000.0f
#endif

/* DROK probe: 10 kΩ at 25 °C, B3950 curve. */
#ifndef SAW_NTC_R_NOMINAL_OHMS
#define SAW_NTC_R_NOMINAL_OHMS      10000.0f
#endif
#ifndef SAW_NTC_T_NOMINAL_C
#define SAW_NTC_T_NOMINAL_C         25.0f
#endif
#ifndef SAW_NTC_BETA
#define SAW_NTC_BETA                3950.0f
#endif

/* Divider supply and ADC full scale. The ESP32 ADC is nonlinear; the two-point
 * calibration absorbs that, which is why it is not optional. */
#ifndef SAW_NTC_VREF_V
#define SAW_NTC_VREF_V              3.3f
#endif
#ifndef SAW_NTC_ADC_FULL_SCALE
#define SAW_NTC_ADC_FULL_SCALE      4095.0f
#endif

/* Additive correction from calibration step 5. */
#ifndef SAW_NTC_OFFSET_C
#define SAW_NTC_OFFSET_C            0.0f
#endif

/* K-type / MAX31855 correction. The amplifier is factory-trimmed and does its own
 * cold-junction compensation, so this should stay 0 unless the ice-bath and boiling
 * checks in ARCHITECTURE.md § Sensor calibration say otherwise. */
#ifndef SAW_TC_OFFSET_C
#define SAW_TC_OFFSET_C             0.0f
#endif

/*
 * Baseline rate of rise in °C/min at normal workload, from commissioning step 10.
 * 0 disables W02 (HEATING_FASTER_THAN_BASELINE) — there is no honest way to say
 * "faster than baseline" before a baseline exists, and a fabricated one would either
 * cry wolf on every cut or never fire at all.
 */
#ifndef SAW_ROR_BASELINE_C_PER_MIN
#define SAW_ROR_BASELINE_C_PER_MIN  0.0f
#endif
