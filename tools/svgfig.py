"""Minimal SVG figure builder for the README figures. No dependencies.

Every figure is written twice, for light and dark pages. Colors are role
names resolved through THEMES, never literals in the figure code.
"""

from html import escape
from pathlib import Path

FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"

THEMES = {
    "light": {
        "surface": "#fcfcfb",
        "text": "#0b0b0b",
        "secondary": "#52514e",
        "grid": "#e4e3df",
        "series1": "#2a78d6",
        "series2": "#eb6834",
        "series3": "#1baf7a",
        "good": "#0ca30c",
        "critical": "#d03b3b",
    },
    "dark": {
        "surface": "#1a1a19",
        "text": "#ffffff",
        "secondary": "#c3c2b7",
        "grid": "#33332f",
        "series1": "#3987e5",
        "series2": "#d95926",
        "series3": "#199e70",
        "good": "#0ca30c",
        "critical": "#d03b3b",
    },
}


def scale(domain, pixels):
    (d0, d1), (p0, p1) = domain, pixels
    return lambda value: p0 + (value - d0) / (d1 - d0) * (p1 - p0)


class Figure:
    def __init__(self, width, height, mode, title, subtitle=""):
        self.width, self.height = width, height
        self.colors = THEMES[mode]
        self.parts = []
        self.rect(0, 0, width, height, "surface", rx=8)
        self.text(24, 30, title, size=15, weight=600)
        if subtitle:
            self.text(24, 50, subtitle, size=12, color="secondary")

    def color(self, role):
        return self.colors.get(role, role)

    def add(self, markup):
        self.parts.append(markup)

    def rect(self, x, y, w, h, fill, rx=0, opacity=1.0):
        self.add(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" '
            f'fill="{self.color(fill)}" fill-opacity="{opacity}"/>'
        )

    def line(self, x1, y1, x2, y2, stroke="grid", width=1, dash=""):
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{self.color(stroke)}" stroke-width="{width}" stroke-linecap="round"{extra}/>'
        )

    def polyline(self, points, stroke, width=2):
        path = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        self.add(
            f'<polyline points="{path}" fill="none" stroke="{self.color(stroke)}" '
            f'stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>'
        )

    def dot(self, x, y, fill, r=4):
        """Marker with a surface-colored ring so it stays legible on lines and overlaps."""
        self.add(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{self.color(fill)}" '
            f'stroke="{self.color("surface")}" stroke-width="2"/>'
        )

    def bar(self, x, y, w, h, fill, round_end=True):
        """Horizontal bar: square at the baseline, 4px rounded at the data end."""
        if not round_end or w < 8:
            self.rect(x, y, w, h, fill)
            return
        r = 4
        self.add(
            f'<path d="M{x:.1f},{y:.1f} h{w - r:.1f} a{r},{r} 0 0 1 {r},{r} v{h - 2 * r:.1f} '
            f'a{r},{r} 0 0 1 -{r},{r} h-{w - r:.1f} z" fill="{self.color(fill)}"/>'
        )

    def text(self, x, y, content, size=12, color="text", anchor="start", weight=400):
        self.add(
            f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" '
            f'text-anchor="{anchor}" fill="{self.color(color)}">{escape(str(content))}</text>'
        )

    def render(self):
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" font-family="{FONT}" role="img">\n'
            + "\n".join(self.parts)
            + "\n</svg>\n"
        )


def save_both(directory, name, build):
    """build(mode) returns a Figure. Writes <name>-light.svg and <name>-dark.svg."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for mode in THEMES:
        path = directory / f"{name}-{mode}.svg"
        path.write_text(build(mode).render(), encoding="utf-8", newline="\n")
        print(f"wrote {path}")
