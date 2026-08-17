#include "saw_ror.h"

bool SawRor::push(uint32_t now_ms, float celsius)
{
    if (have_last_ && (uint32_t)(now_ms - last_push_ms_) < SAW_ROR_MIN_GAP_MS) {
        return false;
    }

    buf_[head_].t_ms = now_ms;
    buf_[head_].c = celsius;
    head_ = (uint8_t)((head_ + 1) % SAW_ROR_CAPACITY);
    if (count_ < SAW_ROR_CAPACITY) {
        count_++;
    }

    last_push_ms_ = now_ms;
    have_last_ = true;
    return true;
}

void SawRor::reset()
{
    head_ = 0;
    count_ = 0;
    have_last_ = false;
    last_push_ms_ = 0;
}

uint8_t SawRor::samples_in_window(uint32_t now_ms, uint32_t window_ms) const
{
    uint8_t n = 0;
    for (uint8_t i = 0; i < count_; i++) {
        uint8_t idx = (uint8_t)((head_ + SAW_ROR_CAPACITY - 1 - i) % SAW_ROR_CAPACITY);
        if ((uint32_t)(now_ms - buf_[idx].t_ms) > window_ms) {
            break;
        }
        n++;
    }
    return n;
}

float SawRor::slope_c_per_min(uint32_t now_ms, uint32_t window_ms) const
{
    /* Sums for an ordinary least-squares fit of c against time. Time is carried in
     * seconds relative to the newest sample to keep the products small. */
    double n = 0.0, sum_t = 0.0, sum_c = 0.0, sum_tt = 0.0, sum_tc = 0.0;

    if (count_ == 0) {
        return 0.0f;
    }

    uint8_t newest = (uint8_t)((head_ + SAW_ROR_CAPACITY - 1) % SAW_ROR_CAPACITY);
    uint32_t t0 = buf_[newest].t_ms;

    for (uint8_t i = 0; i < count_; i++) {
        uint8_t idx = (uint8_t)((head_ + SAW_ROR_CAPACITY - 1 - i) % SAW_ROR_CAPACITY);
        if ((uint32_t)(now_ms - buf_[idx].t_ms) > window_ms) {
            break;
        }
        /* Negative seconds, older samples further from zero. */
        double t = ((double)buf_[idx].t_ms - (double)t0) / 1000.0;
        double c = (double)buf_[idx].c;
        n += 1.0;
        sum_t += t;
        sum_c += c;
        sum_tt += t * t;
        sum_tc += t * c;
    }

    if (n < 3.0) {
        return 0.0f;
    }

    double denom = n * sum_tt - sum_t * sum_t;
    if (denom > -1e-9 && denom < 1e-9) {
        return 0.0f;   /* every sample at the same instant: no slope to report */
    }

    double slope_per_s = (n * sum_tc - sum_t * sum_c) / denom;
    return (float)(slope_per_s * 60.0);
}
