#include <Arduino.h>
#include <LittleFS.h>
#include <Preferences.h>

#include "saw_config.h"
#include "saw_store.h"

#define NVS_NAMESPACE      "saw"
#define KEY_LAST_STATE     "last_state"
#define KEY_SESSION        "session"
#define KEY_TRIPS          "trips"

#define SEGMENTS           8
#define SEGMENT_BYTES      ((SAW_LOG_RING_BYTES) / SEGMENTS)
#define SEGMENT_RECORDS    (SEGMENT_BYTES / sizeof(SawSampleRecord))
#define META_MAGIC         0x53415701UL   /* "SAW" + version */

static Preferences s_prefs;
static bool     s_fs_ok = false;
static bool     s_nvs_ok = false;
static SawState s_last_state = SAW_COOLDOWN;
static uint32_t s_session = 0;
static uint32_t s_trips_lifetime = 0;
static uint8_t  s_segment = 0;
static uint32_t s_segment_records = 0;

struct __attribute__((packed)) LogMeta {
    uint32_t magic;
    uint8_t  segment;
    uint8_t  wrapped;    /* 1 once every segment has been written at least once */
    uint16_t crc;
};

uint16_t saw_crc16(const uint8_t *data, size_t len)
{
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (int b = 0; b < 8; b++) {
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
        }
    }
    return crc;
}

static void segment_path(uint8_t index, char *out, size_t len)
{
    snprintf(out, len, "/s%u.bin", (unsigned)index);
}

static bool meta_read(LogMeta *m)
{
    File f = LittleFS.open("/meta.bin", "r");
    if (!f) {
        return false;
    }
    bool ok = (f.read((uint8_t *)m, sizeof(*m)) == sizeof(*m));
    f.close();
    if (!ok || m->magic != META_MAGIC) {
        return false;
    }
    uint16_t want = saw_crc16((const uint8_t *)m, sizeof(*m) - sizeof(uint16_t));
    return want == m->crc;
}

static void meta_write(uint8_t segment, uint8_t wrapped)
{
    LogMeta m;
    m.magic = META_MAGIC;
    m.segment = segment;
    m.wrapped = wrapped;
    m.crc = saw_crc16((const uint8_t *)&m, sizeof(m) - sizeof(uint16_t));

    File f = LittleFS.open("/meta.bin", "w");
    if (!f) {
        return;
    }
    f.write((const uint8_t *)&m, sizeof(m));
    f.close();
}

static uint8_t s_wrapped = 0;

bool saw_store_begin(void)
{
    s_nvs_ok = s_prefs.begin(NVS_NAMESPACE, false);
    if (s_nvs_ok) {
        s_last_state = (SawState)s_prefs.getUChar(KEY_LAST_STATE, (uint8_t)SAW_COOLDOWN);
        if (s_last_state < SAW_BOOT || s_last_state > SAW_MANUAL_LOCKOUT) {
            s_last_state = SAW_COOLDOWN;
        }
        s_session = s_prefs.getUInt(KEY_SESSION, 0) + 1;
        s_prefs.putUInt(KEY_SESSION, s_session);
        s_trips_lifetime = s_prefs.getUInt(KEY_TRIPS, 0);
    } else {
        /* No NVS is not a reason to run unprotected, but it is a reason to be
         * pessimistic: assume the last state was a trip so a cold start after a real
         * trip cannot arm early. COOLDOWN already holds the contact open for
         * COOLDOWN_HOLD, and TRIPPED is honoured only when the motor is also hot. */
        s_last_state = SAW_TRIPPED;
    }

    /* LittleFS carries the log and the offline error-code bundle. Formatting on failure
     * is safe: nothing on it is protection state. */
    s_fs_ok = LittleFS.begin(true);
    if (s_fs_ok) {
        LogMeta m;
        if (meta_read(&m) && m.segment < SEGMENTS) {
            s_segment = m.segment;
            s_wrapped = m.wrapped;
        } else {
            s_segment = 0;
            s_wrapped = 0;
            meta_write(s_segment, s_wrapped);
        }

        char path[16];
        segment_path(s_segment, path, sizeof(path));
        File f = LittleFS.open(path, "r");
        s_segment_records = f ? (uint32_t)(f.size() / sizeof(SawSampleRecord)) : 0;
        if (f) {
            f.close();
        }
    }

    return s_fs_ok && s_nvs_ok;
}

bool saw_store_fs_ok(void)
{
    return s_fs_ok;
}

SawState saw_store_last_state(void)
{
    return s_last_state;
}

void saw_store_set_last_state(SawState s)
{
    if (s == s_last_state) {
        return;
    }
    s_last_state = s;
    if (s_nvs_ok) {
        s_prefs.putUChar(KEY_LAST_STATE, (uint8_t)s);
    }
}

uint32_t saw_store_session(void)
{
    return s_session;
}

uint32_t saw_store_trips_lifetime(void)
{
    return s_trips_lifetime;
}

void saw_store_set_trips_lifetime(uint32_t n)
{
    if (n == s_trips_lifetime) {
        return;
    }
    s_trips_lifetime = n;
    if (s_nvs_ok) {
        s_prefs.putUInt(KEY_TRIPS, n);
    }
}

void saw_store_log_event(const char *line)
{
    if (!s_fs_ok || !line) {
        return;
    }

    File f = LittleFS.open("/events.log", "a");
    if (!f) {
        return;
    }
    /* Trip events are the records that matter most and the ones a builder will read
     * months later, so the event log rotates rather than wrapping: when it fills, the
     * current file becomes events.1.log and a fresh one starts. Worst case one full
     * generation is lost, never the newest lines. */
    if (f.size() >= SAW_LOG_EVENT_BYTES) {
        f.close();
        LittleFS.remove("/events.1.log");
        LittleFS.rename("/events.log", "/events.1.log");
        f = LittleFS.open("/events.log", "a");
        if (!f) {
            return;
        }
    }
    f.print(line);
    f.print('\n');
    f.close();
}

void saw_store_log_sample(SawSampleRecord rec)
{
    if (!s_fs_ok) {
        return;
    }

    rec.crc = saw_crc16((const uint8_t *)&rec, sizeof(rec) - sizeof(uint16_t));

    if (s_segment_records >= SEGMENT_RECORDS) {
        /* Roll into the next segment, dropping the oldest generation. */
        s_segment = (uint8_t)((s_segment + 1) % SEGMENTS);
        if (s_segment == 0) {
            s_wrapped = 1;
        }
        char path[16];
        segment_path(s_segment, path, sizeof(path));
        LittleFS.remove(path);
        s_segment_records = 0;
        meta_write(s_segment, s_wrapped);
    }

    char path[16];
    segment_path(s_segment, path, sizeof(path));
    File f = LittleFS.open(path, "a");
    if (!f) {
        return;
    }
    if (f.write((const uint8_t *)&rec, sizeof(rec)) == sizeof(rec)) {
        s_segment_records++;
    }
    f.close();
}

uint32_t saw_store_sample_count(void)
{
    if (!s_fs_ok) {
        return 0;
    }
    uint32_t total = 0;
    for (uint8_t i = 0; i < SEGMENTS; i++) {
        char path[16];
        segment_path(i, path, sizeof(path));
        File f = LittleFS.open(path, "r");
        if (f) {
            total += (uint32_t)(f.size() / sizeof(SawSampleRecord));
            f.close();
        }
    }
    return total;
}

uint32_t saw_store_stream_samples(SawSampleVisitor cb, void *ctx)
{
    if (!s_fs_ok || !cb) {
        return 0;
    }

    /* Oldest first. Once the ring has wrapped, the oldest generation is the segment just
     * after the one being written. */
    uint8_t first = s_wrapped ? (uint8_t)((s_segment + 1) % SEGMENTS) : 0;
    uint32_t emitted = 0;

    for (uint8_t n = 0; n < SEGMENTS; n++) {
        uint8_t i = (uint8_t)((first + n) % SEGMENTS);
        char path[16];
        segment_path(i, path, sizeof(path));
        File f = LittleFS.open(path, "r");
        if (!f) {
            continue;
        }
        SawSampleRecord rec;
        while (f.read((uint8_t *)&rec, sizeof(rec)) == sizeof(rec)) {
            uint16_t want = saw_crc16((const uint8_t *)&rec,
                                      sizeof(rec) - sizeof(uint16_t));
            if (want != rec.crc) {
                continue;   /* torn by a power loss mid-write; drop it silently */
            }
            cb(rec, ctx);
            emitted++;
        }
        f.close();
    }

    return emitted;
}

uint32_t saw_store_retention_hours(void)
{
    /* What the ring can hold, not what is currently in it. */
    uint32_t records = (uint32_t)SEGMENT_RECORDS * SEGMENTS;
    return (uint32_t)((uint64_t)records * SAW_LOG_PERIOD_S / 3600ULL);
}

void saw_store_usage(uint32_t *used, uint32_t *total)
{
    if (used) {
        *used = s_fs_ok ? (uint32_t)LittleFS.usedBytes() : 0;
    }
    if (total) {
        *total = s_fs_ok ? (uint32_t)LittleFS.totalBytes() : 0;
    }
}
