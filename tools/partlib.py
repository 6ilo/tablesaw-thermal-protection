"""
The part library: everything tools/cirkit.py can place on a sheet.

Three sources, ONE interface. A `Part` exposes a size, a way to draw itself at an
offset, and named pins with local coordinates — which is Wokwi's `pinInfo` shape,
adopted deliberately so the router cannot tell an imported part from a local one.

  1. IMPORTED   hardware/parts/wokwi/*.svg + index.json — real art, MIT, extracted
                by tools/ingest_wokwi.mjs. Six discrete parts.
  2. LOCAL      hardware/parts/local/*.json — the project-specific parts nobody
                ships: the fob, the receiver, the contactor, the optocoupler.
                Declarative primitives, rendered here.
  3. PROCEDURAL the ESP32 DevKitC-32E board, built from the pin database so its
                labels cannot disagree with the firmware or with Espressif.

WHY THE BOARD IS OURS AND NOT WOKWI'S

Wokwi ship a DevKit **v1**: 30 pins, Arduino-style D13/D25 naming. This project
uses a DevKitC-32E — 38 pins — and the firmware speaks GPIO numbers. Relabelling
someone else's board art into a board we do not own is how a drawing starts lying.

A NOTE ON THE HEADER ORDER, WHICH IS THE ONE UNSOURCED FACT HERE

Espressif publish per-GPIO capability as machine-readable headers, but they do NOT
publish the DevKitC's physical header order anywhere machine-readable — esp-idf is
chip-level, and a search of esp-dev-kits turns up nothing. So HEADER_LEFT/RIGHT below
are transcribed from the DevKitC-32E pin layout by hand, and are the only thing in
this file that is not derived from a source. They are laid out as data, not buried in
drawing code, precisely so they can be checked against a board and corrected. Sheets
that use them say so in their footer.
"""

import json
import re
from pathlib import Path

from svgcanvas import Canvas, tw

REPO = Path(__file__).resolve().parent.parent
WOKWI_DIR = REPO / "hardware" / "parts" / "wokwi"
LOCAL_DIR = REPO / "hardware" / "parts" / "local"
PIN_DB = REPO / "hardware" / "parts" / "esp32_pins.json"

INK = "#16181D"
MUTE = "#6E7178"
RULE = "#C7CAD1"

# --------------------------------------------------------------------------- #
# ESP32-DevKitC-32E physical header order, outside in, top to bottom.
# UNSOURCED — see the module docstring. Entries are the silkscreen labels.
# --------------------------------------------------------------------------- #
HEADER_LEFT = ["3V3", "EN", "VP", "VN", "GPIO34", "GPIO35", "GPIO32", "GPIO33",
               "GPIO25", "GPIO26", "GPIO27", "GPIO14", "GPIO12", "GND", "GPIO13",
               "SD2", "SD3", "CMD", "5V"]
HEADER_RIGHT = ["GND", "GPIO23", "GPIO22", "TX0", "RX0", "GPIO21", "GND", "GPIO19",
                "GPIO18", "GPIO5", "GPIO17", "GPIO16", "GPIO4", "GPIO0", "GPIO2",
                "GPIO15", "SD1", "SD0", "CLK"]


def pin_db():
    if not PIN_DB.exists():
        return {}
    return {int(k): v for k, v in json.loads(PIN_DB.read_text())["pins"].items()}


class Part:
    """A placeable thing. Local coordinates, origin top-left."""

    def __init__(self, pid, title, w, h, pins, subtitle=None, ghost=False):
        self.id = pid
        self.title = title
        self.subtitle = subtitle
        self.w = w
        self.h = h
        self.pins = {p["name"]: p for p in pins}
        self.ghost = ghost

    def pin_at(self, name, ox, oy):
        p = self.pins.get(name)
        if p is None:
            raise KeyError(name)
        return ox + p["x"], oy + p["y"]

    def draw(self, c, ox, oy):
        raise NotImplementedError


class ImportedPart(Part):
    """Wokwi art: a rendered SVG fragment, placed by translate.

    UNITS. Wokwi's pinInfo coordinates are CSS pixels at 96 dpi, matching the
    element's physical size — a 15.645 mm resistor is 59.1 px wide and its far pin
    sits at x=58.8. The viewBox is NOT that space (the resistor's is 0 0 15.645 3),
    so nesting the svg and letting the viewBox govern renders the part at whatever
    size the viewport implies, which is how the first attempt produced a pushbutton
    the size of the board. Set the nested svg to the mm->px box and the viewBox maps
    into it, putting the art and the pin coordinates in the same space.
    """

    PX_PER_MM = 96.0 / 25.4

    @classmethod
    def _px(cls, v, fallback):
        if v is None:
            return fallback
        v = str(v).strip()
        m = re.match(r"^([\d.]+)\s*mm$", v)
        if m:
            return float(m.group(1)) * cls.PX_PER_MM
        m = re.match(r"^([\d.]+)(px)?$", v)
        return float(m.group(1)) if m else fallback

    def __init__(self, pid, meta, svg):
        vb = [float(v) for v in (meta.get("viewBox") or "0 0 100 100").split()]
        w = self._px(meta.get("width"), vb[2])
        h = self._px(meta.get("height"), vb[3])
        super().__init__(pid, pid.replace("wokwi-", ""), w, h, meta["pins"])
        self.svg = svg
        self.viewBox = meta.get("viewBox") or f"0 0 {w} {h}"
        self.use = meta.get("use", "")

    def draw(self, c, ox, oy):
        inner = self.svg
        # Re-declare the box in px; whatever width/height the element shipped with
        # (mm, or nothing) must not survive into the nested element.
        inner = re.sub(r'^<svg\b', "<svg", inner, count=1)
        for attr in ("width", "height"):
            inner = re.sub(rf'\s{attr}="[^"]*"', "", inner, count=1)
        inner = inner.replace(
            "<svg", f'<svg width="{self.w:.2f}" height="{self.h:.2f}"', 1)
        with c.group(f"translate({ox:.2f},{oy:.2f})"):
            c.raw(inner)


class LocalPart(Part):
    """Declarative primitives drawn here — see hardware/parts/local/README.md."""

    def __init__(self, d):
        super().__init__(d["id"], d.get("title", d["id"]), d["w"], d["h"], d["pins"],
                         subtitle=d.get("subtitle"), ghost=d.get("ghost", False))
        self.shapes = d.get("shapes", [])

    def draw(self, c, ox, oy):
        with c.group(f"translate({ox:.2f},{oy:.2f})",
                     opacity=0.45 if self.ghost else None):
            for s in self.shapes:
                t = s.get("t")
                if t == "rect":
                    c.rect(s["x"], s["y"], s["w"], s["h"], s.get("fill", "none"),
                           s.get("rx", 0), s.get("stroke", "none"), s.get("sw", 1))
                elif t == "circle":
                    c.circle(s["cx"], s["cy"], s["r"], s.get("fill", "none"),
                             s.get("stroke", "none"), s.get("sw", 1))
                elif t == "line":
                    c.line(s["x1"], s["y1"], s["x2"], s["y2"],
                           s.get("stroke", INK), s.get("sw", 1.5), s.get("dash"))
                elif t == "path":
                    c.path(s["d"], s.get("stroke", INK), s.get("sw", 1.5),
                           s.get("fill", "none"), s.get("dash"))
                elif t == "text":
                    c.text(s["x"], s["y"], s["s"], s.get("size", 10),
                           s.get("fill", INK), s.get("anchor", "start"),
                           s.get("weight", "400"), s.get("mono", False))
                else:
                    raise SystemExit(f"partlib: {self.id}: unknown shape type {t!r}")


class Esp32DevKitC(Part):
    """The 38-pin board, drawn from the pin database rather than from memory.

    Every silkscreen label comes from HEADER_LEFT/RIGHT; every function tag beside
    it comes from Espressif. The two are joined here, not typed together anywhere.
    """

    ROW = 15.5
    PAD = 26

    def __init__(self, show_tags=True, used=None):
        self.caps = pin_db()
        self.show_tags = show_tags
        self.used = set(used or [])
        rows = max(len(HEADER_LEFT), len(HEADER_RIGHT))
        w = 168
        h = self.PAD * 2 + rows * self.ROW
        pins = []
        for side, names in (("L", HEADER_LEFT), ("R", HEADER_RIGHT)):
            for i, nm in enumerate(names):
                y = self.PAD + i * self.ROW + self.ROW / 2
                x = 0 if side == "L" else w
                # Duplicate labels (GND appears three times) get a suffix so the
                # netlist can address a specific one, but the silkscreen stays clean.
                key = nm if nm not in [p["name"] for p in pins] else f"{nm}.{side}{i}"
                pins.append({"name": key, "x": x, "y": y, "signals": [],
                             "description": nm, "silk": nm, "side": side})
        super().__init__("esp32-devkitc-38", "ESP32-DevKitC-32E", w, h, pins,
                         subtitle="38-pin · USB-C")

    def draw(self, c, ox, oy):
        w, h = self.w, self.h
        c.rect(ox, oy, w, h, "#1B1E22", r=7)
        # shield can + antenna, so orientation reads without a caption
        c.rect(ox + 26, oy + 8, w - 52, 42, "#3A3F45", r=3)
        c.text(ox + w / 2, oy + 33, "WROOM-32E", 9, "#AAB0B6", anchor="middle", mono=True)
        c.path(f"M{ox+w/2-20} {oy+62} l7 -9 l7 9 l7 -9 l7 9", "#5A6067", 2)
        c.text(ox + w / 2, oy + h - 12, "DevKitC-32E", 9.5, "#8A9096",
               anchor="middle", mono=True)
        c.rect(ox + w / 2 - 17, oy + h - 5, 34, 11, "#8A9096", r=2)

        for p in self.pins.values():
            x, y = ox + p["x"], oy + p["y"]
            silk = p["silk"]
            gpio = int(silk[4:]) if silk.startswith("GPIO") and silk[4:].isdigit() else None
            hot = silk in self.used or p["name"] in self.used
            # header pad
            c.rect(x - 5 if p["side"] == "L" else x - 5, y - 4.5, 10, 9,
                   "#C9A227" if hot else "#6E7178", r=1.5)
            inner = ox + 12 if p["side"] == "L" else ox + w - 12
            c.text(inner, y + 3.2, silk, 8.2,
                   "#FFFFFF" if hot else "#9BA2A8",
                   anchor="start" if p["side"] == "L" else "end",
                   mono=True, weight="700" if hot else "400")
            if self.show_tags and gpio is not None:
                cap = self.caps.get(gpio, {})
                warn = [t for t in cap.get("tags", [])
                        if t in ("INPUT ONLY", "STRAPPING", "FLASH")]
                if warn:
                    mark = "!" if "STRAPPING" in warn or "FLASH" in warn else "<"
                    mx = ox + w - 5 if p["side"] == "L" else ox + 5
                    c.text(mx, y + 3.2, mark, 8, "#E0B23C", anchor="middle",
                           mono=True, weight="700")


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #

def load_all(used=None):
    parts = {}

    idx = WOKWI_DIR / "index.json"
    if idx.exists():
        d = json.loads(idx.read_text())
        for name, meta in d["parts"].items():
            svg = (WOKWI_DIR / meta["svg"]).read_text()
            parts[name] = ImportedPart(name, meta, svg)

    if LOCAL_DIR.exists():
        for f in sorted(LOCAL_DIR.glob("*.json")):
            d = json.loads(f.read_text())
            for one in (d["parts"] if "parts" in d else [d]):
                parts[one["id"]] = LocalPart(one)

    board = Esp32DevKitC(used=used)
    parts[board.id] = board
    return parts


def describe():
    """`cirkit.py parts` — the vocabulary, so a spec can be written without
    reading source. This is the bit that makes the format usable by someone,
    or something, that has not memorised the library."""
    out = []
    for pid, p in sorted(load_all().items()):
        origin = ("wokwi" if isinstance(p, ImportedPart)
                  else "board" if isinstance(p, Esp32DevKitC) else "local")
        out.append({
            "id": pid, "origin": origin, "title": p.title,
            "size": [round(p.w, 1), round(p.h, 1)],
            "pins": [{"name": n, "description": v.get("description", "")}
                     for n, v in p.pins.items()],
        })
    return out
