"""Dataclass model of the Brother ScanNCut FCM file structure.

The model mirrors the byte-layout documented in ``docs/FCM_FORMAT.md``: a file
is a :class:`FileHeader` + :class:`CutData` + a list of ``(piece_id, Piece)``
pairs, where each :class:`Piece` holds one or more :class:`Path` records, and
each path's geometry is described as a :class:`PathShape` made of
:class:`Outline` records (either runs of :class:`SegmentLine` or runs of
:class:`SegmentBezier`).

All numeric coordinates are integers in units of 1/100 mm. See
``svg2fcm.fcm.constants.UNITS_PER_MM``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from svg2fcm.fcm.constants import UNITS_PER_MM

# Type alias for the affine 2D transform stored in a :class:`Piece`.
# Components are ``(a, b, c, d, tx, ty)`` matching SVG/PostScript convention:
# the transform maps ``(x, y)`` to ``(a·x + c·y + tx, b·x + d·y + ty)``.
Affine2D = tuple[float, float, float, float, float, float]


@dataclass(frozen=True, slots=True)
class Point:
    """A 2D coordinate in raw FCM units (1/100 mm).

    Attributes:
        x: Horizontal coordinate in 1/100 mm units, signed.
        y: Vertical coordinate in 1/100 mm units, signed.
    """

    x: int
    y: int

    @property
    def x_mm(self) -> float:
        """Return ``x`` expressed in millimetres."""
        return self.x / UNITS_PER_MM

    @property
    def y_mm(self) -> float:
        """Return ``y`` expressed in millimetres."""
        return self.y / UNITS_PER_MM

    def __repr__(self) -> str:
        return f"({self.x_mm:.3f}, {self.y_mm:.3f})mm"


@dataclass(frozen=True, slots=True)
class SegmentLine:
    """A straight-line segment ending at :attr:`end`.

    The implicit start point is the previous segment's end (or the
    :class:`PathShape`'s ``start`` for the first segment).
    """

    end: Point


@dataclass(frozen=True, slots=True)
class SegmentBezier:
    """A cubic Bézier segment.

    The implicit start point is the previous segment's end (or the
    :class:`PathShape`'s ``start`` for the first segment).

    Attributes:
        control1: First Bézier control point.
        control2: Second Bézier control point.
        end: Segment endpoint.
    """

    control1: Point
    control2: Point
    end: Point


OutlineKind = Literal["line", "bezier"]


@dataclass(slots=True)
class Outline:
    """A run of consecutive segments of the same kind.

    A :class:`PathShape` is a sequence of outlines; outlines of different
    kinds alternate to express a path that mixes straight runs and curve runs.

    Attributes:
        kind: Either ``"line"`` or ``"bezier"``.
        segments: List of :class:`SegmentLine` or :class:`SegmentBezier`
            (homogeneous; the list element type matches :attr:`kind`).
    """

    kind: OutlineKind
    segments: list[SegmentLine] | list[SegmentBezier]


@dataclass(slots=True)
class PathShape:
    """The geometric content of a :class:`Path`.

    Attributes:
        start: First point of the path. Subsequent segments connect through
            their endpoints.
        outlines: Ordered list of :class:`Outline` records.
    """

    start: Point
    outlines: list[Outline]


@dataclass(slots=True)
class Path:
    """A single drawable path within a :class:`Piece`.

    Attributes:
        tool: ``PathTool`` bitflags (see :mod:`svg2fcm.fcm.constants`).
        rhinestone_diameter: Either an integer diameter (raw u32 as stored on
            disk) or ``None`` when the file has no rhinestones. The
            sentinel-vs-zero distinction is handled by the parser/writer.
        shape: Path geometry, or ``None`` when ``outline_count == 0``.
        rhinestones: List of rhinestone placement points.
    """

    tool: int
    rhinestone_diameter: int | None
    shape: PathShape | None
    rhinestones: list[Point]


@dataclass(slots=True)
class Piece:
    """A top-level drawable group of paths.

    A piece corresponds to one selectable design element in Canvas Workspace
    (and one item in the machine's file picker when imported).

    Attributes:
        width: Bounding-box width in 1/100 mm.
        height: Bounding-box height in 1/100 mm.
        transform: Optional 2D affine ``(a, b, c, d, tx, ty)`` placing the
            piece on the mat. ``None`` means no transform stored (identity).
        expansion_limit_value: Reserved field copied verbatim.
        reduction_limit_value: Reserved field copied verbatim.
        restriction_flags: ``PieceRestrictions`` bitflags (u32).
        label: Up to 3 ASCII characters (e.g. ``"A01"``). Empty when absent.
        paths: One or more :class:`Path` records contained in this piece.
    """

    width: int
    height: int
    transform: Affine2D | None
    expansion_limit_value: int
    reduction_limit_value: int
    restriction_flags: int
    label: str
    paths: list[Path]


@dataclass(slots=True)
class AlignmentData:
    """Print-and-cut alignment marks.

    Only present in files whose :attr:`CutData.file_type` is
    ``FILE_TYPE_PRINT_AND_CUT``.
    """

    needed: bool
    marks: list[Point]


@dataclass(slots=True)
class CutData:
    """Mat-level metadata describing how the file should be cut/drawn.

    Attributes:
        file_type: ``FILE_TYPE_CUT`` (``0x10``) or
            ``FILE_TYPE_PRINT_AND_CUT`` (``0x38``).
        mat_id: Identifier of the target mat type (0 for the default mat).
        cut_width: Mat working-area width in 1/100 mm.
        cut_height: Mat working-area height in 1/100 mm.
        seam_allowance_width: Seam allowance width in 1/100 mm.
        alignment: Print-and-cut alignment data (only when ``file_type ==
            FILE_TYPE_PRINT_AND_CUT``).
    """

    file_type: int
    mat_id: int
    cut_width: int
    cut_height: int
    seam_allowance_width: int
    alignment: AlignmentData | None


GeneratorKind = Literal["1APP", "1WEB", "device"]


@dataclass(slots=True)
class Generator:
    """Identifies which Brother application produced the file.

    Attributes:
        kind: ``"1APP"`` (desktop Canvas Workspace), ``"1WEB"`` (browser
            Canvas Workspace), or ``"device"`` (created on a ScanNCut).
        version: Generator-internal version number.
        device_id: Numeric device identifier, only meaningful for
            ``kind == "device"``.
    """

    kind: GeneratorKind
    version: int
    device_id: int | None = None


@dataclass(slots=True)
class FileHeader:
    """The variable-length FCM file header preceding the cut/piece data.

    Attributes:
        variant: ``"#FCM"`` or ``"#VCM"`` as a 4-character ASCII tag.
        version: 4-character ASCII version, e.g. ``"0100"``.
        content_id: Asset/content identifier.
        short_name: UTF-8 short name, null-padded to 8 bytes on disk.
        long_name: UTF-16 long name (length-prefixed).
        author_name: UTF-16 author name.
        copyright: UTF-16 copyright string.
        thumbnail_block_size_width: Thumbnail block-size hint (typically 1).
        thumbnail_block_size_height: Thumbnail block-size hint (typically 1).
        thumbnail: Raw BMP bytes (88×88, 1-bit, ~1118 bytes typical).
        generator: Producer identification.
        print_to_cut: Optional bool32 flag present in some files.
    """

    variant: str
    version: str
    content_id: int
    short_name: str
    long_name: str
    author_name: str
    copyright: str
    thumbnail_block_size_width: int
    thumbnail_block_size_height: int
    thumbnail: bytes
    generator: Generator
    print_to_cut: bool | None


@dataclass(slots=True)
class FcmFile:
    """Top-level container for a parsed FCM document.

    Attributes:
        header: The :class:`FileHeader` describing metadata and the embedded
            thumbnail.
        cut_data: Mat dimensions, file type, and print-and-cut alignment.
        pieces: Ordered list of ``(piece_id, Piece)`` tuples. ``piece_id`` is
            the u16 identifier the file stores in its piece-id table.
    """

    header: FileHeader
    cut_data: CutData
    pieces: list[tuple[int, Piece]] = field(default_factory=list)
