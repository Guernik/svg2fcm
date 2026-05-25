"""Split an SVG into one standalone SVG per top-level pen-group.

For pen-plotting workflows users typically want one ``.fcm`` per pen,
which in source SVGs maps to one top-level ``<g>``. Different exporters
mark up these groups differently:

* **Inkscape** uses ``<g inkscape:groupmode="layer" inkscape:label="...">``.
* **DrawingBot V3 / Vpype / Illustrator** use plain ``<g id="...">``
  with a human-readable id (e.g. ``id="CMYK_Yellow"``).

This module accepts both shapes. The rule is conservative:

    A top-level ``<g>`` is treated as a pen-group when **every** direct
    ``<g>`` child of ``<svg>`` carries either ``inkscape:groupmode="layer"``
    *or* an ``id`` attribute.

That avoids accidentally splitting Illustrator exports where some groups
are decoration and only one is labelled.

This module operates on the **raw SVG text** with
:mod:`xml.etree.ElementTree` and rebuilds, for each pen-group, a
standalone SVG document containing only that group's shapes. The full
pipeline (:func:`svg2fcm.svg.loader.load_svg`, the builder, the writer)
then runs once per pen-group without any further changes.

The split is purely a pre-processing step — coordinate systems, viewBox,
and ``<defs>`` are preserved verbatim, so per-pen-group outputs have the
exact same geometry they would have if the original document only
contained that group.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass

logger = logging.getLogger(__name__)

SVG_NS = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"

_SVG_TAG = f"{{{SVG_NS}}}svg"
_G_TAG = f"{{{SVG_NS}}}g"
_GROUPMODE_ATTR = f"{{{INKSCAPE_NS}}}groupmode"
_LABEL_ATTR = f"{{{INKSCAPE_NS}}}label"


@dataclass(frozen=True)
class Layer:
    """A single pen-group extracted as a standalone SVG document.

    Attributes:
        label: The group's label, in priority order: ``inkscape:label``,
            then ``id``, then ``""``. Callers fall back to ``layer<index>``
            if empty.
        index: 1-based position in document order (first group is ``1``).
        svg_text: A complete, well-formed SVG document containing only
            this group's content, with the original root attributes and
            ``<defs>`` preserved.
    """

    label: str
    index: int
    svg_text: str


def split_layers(svg_text: str) -> list[Layer]:
    """Return one :class:`Layer` per top-level pen-group in ``svg_text``.

    A *top-level pen-group* is a ``<g>`` element that is a direct child
    of the root ``<svg>``. The function only returns a non-empty list
    when **every** top-level ``<g>`` carries either
    ``inkscape:groupmode="layer"`` or an ``id`` attribute — that's the
    signal that the document is partitioned by pen rather than by
    drawing structure. Mixed documents (some labelled groups, some
    anonymous) fall through to single-output mode.

    Args:
        svg_text: The raw SVG document as a string.

    Returns:
        A list of :class:`Layer` objects in document order. Returns an
        empty list if the document doesn't look pen-partitioned — the
        caller then falls back to processing the original SVG as one
        unit.
    """
    # Register the inkscape namespace so ``ET.tostring`` re-emits the
    # ``inkscape:`` prefix instead of inventing ``ns0:``. Registering the
    # default SVG namespace with an empty prefix keeps the output readable
    # and identical in structure to typical Inkscape output.
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("inkscape", INKSCAPE_NS)

    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError:
        # Not our job to diagnose malformed SVG here — the downstream
        # loader will produce a clearer error. Treat as "no layers".
        return []

    if root.tag != _SVG_TAG:
        return []

    top_level_groups = [child for child in root if child.tag == _G_TAG]
    if not top_level_groups:
        return []

    # Heuristic: only split when every top-level <g> is identifiable as a
    # pen-group. If even one is anonymous, the file is probably structured
    # for visual organisation rather than per-pen output.
    if not all(_is_pen_group(g) for g in top_level_groups):
        logger.debug(
            "Top-level <g> elements are not all labelled pen-groups (%d total); "
            "skipping per-layer split.",
            len(top_level_groups),
        )
        return []

    layers: list[Layer] = []
    for idx, layer_el in enumerate(top_level_groups, start=1):
        label = layer_el.get(_LABEL_ATTR) or layer_el.get("id") or ""
        svg_text_for_layer = _serialize_with_only_layer(root, top_level_groups, layer_el)
        layers.append(Layer(label=label, index=idx, svg_text=svg_text_for_layer))
    logger.debug(
        "Detected %d pen-group(s): %s",
        len(layers),
        [layer.label or f"<index {layer.index}>" for layer in layers],
    )
    return layers


def _is_pen_group(g: ET.Element) -> bool:
    """Return ``True`` when a top-level ``<g>`` looks like a pen-group.

    A pen-group is identified by either Inkscape's ``groupmode="layer"``
    attribute or a plain ``id`` (used by DrawingBot, Vpype, Illustrator).
    """
    return g.get(_GROUPMODE_ATTR) == "layer" or bool(g.get("id"))


def _serialize_with_only_layer(
    root: ET.Element,
    all_layers: list[ET.Element],
    keep: ET.Element,
) -> str:
    """Serialize ``root`` with every layer in ``all_layers`` except ``keep`` removed.

    Non-layer children (``<defs>``, ``<metadata>``, raw shapes at the
    root, etc.) stay untouched so any cross-references resolve.
    """
    removed_indices: list[tuple[int, ET.Element]] = []
    for layer_el in all_layers:
        if layer_el is keep:
            continue
        # ET has no parent pointer; layers are direct children of root,
        # so we can remove them straight from ``root`` and re-insert
        # afterwards to leave the input element tree untouched for the
        # next iteration.
        position = list(root).index(layer_el)
        removed_indices.append((position, layer_el))
        root.remove(layer_el)
    try:
        body = ET.tostring(root, encoding="unicode")
    finally:
        for position, layer_el in removed_indices:
            root.insert(position, layer_el)
    return '<?xml version="1.0" encoding="utf-8"?>\n' + body
