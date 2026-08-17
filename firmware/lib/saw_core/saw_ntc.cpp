#include "saw_ntc.h"

#include <math.h>

#define KELVIN 273.15f

float saw_ntc_resistance(float adc_code, const SawNtcParams &p)
{
    if (p.adc_full_scale <= 0.0f || p.r_fixed_ohms <= 0.0f) {
        return -1.0f;
    }

    float v = adc_code / p.adc_full_scale * p.vref_v;

    /* At either rail the divider tells us nothing: v == vref means the NTC looks like an
     * open circuit, v == 0 means it looks like a short. Both are faults, and the driver's
     * raw-band check catches them before this is ever called. */
    float headroom = p.vref_v - v;
    if (v <= 0.0f || headroom <= 0.0f) {
        return -1.0f;
    }

    return p.r_fixed_ohms * v / headroom;
}

float saw_ntc_celsius_from_r(float r_ntc_ohms, const SawNtcParams &p)
{
    if (r_ntc_ohms <= 0.0f || p.r_nominal_ohms <= 0.0f || p.beta == 0.0f) {
        return NAN;
    }

    float inv_t = 1.0f / (p.t_nominal_c + KELVIN) +
                  (1.0f / p.beta) * logf(r_ntc_ohms / p.r_nominal_ohms);
    if (inv_t == 0.0f) {
        return NAN;
    }

    return (1.0f / inv_t) - KELVIN;
}

float saw_ntc_celsius(float adc_code, const SawNtcParams &p)
{
    float r = saw_ntc_resistance(adc_code, p);
    if (r <= 0.0f) {
        return NAN;
    }
    float c = saw_ntc_celsius_from_r(r, p);
    if (isnan(c)) {
        return NAN;
    }
    return c + p.offset_c;
}

float saw_ntc_solve_beta(float r_cold_ohms, float t_cold_c,
                         float r_hot_ohms, float t_hot_c)
{
    if (r_cold_ohms <= 0.0f || r_hot_ohms <= 0.0f) {
        return 0.0f;
    }

    float inv_t_hot  = 1.0f / (t_hot_c + KELVIN);
    float inv_t_cold = 1.0f / (t_cold_c + KELVIN);
    float denom = inv_t_hot - inv_t_cold;
    if (denom == 0.0f) {
        return 0.0f;
    }

    return logf(r_hot_ohms / r_cold_ohms) / denom;
}
