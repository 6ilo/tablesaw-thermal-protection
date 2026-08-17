# Wiring table — ESP32 supervisor (Path B target)

> **Most of the parts in this table have not been purchased.** The
> MAX31855 (TASK-1), the opto-isolated relay module (TASK-3), the
> Mean Well PSU (TASK-2) and the bimetallic thermostat (TASK-6) are
> all still to be sourced. This table describes the end-state design.
>
> **To wire the build that can be made from parts on hand, use
> [`WIRING-PATH-A.md`](WIRING-PATH-A.md).** Do not mix rows between
> the two tables — the sensor, the power path, and the coil-circuit
> interface are all different parts.

The pin-level, build-without-translating-a-schematic reference. If you
are wiring the board and only want to look at one thing, look at this
table. The schematic (`esp32_supervisor.svg`) and pictorial
(`esp32_pictorial.svg`) are cross-checks.

All ESP32 pin numbers refer to the printed silkscreen on the purchased
**ESP32-DevKitC-32E** (`B0GF1ZJCCN`) — the **38-pin USB-C** variant
carrying an ESP32-WROOM-32E with 8 MB of flash. Every GPIO used below
is also present on the 30-pin DOIT-style boards, so the assignments
port unchanged if you substitute one.

## ESP32 power

| ESP32 pin | Goes to | Wire colour | Notes |
|---|---|---|---|
| `VIN` | Isolated PSU **+5V** | red | PSU is Mean Well IRM-05-5 or equivalent. 5 V SELV. Do **not** feed 3V3 to VIN. |
| `GND` (right, near VIN) | PSU **return** | black | Common bus with everything else's GND. |
| `GND` (left, mid-column) | Same common GND bus | black | Tie both ESP32 GND pins together, do not run separate returns. |
| `3V3` | MAX31855 `VCC` and NTC divider top | orange | Regulated on the DevKitC — do not connect an external 3V3 supply here. |

## MAX31855 K-type thermocouple breakout

| MAX31855 pin | Goes to | Wire colour | Notes |
|---|---|---|---|
| `VCC` | ESP32 `3V3` | orange | Do not use 5 V — MAX31855 is 3.3 V only. |
| `GND` | Common GND bus | black | |
| `SCK` | ESP32 `GPIO18` | yellow | SPI clock. GPIO18/19/23/5 is the **VSPI** (SPI3) default pin group — not HSPI, which is GPIO14/12/13/15. |
| `SO` (a.k.a. MISO / DO) | ESP32 `GPIO19` | green | SPI data out from MAX31855. |
| `CS` | ESP32 `GPIO5` | blue | Chip select. Active-LOW; firmware drives this. |
| `T+` (yellow) | Motor pigtail: **yellow** K-type wire | yellow (K-type) | See `../harness/motor_pigtail.yml`. Do not swap polarity — K-type is polarised. |
| `T−` (red) | Motor pigtail: **red** K-type wire | red (K-type) | The red lead is the negative on K-type — this is not a typo. |

## NTC frame-temperature divider (advisory secondary sensor)

Divider topology: `3V3 → 10 kΩ 1% (pullup) → GPIO34 → NTC 10 kΩ B3950 → GND`

| Node | Goes to | Wire colour | Notes |
|---|---|---|---|
| Top of 10 kΩ pullup | ESP32 `3V3` | orange | |
| Junction (pullup / NTC) | ESP32 `GPIO34` | purple | GPIO34 is ADC1_CH6 — **input only**, and ADC1 stays usable when Wi-Fi is active. Do **not** move this to an ADC2 pin. |
| Bottom of NTC | Common GND bus | black | |
| NTC body | Motor frame, thermal grease under stainless housing | — | DROK `B0F8NQ9S4R` — 10 kΩ / B3950 1%, −25 to +125 °C, 5 × 25 mm stainless, 1 m PVC, JST XH 2.54. Supplied as a 3-pack, so this is the one purchased part both build paths share. Advisory only here — the winding K-type is the trip authority in Path B. |

## Relay module (opto-isolated, active-HIGH, NO output)

| Relay pin | Goes to | Wire colour | Notes |
|---|---|---|---|
| `VCC` | +5 V bus (same as ESP32 VIN) | red | Not 3.3 V — cheap opto-relay modules are 5 V. |
| `GND` | Common GND bus | black | |
| `IN` | ESP32 `GPIO26` **and** 10 kΩ pulldown to GND | brown | The pulldown is non-optional. Floating GPIO26 during boot / crash / brown-out must leave the relay OPEN. |
| `COM` | Passive thermostat NC lead (mains side) | 14 AWG mains-rated | Mains potential — see the DANGER block in `../../ARCHITECTURE.md`. |
| `NO` | M1 contactor coil terminal `A1` | 14 AWG mains-rated | The relay is in series with the thermostat; either open drops the coil. |
| `NC` | *not connected* | — | Leave open. NC is unused in a fail-safe topology. |

## Ack button

| Wire | Goes to | Wire colour | Notes |
|---|---|---|---|
| Button pole 1 | ESP32 `GPIO27` | grey | Firmware enables the internal pullup — external pullup not required. |
| Button pole 2 | Common GND bus | black | Momentary, normally-open. |

## Onboard status LED

| ESP32 pin | Behaviour | Notes |
|---|---|---|
| `GPIO2` | Onboard blue LED on the DevKitC-32E | No external wire needed. See ARCHITECTURE.md for the LED-pattern-per-state table. |

## Motor pigtail — cable that leaves the motor

See `../harness/motor_pigtail.yml` for the full cable. Landing points:

| Motor-side termination | Terminal-block landing (inside ESP32 enclosure) | Notes |
|---|---|---|
| K-type at winding, yellow (+) | MAX31855 `T+` | AlN substrate at the sensor tip for isolation from mains potential. |
| K-type at winding, red (−) | MAX31855 `T−` | |
| Thermostat lead 1 (black, fiberglass) | Relay `COM` (jumper on terminal block) | Bimetallic snap-action, NC, opens ~110 °C. See ARCHITECTURE.md § BOM. |
| Thermostat lead 2 (black, fiberglass) | M1 contactor coil `A1` (via relay `NO` — the coil-circuit chain) | The thermostat is upstream of the relay in the coil circuit — see `ladder_coil_circuit.svg`. |

## Mains-side coil-circuit landings

Not on the low-voltage sheet. Full chain in `ladder_coil_circuit.svg`:

```
L1 → STOP → [START ∥ M1 aux] → TSTAT (NC) → KA (ESP32 relay, NO) → OL → M1 coil → L2
```

Where `KA` is the relay `COM/NO` pair from this table. See
`../harness/mains_and_coil.yml` for the physical harness inside the
starter enclosure.

## Sanity checklist before first power-up

1. **Both ESP32 GND pins are jumpered together.** Test with a
   multimeter (continuity) with the module unpowered.
2. **10 kΩ pulldown between relay `IN` and GND.** Measure
   resistance across relay IN and GND: should be ~10 kΩ.
   Without this, GPIO26 float on boot could momentarily energise the
   coil.
3. **MAX31855 VCC reads 3.3 V**, not 5 V, when the ESP32 is powered.
   A 5 V feed to VCC destroys the part.
4. **K-type polarity.** Yellow is +, red is −. Reversing this reads
   as a large negative temperature and the firmware will trip
   immediately — annoying but safe.
5. **NTC is on GPIO34, not on a GPIO0/2/4/12–15/25–27 (ADC2) pin.**
   ADC2 conflicts with Wi-Fi and will read zeros.
6. **Thermostat is wired IN SERIES with the ESP32 relay on the coil
   circuit** — not in parallel, not on the low-voltage side. See
   the ladder diagram.
7. **PSU output is SELV, isolated from mains input.** Do not
   substitute a non-isolated buck converter.
