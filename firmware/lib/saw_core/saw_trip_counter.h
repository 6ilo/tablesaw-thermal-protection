/*
 * Rolling-window trip counter — ARCHITECTURE.md § State machine, "Chatter suppression".
 *
 * MAX_CONSECUTIVE_TRIPS trips inside TRIP_WINDOW_MIN drop the supervisor into
 * MANUAL_LOCKOUT instead of letting it auto-cycle the coil relay every few minutes.
 *
 * One deliberate deviation from the reference pseudocode, which counts a trip on every
 * protection-loop iteration that calls trip(). At SAMPLE_HZ = 4 a single stuck sensor
 * fault would reach three "trips" in 750 ms and lock out instantly, which is not what
 * E04 promises the operator ("three trips inside ten minutes") and not what chatter
 * suppression is for. record() is therefore called once per *entry* into TRIPPED —
 * counting edges, not cycles. A persistent fault is one trip; a fault that clears and
 * returns three times in ten minutes is three.
 */
#pragma once

#include <stdint.h>

class SawTripCounter {
public:
    SawTripCounter() : count_(0), window_start_ms_(0), window_open_(false) {}

    /* Record one trip. Returns true if this trip escalates to MANUAL_LOCKOUT. */
    bool record(uint32_t now_ms, uint8_t max_trips, uint32_t window_ms);

    void reset();

    uint8_t  count() const { return count_; }
    bool     window_open() const { return window_open_; }
    uint32_t window_start_ms() const { return window_start_ms_; }

    /* Milliseconds until the current window lapses, 0 if no window is open. */
    uint32_t window_remaining_ms(uint32_t now_ms, uint32_t window_ms) const;

private:
    uint8_t  count_;
    uint32_t window_start_ms_;
    bool     window_open_;
};
