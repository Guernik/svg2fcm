"""Serialise the FCM dataclass model back to bytes.

The encoder is **deterministic and byte-exact**: round-tripping any of the
checked-in sample files through :func:`~svg2fcm.fcm.parser.parse_fcm` and back
through :func:`encode_fcm` produces the original bytes byte-for-byte. The
round-trip property is enforced by ``tests/integration/test_round_trip.py``.

The entry point is :func:`encode_fcm`. All encoding failures raise
:exc:`svg2fcm.exceptions.FcmEncodeError`.
"""

from __future__ import annotations

import struct
from io import BytesIO

from svg2fcm.exceptions import FcmEncodeError
from svg2fcm.fcm import constants as fcm_const
from svg2fcm.fcm.model import (
    AlignmentData,
    CutData,
    FcmFile,
    FileHeader,
    Generator,
    Outline,
    Path,
    Piece,
    Point,
    SegmentBezier,
    SegmentLine,
)


class _Writer:
    """Tiny byte-buffer helper with primitive writers."""

    __slots__ = ("_buf",)

    def __init__(self) -> None:
        self._buf = BytesIO()

    def write(self, b: bytes) -> None:
        self._buf.write(b)

    def u8(self, v: int) -> None:
        self._buf.write(struct.pack("<B", v))

    def u16(self, v: int) -> None:
        self._buf.write(struct.pack("<H", v))

    def u32(self, v: int) -> None:
        self._buf.write(struct.pack("<I", v))

    def i32(self, v: int) -> None:
        self._buf.write(struct.pack("<i", v))

    def f32(self, v: float) -> None:
        self._buf.write(struct.pack("<f", v))

    def point(self, p: Point) -> None:
        self._buf.write(struct.pack("<ii", p.x, p.y))

    def utf8_fixed(self, s: str, n: int) -> None:
        encoded = s.encode("utf-8")
        if len(encoded) > n:
            raise FcmEncodeError(f"UTF-8 string {s!r} exceeds fixed width {n}")
        self._buf.write(encoded.ljust(n, b"\x00"))

    def length_utf16(self, s: str) -> None:
        if len(s) > 255:
            raise FcmEncodeError(f"UTF-16 string {s!r} exceeds max length 255")
        self.u8(len(s))
        for ch in s:
            self.u16(ord(ch))

    def value(self) -> bytes:
        return self._buf.getvalue()


# ---------------------------------------------------------------------------
# Encoders for each model record
# ---------------------------------------------------------------------------


def _encode_generator(g: Generator) -> bytes:
    w = _Writer()
    if g.kind == "1APP":
        w.write(fcm_const.GENERATOR_APP_TAG)
        w.u32(g.version)
    elif g.kind == "1WEB":
        w.write(fcm_const.GENERATOR_WEB_TAG)
        w.u32(g.version)
    elif g.kind == "device":
        if g.device_id is None:
            raise FcmEncodeError("Generator kind='device' requires device_id")
        w.u32(g.device_id)
        w.u32(g.version)
    else:  # pragma: no cover — exhaustive on Literal
        raise FcmEncodeError(f"Unknown generator kind: {g.kind!r}")
    return w.value()


def _encode_header(h: FileHeader) -> bytes:
    # Build the dynamic block first so we can prefix it with its length.
    dyn = _Writer()
    dyn.utf8_fixed(h.short_name, 8)
    dyn.length_utf16(h.long_name)
    dyn.length_utf16(h.author_name)
    dyn.length_utf16(h.copyright)
    dyn.u8(h.thumbnail_block_size_width)
    dyn.u8(h.thumbnail_block_size_height)
    dyn.u32(len(h.thumbnail))
    dyn.write(h.thumbnail)
    dyn.write(_encode_generator(h.generator))
    if h.print_to_cut is not None:
        dyn.u32(1 if h.print_to_cut else 0)
    dyn_bytes = dyn.value()

    out = _Writer()
    out.write(h.variant.encode("ascii"))
    version_bytes = h.version.encode("ascii")[:4].ljust(4, b"0")
    out.write(version_bytes)
    out.u32(h.content_id)
    out.u32(len(dyn_bytes))
    out.write(dyn_bytes)
    return out.value()


def _encode_alignment(a: AlignmentData) -> bytes:
    w = _Writer()
    w.u32(1 if a.needed else 0)
    w.u32(len(a.marks))
    for mark in a.marks:
        w.point(mark)
    return w.value()


def _encode_cut_data(c: CutData) -> bytes:
    w = _Writer()
    w.u32(c.file_type)
    w.u32(c.mat_id)
    w.u32(c.cut_width)
    w.u32(c.cut_height)
    w.u32(c.seam_allowance_width)
    if c.alignment is not None:
        w.write(_encode_alignment(c.alignment))
    return w.value()


def _encode_outline(o: Outline) -> bytes:
    w = _Writer()
    if o.kind == "line":
        w.u32(fcm_const.OUTLINE_TAG_LINE)
        w.u32(len(o.segments))
        for seg in o.segments:
            if not isinstance(seg, SegmentLine):
                raise FcmEncodeError(
                    f"Outline kind='line' contains non-line segment {type(seg).__name__}",
                )
            w.point(seg.end)
    elif o.kind == "bezier":
        w.u32(fcm_const.OUTLINE_TAG_BEZIER)
        w.u32(len(o.segments))
        for seg in o.segments:
            if not isinstance(seg, SegmentBezier):
                raise FcmEncodeError(
                    f"Outline kind='bezier' contains non-bezier segment {type(seg).__name__}",
                )
            w.point(seg.control1)
            w.point(seg.control2)
            w.point(seg.end)
    else:  # pragma: no cover — exhaustive on Literal
        raise FcmEncodeError(f"Bad outline kind: {o.kind!r}")
    return w.value()


def _encode_path(p: Path) -> bytes:
    w = _Writer()
    # The tool field is itself length-prefixed: u32 length=4, then u32 bits.
    w.u32(4)
    w.u32(p.tool)
    n_outlines = len(p.shape.outlines) if p.shape else 0
    w.u32(n_outlines)
    w.u32(len(p.rhinestones))
    if p.rhinestone_diameter is None:
        w.u32(fcm_const.RHINESTONE_DIAMETER_NONE)
    else:
        w.u32(p.rhinestone_diameter)
    if p.shape is not None:
        w.point(p.shape.start)
        for o in p.shape.outlines:
            w.write(_encode_outline(o))
    for pt in p.rhinestones:
        w.point(pt)
    return w.value()


def _encode_piece(piece: Piece) -> bytes:
    w = _Writer()
    w.write(b"\x00" * 8)  # 8 reserved zero bytes
    w.u32(piece.width)
    w.u32(piece.height)
    if piece.transform is not None:
        w.u32(1)
        for v in piece.transform:
            w.f32(v)
    else:
        w.u32(0)
    w.u32(piece.expansion_limit_value)
    w.u32(piece.reduction_limit_value)
    w.u32(piece.restriction_flags)
    # Label slot is always length-prefixed at u32=4.
    w.u32(4)
    if piece.label:
        w.u8(1)
        label_bytes = piece.label.encode("ascii")[:3].ljust(3, b"\x00")
        w.write(label_bytes)
    else:
        w.u32(0)
    w.u32(len(piece.paths))
    for path in piece.paths:
        encoded = _encode_path(path)
        w.u32(len(encoded))
        w.write(encoded)
    return w.value()


def _encode_piece_table(pieces: list[tuple[int, Piece]]) -> bytes:
    encoded: list[tuple[int, bytes]] = [(pid, _encode_piece(p)) for pid, p in pieces]
    w = _Writer()
    w.u32(len(encoded))
    offset = 0
    for _, blob in encoded:
        w.u32(offset)
        offset += len(blob)
    w.u32(offset)  # total_length
    w.u32(len(encoded))
    for pid, _ in encoded:
        w.u16(pid)
    for _, blob in encoded:
        w.write(blob)
    return w.value()


def encode_fcm(fcm: FcmFile) -> bytes:
    """Serialise an :class:`~svg2fcm.fcm.model.FcmFile` to raw FCM bytes.

    Args:
        fcm: The in-memory FCM document.

    Returns:
        Raw FCM bytes, ready to write to disk.

    Raises:
        FcmEncodeError: If the model violates the encoder's invariants (e.g.
            a generator with kind ``"device"`` but no ``device_id``).
    """
    return (
        _encode_header(fcm.header)
        + _encode_cut_data(fcm.cut_data)
        + _encode_piece_table(fcm.pieces)
    )


def encode_fcm_to_file(fcm: FcmFile, path: str) -> None:
    """Convenience: encode ``fcm`` and write it to ``path``."""
    with open(path, "wb") as f:
        f.write(encode_fcm(fcm))


__all__ = ["encode_fcm", "encode_fcm_to_file"]
