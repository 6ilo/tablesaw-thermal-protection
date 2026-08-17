#include "saw_led.h"

/* A pattern is a list of (lit, duration) segments that repeats. */
struct LedSegment {
    bool     lit;
    uint16_t ms;
};

/* 50-50-50-850 ms, per BUILD-TONIGHT.md § 5. */
static const LedSegment DOUBLE_BLINK[] = {
    {true, 50}, {false, 50}, {true, 50}, {false, 850},
};

static const LedSegment TRIPLE_BLINK[] = {
    {true, 100}, {false, 150}, {true, 100}, {false, 150}, {true, 100}, {false, 1300},
};

/* ... --- ...  dot = 1 unit, dash = 3 units, 1 unit between symbols,
 * 3 units between letters, 7 units before the pattern repeats. */
#define U 150
static const LedSegment SOS[] = {
    {true, U}, {false, U}, {true, U}, {false, U}, {true, U}, {false, 3 * U},
    {true, 3 * U}, {false, U}, {true, 3 * U}, {false, U}, {true, 3 * U}, {false, 3 * U},
    {true, U}, {false, U}, {true, U}, {false, U}, {true, U}, {false, 7 * U},
};
#undef U

static bool walk(const LedSegment *segs, uint8_t count, uint32_t elapsed_ms,
                 uint32_t *period_out)
{
    uint32_t period = 0;
    for (uint8_t i = 0; i < count; i++) {
        period += segs[i].ms;
    }
    if (period_out) {
        *period_out = period;
    }
    if (period == 0) {
        return false;
    }

    uint32_t t = elapsed_ms % period;
    for (uint8_t i = 0; i < count; i++) {
        if (t < segs[i].ms) {
            return segs[i].lit;
        }
        t -= segs[i].ms;
    }
    return false;
}

#define SEG_COUNT(a) ((uint8_t)(sizeof(a) / sizeof((a)[0])))

bool saw_led_output(SawLedPattern pattern, uint32_t elapsed_ms)
{
    switch (pattern) {
    case SAW_LED_SOLID:
        return true;
    case SAW_LED_SLOW_BLINK:
        return (elapsed_ms % 1000u) < 500u;   /* 1 Hz  */
    case SAW_LED_FAST_BLINK:
        return (elapsed_ms % 200u) < 100u;    /* 5 Hz  */
    case SAW_LED_DOUBLE_BLINK:
        return walk(DOUBLE_BLINK, SEG_COUNT(DOUBLE_BLINK), elapsed_ms, 0);
    case SAW_LED_TRIPLE_BLINK:
        return walk(TRIPLE_BLINK, SEG_COUNT(TRIPLE_BLINK), elapsed_ms, 0);
    case SAW_LED_SOS:
        return walk(SOS, SEG_COUNT(SOS), elapsed_ms, 0);
    case SAW_LED_OFF:
    default:
        return false;
    }
}

uint32_t saw_led_period_ms(SawLedPattern pattern)
{
    uint32_t period = 0;
    switch (pattern) {
    case SAW_LED_SLOW_BLINK:
        return 1000u;
    case SAW_LED_FAST_BLINK:
        return 200u;
    case SAW_LED_DOUBLE_BLINK:
        walk(DOUBLE_BLINK, SEG_COUNT(DOUBLE_BLINK), 0, &period);
        return period;
    case SAW_LED_TRIPLE_BLINK:
        walk(TRIPLE_BLINK, SEG_COUNT(TRIPLE_BLINK), 0, &period);
        return period;
    case SAW_LED_SOS:
        walk(SOS, SEG_COUNT(SOS), 0, &period);
        return period;
    default:
        return 0;
    }
}

const char *saw_led_name(SawLedPattern pattern)
{
    switch (pattern) {
    case SAW_LED_SOLID:        return "Solid ON";
    case SAW_LED_SLOW_BLINK:   return "Slow blink (1 Hz)";
    case SAW_LED_FAST_BLINK:   return "Fast blink (5 Hz)";
    case SAW_LED_DOUBLE_BLINK: return "Double-blink then pause";
    case SAW_LED_TRIPLE_BLINK: return "Triple-blink then long pause";
    case SAW_LED_SOS:          return "SOS pattern";
    case SAW_LED_OFF:
    default:                   return "Off";
    }
}
