# Brother ScanNCut FCM Format

Based on [justjanne/fcmlib](https://github.com/justjanne/fcmlib) (MPL-2.0, an
upstream Rust reference implementation validated against 1000+ samples) and
cross-checked against two locally-produced sample files. All integers are
**little-endian**.

> **Interoperability notice.** The FCM format is not publicly documented
> by Brother Industries, Ltd. This document was assembled from public
> open-source reference implementations and from byte-level observation
> of files produced by Canvas Workspace, **for the sole purpose of
> enabling an independently-created program (`svg2fcm`) to interoperate
> with the ScanNCut machine**. This is the kind of activity protected
> under 17 U.S.C. §1201(f) (US DMCA reverse-engineering for
> interoperability) and Article 6 of EU Directive 2009/24/EC. "Brother",
> "ScanNCut", and "Canvas Workspace" are trademarks of Brother
> Industries, Ltd.; this project is not affiliated with or endorsed by
> Brother.

## Top-level layout

```
FcmFile = FileHeader + CutData + PieceTable
```

No other framing. Once the header ends, cut data starts; once cut data ends,
the piece table starts.

---

## 1. FileHeader

| Bytes        | Field                       | Notes |
|--------------|-----------------------------|-------|
| 4            | `FileVariant`               | ASCII `#FCM` or `#VCM` |
| 4            | `version`                   | ASCII e.g. `0100` |
| 4            | `content_id` (u32)          | Content/asset ID |
| 4            | `dynamic_length` (u32)      | Length in bytes of the dynamic block that follows |
| `dynamic_length` | dynamic block           | See below |

### Dynamic block

| Bytes | Field | Notes |
|-------|-------|-------|
| 8     | `short_name` | UTF-8, null-padded to 8 bytes |
| 1+N×2 | `long_name`  | u8 length (chars) + UTF-16LE chars |
| 1+N×2 | `author_name` | u8 length + UTF-16LE |
| 1+N×2 | `copyright`   | u8 length + UTF-16LE |
| 1     | `thumbnail_block_size_width` (u8)  | Always seen as 1 |
| 1     | `thumbnail_block_size_height` (u8) | Always seen as 1 |
| 4     | `thumbnail_byte_length` (u32) | |
| N     | `thumbnail` | Raw bytes — a complete BMP file (the 88×88 1-bit thumbnail) |
| 4+    | `Generator`  | One of: `"1APP"+u32 version`, `"1WEB"+u32 version`, or `u32 device_id + u32 version` |
| 0 or 4 | `print_to_cut` (optional bool32) | Present in some files |

**Important correction**: the `1APP` marker is the *generator tag inside the
header*, not a "start of objects" marker. The header is fully length-prefixed,
so the cut data begins at `offset 16 + dynamic_length`, not at `1APP`.

---

## 2. CutData

| Bytes | Field | Notes |
|-------|-------|-------|
| 4 | `FileType` (u32) | `0x10` = `Cut`, `0x38` = `PrintAndCut` |
| 4 | `mat_id` (u32) | |
| 4 | `cut_width` (u32) | |
| 4 | `cut_height` (u32) | |
| 4 | `seam_allowance_width` (u32) | |
| ? | `AlignmentData` | **Only present if `FileType == PrintAndCut`** |

### AlignmentData (only for PrintAndCut)

| Bytes | Field |
|-------|-------|
| 4 | `needed` (bool32) |
| 4 | `marks_count` (u32) |
| 8×N | `marks` — array of `Point` (i32 x, i32 y) |

---

## 3. PieceTable

A "piece" is a top-level cut/draw object (one shape or a grouped set of paths).

```
piece_count : u32
offsets     : u32 × piece_count   (offsets into piece data block)
total_length: u32                 (length of piece data block)
ids_count   : u32   (== piece_count)
ids         : u16 × piece_count
piece_data  : raw bytes of length total_length
```

Each entry in `piece_data` is a `Piece`, located by the corresponding offset.

### Piece

| Bytes | Field | Notes |
|-------|-------|-------|
| 8 | (reserved, written as zeros) | |
| 4 | `width` (u32) | piece bounding-box width in 1/50 mm |
| 4 | `height` (u32) | piece bounding-box height in 1/50 mm |
| 4 | `has_transform` (bool32) | |
| 24 | `transform` (six f32) | Only if `has_transform`; 2D affine matrix (a, b, c, d, tx, ty) |
| 4 | `expansion_limit_value` (u32) | |
| 4 | `reduction_limit_value` (u32) | |
| 4 | `PieceRestrictions` (u32 bitflags) | See below |
| 4 | `label_length` (u32) | usually 4 |
| N | `label` | If `label_length == 4`: `u8 marker` + 3 ASCII chars (e.g. `"BMP"`). If marker==0, treat as empty. |
| 4 | `paths_count` (u32) | |
| (`path_length`:u32 + `path_data`:bytes) × `paths_count` | Length-prefixed `Path` records |

#### PieceRestrictions bitflags (u32)

```
0x0001  LICENSE_DESIGN
0x0002  SEAM_ALLOWANCE
0x0004  PROHIBITION_OF_SEAM_ALLOWANCE_SETTING
0x0020  NO_ASPECT_RATIO_CHANGE_PROHIBITED / JUDGE_BY_USING_PERFECT_MASK_AT_AUTO_LAYOUT
0x0040  TEST_PATTERN
0x0080  PROHIBITION_OF_EDIT
0x0100  PROHIBITION_OF_TOOL
```

### Path

| Bytes | Field | Notes |
|-------|-------|-------|
| 4 | `tool_length` (u32) | always 4 |
| 4 | `PathTool` (u32 bitflags) | See below — **this is the cut/draw operation field** |
| 4 | `outline_count` (u32) | |
| 4 | `rhinestone_count` (u32) | |
| 4 | `rhinestone_diameter` | `0x3f000000` (= float 0.5, but treated as sentinel) means "none"; otherwise a u32 |
| 8 | `start_point` (Point) | Only present if `outline_count > 0` |
| ? | `outlines` × `outline_count` | Each is an `Outline` |
| 8×N | `rhinestones` × `rhinestone_count` | |

#### PathTool bitflags (u32) — operation field

```
0x0001  PATH_OPEN          (path is not closed; for open polylines)
0x0002  TOOL_CUT
0x0004  TOOL_DRAW          ← what we want for plotting
0x0008  SEAM_ALLOWANCE
0x0010  TOOL_RHINESTONE
0x0020  FILL
0x0040  AUTO_ALIGN
0x1000  TOOL_DRAW_ONLY
0x2000  TOOL_EMBOSS
0x4000  TOOL_FOIL
0x8000  TOOL_PERFORATING
```

For a closed shape drawn with a pen: `TOOL_DRAW` (= 0x0004).
For an open polyline drawn with a pen: `TOOL_DRAW | PATH_OPEN` (= 0x0005).

#### Outline

| Bytes | Field | Notes |
|-------|-------|-------|
| 4 | `OutlineTag` (u32) | `0` = Line, `1` = Bezier |
| 4 | `segment_count` (u32) | |
| ? | segments × `segment_count` | `SegmentLine` (1 Point) or `SegmentBezier` (3 Points) |

**SegmentLine**: one `Point` (end). Implicit start = previous end / path start.

**SegmentBezier**: three `Point`s — control1, control2, end. Cubic Bézier from
the implicit current point.

**Point**: two **signed** `i32`, little-endian. Units are **1/100 mm** (= 0.01 mm).

---

## Coordinate system

- Units: **1/100 mm** (`x_mm = x_units / 100.0`).
- Origin: top-left of the mat area.
- All `Point` values are signed `i32`.
- Path coordinates are **path-local, centered on the piece's origin** (so a
  200×100 mm rectangle is stored as a path running from (−100, −50) to (100, 50)).
- Object positioning is handled by the `Piece.transform` 2D affine matrix —
  specifically the `(tx, ty)` translation components, which place the piece
  origin at that mat-relative coordinate.
- **Canvas Workspace UI offset**: Canvas Workspace's position display is offset
  3 mm in from the mat edge. So `transform.tx = UI_x + half_width − 3 mm` (and
  same for `y`). When writing FCMs that match what Canvas Workspace would
  produce for a given on-screen position, add `half_extent − 3 mm`.

---

## Operation field (cut vs draw) — the one field that absolutely must be right

For an SVG→FCM plotter:

```
PathTool = TOOL_DRAW                  (0x0004) for closed shapes
         = TOOL_DRAW | PATH_OPEN      (0x0005) for open polylines/paths
```

Encoded as:
```
u32 length = 4
u32 bits   = the bitflags value
```

(That's 8 bytes total for the PathTool field, including its own length prefix.)

---

## Sanity checks vs. our two sample files

| Observation                | Value | Confirmed by |
|----------------------------|-------|--------------|
| Line span (200 mm wide)    | ±10000 units = ±100 mm | `10 27` LE = 10000 |
| Circle radius (135 mm)     | 13500 units = 135 mm  | (raw int32) |
| Cubic-Bézier kappa for circle | 13500 × 0.5523 ≈ 7455.6 | path bytes |
| Draw operation             | `0x1005` = PATH_OPEN \| TOOL_DRAW \| TOOL_DRAW_ONLY | tool field |
| Cut operation              | `0x0003` = PATH_OPEN \| TOOL_CUT | tool field |
| Circle = 4 cubic Béziers   | yes | matches kappa pattern |
| Thumbnail format           | embedded BMP, 88×88, 1-bit, ~1118 bytes | `BM` signature at offset 0x24 |
| Generator tag              | `1APP` (Canvas Workspace app) | at offset 0x484 inside header |
