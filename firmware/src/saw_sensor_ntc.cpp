/*
 * DROK 10K NTC / B3950 on the motor frame, read through the ESP32's ADC1.
 *
 * On Path A this is the trip source. On Path B it is demoted to advisory frame
 * monitoring, and the delta between frame and winding is the airflow-restriction signal
 * the whole project exists to detect.
 *
 * Divider and mounting: hardware/schematic/WIRING.md. Calibration:
 * ARCHITECTURE.md § Sensor calibration.
 */
#include <Arduino.h>
#include <math.h>

#include "saw_calibration.h"
#include "saw_config.h"
#include "saw_hw.h"
#include "saw_ntc.h"

static const SawNtcParams NTC_PARAMS = {
    SAW_NTC_R_FIXED_OHMS,
    SAW_NTC_R_NOMINAL_OHMS,
    SAW_NTC_T_NOMINAL_C,
    SAW_NTC_BETA,
    SAW_NTC_VREF_V,
    SAW_NTC_ADC_FULL_SCALE,
    SAW_NTC_OFFSET_C,
};

static int32_t s_last_raw = -1;
static float   s_last_r = -1.0f;

static bool ntc_begin(void)
{
    analogReadResolution(12);
    /* 11 dB attenuation covers the full divider swing: about 3.01 V at −20 °C down to
     * 65 mV at 150 °C. */
    analogSetPinAttenuation(SAW_PIN_NTC, ADC_11db);
    return true;
}

/*
 * Oversample to beat down the ESP32 ADC's noise. The nonlinearity that remains is
 * absorbed by the two-point calibration, which is why that step is mandatory rather
 * than optional.
 */
static int32_t ntc_read_raw(void)
{
    uint32_t sum = 0;
    for (int i = 0; i < SAW_NTC_OVERSAMPLE; i++) {
        sum += (uint32_t)analogRead(SAW_PIN_NTC);
    }
    return (int32_t)(sum / (uint32_t)SAW_NTC_OVERSAMPLE);
}

static SawReading ntc_read(void)
{
    SawReading r;
    int32_t raw = ntc_read_raw();
    s_last_raw = raw;

    r.answered = true;   /* the ADC always answers; the question is whether we believe it */
    r.raw = raw;
    r.internal_c = NAN;

    /* Electrical checks, kept separate from the temperature range check. Below the low
     * bound the probe looks shorted to GND; above the high bound it looks open. A
     * genuinely hot motor is caught by the range check instead, so a real overtemperature
     * is never mistaken for a short. */
    if (raw < SAW_NTC_RAW_MIN) {
        r.raw_out_of_band = true;
        r.fault_short_gnd = true;
    } else if (raw > SAW_NTC_RAW_MAX) {
        r.raw_out_of_band = true;
        r.fault_open = true;
    }

    s_last_r = saw_ntc_resistance((float)raw, NTC_PARAMS);
    r.celsius = saw_ntc_celsius((float)raw, NTC_PARAMS);
    return r;
}

int32_t saw_ntc_last_raw(void)
{
    return s_last_raw;
}

float saw_ntc_last_resistance(void)
{
    return s_last_r;
}

/* --------------------------------------------------------------------------- */
/* Role wiring                                                                 */
/* --------------------------------------------------------------------------- */

#if SAW_PRIMARY_IS_NTC

bool saw_primary_begin(void)
{
    return ntc_begin();
}

SawReading saw_primary_read(void)
{
    return ntc_read();
}

const char *saw_primary_name(void)
{
    return "DROK 10K NTC B3950 on motor frame (ADC1)";
}

bool saw_frame_available(void)
{
    /* The frame NTC is the primary on this path. Reporting it twice would invent a
     * winding-versus-frame delta out of one sensor. */
    return false;
}

float saw_frame_celsius(void)
{
    return NAN;
}

#elif SAW_HAS_FRAME_NTC

/* Path B: advisory only, never a trip source. */
static bool s_frame_ready = false;

bool saw_frame_available(void)
{
    if (!s_frame_ready) {
        s_frame_ready = ntc_begin();
    }
    return s_frame_ready;
}

float saw_frame_celsius(void)
{
    if (!saw_frame_available()) {
        return NAN;
    }
    SawReading r = ntc_read();
    if (r.raw_out_of_band) {
        return NAN;
    }
    return r.celsius;
}

#endif
