"""Unit tests for :mod:`svg2fcm.thumbnail`."""

from __future__ import annotations

from svg2fcm.svg.loader import load_svg_from_string
from svg2fcm.thumbnail import THUMBNAIL_HEIGHT, THUMBNAIL_WIDTH, render_thumbnail

SVG_WRAP = (
    '<?xml version="1.0"?>'
    '<svg xmlns="http://www.w3.org/2000/svg" width="200mm" height="200mm" '
    'viewBox="0 0 200 200">{}</svg>'
)


def test_empty_thumbnail_is_valid_bmp() -> None:
    out = render_thumbnail([])
    assert out.startswith(b"BM"), "BMP signature missing"
    # 1-bit 88×88 BMP is exactly 1118 bytes — matches the format embedded
    # by Canvas Workspace.
    assert len(out) == 1118
    # Check the DIB header records the expected dimensions.
    import struct

    width = struct.unpack("<i", out[18:22])[0]
    height = struct.unpack("<i", out[22:26])[0]
    bpp = struct.unpack("<H", out[28:30])[0]
    assert (width, height, bpp) == (THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT, 1)


def test_line_renders_at_least_one_pixel() -> None:
    line = '<line x1="10" y1="100" x2="190" y2="100" stroke="black"/>'
    shapes = load_svg_from_string(SVG_WRAP.format(line))
    out = render_thumbnail(shapes)
    # Pixel data starts at offset 62 (header 14 + DIB 40 + palette 8).
    pixel_data = out[62:]
    # At least one bit set to 0 (black) somewhere — a fully-white image
    # would have every byte equal to 0xff.
    assert any(b != 0xFF for b in pixel_data), "no pixels drawn"


def test_circle_thumbnail_is_recognisable() -> None:
    circle = '<circle cx="100" cy="100" r="50" stroke="black" fill="none"/>'
    shapes = load_svg_from_string(SVG_WRAP.format(circle))
    out = render_thumbnail(shapes)
    # Should produce visibly more black pixels than a single line.
    pixel_data = out[62:]
    black_pixel_byte_count = sum(1 for b in pixel_data if b != 0xFF)
    assert black_pixel_byte_count > 5
