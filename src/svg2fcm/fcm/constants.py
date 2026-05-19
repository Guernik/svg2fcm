"""Named constants and bitflag tables for the FCM binary format.

Every magic number used by the parser, writer, and SVG-to-FCM mapping layer
lives here, so the rest of the codebase is self-documenting. Values were
sourced from:

* The upstream MPL-2.0 reference implementation `justjanne/fcmlib`,
  validated against 1000+ Canvas Workspace–produced samples.
* Cross-checks against locally produced sample files (square, circle, line in
  draw mode, line in cut mode).

See ``docs/FCM_FORMAT.md`` for the full byte-layout spec.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# Units and geometry
# ---------------------------------------------------------------------------

#: FCM stores all coordinates as signed 32-bit integers in units of 1/100 mm.
UNITS_PER_MM: Final = 100

#: Canvas Workspace's position UI is measured from a point 3 mm in from the
#: mat edge, while the on-disk ``transform`` is mat-edge-relative. When
#: replicating Canvas Workspace's storage convention from a "UI position",
#: subtract this margin from each axis.
CW_UI_OFFSET_MM: Final = 4.0

#: ScanNCut mat working area, in millimetres. Sourced from the ``cut_width``
#: and ``cut_height`` fields of every Canvas Workspace sample we've parsed
#: (29667 × 29880 = 296.67 × 298.80 mm).
MAT_WIDTH_MM: Final = 296.67
MAT_HEIGHT_MM: Final = 298.80

# Same dimensions in raw FCM units, ready to drop into ``CutData``.
MAT_WIDTH_UNITS: Final = 29667
MAT_HEIGHT_UNITS: Final = 29880

# ---------------------------------------------------------------------------
# File header magic
# ---------------------------------------------------------------------------

FCM_VARIANT_TAG: Final = b"#FCM"
VCM_VARIANT_TAG: Final = b"#VCM"
FCM_VERSION_DEFAULT: Final = "0100"

# Generator tags inside the file header.
GENERATOR_APP_TAG: Final = b"1APP"
GENERATOR_WEB_TAG: Final = b"1WEB"

# ---------------------------------------------------------------------------
# CutData::file_type
# ---------------------------------------------------------------------------

FILE_TYPE_CUT: Final = 0x10
FILE_TYPE_PRINT_AND_CUT: Final = 0x38

# ---------------------------------------------------------------------------
# Outline tag (u32 discriminator before each Outline)
# ---------------------------------------------------------------------------

OUTLINE_TAG_LINE: Final = 0
OUTLINE_TAG_BEZIER: Final = 1

# ---------------------------------------------------------------------------
# PathTool bitflags (u32)
# ---------------------------------------------------------------------------

PATH_OPEN: Final = 0x0001
TOOL_CUT: Final = 0x0002
TOOL_DRAW: Final = 0x0004
SEAM_ALLOWANCE: Final = 0x0008
TOOL_RHINESTONE: Final = 0x0010
FILL: Final = 0x0020
AUTO_ALIGN: Final = 0x0040
TOOL_DRAW_ONLY: Final = 0x1000
TOOL_EMBOSS: Final = 0x2000
TOOL_FOIL: Final = 0x4000
TOOL_PERFORATING: Final = 0x8000

#: Mapping bit → human-readable name, for pretty-printing.
PATH_TOOL_FLAG_NAMES: Final[dict[int, str]] = {
    PATH_OPEN: "PATH_OPEN",
    TOOL_CUT: "TOOL_CUT",
    TOOL_DRAW: "TOOL_DRAW",
    SEAM_ALLOWANCE: "SEAM_ALLOWANCE",
    TOOL_RHINESTONE: "TOOL_RHINESTONE",
    FILL: "FILL",
    AUTO_ALIGN: "AUTO_ALIGN",
    TOOL_DRAW_ONLY: "TOOL_DRAW_ONLY",
    TOOL_EMBOSS: "TOOL_EMBOSS",
    TOOL_FOIL: "TOOL_FOIL",
    TOOL_PERFORATING: "TOOL_PERFORATING",
}

# Canonical bit combinations actually emitted by Canvas Workspace:
#: Open path drawn with a pen.
TOOL_DRAW_OPEN: Final = PATH_OPEN | TOOL_DRAW | TOOL_DRAW_ONLY  # 0x1005
#: Closed path drawn with a pen.
TOOL_DRAW_CLOSED: Final = TOOL_DRAW | TOOL_DRAW_ONLY  # 0x1004
#: Open path to be cut.
TOOL_CUT_OPEN: Final = PATH_OPEN | TOOL_CUT  # 0x0003
#: Closed path to be cut.
TOOL_CUT_CLOSED: Final = TOOL_CUT  # 0x0002

# ---------------------------------------------------------------------------
# Path::rhinestone_diameter sentinel
# ---------------------------------------------------------------------------

#: When the file has no rhinestones, ``rhinestone_diameter`` is written as
#: this sentinel value. Canvas Workspace sometimes writes a literal ``0``
#: instead; both must round-trip correctly.
RHINESTONE_DIAMETER_NONE: Final = 0x3F000000

# ---------------------------------------------------------------------------
# Header constants used by the CLI when synthesising a fresh FCM file
# ---------------------------------------------------------------------------
#
# These values were extracted from ``line_draw_REFERENCE.fcm`` (a Canvas
# Workspace-produced file). The combination is known to be accepted by the
# machine and by Canvas Workspace.

#: Default ``content_id`` for files we generate.
DEFAULT_CONTENT_ID: Final = 400000002

#: Default ``long_name``/``author_name``/``copyright`` — a single space.
#: Canvas Workspace writes a single space for empty UTF-16 string slots.
DEFAULT_HEADER_PLACEHOLDER: Final = " "

#: Default thumbnail block-size hint (observed value).
DEFAULT_THUMBNAIL_BLOCK_SIZE: Final = 3

#: Default generator version we identify ourselves with.
DEFAULT_GENERATOR_VERSION: Final = 206

#: Default piece restriction flags (observed in reference files).
DEFAULT_PIECE_RESTRICTION_FLAGS: Final = 0x4
