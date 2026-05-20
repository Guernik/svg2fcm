"""Unit tests for :mod:`svg2fcm.svg.viewbox`."""

from __future__ import annotations

import re

from svg2fcm.svg.viewbox import ensure_viewbox

# A DrawingBot-style document: width/height in mm, no viewBox, content
# lives in a coordinate system unrelated to mm.
NO_VB_LARGE_COORDS = """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="297mm">
  <path d="M 100 100 L 800 1100" stroke="black" fill="none"/>
</svg>
"""

WITH_VB = """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="297mm" viewBox="0 0 793 1122">
  <path d="M 100 100 L 700 1000"/>
</svg>
"""


def _viewbox_of(svg_text: str) -> str | None:
    match = re.search(r'viewBox="([^"]+)"', svg_text)
    return match.group(1) if match else None


def test_injects_viewbox_from_content_bbox() -> None:
    """ViewBox should match the actual coordinate range of the paths."""
    out, modified = ensure_viewbox(NO_VB_LARGE_COORDS)
    assert modified is True
    # Content goes from (100,100) to (800,1100), so bbox is 700 x 1000
    # with origin (100,100).
    assert _viewbox_of(out) == "100 100 700 1000"


def test_idempotent_when_viewbox_present() -> None:
    out, modified = ensure_viewbox(WITH_VB)
    assert modified is False
    assert out == WITH_VB  # exact byte match


def test_group_transform_applied_to_bbox() -> None:
    """A scaling group transform should be baked into the computed viewBox.

    This is the DrawingBot pattern: outer transform matrix(0.64,...) +
    raw plotter-unit path coordinates. The viewBox we synthesise must
    reflect the post-transform geometry, not the raw path data.
    """
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="297mm">
      <g transform="matrix(0.64,0,0,0.64,0,0)">
        <path d="M 100 100 L 1750 1100"/>
      </g>
    </svg>"""
    out, modified = ensure_viewbox(svg)
    assert modified is True
    # 100*0.64=64, 1750*0.64=1120 -> bbox (64,64) to (1120,704), 1056 x 640.
    assert _viewbox_of(out) == "64 64 1056 640"


def test_no_shapes_leaves_file_alone() -> None:
    """Documents with nothing drawable get no synthesised viewBox."""
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="297mm"/>'
    out, modified = ensure_viewbox(svg)
    assert modified is False
    assert out == svg


def test_only_defs_leaves_file_alone() -> None:
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="297mm">
      <defs><marker id="dot"/></defs>
    </svg>"""
    out, modified = ensure_viewbox(svg)
    assert modified is False
    assert out == svg


def test_malformed_xml_leaves_text_alone() -> None:
    svg = "<svg <not-closed"
    out, modified = ensure_viewbox(svg)
    assert modified is False
    assert out == svg


def test_non_svg_root_leaves_text_alone() -> None:
    _, modified = ensure_viewbox("<?xml version='1.0'?><html/>")
    assert modified is False


def test_existing_empty_viewbox_is_replaced() -> None:
    """A literal empty/whitespace viewBox attribute is treated as missing."""
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="297mm" viewBox="  ">
      <path d="M 0 0 L 50 50"/>
    </svg>"""
    out, modified = ensure_viewbox(svg)
    assert modified is True
    assert _viewbox_of(out) == "0 0 50 50"


def test_negative_coordinates_handled() -> None:
    """Paths with negative coordinates produce a viewBox with negative origin."""
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm">
      <path d="M -50 -50 L 50 50"/>
    </svg>"""
    out, modified = ensure_viewbox(svg)
    assert modified is True
    assert _viewbox_of(out) == "-50 -50 100 100"


def test_multiple_shapes_unioned() -> None:
    """The viewBox spans every shape, not just the first one."""
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm">
      <line x1="0" y1="0" x2="10" y2="10"/>
      <rect x="50" y="50" width="40" height="40"/>
    </svg>"""
    out, modified = ensure_viewbox(svg)
    assert modified is True
    # union: (0,0) to (90,90)
    assert _viewbox_of(out) == "0 0 90 90"
