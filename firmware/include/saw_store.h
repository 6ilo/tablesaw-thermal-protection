/*
 * Persistence: NVS for state that must survive a power cycle, LittleFS for the log.
 *
 * Two requirements drive this file.
 *
 * SR-5 adjacent, from ARCHITECTURE.md § State machine: "Trip events persist across power
 * loss. On boot, if the last state was TRIPPED or MANUAL_LOCKOUT, the persisted state is
 * honored — a hot power-cycle cannot clear a lockout." That is what the NVS half is for,
 * and it is why the last state is written on the transition rather than on a timer.
 *
 * ARCHITECTURE.md § Logging: "Retain at least 30 days of run data and all trip events."
 * The sample log is a ring of eight rotating segments sized from SAW_LOG_RING_BYTES.
 * A segment boundary is the only time any index is rewritten — roughly once every
 * retention/8, so about every four days — which keeps flash wear off the hot path.
 */
#pragma once

#include <stdint.h>
#include <stddef.h>

#include "saw_types.h"

/* 16 bytes. Packed and CRC'd so a record torn by a power loss mid-write is detectable
 * rather than silently decoded as a plausible temperature. */
struct __attribute__((packed)) SawSampleRecord {
    uint32_t session;    /* boot counter, so records order across power cycles */
    uint32_t uptime_s;   /* seconds since boot of that session                 */
    int16_t  c_x10;      /* primary temperature × 10, INT16_MIN if invalid     */
    int16_t  frame_x10;  /* frame temperature × 10, INT16_MIN if unavailable   */
    uint8_t  state;      /* SawState                                           */
    uint8_t  flags;      /* SawAlert bits, truncated to 8                      */
    uint16_t crc;        /* CRC-16/CCITT over the preceding 14 bytes           */
};

bool saw_store_begin(void);
bool saw_store_fs_ok(void);

/* NVS-backed protection state. */
SawState saw_store_last_state(void);
void     saw_store_set_last_state(SawState s);
uint32_t saw_store_session(void);
uint32_t saw_store_trips_lifetime(void);
void     saw_store_set_trips_lifetime(uint32_t n);

/* Append one line to the event log. Already-formatted text; the caller owns the format
 * so serial and flash cannot drift. */
void saw_store_log_event(const char *line);

/* Append one aggregated sample. Fills in the CRC. */
void saw_store_log_sample(SawSampleRecord rec);

/* Total sample records currently retained, and what the ring is worth in hours. */
uint32_t saw_store_sample_count(void);
uint32_t saw_store_retention_hours(void);

/* Walk every retained sample, oldest first, skipping records whose CRC does not check.
 * Used to stream the log out as CSV. Returns the number of records passed to `cb`. */
typedef void (*SawSampleVisitor)(const SawSampleRecord &rec, void *ctx);
uint32_t saw_store_stream_samples(SawSampleVisitor cb, void *ctx);

/* Bytes used / total on the log filesystem. */
void saw_store_usage(uint32_t *used, uint32_t *total);

uint16_t saw_crc16(const uint8_t *data, size_t len);
