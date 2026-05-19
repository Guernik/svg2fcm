"""Unit tests for :mod:`svg2fcm.svg.loader`."""

from __future__ import annotations

import math

import pytest

from svg2fcm.exceptions import InvalidSvgError
from svg2fcm.fcm.model import SegmentBezier, SegmentLine
from svg2fcm.svg.loader import load_svg_from_string

# Minimal SVG header that fixes the user-unit to 1 mm.
SVG_PRE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="200mm" height="200mm" viewBox="0 0 200 200">'
)
SVG_POST = "</svg>"


def _wrap(inner: str) -> str:
    return f'<?xml version="1.0"?>{SVG_PRE}{inner}{SVG_POST}'


# ---------------------------------------------------------------------------
# Single-primitive shapes
# ---------------------------------------------------------------------------


def test_single_line() -> None:
    shapes = load_svg_from_string(_wrap('<line x1="10" y1="20" x2="40" y2="20" stroke="black"/>'))
    assert len(shapes) == 1
    s = shapes[0]
    assert s.is_open is True
    assert math.isclose(s.width_mm, 30.0, abs_tol=0.01)
    assert math.isclose(s.height_mm, 0.0, abs_tol=0.01)
    assert math.isclose(s.center_x_mm, 25.0, abs_tol=0.01)
    assert math.isclose(s.center_y_mm, 20.0, abs_tol=0.01)
    # Path-local coordinates: line centered on the piece origin, span ±15 mm.
    assert len(s.outlines) == 1
    outline = s.outlines[0]
    assert outline.kind == "line"
    assert len(outline.segments) == 1
    seg = outline.segments[0]
    assert isinstance(seg, SegmentLine)
    assert seg.end.x == 1500  # +15 mm in 1/100 mm units
    assert seg.end.y == 0


def test_closed_rectangle() -> None:
    shapes = load_svg_from_string(
        _wrap('<rect x="50" y="60" width="40" height="20" stroke="red" fill="none"/>'),
    )
    assert len(shapes) == 1
    s = shapes[0]
    assert s.is_open is False  # rect always closes
    assert math.isclose(s.width_mm, 40.0, abs_tol=0.01)
    assert math.isclose(s.height_mm, 20.0, abs_tol=0.01)
    # The rect expands to 4 line segments; outline grouping merges them.
    assert all(o.kind == "line" for o in s.outlines)
    total_line_segments = sum(len(o.segments) for o in s.outlines)
    assert total_line_segments == 4


def test_circle_decomposes_to_cubic_beziers() -> None:
    shapes = load_svg_from_string(
        _wrap('<circle cx="100" cy="100" r="20" stroke="blue" fill="none"/>'),
    )
    assert len(shapes) == 1
    s = shapes[0]
    assert s.is_open is False
    assert math.isclose(s.width_mm, 40.0, abs_tol=0.01)
    assert math.isclose(s.height_mm, 40.0, abs_tol=0.01)
    # Circle decomposes to all-bezier outlines.
    assert all(o.kind == "bezier" for o in s.outlines)
    assert all(isinstance(seg, SegmentBezier) for o in s.outlines for seg in o.segments)
    # svgelements emits ~3 cubics per quadrant for an arc-circle → ≥4 cubics total.
    total_segments = sum(len(o.segments) for o in s.outlines)
    assert total_segments >= 4


def test_polyline_open_path() -> None:
    shapes = load_svg_from_string(
        _wrap('<polyline points="10,10 30,10 30,30 50,30" stroke="black" fill="none"/>'),
    )
    assert len(shapes) == 1
    s = shapes[0]
    assert s.is_open is True
    assert sum(len(o.segments) for o in s.outlines) == 3  # 4 points → 3 segments


def test_polygon_closed_path() -> None:
    shapes = load_svg_from_string(
        _wrap('<polygon points="0,0 30,0 15,25" stroke="black" fill="none"/>'),
    )
    assert len(shapes) == 1
    assert shapes[0].is_open is False


# ---------------------------------------------------------------------------
# Path edge cases
# ---------------------------------------------------------------------------


def test_path_with_subpaths_yields_multiple_shapes() -> None:
    shapes = load_svg_from_string(
        _wrap('<path d="M 10,10 L 30,10 M 50,50 L 70,50" stroke="black" fill="none"/>'),
    )
    assert len(shapes) == 2
    assert all(s.is_open for s in shapes)


def test_quadratic_bezier_upgraded_to_cubic() -> None:
    shapes = load_svg_from_string(
        _wrap('<path d="M 10,10 Q 30,40 50,10" stroke="black" fill="none"/>'),
    )
    assert len(shapes) == 1
    segs = [seg for o in shapes[0].outlines for seg in o.segments]
    assert all(isinstance(seg, SegmentBezier) for seg in segs)


def test_mixed_line_and_bezier_grouped_into_alternating_outlines() -> None:
    shapes = load_svg_from_string(
        _wrap(
            '<path d="M 0,0 L 10,0 L 20,0 C 30,10 40,10 50,0 L 60,0" stroke="black" fill="none"/>',
        ),
    )
    assert len(shapes) == 1
    kinds = [o.kind for o in shapes[0].outlines]
    # Two L runs separated by a C run.
    assert kinds == ["line", "bezier", "line"]


def test_transforms_are_flattened() -> None:
    # A line under translate(50, 0): endpoints shift by 50 mm in x.
    shapes = load_svg_from_string(
        _wrap(
            '<g transform="translate(50,0)">'
            '<line x1="10" y1="10" x2="20" y2="10" stroke="black"/>'
            "</g>",
        ),
    )
    assert len(shapes) == 1
    # World-space center should be at x=65 (midpoint of 60..70).
    assert math.isclose(shapes[0].center_x_mm, 65.0, abs_tol=0.01)


# ---------------------------------------------------------------------------
# Stroke colour
# ---------------------------------------------------------------------------


def test_stroke_colour_captured() -> None:
    shapes = load_svg_from_string(
        _wrap('<line x1="0" y1="0" x2="10" y2="0" stroke="#ff0000"/>'),
    )
    assert shapes[0].stroke_color == (255, 0, 0)


def test_no_stroke_yields_none() -> None:
    shapes = load_svg_from_string(
        _wrap('<line x1="0" y1="0" x2="10" y2="0" stroke="none"/>'),
    )
    assert shapes[0].stroke_color is None


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_invalid_svg_raises() -> None:
    with pytest.raises(InvalidSvgError):
        load_svg_from_string("not actually svg")


def test_empty_svg_yields_no_shapes() -> None:
    shapes = load_svg_from_string(_wrap(""))
    assert shapes == []


# ---------------------------------------------------------------------------
# Unit handling
# ---------------------------------------------------------------------------


def test_unitless_viewbox_treated_as_points() -> None:
    """Illustrator's default SVG export: no width/height, viewBox in points."""
    svg = (
        '<?xml version="1.0"?>'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 595.28 841.89">'
        '<rect x="0" y="0" width="595.28" height="841.89" '
        'style="fill:none;stroke:#000;stroke-width:2.83"/>'
        "</svg>"
    )
    shapes = load_svg_from_string(svg)
    assert len(shapes) == 1
    assert math.isclose(shapes[0].width_mm, 210.0, abs_tol=0.05)
    assert math.isclose(shapes[0].height_mm, 297.0, abs_tol=0.05)


def test_width_height_in_mm_kept_as_mm() -> None:
    """When width/height are in mm, user units already map to mm."""
    svg = (
        '<?xml version="1.0"?>'
        '<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="297mm" '
        'viewBox="0 0 210 297">'
        '<rect x="0" y="0" width="210" height="297" stroke="black" fill="none"/>'
        "</svg>"
    )
    shapes = load_svg_from_string(svg)
    assert len(shapes) == 1
    assert math.isclose(shapes[0].width_mm, 210.0, abs_tol=0.01)
    assert math.isclose(shapes[0].height_mm, 297.0, abs_tol=0.01)
