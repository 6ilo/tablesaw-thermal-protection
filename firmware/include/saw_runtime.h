/*
 * The boundary between core 0 (protection) and core 1 (advisory).
 *
 * ARCHITECTURE.md § Task layout: "The protection loop must not depend on Wi-Fi, NTP,
 * filesystem, or the web server." SR-8: "Network is advisory only ... Treat all network
 * input as untrusted."
 *
 * So the traffic across this boundary is deliberately lopsided:
 *
 *   core 0 -> core 1   a snapshot struct, a history ring, event lines. Published through
 *                      a seqlock and a try-lock that the protection loop never waits on.
 *                      If core 1 is mid-read, core 0 drops the update and carries on.
 *
 *   core 1 -> core 0   one flag: "the operator acknowledged the alert banner". It clears
 *                      alert bits and nothing else. There is no path from an HTTP request
 *                      to the state machine, the thresholds, or the hold line.
 *
 * The asymmetry is the point. A hung web server, a Wi-Fi panic, or a malicious request
 * can starve the dashboard of updates; none of them can delay a trip or close a contact.
 */
#pragma once

#include <stdint.h>
#include <stddef.h>

#include "saw_led.h"
#include "saw_types.h"

struct SawSnapshot {
    uint8_t  state;
    uint8_t  cause;
    uint8_t  led;
    bool     hold_closed;

    float    celsius;
    float    frame_c;            /* NAN when no frame sensor                    */
    float    delta_c;            /* primary − frame, NAN when no frame sensor   */
    float    internal_c;         /* MAX31855 cold junction, NAN on Path A       */
    float    ror_c_per_min;

    int32_t  ntc_raw;            /* −1 when the NTC is not read on this build   */
    float    ntc_resistance;

    uint32_t alerts;
    uint32_t uptime_ms;
    uint32_t state_ms;           /* time in the current state                   */
    uint32_t cooldown_remaining_ms;
    uint32_t sensor_age_ms;      /* since the last reading we believed          */

    uint8_t  trip_count;         /* inside the rolling window                   */
    uint32_t trips_lifetime;
    uint32_t session;

    bool     probe_verified;
    bool     calibrated;
    bool     fs_ok;
};

struct SawHistPoint {
    uint32_t t_s;
    int16_t  c_x10;
    int16_t  frame_x10;
    uint8_t  state;
};

#define SAW_EVENT_LINE_MAX   120
#define SAW_EVENT_RING       24

void saw_runtime_init(void);

/* Core 0. Never blocks. */
void saw_runtime_publish(const SawSnapshot &s);
void saw_runtime_push_history(uint32_t t_s, float celsius, float frame_c, uint8_t state);
void saw_runtime_push_event(const char *line);

/* Core 1. */
SawSnapshot saw_runtime_snapshot(void);
size_t saw_runtime_history(SawHistPoint *out, size_t max);
size_t saw_runtime_events(char *out, size_t out_len);

/* The one input. Latched here, consumed by the protection loop. */
void saw_runtime_request_alert_clear(void);
bool saw_runtime_take_alert_clear(void);
