#!/usr/bin/env python3
"""Solve the NTC calibration from two known points.

Step 6 of the NTC procedure in ARCHITECTURE.md § Sensor calibration: when the ice-bath
and boiling readings are off in *opposite* directions, β does not match the datasheet's
3950 and no single offset will fix it.

Run the firmware, put the probe in each bath, and read the two `ntc_raw` values off the
serial log or off `http://saw.local/api/state`. Then:

    python3 scripts/solve_beta.py --cold-raw 3156 --hot-raw 267

Add --r-fixed with the *measured* ohms of your divider resistor. It defaults to 10000,
which is exactly the assumption the procedure tells you not to make.

No dependencies beyond the standard library, so it runs on a stock macOS Python.
"""

from __future__ import annotations

import argparse
import math
import sys

KELVIN = 273.15


def resistance(raw: float, r_fixed: float, vref: float, full_scale: float) -> float:
    """NTC resistance implied by an ADC code, for the low-side divider in WIRING.md."""
    v = raw / full_scale * vref
    headroom = vref - v
    if v <= 0 or headroom <= 0:
        raise SystemExit(
            f"ADC code {raw:g} sits at a rail, so the divider equation has no solution. "
            "That is a wiring fault (open or shorted probe), not a calibration problem."
        )
    return r_fixed * v / headroom


def celsius(r_ntc: float, r_nom: float, t_nom: float, beta: float) -> float:
    inv_t = 1.0 / (t_nom + KELVIN) + (1.0 / beta) * math.log(r_ntc / r_nom)
    return 1.0 / inv_t - KELVIN


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--cold-raw", type=float, required=True,
                   help="oversampled ADC code in the ice bath")
    p.add_argument("--hot-raw", type=float, required=True,
                   help="oversampled ADC code in boiling water")
    p.add_argument("--cold-c", type=float, default=0.0,
                   help="actual ice-bath temperature (default 0)")
    p.add_argument("--hot-c", type=float, default=100.0,
                   help="actual boiling point at your elevation "
                        "(default 100; subtract about 1 C per 300 m)")
    p.add_argument("--r-fixed", type=float, default=10000.0,
                   help="MEASURED divider resistance in ohms (default 10000)")
    p.add_argument("--r-nominal", type=float, default=10000.0,
                   help="NTC resistance at 25 C (default 10000)")
    p.add_argument("--vref", type=float, default=3.3)
    p.add_argument("--full-scale", type=float, default=4095.0)
    args = p.parse_args()

    if args.r_fixed == 10000.0:
        print("note: --r-fixed is at its 10000 default. Step 1 of the procedure is to "
              "measure it; a 5% part can read 9500-10500.\n", file=sys.stderr)

    r_cold = resistance(args.cold_raw, args.r_fixed, args.vref, args.full_scale)
    r_hot = resistance(args.hot_raw, args.r_fixed, args.vref, args.full_scale)

    if r_hot >= r_cold:
        raise SystemExit(
            f"resistance rose with temperature ({r_cold:.0f} -> {r_hot:.0f} ohm).\n"
            "An NTC falls. Either the two readings are swapped, or the divider is wired "
            "with the thermistor on the high side instead of the low side. Check WIRING.md "
            "before touching any coefficient."
        )

    t_hot_k = args.hot_c + KELVIN
    t_cold_k = args.cold_c + KELVIN
    beta = math.log(r_hot / r_cold) / (1.0 / t_hot_k - 1.0 / t_cold_k)

    # Where the datasheet curve would have put those two points.
    err_cold = celsius(r_cold, args.r_nominal, 25.0, 3950.0) - args.cold_c
    err_hot = celsius(r_hot, args.r_nominal, 25.0, 3950.0) - args.hot_c

    print(f"measured resistance   cold {r_cold:9.1f} ohm      hot {r_hot:9.1f} ohm")
    print(f"error at beta 3950    cold {err_cold:+9.2f} C        hot {err_hot:+9.2f} C")
    print(f"solved beta           {beta:.1f}")
    print()

    same_sign = (err_cold >= 0) == (err_hot >= 0)
    both_small = abs(err_cold) <= 2.0 and abs(err_hot) <= 2.0

    if both_small:
        print("Both points are within +/-2 C on the datasheet curve. Use it as-is:")
        print("  nothing to change except SAW_NTC_R_FIXED_OHMS, which should already hold")
        print(f"  your measured {args.r_fixed:.0f} ohm.")
    elif same_sign:
        offset = -(err_cold + err_hot) / 2.0
        print("Both points are off in the SAME direction, which is sensor tolerance "
              "rather than a wrong curve. Apply an offset:")
        print(f"  #define SAW_NTC_OFFSET_C   {offset:+.2f}f")
    else:
        print("The points are off in OPPOSITE directions, so beta is wrong. In "
              "include/saw_calibration.h:")
        print(f"  #define SAW_NTC_BETA           {beta:.1f}f")
        print(f"  #define SAW_NTC_R_FIXED_OHMS   {args.r_fixed:.1f}f")
        print()
        print("Then re-verify: the ice bath should read 0.0 +/- 0.5 C, and body heat on "
              "the tip should read 30-35 C.")

    print()
    print("Finally set SAW_CALIBRATED to 1 so the boot log stops reporting "
          "UNCALIBRATED_BUILD.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
