#include "saw_trip_counter.h"

bool SawTripCounter::record(uint32_t now_ms, uint8_t max_trips, uint32_t window_ms)
{
    /* The window is anchored to the first trip of a burst, not to boot. The reference
     * pseudocode leaves first_trip_ms at 0 until the window lapses, which measures the
     * first burst from power-up instead of from the first trip. */
    if (!window_open_ || (uint32_t)(now_ms - window_start_ms_) > window_ms) {
        count_ = 0;
        window_start_ms_ = now_ms;
        window_open_ = true;
    }

    if (count_ < 255) {
        count_++;
    }

    return max_trips > 0 && count_ >= max_trips;
}

void SawTripCounter::reset()
{
    count_ = 0;
    window_start_ms_ = 0;
    window_open_ = false;
}

uint32_t SawTripCounter::window_remaining_ms(uint32_t now_ms, uint32_t window_ms) const
{
    if (!window_open_) {
        return 0;
    }
    uint32_t elapsed = (uint32_t)(now_ms - window_start_ms_);
    if (elapsed >= window_ms) {
        return 0;
    }
    return window_ms - elapsed;
}
