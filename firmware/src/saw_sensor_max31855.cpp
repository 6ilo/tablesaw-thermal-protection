/*
 * MAX31855 K-type thermocouple amplifier — Path B trip source.
 *
 * Read-only device: CS low, then clock out 32 bits. No MOSI, so SPI.begin() is given
 * −1 for it.
 *
 *   D31..D18  thermocouple temperature, 14-bit signed, 0.25 °C/LSB
 *   D17       reserved, reads 0
 *   D16       fault
 *   D15..D4   cold-junction temperature, 12-bit signed, 0.0625 °C/LSB
 *   D3        reserved, reads 0
 *   D2        SCV — short to VCC
 *   D1        SCG — short to GND
 *   D0        OC  — open circuit
 *
 * The part has no CRC, so the reserved bits and the all-ones / all-zeros checks below are
 * what stands in for the "CRC / communication failure" half of SR-5. Direct SPI rather
 * than a library, because the fault bits are the whole point of choosing this amplifier
 * and wrappers routinely collapse all three into one boolean.
 */
#include "saw_config.h"

#if SAW_HAS_MAX31855

#include <Arduino.h>
#include <SPI.h>

#include "saw_calibration.h"
#include "saw_hw.h"

static bool s_ready = false;

bool saw_primary_begin(void)
{
    pinMode(SAW_PIN_TC_CS, OUTPUT);
    digitalWrite(SAW_PIN_TC_CS, HIGH);
    /* The global SPI object rather than a fresh SPIClass(VSPI): nothing else in this
     * firmware uses the bus, and the VSPI/HSPI enum names were reshuffled between
     * Arduino-ESP32 2.x and 3.x. MOSI and SS are -1 because the MAX31855 is read-only and
     * chip select is driven by hand. */
    SPI.begin(SAW_PIN_TC_SCK, SAW_PIN_TC_DO, -1, -1);
    s_ready = true;
    /* First conversion after power-up takes about 100 ms. The boot self-test's ten reads
     * at SAW_SELFTEST_GAP_MS apart cover that comfortably. */
    delay(100);
    return true;
}

static uint32_t read_register(void)
{
    uint32_t v = 0;
    SPI.beginTransaction(SPISettings(4000000, MSBFIRST, SPI_MODE0));
    digitalWrite(SAW_PIN_TC_CS, LOW);
    delayMicroseconds(2);
    for (int i = 0; i < 4; i++) {
        v = (v << 8) | (uint32_t)SPI.transfer(0x00);
    }
    digitalWrite(SAW_PIN_TC_CS, HIGH);
    SPI.endTransaction();
    return v;
}

SawReading saw_primary_read(void)
{
    SawReading r;

    if (!s_ready) {
        r.answered = false;
        return r;
    }

    uint32_t v = read_register();
    r.raw = (int32_t)v;

    /*
     * A silent or absent bus. 0xFFFFFFFF is unambiguous — the reserved bits cannot read
     * 1. 0x00000000 would decode as "0.00 °C thermocouple, 0.00 °C cold junction, no
     * faults", which is legal but only occurs if the cold junction is at exactly 0 °C to
     * the LSB. Treating it as no-answer costs a nuisance stop in a literal ice bath and
     * catches an unpowered amplifier or a MISO stuck low, which would otherwise read as
     * a comfortable 0 °C winding forever.
     */
    if (v == 0xFFFFFFFFu || v == 0x00000000u) {
        r.answered = false;
        return r;
    }

    /* Reserved bits must read 0. If they do not, the bus is not framing correctly and
     * nothing decoded out of it can be trusted. */
    if ((v & ((1u << 17) | (1u << 3))) != 0) {
        r.answered = false;
        return r;
    }

    r.answered = true;
    r.fault_short_vcc = (v & (1u << 2)) != 0;
    r.fault_short_gnd = (v & (1u << 1)) != 0;
    r.fault_open      = (v & (1u << 0)) != 0;

    /* Cold-junction temperature: 12-bit signed, 0.0625 °C/LSB. */
    int16_t internal = (int16_t)((v >> 4) & 0x0FFF);
    if (internal & 0x0800) {
        internal |= (int16_t)0xF000;   /* sign extend */
    }
    r.internal_c = (float)internal * 0.0625f;

    /* Thermocouple temperature: 14-bit signed, 0.25 °C/LSB. */
    int16_t tc = (int16_t)((v >> 18) & 0x3FFF);
    if (tc & 0x2000) {
        tc |= (int16_t)0xC000;         /* sign extend */
    }
    r.celsius = (float)tc * 0.25f + SAW_TC_OFFSET_C;

    /* D16 is the OR of the three fault bits. If it is set and none of them is, the part
     * is reporting a fault it will not name — still a fault. */
    if ((v & (1u << 16)) != 0 && !r.fault_open && !r.fault_short_gnd &&
        !r.fault_short_vcc) {
        r.fault_open = true;
    }

    return r;
}

const char *saw_primary_name(void)
{
    return "K-type via MAX31855 on winding end turns (SPI)";
}

#endif /* SAW_HAS_MAX31855 */
