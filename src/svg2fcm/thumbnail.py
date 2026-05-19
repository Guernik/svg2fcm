"""Render IR shapes to the 88×88 1-bit BMP thumbnail embedded in an FCM file.

The thumbnail is shown in the ScanNCut machine's file picker. It must be a
valid BMP the machine can decode. This module is implemented in **pure
Python** (no Pillow, no compiled extensions) so the same code runs in any
Python environment — including Inkscape's bundled interpreter where
binary wheels for the host platform cannot be assumed.

Output: a 1-bit (monochrome) 88×88 BMP, 1118 bytes total. Byte layout
matches Pillow's ``Image.save(..., format="BMP")`` exactly, so files
produced here are interchangeable with the Pillow-based thumbnails
embedded by Canvas Workspace (palette index 0 = black ink, index 1 =
white background). Cubic Bézier segments are flattened to short line
runs and rasterised with a straightforward Bresenham line algorithm.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence
from itertools import pairwise

from svg2fcm.fcm.constants import MAT_HEIGHT_MM, MAT_WIDTH_MM
from svg2fcm.fcm.model import SegmentBezier, SegmentLine
from svg2fcm.svg.loader import IRShape

#: Thumbnail pixel dimensions used by Brother ScanNCut.
THUMBNAIL_WIDTH: int = 88
THUMBNAIL_HEIGHT: int = 88

#: Pixels left blank around the rendered geometry, so strokes near the mat
#: edge are still visible at thumbnail scale.
_THUMBNAIL_MARGIN_PX: int = 2

#: Number of straight-line subdivisions used to flatten each cubic Bézier.
#: 16 is plenty for 88×88 pixels.
_BEZIER_FLATTEN_STEPS: int = 16


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _flatten_cubic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    steps: int = _BEZIER_FLATTEN_STEPS,
) -> list[tuple[float, float]]:
    """Sample a cubic Bézier into ``steps + 1`` straight-line vertices."""
    out: list[tuple[float, float]] = []
    for i in range(steps + 1):
        t = i / steps
        u = 1.0 - t
        b0 = u * u * u
        b1 = 3 * u * u * t
        b2 = 3 * u * t * t
        b3 = t * t * t
        x = b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0]
        y = b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1]
        out.append((x, y))
    return out


def _shape_polyline_mm(shape: IRShape) -> list[tuple[float, float]]:
    """Flatten an :class:`IRShape` into a list of ``(x, y)`` points in mm.

    Coordinates are translated back to world-space (mat-edge-relative) using
    the shape's centre.
    """
    cx = shape.center_x_mm
    cy = shape.center_y_mm

    def to_world(pt_units_x: int, pt_units_y: int) -> tuple[float, float]:
        return (pt_units_x / 100.0 + cx, pt_units_y / 100.0 + cy)

    pts: list[tuple[float, float]] = [to_world(shape.start_point.x, shape.start_point.y)]

    for outline in shape.outlines:
        for seg in outline.segments:
            if isinstance(seg, SegmentLine):
                pts.append(to_world(seg.end.x, seg.end.y))
            elif isinstance(seg, SegmentBezier):
                prev = pts[-1]
                c1 = to_world(seg.control1.x, seg.control1.y)
                c2 = to_world(seg.control2.x, seg.control2.y)
                end = to_world(seg.end.x, seg.end.y)
                # Drop the first sample — it's the previous endpoint.
                pts.extend(_flatten_cubic(prev, c1, c2, end)[1:])
    return pts


# ---------------------------------------------------------------------------
# 1-bit raster + BMP encoding (no third-party deps)
# ---------------------------------------------------------------------------


class _MonoBitmap:
    """Mutable 1-bit bitmap with a Bresenham line drawer.

    ``pixels`` is row-major, top-to-bottom, with each row stored as a
    ``bytearray`` of length :data:`width` (one byte per pixel for ease of
    manipulation — packed only at encode time).
    """

    __slots__ = ("height", "rows", "width")

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        # 0 = background (white), 1 = ink (black).
        self.rows: list[bytearray] = [bytearray(width) for _ in range(height)]

    def set_pixel(self, x: int, y: int) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.rows[y][x] = 1

    def draw_line(self, x0: int, y0: int, x1: int, y1: int) -> None:
        """Draw a 1-pixel-wide line using Bresenham's algorithm."""
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.set_pixel(x0, y0)
            if x0 == x1 and y0 == y1:
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy


def _encode_bmp_1bit(bitmap: _MonoBitmap) -> bytes:
    """Encode a :class:`_MonoBitmap` as a 1-bit Windows BMP file.

    Layout matches Pillow's output for the same image: 14-byte file
    header, 40-byte ``BITMAPINFOHEADER``, 8-byte palette (white then
    black), then bottom-up rows padded to 4-byte alignment.
    """
    w, h = bitmap.width, bitmap.height
    # 1 bit per pixel, rounded up to whole bytes, padded to a 4-byte row.
    row_bytes = ((w + 7) // 8 + 3) & ~3
    pixel_data_size = row_bytes * h
    palette_size = 8  # two BGRA entries
    dib_header_size = 40
    file_header_size = 14
    pixel_offset = file_header_size + dib_header_size + palette_size
    file_size = pixel_offset + pixel_data_size

    out = bytearray()
    # ---- BMP file header (14 bytes) ----
    out += b"BM"
    out += struct.pack("<I", file_size)
    out += struct.pack("<HH", 0, 0)  # reserved
    out += struct.pack("<I", pixel_offset)
    # ---- BITMAPINFOHEADER (40 bytes) ----
    out += struct.pack(
        "<IiiHHIIiiII",
        dib_header_size,
        w,
        h,
        1,  # planes
        1,  # bits per pixel
        0,  # BI_RGB (no compression)
        pixel_data_size,
        3780,  # x px/m (= 96 dpi; matches Pillow's default for 1-bit BMP)
        3780,  # y px/m
        2,  # colors used
        2,  # important colors
    )
    # ---- Palette (BGRA): index 0 = black, index 1 = white ----
    # This matches Pillow's 1-bit BMP output so any consumer that has
    # only ever seen Pillow-produced thumbnails (Canvas Workspace, the
    # machine, our test fixtures) sees the exact same palette layout.
    out += b"\x00\x00\x00\x00"
    out += b"\xff\xff\xff\x00"

    # ---- Pixel data, bottom-up, 1 bit per pixel ----
    # Background pixel (0) → palette index 1 (white). Ink pixel (1) →
    # palette index 0 (black). So a white row packs to all 0xFF bytes
    # for the image area, then 0x00 padding to a 4-byte row boundary
    # (matches Pillow's exact output).
    image_bytes = (w + 7) // 8
    for y in range(h - 1, -1, -1):
        row = bitmap.rows[y]
        row_buf = bytearray(b"\xff" * image_bytes + b"\x00" * (row_bytes - image_bytes))
        for x in range(w):
            if row[x]:
                # Clear this bit to 0 (= palette index 0 = black).
                row_buf[x >> 3] &= ~(0x80 >> (x & 7)) & 0xFF
        out += row_buf
    return bytes(out)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def render_thumbnail(
    shapes: Sequence[IRShape],
    mat_width_mm: float = MAT_WIDTH_MM,
    mat_height_mm: float = MAT_HEIGHT_MM,
) -> bytes:
    """Render IR shapes to an 88×88 1-bit BMP suitable for embedding in an FCM.

    The geometry is scaled so the full mat working area maps onto the
    thumbnail with a small margin. White background, black ink.

    Args:
        shapes: IR shapes in world (mat-edge-relative) coordinates.
        mat_width_mm: Mat working-area width, defaulting to the standard
            ScanNCut value.
        mat_height_mm: Mat working-area height, defaulting to the standard
            ScanNCut value.

    Returns:
        Raw BMP bytes (1118 bytes for the default 88×88 size).
    """
    bitmap = _MonoBitmap(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)

    drawable_w = THUMBNAIL_WIDTH - 2 * _THUMBNAIL_MARGIN_PX
    drawable_h = THUMBNAIL_HEIGHT - 2 * _THUMBNAIL_MARGIN_PX
    scale = min(drawable_w / mat_width_mm, drawable_h / mat_height_mm)

    def to_px(x_mm: float, y_mm: float) -> tuple[int, int]:
        return (
            _THUMBNAIL_MARGIN_PX + round(x_mm * scale),
            _THUMBNAIL_MARGIN_PX + round(y_mm * scale),
        )

    for shape in shapes:
        polyline_mm = _shape_polyline_mm(shape)
        if len(polyline_mm) < 2:
            continue
        polyline_px = [to_px(x, y) for x, y in polyline_mm]
        for (x0, y0), (x1, y1) in pairwise(polyline_px):
            bitmap.draw_line(x0, y0, x1, y1)

    return _encode_bmp_1bit(bitmap)


__all__ = ["THUMBNAIL_HEIGHT", "THUMBNAIL_WIDTH", "render_thumbnail"]
