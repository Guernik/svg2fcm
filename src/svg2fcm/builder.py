"""Assemble :class:`~svg2fcm.fcm.model.FcmFile` records from IR shapes.

This is the bridge between the SVG layer (:mod:`svg2fcm.svg.loader`) and the
FCM byte encoder (:mod:`svg2fcm.fcm.writer`): given a list of IR shapes plus
a rendered thumbnail, produce an in-memory FCM document.

The function is pure and side-effect free — the CLI handles I/O.
"""

from __future__ import annotations

from collections.abc import Sequence

from svg2fcm.fcm.constants import (
    DEFAULT_CONTENT_ID,
    DEFAULT_GENERATOR_VERSION,
    DEFAULT_HEADER_PLACEHOLDER,
    DEFAULT_PIECE_RESTRICTION_FLAGS,
    DEFAULT_THUMBNAIL_BLOCK_SIZE,
    FCM_VERSION_DEFAULT,
    FILE_TYPE_CUT,
    MAT_HEIGHT_UNITS,
    MAT_WIDTH_UNITS,
    TOOL_DRAW_CLOSED,
    TOOL_DRAW_OPEN,
    UNITS_PER_MM,
)
from svg2fcm.fcm.model import (
    CutData,
    FcmFile,
    FileHeader,
    Generator,
    Outline,
    Path,
    PathShape,
    Piece,
    Point,
    SegmentBezier,
    SegmentLine,
)
from svg2fcm.svg.loader import IRShape

#: Default mat seam allowance width used when generating fresh files.
_DEFAULT_SEAM_ALLOWANCE: int = 2000


def _piece_label(index: int) -> str:
    """Return the Canvas Workspace–style label for the ``index``-th piece.

    Indexing is zero-based; labels are ``"A01"``, ``"A02"``, ..., ``"A99"``.
    The label slot only holds three ASCII characters, so callers must keep
    designs to fewer than 100 pieces. Pieces past that limit get an empty
    label — the file remains valid, just unlabeled.
    """
    one_based = index + 1
    if 1 <= one_based <= 99:
        return f"A{one_based:02d}"
    return ""


def _shape_to_piece(shape: IRShape, label: str) -> Piece:
    """Convert one :class:`IRShape` to a :class:`~svg2fcm.fcm.model.Piece`.

    The SVG (0, 0) origin maps to the top-left of the ScanNCut **drawable
    area** (i.e. inside the 3 mm mat margin), so a shape placed at SVG
    (0, 0) lands at Canvas Workspace UI position (3, 3) — the corner of
    the red zone where the pen can actually draw.
    """
    width_units = round(shape.width_mm * UNITS_PER_MM)
    height_units = round(shape.height_mm * UNITS_PER_MM)

    # transform.tx/ty are measured from the mat edge to the piece centre.
    # CW UI corner = tx + 3 mm - half_w. We want SVG x=0 → CW UI 3 mm
    # (drawable-area origin), i.e. corner = SVG_left + 3 = cx - half_w + 3,
    # which gives tx = cx exactly. No additional offset needed.
    tx_mm = shape.center_x_mm
    ty_mm = shape.center_y_mm
    transform = (
        1.0,
        0.0,
        0.0,
        1.0,
        tx_mm * UNITS_PER_MM,
        ty_mm * UNITS_PER_MM,
    )

    tool = TOOL_DRAW_OPEN if shape.is_open else TOOL_DRAW_CLOSED

    return Piece(
        width=width_units,
        height=height_units,
        transform=transform,
        expansion_limit_value=0,
        reduction_limit_value=0,
        restriction_flags=DEFAULT_PIECE_RESTRICTION_FLAGS,
        label=label,
        paths=[
            Path(
                tool=tool,
                rhinestone_diameter=0,
                shape=PathShape(start=shape.start_point, outlines=list(shape.outlines)),
                rhinestones=[],
            ),
        ],
    )


def _shape_to_path(shape: IRShape, piece_cx_mm: float, piece_cy_mm: float) -> Path:
    """Convert one :class:`IRShape` into a piece-local :class:`Path`.

    The shape's outlines and start point arrive expressed relative to the
    shape's own centre. We translate them so they are expressed relative
    to the **piece** centre at ``(piece_cx_mm, piece_cy_mm)`` — the only
    coordinate frame the FCM file stores for paths inside a piece.
    """
    dx_units = round((shape.center_x_mm - piece_cx_mm) * UNITS_PER_MM)
    dy_units = round((shape.center_y_mm - piece_cy_mm) * UNITS_PER_MM)

    def _translate(p: Point) -> Point:
        return Point(p.x + dx_units, p.y + dy_units)

    translated_outlines: list[Outline] = []
    for outline in shape.outlines:
        if outline.kind == "line":
            line_segments = [
                SegmentLine(_translate(s.end))
                for s in outline.segments
                if isinstance(s, SegmentLine)
            ]
            translated_outlines.append(Outline(kind="line", segments=line_segments))
        else:
            bezier_segments = [
                SegmentBezier(
                    control1=_translate(s.control1),
                    control2=_translate(s.control2),
                    end=_translate(s.end),
                )
                for s in outline.segments
                if isinstance(s, SegmentBezier)
            ]
            translated_outlines.append(Outline(kind="bezier", segments=bezier_segments))

    tool = TOOL_DRAW_OPEN if shape.is_open else TOOL_DRAW_CLOSED
    return Path(
        tool=tool,
        rhinestone_diameter=0,
        shape=PathShape(start=_translate(shape.start_point), outlines=translated_outlines),
        rhinestones=[],
    )


def _grouped_piece(shapes: Sequence[IRShape], label: str) -> Piece:
    """Bundle every shape into a single :class:`Piece` with one :class:`Path` per shape.

    The machine refuses to import files with too many independent pieces
    (observed failure with ~100 pieces). Canvas Workspace's "select all
    → group" action collapses everything into a single piece whose
    ``paths`` list holds every original path, and that import succeeds.
    This function emits that grouped form directly.

    The piece's bounding box is the union of all shapes' bounding boxes.
    Each shape's path is translated so its coordinates are relative to
    the combined piece centre rather than the shape's own centre.
    """
    min_x = min(s.center_x_mm - s.width_mm / 2.0 for s in shapes)
    min_y = min(s.center_y_mm - s.height_mm / 2.0 for s in shapes)
    max_x = max(s.center_x_mm + s.width_mm / 2.0 for s in shapes)
    max_y = max(s.center_y_mm + s.height_mm / 2.0 for s in shapes)

    piece_w_mm = max_x - min_x
    piece_h_mm = max_y - min_y
    piece_cx_mm = (min_x + max_x) / 2.0
    piece_cy_mm = (min_y + max_y) / 2.0

    transform = (
        1.0,
        0.0,
        0.0,
        1.0,
        piece_cx_mm * UNITS_PER_MM,
        piece_cy_mm * UNITS_PER_MM,
    )

    paths = [_shape_to_path(shape, piece_cx_mm, piece_cy_mm) for shape in shapes]

    return Piece(
        width=round(piece_w_mm * UNITS_PER_MM),
        height=round(piece_h_mm * UNITS_PER_MM),
        transform=transform,
        expansion_limit_value=0,
        reduction_limit_value=0,
        restriction_flags=DEFAULT_PIECE_RESTRICTION_FLAGS,
        label=label,
        paths=paths,
    )


def build_fcm(
    shapes: Sequence[IRShape],
    thumbnail: bytes,
    *,
    group: bool = True,
) -> FcmFile:
    """Build a complete :class:`FcmFile` from IR shapes and a thumbnail.

    Args:
        shapes: Ordered IR shapes.
        thumbnail: Raw BMP bytes for the file's preview thumbnail.
        group: When ``True`` (default), emit a single Piece containing one
            Path per shape — the same shape Canvas Workspace produces for
            "select all → group". This avoids ScanNCut import failures on
            files with many independent pieces. When ``False``, emit one
            Piece per shape (legacy behaviour). Has no effect when there
            are zero or one shapes.

    Returns:
        An in-memory FCM document, ready to encode with
        :func:`~svg2fcm.fcm.writer.encode_fcm`.
    """
    header = FileHeader(
        variant="#FCM",
        version=FCM_VERSION_DEFAULT,
        content_id=DEFAULT_CONTENT_ID,
        short_name="",
        long_name=DEFAULT_HEADER_PLACEHOLDER,
        author_name=DEFAULT_HEADER_PLACEHOLDER,
        copyright=DEFAULT_HEADER_PLACEHOLDER,
        thumbnail_block_size_width=DEFAULT_THUMBNAIL_BLOCK_SIZE,
        thumbnail_block_size_height=DEFAULT_THUMBNAIL_BLOCK_SIZE,
        thumbnail=thumbnail,
        generator=Generator(kind="1APP", version=DEFAULT_GENERATOR_VERSION),
        print_to_cut=None,
    )
    cut_data = CutData(
        file_type=FILE_TYPE_CUT,
        mat_id=0,
        cut_width=MAT_WIDTH_UNITS,
        cut_height=MAT_HEIGHT_UNITS,
        seam_allowance_width=_DEFAULT_SEAM_ALLOWANCE,
        alignment=None,
    )

    pieces: list[tuple[int, Piece]]
    if group and len(shapes) > 1:
        pieces = [(0, _grouped_piece(shapes, _piece_label(0)))]
    else:
        pieces = [(i, _shape_to_piece(shape, _piece_label(i))) for i, shape in enumerate(shapes)]

    return FcmFile(header=header, cut_data=cut_data, pieces=pieces)


__all__ = ["build_fcm"]
