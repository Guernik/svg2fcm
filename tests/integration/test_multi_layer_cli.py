"""End-to-end tests for the multi-layer CLI dispatch."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from svg2fcm.cli import main
from svg2fcm.fcm.parser import parse_fcm

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
TWO_LAYER = FIXTURES / "two_layer.svg"
SINGLE_LAYER = FIXTURES / "single_layer.svg"
DRAWINGBOT_STYLE = FIXTURES / "drawingbot_style.svg"
SAMPLES = Path(__file__).resolve().parent.parent.parent / "samples"
PLAIN_SVG = SAMPLES / "three_shapes_demo.svg"


def _copy(src: Path, dst: Path) -> Path:
    dst.write_bytes(src.read_bytes())
    return dst


def test_multi_layer_writes_one_fcm_per_layer(tmp_path: Path) -> None:
    """A 2-layer SVG -> two .fcm files next to the input by default."""
    src = _copy(TWO_LAYER, tmp_path / "design.svg")

    rc = main([str(src)])
    assert rc == 0

    outputs = sorted(tmp_path.glob("design_*.fcm"))
    assert [p.name for p in outputs] == ["design_A.fcm", "design_B.fcm"]


def test_multi_layer_explicit_output_dir(tmp_path: Path) -> None:
    """Passing an output directory routes per-layer files into it."""
    src = _copy(TWO_LAYER, tmp_path / "design.svg")
    out_dir = tmp_path / "out"

    rc = main([str(src), "-o", str(out_dir)])
    assert rc == 0

    outputs = sorted(out_dir.glob("design_*.fcm"))
    assert [p.name for p in outputs] == ["design_A.fcm", "design_B.fcm"]


def test_multi_layer_rejects_fcm_file_as_output(tmp_path: Path) -> None:
    """A .fcm output path is meaningless when the SVG has multiple layers."""
    src = _copy(TWO_LAYER, tmp_path / "design.svg")
    rc = main([str(src), "-o", str(tmp_path / "out.fcm")])
    assert rc == 1
    # No files should have been written.
    assert list(tmp_path.glob("*.fcm")) == []


def test_multi_layer_outputs_are_parseable_fcm(tmp_path: Path) -> None:
    """Each emitted file must round-trip through the existing parser."""
    src = _copy(TWO_LAYER, tmp_path / "design.svg")
    assert main([str(src)]) == 0

    for fcm_path in sorted(tmp_path.glob("design_*.fcm")):
        fcm = parse_fcm(fcm_path.read_bytes())
        # Each layer holds exactly one shape, so the parsed file should
        # have at least one piece with at least one outline.
        assert fcm.pieces, f"{fcm_path.name} has no pieces"


def test_single_layer_writes_one_unsuffixed_fcm(tmp_path: Path) -> None:
    """A 1-layer Inkscape SVG is a valid single-pen design — no _<label>."""
    src = _copy(SINGLE_LAYER, tmp_path / "design.svg")

    rc = main([str(src)])
    assert rc == 0

    assert (tmp_path / "design.fcm").exists()
    assert sorted(p.name for p in tmp_path.glob("*.fcm")) == ["design.fcm"]


@pytest.mark.skipif(not PLAIN_SVG.exists(), reason="samples/three_shapes_demo.svg missing")
def test_plain_svg_unchanged_single_output(tmp_path: Path) -> None:
    """Plain (no Inkscape namespace) SVG -> single output, current behavior."""
    src = tmp_path / "plain.svg"
    shutil.copyfile(PLAIN_SVG, src)
    out = tmp_path / "plain.fcm"

    rc = main([str(src), "-o", str(out)])
    assert rc == 0
    assert out.exists()


def test_default_output_lives_next_to_input(tmp_path: Path) -> None:
    """No output arg + plain SVG -> writes <stem>.fcm next to the input."""
    src = _copy(SINGLE_LAYER, tmp_path / "neighbours.svg")

    rc = main([str(src)])
    assert rc == 0
    assert (tmp_path / "neighbours.fcm").exists()


def test_drawingbot_style_id_groups_split(tmp_path: Path) -> None:
    """DrawingBot exports use <g id="CMYK_*"> with no inkscape namespace.

    The splitter must still treat each top-level id-bearing group as a
    pen and emit one .fcm per group.
    """
    src = _copy(DRAWINGBOT_STYLE, tmp_path / "design.svg")

    rc = main([str(src)])
    assert rc == 0

    outputs = sorted(p.name for p in tmp_path.glob("design_*.fcm"))
    assert outputs == [
        "design_CMYK_Cyan.fcm",
        "design_CMYK_Magenta.fcm",
        "design_CMYK_Yellow.fcm",
    ]
