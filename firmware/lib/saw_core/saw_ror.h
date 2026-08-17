/*
 * Rate-of-rise tracking — ARCHITECTURE.md § Rate-of-rise tracking.
 *
 * "The genuinely new capability. A °C/min figure that climbs across sessions at constant
 * workload means airflow is degrading — cleaning is due *before* a trip."
 *
 * A least-squares fit over a trailing window, rather than (last - first) / dt, because a
 * single noisy sample at either end of the window would otherwise swing the answer
 * enough to raise or hide W02.
 *
 * Fixed capacity, no allocation. Samples are pushed at most once per SAW_ROR_MIN_GAP_MS
 * so a 4 Hz protection loop does not need a 240-deep buffer to cover 60 seconds.
 */
#pragma once

#include <stdint.h>

#define SAW_ROR_CAPACITY    96
#define SAW_ROR_MIN_GAP_MS  1000

class SawRor {
public:
    SawRor() : head_(0), count_(0), have_last_(false), last_push_ms_(0) {}

    /* Returns true if the sample was taken (rate-limited). */
    bool push(uint32_t now_ms, float celsius);

    /* Least-squares slope in °C per minute over samples inside `window_ms` of `now_ms`.
     * Returns 0 when there is not enough spread to fit a line. */
    float slope_c_per_min(uint32_t now_ms, uint32_t window_ms) const;

    /* Number of samples currently inside the window. */
    uint8_t samples_in_window(uint32_t now_ms, uint32_t window_ms) const;

    void reset();

private:
    struct Sample {
        uint32_t t_ms;
        float    c;
    };

    Sample   buf_[SAW_ROR_CAPACITY];
    uint8_t  head_;      /* next write position */
    uint8_t  count_;
    bool     have_last_;
    uint32_t last_push_ms_;
};
