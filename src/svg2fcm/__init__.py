"""svg2fcm — convert SVG files to Brother ScanNCut FCM format for pen plotting.

Public API surface:
    from svg2fcm import FcmFile, parse_fcm, encode_fcm

The submodules are organised as:
    svg2fcm.fcm.model    — the dataclass model of an FCM file
    svg2fcm.fcm.parser   — bytes → FcmFile
    svg2fcm.fcm.writer   — FcmFile → bytes
    svg2fcm.fcm.constants — named constants and bitflag tables
    svg2fcm.svg.loader   — SVG → list of IRShape (Phase 4, in progress)
    svg2fcm.thumbnail    — IRShape list → 88×88 1-bit BMP bytes (Phase 5)
    svg2fcm.cli          — argparse entry point (Phase 6)
"""

from __future__ import annotations

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
from svg2fcm.fcm.parser import parse_fcm
from svg2fcm.fcm.writer import encode_fcm

__all__ = [
    "AlignmentData",
    "CutData",
    "FcmFile",
    "FileHeader",
    "Generator",
    "Outline",
    "Path",
    "PathShape",
    "Piece",
    "Point",
    "SegmentBezier",
    "SegmentLine",
    "encode_fcm",
    "parse_fcm",
]

__version__ = "0.3.0"
