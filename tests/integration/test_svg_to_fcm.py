"""End-to-end SVG → FCM pipeline integration tests.

These verify that the SVG loader, thumbnail renderer, builder, and writer
compose into a valid FCM file: every produced file must round-trip through
the parser and reproduce the shape count and geometry of the input.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from svg2fcm import parse_fcm
from svg2fcm.builder import build_fcm
from svg2fcm.cli import convert, main
from svg2fcm.fcm.constants import (
    TOOL_DRAW_CLOSED,
    TOOL_DRAW_OPEN,
    UNITS_PER_MM,
)
from svg2fcm.fcm.writer import encode_fcm
from svg2fcm.svg.loader import load_svg_from_string
from svg2fcm.thumbnail import render_thumbnail

SVG_WRAP = (
    '<?xml version="1.0"?>'
    '<svg xmlns="http://www.w3.org/2000/svg" width="200mm" height="200mm" '
    'viewBox="0 0 200 200">{}</svg>'
)


def _build_bytes(inner_svg: str, *, group: bool = True) -> bytes:
    shapes = load_svg_from_string(SVG_WRAP.format(inner_svg))
    return encode_fcm(build_fcm(shapes, render_thumbnail(shapes), group=group))


def test_single_line_produces_parseable_fcm() -> None:
    data = _build_bytes('<line x1="10" y1="20" x2="40" y2="20" stroke="black"/>')
    fcm = parse_fcm(data)
    assert len(fcm.pieces) == 1
    _, piece = fcm.pieces[0]
    # Width in 1/100 mm units: 30 mm × 100 = 3000.
    assert piece.width == 3000
    assert piece.height == 0
    # Single open-draw path.
    assert len(piece.paths) == 1
    assert piece.paths[0].tool == TOOL_DRAW_OPEN


def test_closed_shape_uses_draw_closed_flag() -> None:
    data = _build_bytes(
        '<rect x="50" y="60" width="40" height="20" stroke="black" fill="none"/>',
    )
    fcm = parse_fcm(data)
    _, piece = fcm.pieces[0]
    assert piece.paths[0].tool == TOOL_DRAW_CLOSED


def test_multiple_shapes_default_to_grouped_into_single_piece() -> None:
    # Default behaviour (group=True) emits one Piece containing one Path
    # per shape — emulates Canvas Workspace's "select all → group", and
    # avoids the ScanNCut import failure observed on files with many
    # independent pieces.
    inner = (
        '<line x1="10" y1="10" x2="20" y2="10" stroke="black"/>'
        '<line x1="30" y1="30" x2="40" y2="30" stroke="black"/>'
        '<line x1="50" y1="50" x2="60" y2="50" stroke="black"/>'
    )
    fcm = parse_fcm(_build_bytes(inner))
    assert len(fcm.pieces) == 1
    _, piece = fcm.pieces[0]
    assert piece.label == "A01"
    assert len(piece.paths) == 3


def test_no_group_emits_one_piece_per_shape_with_labels() -> None:
    # Opt-out flag preserves the legacy one-piece-per-shape layout.
    inner = (
        '<line x1="10" y1="10" x2="20" y2="10" stroke="black"/>'
        '<line x1="30" y1="30" x2="40" y2="30" stroke="black"/>'
        '<line x1="50" y1="50" x2="60" y2="50" stroke="black"/>'
    )
    fcm = parse_fcm(_build_bytes(inner, group=False))
    assert len(fcm.pieces) == 3
    labels = [piece.label for _, piece in fcm.pieces]
    assert labels == ["A01", "A02", "A03"]


def test_grouped_piece_preserves_world_geometry() -> None:
    # Two lines: one at y=10 spanning x=0..10, one at y=50 spanning x=20..40.
    # Combined bbox: x=0..40, y=10..50 → centre (20, 30), size 40×40 mm.
    # Each path inside the grouped piece must remain at its original
    # world position once the piece transform is applied.
    inner = (
        '<line x1="0" y1="10" x2="10" y2="10" stroke="black"/>'
        '<line x1="20" y1="50" x2="40" y2="50" stroke="black"/>'
    )
    fcm = parse_fcm(_build_bytes(inner))
    _, piece = fcm.pieces[0]
    assert piece.width == 4000  # 40 mm
    assert piece.height == 4000  # 40 mm
    assert piece.transform is not None
    tx, ty = piece.transform[4], piece.transform[5]
    assert math.isclose(tx, 20.0 * UNITS_PER_MM, abs_tol=0.5)
    assert math.isclose(ty, 30.0 * UNITS_PER_MM, abs_tol=0.5)
    # First path should start at piece-local (-2000, -2000) = world (0, 10).
    first_shape = piece.paths[0].shape
    assert first_shape is not None
    first_start = first_shape.start
    assert math.isclose(first_start.x + tx, 0.0, abs_tol=0.5)
    assert math.isclose(first_start.y + ty, 10.0 * UNITS_PER_MM, abs_tol=0.5)


def test_svg_origin_maps_to_drawable_area_origin() -> None:
    # SVG (0, 0) must land at Canvas Workspace UI (3, 3), the top-left
    # of the drawable red area. CW UI corner = tx + 3 mm - half_w, so for
    # an SVG-origin-aligned shape we need tx = piece centre exactly.
    # 30-mm-wide line centred at SVG x=25 mm → tx = 25 × 100 = 2500;
    # CW UI left edge = 2500/100 + 3 - 15 = 13 = SVG_left (10) + 3.
    data = _build_bytes('<line x1="10" y1="20" x2="40" y2="20" stroke="black"/>')
    fcm = parse_fcm(data)
    _, piece = fcm.pieces[0]
    assert piece.transform is not None
    tx, ty = piece.transform[4], piece.transform[5]
    assert math.isclose(tx, 25.0 * UNITS_PER_MM, abs_tol=0.5)
    assert math.isclose(ty, 20.0 * UNITS_PER_MM, abs_tol=0.5)


def test_element_transform_and_viewbox_scale_are_applied() -> None:
    # Physical width/height in mm with a viewBox in *points* (Illustrator-
    # style: 419.53 × 595.28 pt = 148 × 210 mm = A5). The inner <rect> also
    # carries a rotate(90) transform. svgelements computes the viewBox→mm
    # mapping for us; we must apply the element's accumulated transform so
    # rotation and scale survive (regression — previously we used the raw
    # viewBox-space d-string and produced a 538 × 362 mm shape).
    svg = (
        '<?xml version="1.0"?>'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="148mm" height="210mm" viewBox="0 0 419.5276 595.2756">'
        '<rect x="-59.5278" y="116.221" width="538.5825" height="362.834" '
        'transform="translate(507.4015 87.8744) rotate(90)" '
        'stroke="black" fill="none"/>'
        "</svg>"
    )
    shapes = load_svg_from_string(svg)
    assert len(shapes) == 1
    s = shapes[0]
    assert math.isclose(s.width_mm, 128.0, abs_tol=0.05)
    assert math.isclose(s.height_mm, 190.0, abs_tol=0.05)


def test_cli_convert_writes_a_valid_file(tmp_path: Path) -> None:
    svg_path = tmp_path / "input.svg"
    fcm_path = tmp_path / "output.fcm"
    svg_path.write_text(SVG_WRAP.format('<line x1="0" y1="0" x2="50" y2="0" stroke="black"/>'))
    count = convert(svg_path, fcm_path)
    assert count == 1
    fcm = parse_fcm(fcm_path.read_bytes())
    assert len(fcm.pieces) == 1


def test_cli_main_returns_zero_on_success(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    svg_path = tmp_path / "in.svg"
    fcm_path = tmp_path / "out.fcm"
    rect = '<rect x="0" y="0" width="10" height="10" stroke="black" fill="none"/>'
    svg_path.write_text(SVG_WRAP.format(rect))
    exit_code = main([str(svg_path), str(fcm_path)])
    assert exit_code == 0
    assert fcm_path.exists()
    captured = capsys.readouterr()
    assert "Converted 1 shape" in captured.out


def test_cli_main_returns_one_on_invalid_svg(tmp_path: Path) -> None:
    bad = tmp_path / "bad.svg"
    out = tmp_path / "out.fcm"
    bad.write_text("not actually svg")
    assert main([str(bad), str(out)]) == 1
    assert not out.exists()
