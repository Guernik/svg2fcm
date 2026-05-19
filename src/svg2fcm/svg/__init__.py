"""SVG ingestion: load an SVG and produce IR shapes ready for FCM emission."""

from __future__ import annotations

from svg2fcm.svg.loader import IRShape, load_svg

__all__ = ["IRShape", "load_svg"]
