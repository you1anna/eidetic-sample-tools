"""Drawing kit for documentation figures in the Eidetic Engineering figure style.

The style comes from the Eidetic Engineering site's system figures: paper ground,
one muted ink for every line, uppercase mono labels on boundaries, a sans face
for component names, orthogonal connections and small filled arrowheads. Figures
are generated from code rather than drawn by hand so the committed SVG always
matches its reviewed source. docs/images/README.md explains the rules.

Type sizes are set for a GitHub README, which shows an SVG at its natural width
up to an 838px column. Sizes are in SVG units, which equal CSS pixels at that
width.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
import math

PAPER = '#f2f3f1'
INK = '#171918'
MUTED = '#565b58'

SANS = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace"

NAME_SIZE = 15
DETAIL_SIZE = 12
LABEL_SIZE = 11

# Line pitch per text class, used to centre a box's lines on the box.
PITCH = {'name': 19, 'detail': 16}
SIZE = {'name': NAME_SIZE, 'detail': DETAIL_SIZE}
CAP_HEIGHT = 0.72

FRAME_INSET = 16
FRAME_LABEL_BASELINE = 21

STYLE = f"""
text {{ font-family: {SANS}; fill: {MUTED}; }}
.frame-label {{ font-family: {MONO}; font-size: {LABEL_SIZE}px; letter-spacing: 0.1em; }}
.name {{ font-size: {NAME_SIZE}px; font-weight: 500; fill: {INK}; }}
.detail, .edge-label {{ font-size: {DETAIL_SIZE}px; }}
.frame, .box, .flow {{ fill: none; stroke: {MUTED}; stroke-width: 1; }}
.optional {{ stroke-dasharray: 4 4; }}
.arrowhead {{ fill: {MUTED}; }}
.port {{ fill: {PAPER}; stroke: {MUTED}; stroke-width: 1; }}
"""


def _number(value: float) -> str:
    rounded = round(value * 2) / 2
    return str(int(rounded)) if rounded == int(rounded) else str(rounded)


def _points(points: list[tuple[float, float]]) -> str:
    x, y = points[0]
    path = [f'M{_number(x)} {_number(y)}']
    for next_x, next_y in points[1:]:
        if next_y == y:
            path.append(f'H{_number(next_x)}')
        elif next_x == x:
            path.append(f'V{_number(next_y)}')
        else:
            raise ValueError(f'connections must be orthogonal: {(x, y)} to {(next_x, next_y)}')
        x, y = next_x, next_y
    return ''.join(path)


@dataclass
class Figure:
    """Accumulates the parts of one figure and renders them as a standalone SVG.

    The height follows the content: the lowest part plus the margin. Content that
    reaches into the right margin is an error, because an image is clipped silently.
    """

    width: int
    title: str
    description: str
    margin: int = 24
    parts: list[str] = field(default_factory=list)
    _right: float = field(default=0, init=False)
    _bottom: float = field(default=0, init=False)

    def _reach(self, x: float, y: float) -> None:
        self._right = max(self._right, x)
        self._bottom = max(self._bottom, y)

    def frame(self, x: float, y: float, width: float, height: float, label: str,
              *, optional: bool = False) -> None:
        """A labelled boundary around components that belong together."""
        self._reach(x + width, y + height)
        style = 'frame optional' if optional else 'frame'
        # Uppercase in the markup, not CSS, so renderers without text-transform agree.
        label = label.upper()
        self.parts.append(
            f'<g data-frame="{escape(label)}">'
            f'<rect class="{style}" x="{_number(x)}" y="{_number(y)}" '
            f'width="{_number(width)}" height="{_number(height)}"/>'
            f'<text class="frame-label" x="{_number(x + FRAME_INSET)}" '
            f'y="{_number(y + FRAME_LABEL_BASELINE)}">{escape(label)}</text></g>')

    def box(self, x: float, y: float, width: float, height: float,
            lines: list[tuple[str, str]], *, optional: bool = False) -> None:
        """A component with centred lines; each line is (text, 'name' or 'detail')."""
        self._reach(x + width, y + height)
        style = 'box optional' if optional else 'box'
        block = sum(PITCH[kind] for _, kind in lines)
        top = y + (height - block) / 2
        texts = []
        for text, kind in lines:
            baseline = top + (PITCH[kind] + CAP_HEIGHT * SIZE[kind]) / 2
            texts.append(
                f'<text class="{kind}" x="{_number(x + width / 2)}" y="{_number(baseline)}" '
                f'text-anchor="middle">{escape(text)}</text>')
            top += PITCH[kind]
        self.parts.append(
            f'<g data-box="{escape(lines[0][0])}">'
            f'<rect class="{style}" x="{_number(x)}" y="{_number(y)}" '
            f'width="{_number(width)}" height="{_number(height)}"/>{"".join(texts)}</g>')

    def flow(self, points: list[tuple[float, float]], *, optional: bool = False,
             both: bool = False) -> None:
        """An orthogonal connection ending in an arrowhead; `both` marks each end."""
        for x, y in points:
            self._reach(x, y)
        style = 'flow optional' if optional else 'flow'
        start = ' marker-start="url(#arrow)"' if both else ''
        self.parts.append(
            f'<path class="{style}" d="{_points(points)}"{start} marker-end="url(#arrow)"/>')

    def line(self, points: list[tuple[float, float]]) -> None:
        """An orthogonal connection without arrowheads, such as a bus."""
        for x, y in points:
            self._reach(x, y)
        self.parts.append(f'<path class="flow" d="{_points(points)}"/>')

    def port(self, x: float, y: float) -> None:
        """The junction where one connection fans out to several components."""
        self._reach(x + 3, y + 3)
        self.parts.append(f'<circle class="port" cx="{_number(x)}" cy="{_number(y)}" r="3"/>')

    def label(self, x: float, y: float, text: str, *, anchor: str = 'start') -> None:
        """A short note beside a connection saying what passes along it."""
        self._reach(x, y + 4)
        aligned = '' if anchor == 'start' else f' text-anchor="{anchor}"'
        self.parts.append(
            f'<text class="edge-label" x="{_number(x)}" y="{_number(y)}"{aligned}>'
            f'{escape(text)}</text>')

    def render(self) -> str:
        if self._right > self.width - self.margin:
            raise ValueError(f'content reaches x={self._right}, inside the {self.margin}px '
                             f'margin of a {self.width}px figure')
        height = math.ceil(self._bottom + self.margin)
        return '\n'.join([
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{height}" '
            f'viewBox="0 0 {self.width} {height}" role="img" '
            'aria-labelledby="title description">',
            '<!-- Generated by scripts/generate_figures.py; edit the spec there, not this file. -->',
            f'<title id="title">{escape(self.title)}</title>',
            f'<desc id="description">{escape(self.description)}</desc>',
            '<defs>',
            '<marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" '
            'markerHeight="6" orient="auto-start-reverse">'
            '<path class="arrowhead" d="M0 0L8 4L0 8Z"/></marker>',
            f'<style>{STYLE}</style>',
            '</defs>',
            f'<rect width="{self.width}" height="{height}" fill="{PAPER}"/>',
            *self.parts,
            '</svg>',
            '',
        ])
