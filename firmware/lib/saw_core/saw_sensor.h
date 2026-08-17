/*
 * Sensor reading and the SR-5 validation rules.
 *
 * SR-5: "Open sensor, shorted sensor, out-of-range reading, stale reading, CRC /
 * communication failure — all trip. Never fall back to last known good or assume
 * ambient." Everything in here exists to turn a reading into one of three verdicts,
 * and two of those verdicts stop the saw.
 *
 * The split between SAW_VERDICT_FAULT (E02) and SAW_VERDICT_TIMEOUT (E03) matters to
 * the operator, because the two codes send them to different hardware:
 *
 *   E02  the supervisor got an answer and rejected it  -> probe, leads, terminals
 *   E03  the supervisor got no answer at all           -> SPI bus, amplifier, 3V3
 *
 * So `answered` is the discriminator, not elapsed time alone: an amplifier that keeps
 * reporting an open-circuit flag answers every cycle and stays E02 forever, while a
 * silent bus becomes E03 once SENSOR_TIMEOUT has passed with nothing valid arriving.
 */
#pragma once

#include <stdint.h>

struct SawReading {
    bool    answered;        /* the sensing chain responded at all              */
    bool    fault_open;      /* open circuit / open thermocouple                */
    bool    fault_short_gnd; /* short to ground                                 */
    bool    fault_short_vcc; /* short to VCC                                    */
    bool    raw_out_of_band; /* ADC code outside the electrically plausible band */
    float   celsius;
    float   internal_c;      /* MAX31855 cold-junction temperature, else NAN    */
    int32_t raw;             /* ADC code, or the raw 32-bit MAX31855 register   */

    SawReading()
        : answered(false), fault_open(false), fault_short_gnd(false),
          fault_short_vcc(false), raw_out_of_band(false), celsius(0.0f),
          internal_c(0.0f), raw(0) {}
};

struct SawSensorLimits {
    float    min_c;        /* below this the reading is not believable          */
    float    max_c;        /* above this the reading is not believable          */
    float    max_jump_c;   /* implausible change since the last good reading    */
    uint32_t timeout_ms;   /* no valid reading in this window -> E03            */
};

enum SawVerdict {
    SAW_VERDICT_VALID = 0,
    SAW_VERDICT_FAULT,     /* E02 */
    SAW_VERDICT_TIMEOUT,   /* E03 */
};

/*
 * `have_reference` is false only before the first good reading of a session — with no
 * reference there is nothing to measure a jump or a staleness window against.
 */
SawVerdict saw_validate(const SawReading &r, const SawSensorLimits &lim,
                        bool have_reference, float last_valid_c,
                        uint32_t now_ms, uint32_t last_valid_ms);

/* True if the reading itself is self-consistent, ignoring history. Split out so the
 * boot self-test can count good reads without needing a jump reference. */
bool saw_reading_believable(const SawReading &r, const SawSensorLimits &lim);
