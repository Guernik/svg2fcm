"""Unit tests for :mod:`svg2fcm.svg.layers`."""

from __future__ import annotations

from svg2fcm.cli import _sanitize_label
from svg2fcm.svg.layers import split_layers
from svg2fcm.svg.loader import load_svg_from_string

PLAIN_SVG = """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <line x1="0" y1="0" x2="50" y2="50" stroke="black"/>
</svg>
"""

SINGLE_LAYER_SVG = """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     viewBox="0 0 100 100">
  <g inkscape:groupmode="layer" inkscape:label="OnlyPen" stroke="black">
    <line x1="0" y1="0" x2="50" y2="50"/>
  </g>
</svg>
"""

TWO_LAYER_SVG = """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     viewBox="0 0 100 100">
  <defs>
    <marker id="dot"/>
  </defs>
  <g inkscape:groupmode="layer" inkscape:label="A" stroke="#ff0000">
    <line x1="0" y1="0" x2="50" y2="50"/>
  </g>
  <g inkscape:groupmode="layer" inkscape:label="B" stroke="#0000ff">
    <rect x="10" y="10" width="20" height="20"/>
  </g>
</svg>
"""

EMPTY_LABEL_SVG = """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     viewBox="0 0 100 100">
  <g inkscape:groupmode="layer">
    <line x1="0" y1="0" x2="50" y2="50"/>
  </g>
  <g inkscape:groupmode="layer" inkscape:label="">
    <rect x="10" y="10" width="20" height="20"/>
  </g>
</svg>
"""

# DrawingBot / Vpype / Illustrator style: plain <g id="..."> with no
# Inkscape namespace, used to partition by pen colour.
DRAWINGBOT_SVG = """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <g id="CMYK_Yellow">
    <line x1="0" y1="0" x2="50" y2="50"/>
  </g>
  <g id="CMYK_Cyan">
    <rect x="10" y="10" width="20" height="20"/>
  </g>
</svg>
"""

# Mixed: one labelled group, one anonymous. We refuse to split.
MIXED_SVG = """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <g id="Pen1">
    <line x1="0" y1="0" x2="50" y2="50"/>
  </g>
  <g>
    <rect x="10" y="10" width="20" height="20"/>
  </g>
</svg>
"""


def test_plain_svg_returns_no_layers() -> None:
    assert split_layers(PLAIN_SVG) == []


def test_single_layer_returns_one() -> None:
    layers = split_layers(SINGLE_LAYER_SVG)
    assert len(layers) == 1
    assert layers[0].label == "OnlyPen"
    assert layers[0].index == 1


def test_two_layers_returned_in_order() -> None:
    layers = split_layers(TWO_LAYER_SVG)
    assert [(layer.index, layer.label) for layer in layers] == [(1, "A"), (2, "B")]


def test_per_layer_svg_only_contains_that_layer() -> None:
    layers = split_layers(TWO_LAYER_SVG)
    # The "A" layer document must contain the line shape but not the rect.
    assert 'inkscape:label="A"' in layers[0].svg_text
    assert 'inkscape:label="B"' not in layers[0].svg_text
    assert "<line" in layers[0].svg_text or "line" in layers[0].svg_text
    assert "rect" not in layers[0].svg_text

    # Symmetric check for the "B" layer.
    assert 'inkscape:label="B"' in layers[1].svg_text
    assert 'inkscape:label="A"' not in layers[1].svg_text
    assert "rect" in layers[1].svg_text


def test_viewbox_and_defs_preserved() -> None:
    layers = split_layers(TWO_LAYER_SVG)
    for layer in layers:
        assert 'viewBox="0 0 100 100"' in layer.svg_text
        assert 'id="dot"' in layer.svg_text  # <defs> survives


def test_per_layer_svg_is_loadable() -> None:
    """Each per-layer SVG must parse back through the existing loader."""
    layers = split_layers(TWO_LAYER_SVG)
    shapes_a = load_svg_from_string(layers[0].svg_text)
    shapes_b = load_svg_from_string(layers[1].svg_text)
    assert len(shapes_a) == 1  # the line
    assert len(shapes_b) == 1  # the rect


def test_empty_label_preserved_as_empty_string() -> None:
    layers = split_layers(EMPTY_LABEL_SVG)
    assert len(layers) == 2
    assert layers[0].label == ""
    assert layers[1].label == ""


def test_malformed_xml_returns_empty_list() -> None:
    assert split_layers("<svg><not-closed>") == []


def test_non_svg_root_returns_empty_list() -> None:
    assert split_layers("<?xml version='1.0'?><html><body/></html>") == []


# ---------------------------------------------------------------------------
# id-based pen-group detection (DrawingBot / Vpype / Illustrator)
# ---------------------------------------------------------------------------


def test_drawingbot_id_groups_are_split() -> None:
    layers = split_layers(DRAWINGBOT_SVG)
    assert [layer.label for layer in layers] == ["CMYK_Yellow", "CMYK_Cyan"]


def test_drawingbot_per_layer_svg_is_loadable() -> None:
    layers = split_layers(DRAWINGBOT_SVG)
    shapes_y = load_svg_from_string(layers[0].svg_text)
    shapes_c = load_svg_from_string(layers[1].svg_text)
    assert len(shapes_y) == 1
    assert len(shapes_c) == 1


def test_inkscape_label_takes_precedence_over_id() -> None:
    """An Inkscape layer with both attributes should label-by-name."""
    svg = """<svg xmlns="http://www.w3.org/2000/svg"
                  xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">
      <g id="layer1" inkscape:groupmode="layer" inkscape:label="Cyan">
        <line x1="0" y1="0" x2="50" y2="50"/>
      </g>
      <g id="layer2" inkscape:groupmode="layer" inkscape:label="Magenta">
        <rect x="10" y="10" width="20" height="20"/>
      </g>
    </svg>"""
    layers = split_layers(svg)
    assert [layer.label for layer in layers] == ["Cyan", "Magenta"]


def test_mixed_named_and_anonymous_groups_refuses_to_split() -> None:
    """If only some top-level groups are labelled, we don't split."""
    assert split_layers(MIXED_SVG) == []


def test_non_group_top_level_children_dont_block_split() -> None:
    """<defs>, <metadata>, etc. shouldn't disqualify the split decision."""
    svg = """<svg xmlns="http://www.w3.org/2000/svg">
      <defs/>
      <metadata/>
      <g id="A"><line x1="0" y1="0" x2="50" y2="50"/></g>
      <g id="B"><rect x="10" y="10" width="20" height="20"/></g>
    </svg>"""
    layers = split_layers(svg)
    assert [layer.label for layer in layers] == ["A", "B"]


# ---------------------------------------------------------------------------
# Label sanitisation (lives in cli.py but logically belongs to this surface)
# ---------------------------------------------------------------------------


def test_sanitize_label_keeps_alphanumeric() -> None:
    assert _sanitize_label("Cyan") == "Cyan"
    assert _sanitize_label("1") == "1"
    assert _sanitize_label("pen-1") == "pen-1"


def test_sanitize_label_replaces_whitespace() -> None:
    assert _sanitize_label("Pen 1") == "Pen_1"
    assert _sanitize_label("  spaced  out  ") == "spaced_out"


def test_sanitize_label_replaces_path_separators() -> None:
    assert _sanitize_label("a/b") == "a_b"
    assert _sanitize_label("a\\b") == "a_b"
    assert _sanitize_label("a:b") == "a_b"


def test_sanitize_label_empty_for_garbage() -> None:
    assert _sanitize_label("") == ""
    assert _sanitize_label("///") == ""
    assert _sanitize_label("...") == ""
