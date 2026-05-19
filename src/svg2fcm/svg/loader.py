"""Load an SVG document into a list of :class:`IRShape` records.

The IR sits between the SVG layer (geometry in millimetres, flattened
transforms, decomposed primitives) and the FCM writer layer (piece-local
integer coordinates with a placement transform).

The single public entry point is :func:`load_svg`.

Design notes
------------

* SVG parsing is delegated to **``svgelements``**: it flattens all
  ``transform=`` attributes, expands ``<rect>``/``<circle>``/``<line>``/
  ``<polyline>``/``<polygon>`` into ``Path``-like objects, and converts arcs
  to cubic Bézier approximations on demand.
* We pass ``ppi=25.4`` so that one svgelements user unit equals one
  millimetre (since SVG defines 1 inch = 96 px and ``ppi=25.4`` makes
  ``1 unit = 1/25.4 inch = 1 mm`` directly).
* Each top-level SVG ``<path>`` (and each shape that decomposes into a path)
  is split at every ``M`` (Move) so each sub-path becomes its own
  :class:`IRShape`. This matches Canvas Workspace's convention of one piece
  per visually distinct sub-shape.
* Within a sub-path, consecutive segments of the same kind (line vs cubic)
  are grouped into a single :class:`~svg2fcm.fcm.model.Outline`.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path as FsPath
from typing import IO

from svgelements import (
    SVG,
    Arc,
    Close,
    Color,
    CubicBezier,
    Line,
    Move,
    Path,
    QuadraticBezier,
    Shape,
)

from svg2fcm.exceptions import InvalidSvgError
from svg2fcm.fcm.constants import UNITS_PER_MM
from svg2fcm.fcm.model import (
    Outline,
    Point,
    SegmentBezier,
    SegmentLine,
)

logger = logging.getLogger(__name__)

#: ``ppi`` value passed to svgelements so one user unit equals one millimetre
#: when the SVG declares physical ``width``/``height`` (mm/cm/in/pt/pc).
_PPI_FOR_MM: float = 25.4

#: Conversion factor for SVGs that only carry a ``viewBox`` (no physical
#: ``width``/``height``, or unitless/``px``). Illustrator's default SVG
#: export omits physical units and writes the viewBox in points (1 pt =
#: 1/72 in = 0.352778 mm), so we treat one user unit as one point.
_POINTS_TO_MM: float = 25.4 / 72.0

#: Pattern matching a CSS length with an optional unit suffix.
_LENGTH_RE = re.compile(r"^\s*[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?\s*([a-zA-Z%]*)\s*$")


def _detect_unit_scale(svg_text: str) -> float:
    """Return a multiplier converting svgelements user units to millimetres.

    With ``ppi=25.4``, svgelements yields user units = mm whenever the SVG
    declares physical ``width``/``height`` (the viewBox is scaled to fit).
    For unitless / ``px`` documents (Illustrator's default), user units stay
    in viewBox coordinates, which Illustrator writes as points. We then
    multiply by ``1 pt → mm``.
    """
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError:
        return 1.0  # let svgelements report the real error downstream

    physical_units = {"mm", "cm", "in", "pt", "pc"}
    for attr in ("width", "height"):
        value = root.get(attr)
        if value is None:
            continue
        match = _LENGTH_RE.match(value)
        if match and match.group(1).lower() in physical_units:
            return 1.0
    return _POINTS_TO_MM


@dataclass(slots=True)
class IRShape:
    """One drawable shape to be emitted as a single FCM piece.

    Coordinates inside :attr:`outlines` are **piece-local**: the path has
    been re-centered on its own bounding-box origin so the piece's bounding
    box is ``[-w/2, +w/2] × [-h/2, +h/2]`` in millimetres. The world-space
    placement of the piece centre is given by :attr:`center_x_mm` and
    :attr:`center_y_mm`.

    Attributes:
        width_mm: Bounding-box width in millimetres.
        height_mm: Bounding-box height in millimetres.
        center_x_mm: World-space x of the piece centre, in millimetres
            (measured from the mat edge).
        center_y_mm: World-space y of the piece centre, in millimetres.
        outlines: Sequence of FCM outlines (already in 1/100 mm integer
            coordinates, ready to drop into a :class:`~svg2fcm.fcm.model.Path`).
        start_point: First point of the path in piece-local 1/100 mm
            coordinates.
        is_open: ``True`` when the SVG sub-path did not end with a ``Z``
            (close) command. Drives the ``PATH_OPEN`` bit of the FCM tool
            field.
        stroke_color: RGB tuple if the SVG had an explicit stroke colour;
            ``None`` for ``stroke="none"`` or no stroke. Currently retained
            only for the v2 colour-split feature — v1 ignores it.
    """

    width_mm: float
    height_mm: float
    center_x_mm: float
    center_y_mm: float
    outlines: list[Outline]
    start_point: Point
    is_open: bool
    stroke_color: tuple[int, int, int] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mm_to_units(mm: float) -> int:
    """Convert millimetres to FCM units (1/100 mm), rounding to nearest int."""
    return round(mm * UNITS_PER_MM)


def _stroke_color(element: Shape) -> tuple[int, int, int] | None:
    """Extract an RGB stroke colour from an svgelements element, or ``None``.

    Returns ``None`` for ``stroke="none"`` (svgelements represents this as a
    ``Color`` whose RGB components are ``None``) and for elements without a
    stroke attribute at all.
    """
    stroke = getattr(element, "stroke", None)
    if stroke is None:
        return None
    if not isinstance(stroke, Color):
        return None
    if stroke.red is None or stroke.green is None or stroke.blue is None:
        return None
    return int(stroke.red), int(stroke.green), int(stroke.blue)


# ---------------------------------------------------------------------------
# Sub-path splitting and outline grouping
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _SubPath:
    """A single contiguous sub-path extracted from an SVG ``<path>``."""

    start_mm: tuple[float, float]
    # Each "step" is ("line", (x, y)) or ("bezier", (c1x,c1y), (c2x,c2y), (x,y)).
    steps: list[tuple[str, tuple[float, ...]]] = field(default_factory=list)
    closed: bool = False


def _expand_path(path: Path) -> Iterable[_SubPath]:
    """Walk an svgelements ``Path`` and yield one :class:`_SubPath` per ``M``.

    Quadratic Béziers are upgraded to cubics. Arcs are decomposed into cubic
    Béziers (svgelements emits ~3 cubics per 90° arc).
    """
    current: _SubPath | None = None
    pen: tuple[float, float] | None = None

    for seg in path:
        if isinstance(seg, Move):
            if current is not None and current.steps:
                yield current
            sx, sy = float(seg.end.x), float(seg.end.y)
            current = _SubPath(start_mm=(sx, sy))
            pen = (sx, sy)
            continue

        if current is None or pen is None:
            # Degenerate input: a segment without a preceding M. Treat as
            # implicit M to the segment's start.
            sx, sy = float(seg.start.x), float(seg.start.y)
            current = _SubPath(start_mm=(sx, sy))
            pen = (sx, sy)

        if isinstance(seg, Close):
            current.closed = True
            # If the close target differs from the start point, emit an
            # explicit line segment to the start (some SVG paths rely on
            # the Z command to draw the final closing edge).
            sx, sy = current.start_mm
            if pen != (sx, sy):
                current.steps.append(("line", (sx, sy)))
            pen = (sx, sy)
            continue

        if isinstance(seg, Line):
            ex, ey = float(seg.end.x), float(seg.end.y)
            current.steps.append(("line", (ex, ey)))
            pen = (ex, ey)
            continue

        if isinstance(seg, QuadraticBezier):
            # Elevate quadratic to cubic using the standard 2/3 rule.
            sx, sy = pen
            qcx, qcy = float(seg.control.x), float(seg.control.y)
            ex, ey = float(seg.end.x), float(seg.end.y)
            c1x = sx + (2.0 / 3.0) * (qcx - sx)
            c1y = sy + (2.0 / 3.0) * (qcy - sy)
            c2x = ex + (2.0 / 3.0) * (qcx - ex)
            c2y = ey + (2.0 / 3.0) * (qcy - ey)
            current.steps.append(("bezier", (c1x, c1y, c2x, c2y, ex, ey)))
            pen = (ex, ey)
            continue

        if isinstance(seg, CubicBezier):
            c1x, c1y = float(seg.control1.x), float(seg.control1.y)
            c2x, c2y = float(seg.control2.x), float(seg.control2.y)
            ex, ey = float(seg.end.x), float(seg.end.y)
            current.steps.append(("bezier", (c1x, c1y, c2x, c2y, ex, ey)))
            pen = (ex, ey)
            continue

        if isinstance(seg, Arc):
            for cubic in seg.as_cubic_curves():
                c1x, c1y = float(cubic.control1.x), float(cubic.control1.y)
                c2x, c2y = float(cubic.control2.x), float(cubic.control2.y)
                ex, ey = float(cubic.end.x), float(cubic.end.y)
                current.steps.append(("bezier", (c1x, c1y, c2x, c2y, ex, ey)))
                pen = (ex, ey)
            continue

        logger.debug("Ignoring unsupported segment type %s", type(seg).__name__)

    if current is not None and current.steps:
        yield current


def _scale_subpath(sub: _SubPath, scale: float) -> None:
    """Multiply every coordinate in a sub-path by ``scale`` in-place."""
    sx, sy = sub.start_mm
    sub.start_mm = (sx * scale, sy * scale)
    new_steps: list[tuple[str, tuple[float, ...]]] = []
    for kind, params in sub.steps:
        new_steps.append((kind, tuple(v * scale for v in params)))
    sub.steps = new_steps


def _bounding_box_mm(sub: _SubPath) -> tuple[float, float, float, float]:
    """Return ``(min_x, min_y, max_x, max_y)`` over a sub-path's geometry."""
    xs: list[float] = [sub.start_mm[0]]
    ys: list[float] = [sub.start_mm[1]]
    for kind, params in sub.steps:
        if kind == "line":
            x, y = params
            xs.append(x)
            ys.append(y)
        else:  # bezier
            c1x, c1y, c2x, c2y, x, y = params
            # The control points form a conservative bounding box over the
            # actual curve, which is fine for our use (piece sizing).
            xs.extend([c1x, c2x, x])
            ys.extend([c1y, c2y, y])
    return min(xs), min(ys), max(xs), max(ys)


def _build_outlines(
    sub: _SubPath,
    cx_mm: float,
    cy_mm: float,
) -> tuple[Point, list[Outline]]:
    """Convert a sub-path's steps to piece-local FCM outlines.

    Args:
        sub: The sub-path to convert.
        cx_mm: World-space x of the piece centre (in mm), to subtract.
        cy_mm: World-space y of the piece centre (in mm), to subtract.

    Returns:
        ``(start_point, outlines)`` where ``start_point`` is in 1/100 mm
        units and ``outlines`` is a list of consecutive same-kind runs.
    """
    sx, sy = sub.start_mm
    start = Point(_mm_to_units(sx - cx_mm), _mm_to_units(sy - cy_mm))

    outlines: list[Outline] = []
    line_run: list[SegmentLine] = []
    bezier_run: list[SegmentBezier] = []

    def flush_line_run() -> None:
        if line_run:
            outlines.append(Outline("line", list(line_run)))
            line_run.clear()

    def flush_bezier_run() -> None:
        if bezier_run:
            outlines.append(Outline("bezier", list(bezier_run)))
            bezier_run.clear()

    for kind, params in sub.steps:
        if kind == "line":
            flush_bezier_run()
            x, y = params
            line_run.append(
                SegmentLine(Point(_mm_to_units(x - cx_mm), _mm_to_units(y - cy_mm))),
            )
        else:  # bezier
            flush_line_run()
            c1x, c1y, c2x, c2y, x, y = params
            bezier_run.append(
                SegmentBezier(
                    Point(_mm_to_units(c1x - cx_mm), _mm_to_units(c1y - cy_mm)),
                    Point(_mm_to_units(c2x - cx_mm), _mm_to_units(c2y - cy_mm)),
                    Point(_mm_to_units(x - cx_mm), _mm_to_units(y - cy_mm)),
                ),
            )
    flush_line_run()
    flush_bezier_run()
    return start, outlines


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def load_svg(source: str | FsPath | IO[str]) -> list[IRShape]:
    """Load an SVG document and return a list of :class:`IRShape` records.

    Args:
        source: Either a filesystem path (``str`` or :class:`pathlib.Path`)
            or an open text stream containing SVG markup.

    Returns:
        One :class:`IRShape` per visually distinct sub-path discovered in
        the document, in document order.

    Raises:
        InvalidSvgError: If the source cannot be parsed as SVG.
    """
    try:
        if isinstance(source, str | FsPath):
            svg_text = FsPath(source).read_text(encoding="utf-8")
        else:
            svg_text = source.read()
        unit_scale = _detect_unit_scale(svg_text)
        logger.debug("Using unit_scale=%s (user-units -> mm)", unit_scale)
        svg = SVG.parse(StringIO(svg_text), ppi=_PPI_FOR_MM)
    except InvalidSvgError:
        raise
    except Exception as exc:
        raise InvalidSvgError(f"Failed to parse SVG: {exc}") from exc

    shapes: list[IRShape] = []
    for element in svg.elements():
        if not isinstance(element, Shape):
            continue
        try:
            # ``abs(Path(...))`` bakes the element's accumulated transform
            # (its own ``transform=`` plus the viewBox→viewport mapping that
            # svgelements computed for us) into the coordinates. Without
            # this, rotations and the viewBox-to-mm scale are silently
            # dropped — paths come out in raw viewBox units.
            path = abs(Path(element))
        except Exception as exc:
            logger.debug("Skipping %s: %s", type(element).__name__, exc)
            continue
        color = _stroke_color(element)
        for sub in _expand_path(path):
            if unit_scale != 1.0:
                _scale_subpath(sub, unit_scale)
            min_x, min_y, max_x, max_y = _bounding_box_mm(sub)
            width_mm = max_x - min_x
            height_mm = max_y - min_y
            if width_mm == 0.0 and height_mm == 0.0:
                continue  # degenerate
            cx = (min_x + max_x) / 2.0
            cy = (min_y + max_y) / 2.0
            start, outlines = _build_outlines(sub, cx, cy)
            shapes.append(
                IRShape(
                    width_mm=width_mm,
                    height_mm=height_mm,
                    center_x_mm=cx,
                    center_y_mm=cy,
                    outlines=outlines,
                    start_point=start,
                    is_open=not sub.closed,
                    stroke_color=color,
                ),
            )
    return shapes


def load_svg_from_string(svg_text: str) -> list[IRShape]:
    """Parse an SVG document from a string. Convenience for tests."""
    return load_svg(StringIO(svg_text))


__all__ = ["IRShape", "load_svg", "load_svg_from_string"]
