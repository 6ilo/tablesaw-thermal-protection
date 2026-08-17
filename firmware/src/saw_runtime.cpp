#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <math.h>
#include <stdint.h>
#include <string.h>

#include "saw_config.h"
#include "saw_runtime.h"

/* --------------------------------------------------------------------------- */
/* Snapshot — seqlock, so the writer never waits                               */
/* --------------------------------------------------------------------------- */

static volatile uint32_t s_seq = 0;
static SawSnapshot       s_snap;

void saw_runtime_publish(const SawSnapshot &s)
{
    s_seq++;                 /* odd: write in progress */
    __sync_synchronize();
    s_snap = s;
    __sync_synchronize();
    s_seq++;                 /* even: stable */
}

SawSnapshot saw_runtime_snapshot(void)
{
    SawSnapshot out;
    memset(&out, 0, sizeof(out));
    for (int attempt = 0; attempt < 8; attempt++) {
        uint32_t a = s_seq;
        __sync_synchronize();
        if (a & 1u) {
            continue;        /* writer mid-update */
        }
        out = s_snap;
        __sync_synchronize();
        if (s_seq == a) {
            return out;
        }
    }
    /* Eight torn reads in a row is not credible at 4 Hz; return the last attempt rather
     * than spin here, because this runs on the network task and blocking it achieves
     * nothing. A single stale frame on a dashboard is not a safety event. */
    return out;
}

/* --------------------------------------------------------------------------- */
/* History ring and event ring — try-lock from core 0                          */
/* --------------------------------------------------------------------------- */

static SemaphoreHandle_t s_lock = NULL;

static SawHistPoint s_hist[SAW_LOG_RAM_SAMPLES];
static size_t       s_hist_head = 0;
static size_t       s_hist_count = 0;

static char   s_events[SAW_EVENT_RING][SAW_EVENT_LINE_MAX];
static size_t s_ev_head = 0;
static size_t s_ev_count = 0;

static volatile bool s_alert_clear_requested = false;

void saw_runtime_init(void)
{
    if (!s_lock) {
        s_lock = xSemaphoreCreateMutex();
    }
    s_hist_head = s_hist_count = 0;
    s_ev_head = s_ev_count = 0;
    memset(&s_snap, 0, sizeof(s_snap));
}

static int16_t to_x10(float c)
{
    if (isnan(c)) {
        return INT16_MIN;
    }
    if (c > 3200.0f) {
        return 32000;
    }
    if (c < -3200.0f) {
        return -32000;
    }
    return (int16_t)lroundf(c * 10.0f);
}

void saw_runtime_push_history(uint32_t t_s, float celsius, float frame_c, uint8_t state)
{
    if (!s_lock || xSemaphoreTake(s_lock, 0) != pdTRUE) {
        return;   /* core 1 is reading; drop the point rather than wait */
    }
    s_hist[s_hist_head].t_s = t_s;
    s_hist[s_hist_head].c_x10 = to_x10(celsius);
    s_hist[s_hist_head].frame_x10 = to_x10(frame_c);
    s_hist[s_hist_head].state = state;
    s_hist_head = (s_hist_head + 1) % SAW_LOG_RAM_SAMPLES;
    if (s_hist_count < SAW_LOG_RAM_SAMPLES) {
        s_hist_count++;
    }
    xSemaphoreGive(s_lock);
}

void saw_runtime_push_event(const char *line)
{
    if (!line || !s_lock || xSemaphoreTake(s_lock, 0) != pdTRUE) {
        return;
    }
    strncpy(s_events[s_ev_head], line, SAW_EVENT_LINE_MAX - 1);
    s_events[s_ev_head][SAW_EVENT_LINE_MAX - 1] = '\0';
    s_ev_head = (s_ev_head + 1) % SAW_EVENT_RING;
    if (s_ev_count < SAW_EVENT_RING) {
        s_ev_count++;
    }
    xSemaphoreGive(s_lock);
}

size_t saw_runtime_history(SawHistPoint *out, size_t max)
{
    if (!out || !s_lock || xSemaphoreTake(s_lock, pdMS_TO_TICKS(50)) != pdTRUE) {
        return 0;
    }
    size_t n = s_hist_count < max ? s_hist_count : max;
    /* Oldest first, so the dashboard can plot without reversing. */
    for (size_t i = 0; i < n; i++) {
        size_t idx = (s_hist_head + SAW_LOG_RAM_SAMPLES - s_hist_count + i) %
                     SAW_LOG_RAM_SAMPLES;
        out[i] = s_hist[idx];
    }
    xSemaphoreGive(s_lock);
    return n;
}

size_t saw_runtime_events(char *out, size_t out_len)
{
    if (!out || out_len == 0) {
        return 0;
    }
    out[0] = '\0';
    if (!s_lock || xSemaphoreTake(s_lock, pdMS_TO_TICKS(50)) != pdTRUE) {
        return 0;
    }
    size_t used = 0;
    /* Newest first: the line that explains why the saw just stopped goes at the top. */
    for (size_t i = 0; i < s_ev_count; i++) {
        size_t idx = (s_ev_head + SAW_EVENT_RING - 1 - i) % SAW_EVENT_RING;
        size_t len = strlen(s_events[idx]);
        if (used + len + 2 >= out_len) {
            break;
        }
        memcpy(out + used, s_events[idx], len);
        used += len;
        out[used++] = '\n';
        out[used] = '\0';
    }
    xSemaphoreGive(s_lock);
    return used;
}

void saw_runtime_request_alert_clear(void)
{
    s_alert_clear_requested = true;
}

bool saw_runtime_take_alert_clear(void)
{
    if (!s_alert_clear_requested) {
        return false;
    }
    s_alert_clear_requested = false;
    return true;
}
