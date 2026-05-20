"""Inject a missing ``viewBox`` into an SVG document.

Some SVG generators (DrawingBot V3, certain plotter exporters, Adobe
Illustrator "SVG Tiny") emit files with explicit ``width``/``height`` in
physical units (``210mm`` × ``297mm``) but **no** ``viewBox``. Inkscape
makes a sensible guess; Illustrator, browsers, and :mod:`svgelements`
all guess differently, so the document renders at the wrong scale in
most consumers.

The robust fix is **not** to set ``viewBox`` to match the physical
width/height — the path data is usually in some other unit (raw points,
internal plotter units, …) and would clip if you did that. Instead we
compute the content's actual bounding box (with every group transform
already baked in) using :mod:`svgelements`, and use *that* as the
viewBox. The width/height attributes are left untouched, so the
document still renders at A4/Letter/etc. — just with the right internal
coordinate system.

The fix is intentionally conservative:

* If a ``viewBox`` is already present and well-formed, the input is
  returned unchanged.
* If the document has no recognisable shapes or its bounding box is
  degenerate, the input is returned unchanged — we'd rather under-fix
  than write a misleading viewBox.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from io import StringIO

from svgelements import SVG, Path, Shape

SVG_NS = "http://www.w3.org/2000/svg"
_SVG_TAG = f"{{{SVG_NS}}}svg"


def ensure_viewbox(svg_text: str) -> tuple[str, bool]:
    """Return ``(svg_text', was_modified)`` after possibly injecting a viewBox.

    The returned text is byte-equivalent to the input when no fix was
    applied (``was_modified == False``); otherwise it is the
    re-serialised document with the new ``viewBox`` attribute set on the
    root ``<svg>`` element.

    Args:
        svg_text: Raw SVG markup.

    Returns:
        A tuple ``(new_text, was_modified)``. ``was_modified`` is
        ``True`` only when a ``viewBox`` was actually added.
    """
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError:
        return svg_text, False

    if root.tag != _SVG_TAG:
        return svg_text, False

    existing_vb = root.get("viewBox")
    if existing_vb is not None and existing_vb.strip():
        return svg_text, False

    bbox = _compute_content_bbox(svg_text)
    if bbox is None:
        return svg_text, False
    min_x, min_y, max_x, max_y = bbox
    width = max_x - min_x
    height = max_y - min_y
    if width <= 0 or height <= 0:
        return svg_text, False

    vb = f"{_fmt(min_x)} {_fmt(min_y)} {_fmt(width)} {_fmt(height)}"
    root.set("viewBox", vb)

    ET.register_namespace("", SVG_NS)
    body = ET.tostring(root, encoding="unicode")
    if svg_text.lstrip().startswith("<?xml"):
        body = '<?xml version="1.0" encoding="utf-8"?>\n' + body
    return body, True


def _compute_content_bbox(svg_text: str) -> tuple[float, float, float, float] | None:
    """Union bounding box of every shape, in user-space (post-transform).

    Returns ``None`` when no shape contributes a bbox — typically because
    the document is empty or :mod:`svgelements` can't parse it.
    """
    try:
        svg = SVG.parse(StringIO(svg_text), ppi=96)
    except Exception:
        return None

    min_x: float | None = None
    min_y: float | None = None
    max_x: float | None = None
    max_y: float | None = None
    for element in svg.elements():
        if not isinstance(element, Shape):
            continue
        try:
            path = abs(Path(element))
            bx = path.bbox()
        except Exception:
            continue
        if bx is None:
            continue
        x0, y0, x1, y1 = bx
        if min_x is None or x0 < min_x:
            min_x = x0
        if min_y is None or y0 < min_y:
            min_y = y0
        if max_x is None or x1 > max_x:
            max_x = x1
        if max_y is None or y1 > max_y:
            max_y = y1

    if None in (min_x, min_y, max_x, max_y):
        return None
    # Type narrowing for mypy.
    assert min_x is not None and min_y is not None
    assert max_x is not None and max_y is not None
    return (min_x, min_y, max_x, max_y)


def _fmt(value: float) -> str:
    """Format a length for inclusion in the viewBox attribute."""
    if value == int(value):
        return str(int(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")
