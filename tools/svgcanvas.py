"""
A very small SVG writer, shared by tools/pinmap.py and tools/cirkit.py.

Deliberately not a dependency. Both generators emit a few hundred shapes of
straightforward geometry; svgwrite or cairo would add a build requirement to a
repository whose whole point is that its tooling installs anywhere Python does.

Text width is estimated rather than measured, because measuring means a font
engine. The estimate is used to size boxes, so an error shows up as a visibly
tight box rather than as silent overlap, and the fix is one constant.
"""

from xml.sax.saxutils import escape

SANS = ("-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, "
        "sans-serif")
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

SANS_PX = 0.60
MONO_PX = 0.62


def tw(s, size, mono=False):
    """Approximate advance width of `s` at `size` px."""
    return len(str(s)) * size * (MONO_PX if mono else SANS_PX)


class Canvas:
    def __init__(self, w=0, h=0):
        self.parts = []
        self.w = w
        self.h = h

    # -- primitives --------------------------------------------------------

    def add(self, s):
        self.parts.append(s)

    def rect(self, x, y, w, h, fill="none", r=0, stroke="none", sw=1, opacity=None):
        o = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
                 f'rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{o}/>')

    def circle(self, cx, cy, r, fill="none", stroke="none", sw=1):
        self.add(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill}" '
                 f'stroke="{stroke}" stroke-width="{sw}"/>')

    def line(self, x1, y1, x2, y2, stroke="#000", sw=1.5, dash=None, cap="round"):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                 f'stroke="{stroke}" stroke-width="{sw}" stroke-linecap="{cap}"{d}/>')

    def path(self, d, stroke="#000", sw=1.5, fill="none", dash=None, cap="round"):
        da = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<path d="{d}" stroke="{stroke}" stroke-width="{sw}" fill="{fill}" '
                 f'stroke-linecap="{cap}" stroke-linejoin="round"{da}/>')

    def text(self, x, y, s, size=14, fill="#16181D", anchor="start", weight="400",
             mono=False, ls=0, opacity=None):
        o = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(f'<text x="{x:.2f}" y="{y:.2f}" font-family="{MONO if mono else SANS}" '
                 f'font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
                 f'font-weight="{weight}" letter-spacing="{ls}"{o}>{escape(str(s))}</text>')

    # -- grouping ----------------------------------------------------------

    def group(self, transform=None, opacity=None):
        """Context manager emitting <g>. Used to place a part at (x, y)."""
        return _Group(self, transform, opacity)

    def raw(self, svg_fragment):
        """Insert an already-rendered SVG fragment verbatim (imported part art)."""
        self.add(svg_fragment)

    # -- output ------------------------------------------------------------

    def render(self, w=None, h=None):
        w = w or self.w
        h = h or self.h
        body = "\n".join(self.parts)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'width="{w:.0f}" height="{h:.0f}" viewBox="0 0 {w:.0f} {h:.0f}">\n'
                f'{body}\n</svg>\n')


class _Group:
    def __init__(self, canvas, transform, opacity):
        self.c = canvas
        self.transform = transform
        self.opacity = opacity

    def __enter__(self):
        t = f' transform="{self.transform}"' if self.transform else ""
        o = f' opacity="{self.opacity}"' if self.opacity is not None else ""
        self.c.add(f"<g{t}{o}>")
        return self.c

    def __exit__(self, *exc):
        self.c.add("</g>")
        return False
