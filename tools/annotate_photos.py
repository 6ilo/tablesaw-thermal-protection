#!/usr/bin/env python3
"""Draw numbered callouts onto the build photos.

The annotated images are what NEXT-STEPS.md embeds, so a helper who has never
seen a contactor can be told "the thing marked 2" over a video call and point at
the right object. Callout text lives in the markdown legend, not on the image —
a number survives being viewed on a phone at arm's length; a paragraph does not.

Source photos and callout coordinates are both in this file, so regenerating is:

    python3 tools/annotate_photos.py

Coordinates are in pixels on the 1400 px-wide source images. `at` is what the
callout points at; `badge` is where the number sits, chosen to land on empty
background rather than on top of the thing being pointed at.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PHOTOS = Path(__file__).resolve().parent.parent / "hardware" / "photos"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

AMBER = (255, 200, 0)
INK = (10, 10, 10)
WHITE = (255, 255, 255)

# name: [(number, (at_x, at_y), (badge_x, badge_y)), ...]
CALLOUTS = {
    "2026-08-23-starter-enclosure": [
        (1, (820, 500), (620, 330)),
        (2, (565, 785), (330, 660)),
        (3, (1055, 545), (1245, 660)),
        (4, (662, 996), (880, 1090)),
    ],
    "2026-08-23-fob-cell-side": [
        (1, (800, 545), (640, 300)),
        (2, (905, 600), (1075, 810)),
        (3, (1195, 520), (1235, 295)),
    ],
    "2026-08-23-fob-encoder-side": [
        (1, (652, 432), (425, 185)),
        (2, (835, 462), (1010, 205)),
        (3, (862, 606), (620, 790)),
    ],
    "2026-08-23-fob-pigtail-esp32-topside": [
        (1, (990, 620), (900, 845)),
        (2, (735, 632), (470, 730)),
        (3, (900, 528), (615, 430)),
        (4, (140, 330), (300, 530)),
        (5, (1250, 288), (1140, 440)),
    ],
}

R = 40          # badge radius
DOT = 11        # radius of the dot on the target
LEAD = 7        # leader-line width


def annotate(name: str, marks) -> None:
    im = Image.open(PHOTOS / f"{name}.jpg").convert("RGB")
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype(FONT, 52)

    for _, at, badge in marks:
        # Leader drawn twice: a dark casing under a bright core, so it stays
        # visible over both the black enclosure and the pale bench.
        d.line([badge, at], fill=INK, width=LEAD + 6)
        d.line([badge, at], fill=AMBER, width=LEAD)
        d.ellipse([at[0] - DOT - 3, at[1] - DOT - 3, at[0] + DOT + 3, at[1] + DOT + 3], fill=INK)
        d.ellipse([at[0] - DOT, at[1] - DOT, at[0] + DOT, at[1] + DOT], fill=AMBER)

    for num, _, badge in marks:
        bx, by = badge
        d.ellipse([bx - R - 5, by - R - 5, bx + R + 5, by + R + 5], fill=INK)
        d.ellipse([bx - R, by - R, bx + R, by + R], fill=AMBER)
        d.text((bx, by), str(num), font=font, fill=INK, anchor="mm")

    out = PHOTOS / f"{name}-annotated.jpg"
    im.save(out, quality=86, optimize=True)
    print(f"{out.name}  {im.size[0]}x{im.size[1]}  {out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    for name, marks in CALLOUTS.items():
        annotate(name, marks)
