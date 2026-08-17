/*
 * GENERATED FILE — do not edit.
 *
 * Source:      docs/codes -- one markdown file per code
 * Generator:   tools/codedocs.py
 * Registry:    1.0.0
 *
 * The operator documentation is the source of truth for this table. If you need to
 * change a code's title, summary or severity, edit the markdown and rebuild. Editing
 * this header puts the device out of step with the docs the operator is reading,
 * which is the specific failure this pipeline exists to prevent.
 */

#pragma once

#define SAW_REGISTRY_VERSION "1.0.0"
#define SAW_CODE_COUNT 11

typedef enum {
    SAW_SEV_INFO    = 0,  /* feedback about an operator action, not a fault */
    SAW_SEV_WARNING = 1,  /* advisory; saw keeps running, LED unchanged     */
    SAW_SEV_TRIP    = 2,  /* relay opened, recovers automatically           */
    SAW_SEV_LOCKOUT = 3,  /* relay opened, requires a physical ack press    */
} saw_severity_t;

typedef enum {
    SAW_CODE_E01 = 0,
    SAW_CODE_E02 = 1,
    SAW_CODE_E03 = 2,
    SAW_CODE_E04 = 3,
    SAW_CODE_E05 = 4,
    SAW_CODE_E06 = 5,
    SAW_CODE_E07 = 6,
    SAW_CODE_E08 = 7,
    SAW_CODE_W01 = 8,
    SAW_CODE_W02 = 9,
    SAW_CODE_W03 = 10,
} saw_code_id_t;

typedef struct {
    const char     *code;      /* "E01"                                   */
    const char     *event;     /* firmware log event, e.g. "OVERTEMP"     */
    const char     *title;     /* short operator-facing name              */
    const char     *summary;   /* one line for the status card            */
    const char     *doc_path;  /* page in the on-device bundle            */
    saw_severity_t  severity;
    unsigned char   loto;      /* 1 if remediation needs a lockout         */
} saw_code_t;

static const saw_code_t SAW_CODES[SAW_CODE_COUNT] = {
    { "E01", "OVERTEMP", "Motor overtemperature", "The winding reached 110 °C. The supervisor opened the coil circuit and the saw stopped.",
      "/codes/E01.html", SAW_SEV_TRIP, 1 },
    { "E02", "SENSOR_FAULT", "Sensor fault", "The supervisor read a thermocouple value it does not trust and opened the coil circuit rather than guess at the winding temperature.",
      "/codes/E02.html", SAW_SEV_TRIP, 1 },
    { "E03", "SENSOR_TIMEOUT", "Sensor timeout", "No valid thermocouple reading arrived within SENSOR_TIMEOUT (3 s). The supervisor opened the coil circuit rather than run blind.",
      "/codes/E03.html", SAW_SEV_TRIP, 1 },
    { "E04", "MANUAL_LOCKOUT_ENTERED", "Manual lockout after repeated trips", "Three trips inside ten minutes. The supervisor stopped auto-recovering and stays stopped until someone presses the ack button with the motor cool.",
      "/codes/E04.html", SAW_SEV_LOCKOUT, 0 },
    { "E05", "BOOT_SENSOR_FAIL", "Boot self-test failed", "The boot self-test could not get 8 good thermocouple readings out of 10, so the supervisor refused to arm and the saw cannot start.",
      "/codes/E05.html", SAW_SEV_TRIP, 1 },
    { "E06", "BOOT_HOT_HOLD", "Trip held through a power cycle", "The supervisor rebooted, found its last state was a trip and the winding still at or above 70 °C, and stayed tripped.",
      "/codes/E06.html", SAW_SEV_TRIP, 1 },
    { "E07", "BOOT_INTO_LOCKOUT", "Booted back into lockout", "The supervisor rebooted, found a saved manual lockout in flash, and went straight back into lockout. Power-cycling does not clear a lockout.",
      "/codes/E07.html", SAW_SEV_LOCKOUT, 0 },
    { "E08", "ACK_REJECTED_HOT", "Ack pressed too early", "The ack button was pressed while the winding was still at or above 70 °C, so the press was ignored and logged. Nothing is broken.",
      "/codes/E08.html", SAW_SEV_INFO, 0 },
    { "W01", "APPROACHING_TRIP", "Approaching trip temperature", "The winding passed 95 °C. The saw is still running, and you have 15 °C of headroom before the supervisor trips it.",
      "/codes/W01.html", SAW_SEV_WARNING, 1 },
    { "W02", "HEATING_FASTER_THAN_BASELINE", "Heating faster than baseline", "The winding is heating more than 1.5x faster than the commissioning baseline. The saw is still running. Airflow is most likely degrading.",
      "/codes/W02.html", SAW_SEV_WARNING, 1 },
    { "W03", "PROBE_UNVERIFIED_AT_ARMED_TIME", "Probe never warmed up", "The supervisor has been armed 30 minutes without ever seeing the winding warm up. Usually nobody has cut anything yet. Make one real cut.",
      "/codes/W03.html", SAW_SEV_WARNING, 0 },
};

/* Map a firmware log event name to its registry entry. Returns NULL if the event has
 * no published code — which is itself worth logging, since every operator-visible
 * event is supposed to have one. */
static inline const saw_code_t *saw_code_by_event(const char *event)
{
    if (!event) {
        return (const saw_code_t *)0;
    }
    for (int i = 0; i < SAW_CODE_COUNT; i++) {
        const char *a = SAW_CODES[i].event;
        const char *b = event;
        while (*a && *a == *b) { a++; b++; }
        if (*a == '\0' && *b == '\0') {
            return &SAW_CODES[i];
        }
    }
    return (const saw_code_t *)0;
}
