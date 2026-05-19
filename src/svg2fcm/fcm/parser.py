"""Read a Brother ScanNCut FCM file into the dataclass model.

The entry point is :func:`parse_fcm`. All parse failures raise
:exc:`svg2fcm.exceptions.FcmParseError`.

The byte layout we parse is documented at ``docs/FCM_FORMAT.md``.
"""

from __future__ import annotations

import struct

from svg2fcm.exceptions import FcmParseError
from svg2fcm.fcm import constants as fcm_const
from svg2fcm.fcm.model import (
    AlignmentData,
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


class _Reader:
    """Cursor over a byte buffer with primitive readers and EOF checks."""

    __slots__ = ("_data", "_pos")

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    @property
    def pos(self) -> int:
        """Current cursor offset."""
        return self._pos

    def remaining(self) -> int:
        """Bytes left to read after the cursor."""
        return len(self._data) - self._pos

    def take(self, n: int) -> bytes:
        """Consume exactly ``n`` bytes; raise on EOF."""
        if self._pos + n > len(self._data):
            raise FcmParseError(
                f"Unexpected EOF: needed {n} bytes at offset {self._pos}, "
                f"only {len(self._data) - self._pos} remain",
            )
        out = self._data[self._pos : self._pos + n]
        self._pos += n
        return out

    def skip_to(self, offset: int) -> None:
        """Set the cursor to an absolute offset (must be ≥ current pos)."""
        if offset < self._pos or offset > len(self._data):
            raise FcmParseError(
                f"Invalid skip target {offset} (cursor at {self._pos}, end {len(self._data)})",
            )
        self._pos = offset

    def u8(self) -> int:
        return self.take(1)[0]

    def u16(self) -> int:
        (value,) = struct.unpack("<H", self.take(2))
        return int(value)

    def u32(self) -> int:
        (value,) = struct.unpack("<I", self.take(4))
        return int(value)

    def i32(self) -> int:
        (value,) = struct.unpack("<i", self.take(4))
        return int(value)

    def f32(self) -> float:
        (value,) = struct.unpack("<f", self.take(4))
        return float(value)

    def bool32(self) -> bool:
        return self.u32() != 0

    def point(self) -> Point:
        return Point(self.i32(), self.i32())

    def utf8_fixed(self, n: int) -> str:
        raw = self.take(n)
        end = raw.find(b"\x00")
        if end == -1:
            end = n
        return raw[:end].decode("utf-8", errors="replace")

    def length_utf16(self) -> str:
        n = self.u8()
        chars = [self.u16() for _ in range(n)]
        return "".join(chr(c) for c in chars)


def _parse_generator(r: _Reader) -> Generator:
    tag = r.take(4)
    version = r.u32()
    if tag == fcm_const.GENERATOR_APP_TAG:
        return Generator("1APP", version)
    if tag == fcm_const.GENERATOR_WEB_TAG:
        return Generator("1WEB", version)
    # device variant: the first 4 bytes were a device_id, not a tag
    (device_id,) = struct.unpack("<I", tag)
    return Generator("device", version, int(device_id))


def _parse_header(r: _Reader) -> FileHeader:
    variant_tag = r.take(4)
    if variant_tag not in (fcm_const.FCM_VARIANT_TAG, fcm_const.VCM_VARIANT_TAG):
        raise FcmParseError(f"Bad file magic: {variant_tag!r}")
    variant = variant_tag.decode("ascii")
    version = r.take(4).decode("ascii")
    content_id = r.u32()
    dyn_len = r.u32()
    dyn_end = r.pos + dyn_len

    short_name = r.utf8_fixed(8)
    long_name = r.length_utf16()
    author_name = r.length_utf16()
    copyright_str = r.length_utf16()
    tb_w = r.u8()
    tb_h = r.u8()
    tn_len = r.u32()
    thumbnail = r.take(tn_len)
    generator = _parse_generator(r)
    print_to_cut: bool | None = None
    if r.pos < dyn_end:
        # Optional bool32 trailer.
        print_to_cut = r.bool32()
    if r.pos != dyn_end:
        # There are bytes we don't yet understand; preserve forward
        # compatibility by jumping past them.
        r.skip_to(dyn_end)

    return FileHeader(
        variant=variant,
        version=version,
        content_id=content_id,
        short_name=short_name,
        long_name=long_name,
        author_name=author_name,
        copyright=copyright_str,
        thumbnail_block_size_width=tb_w,
        thumbnail_block_size_height=tb_h,
        thumbnail=thumbnail,
        generator=generator,
        print_to_cut=print_to_cut,
    )


def _parse_alignment(r: _Reader) -> AlignmentData:
    needed = r.bool32()
    n = r.u32()
    marks = [r.point() for _ in range(n)]
    return AlignmentData(needed, marks)


def _parse_cut_data(r: _Reader) -> CutData:
    file_type = r.u32()
    mat_id = r.u32()
    cut_w = r.u32()
    cut_h = r.u32()
    seam = r.u32()
    alignment = _parse_alignment(r) if file_type == fcm_const.FILE_TYPE_PRINT_AND_CUT else None
    return CutData(file_type, mat_id, cut_w, cut_h, seam, alignment)


def _parse_outline(r: _Reader) -> Outline:
    tag = r.u32()
    n = r.u32()
    if tag == fcm_const.OUTLINE_TAG_LINE:
        line_segments: list[SegmentLine] = [SegmentLine(r.point()) for _ in range(n)]
        return Outline("line", line_segments)
    if tag == fcm_const.OUTLINE_TAG_BEZIER:
        bezier_segments: list[SegmentBezier] = []
        for _ in range(n):
            c1 = r.point()
            c2 = r.point()
            end = r.point()
            bezier_segments.append(SegmentBezier(c1, c2, end))
        return Outline("bezier", bezier_segments)
    raise FcmParseError(f"Unexpected outline tag: {tag}")


def _parse_path(r: _Reader) -> Path:
    tool_len = r.u32()
    if tool_len != 4:
        raise FcmParseError(f"Unexpected tool length: {tool_len} (expected 4)")
    tool = r.u32()
    outline_count = r.u32()
    rhinestone_count = r.u32()
    rd_raw = r.u32()
    rhinestone_diameter: int | None
    rhinestone_diameter = None if rd_raw == fcm_const.RHINESTONE_DIAMETER_NONE else rd_raw

    shape: PathShape | None = None
    if outline_count > 0:
        start = r.point()
        outlines = [_parse_outline(r) for _ in range(outline_count)]
        shape = PathShape(start, outlines)

    rhinestones = [r.point() for _ in range(rhinestone_count)]
    return Path(tool, rhinestone_diameter, shape, rhinestones)


def _parse_piece(r: _Reader) -> Piece:
    r.take(8)  # 8 reserved bytes, observed as zero in every sample
    width = r.u32()
    height = r.u32()
    has_transform = r.bool32()
    transform: tuple[float, float, float, float, float, float] | None = None
    if has_transform:
        a = r.f32()
        b = r.f32()
        c = r.f32()
        d = r.f32()
        tx = r.f32()
        ty = r.f32()
        transform = (a, b, c, d, tx, ty)
    expansion = r.u32()
    reduction = r.u32()
    restriction = r.u32()
    label_len = r.u32()
    if label_len == 0:
        label = ""
    else:
        label_bytes = r.take(label_len)
        if label_bytes and label_bytes[0] == 1:
            label = label_bytes[1:4].decode("ascii", errors="replace")
        else:
            label = ""
    paths_count = r.u32()
    paths: list[Path] = []
    for _ in range(paths_count):
        path_len = r.u32()
        sub_data = r.take(path_len)
        sub_reader = _Reader(sub_data)
        paths.append(_parse_path(sub_reader))
    return Piece(
        width=width,
        height=height,
        transform=transform,
        expansion_limit_value=expansion,
        reduction_limit_value=reduction,
        restriction_flags=restriction,
        label=label,
        paths=paths,
    )


def _parse_piece_table(r: _Reader) -> list[tuple[int, Piece]]:
    n_off = r.u32()
    offsets = [r.u32() for _ in range(n_off)]
    total_length = r.u32()
    n_ids = r.u32()
    if n_ids != n_off:
        raise FcmParseError(f"Piece-table id count {n_ids} ≠ offset count {n_off}")
    ids = [r.u16() for _ in range(n_ids)]
    piece_block = r.take(total_length)
    pieces: list[tuple[int, Piece]] = []
    for piece_id, offset in zip(ids, offsets, strict=True):
        sub_reader = _Reader(piece_block[offset:])
        pieces.append((piece_id, _parse_piece(sub_reader)))
    return pieces


def parse_fcm(data: bytes) -> FcmFile:
    """Parse a complete FCM byte stream.

    Args:
        data: Raw FCM file bytes.

    Returns:
        The parsed :class:`~svg2fcm.fcm.model.FcmFile`.

    Raises:
        FcmParseError: If the byte stream is not a valid FCM file.
    """
    r = _Reader(data)
    header = _parse_header(r)
    cut_data = _parse_cut_data(r)
    pieces = _parse_piece_table(r)
    return FcmFile(header=header, cut_data=cut_data, pieces=pieces)


# A helper occasionally useful in tests / debugging.
def parse_fcm_file(path: str) -> FcmFile:
    """Parse an FCM file from disk.

    Args:
        path: Filesystem path to a ``.fcm`` file.

    Returns:
        The parsed :class:`~svg2fcm.fcm.model.FcmFile`.
    """
    with open(path, "rb") as f:
        return parse_fcm(f.read())


__all__ = ["parse_fcm", "parse_fcm_file"]
