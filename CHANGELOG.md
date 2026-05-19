# Changelog

All notable changes to **svg2fcm** are recorded here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial interoperability spec of the Brother ScanNCut FCM binary
  format (`docs/FCM_FORMAT.md`), based on the upstream MPL-2.0 reference
  implementation `justjanne/fcmlib` and cross-checked against locally
  produced samples.
- Byte-exact FCM parser (`svg2fcm.fcm.parser`) and writer
  (`svg2fcm.fcm.writer`). Round-trips every fixture file byte-for-byte.
- SVG ingestion via `svgelements` (`svg2fcm.svg.loader`) that flattens
  transforms, decomposes primitives to lines/cubics, and groups runs of
  same-kind segments into FCM outlines.
- 88×88 1-bit BMP thumbnail renderer using Pillow
  (`svg2fcm.thumbnail`).
- CLI entry point: `svg2fcm input.svg output.fcm` (also `python -m
  svg2fcm`).
- One piece per top-level SVG shape, with Canvas Workspace–style
  `A01`, `A02`, … labels.
- FOSS scaffolding: MPL-2.0 licence, ruff + mypy + pytest config,
  GitHub Actions CI matrix (macOS, Linux, Windows × Python 3.10/3.11/3.12).
- Inkscape Output extension (`File → Save As → Brother ScanNCut FCM`),
  distributed as a single zip with vendored `svgelements`. Build with
  `just package-inkscape`.
- Default to a single grouped piece: every SVG shape is emitted as a
  Path inside one Piece (matching Canvas Workspace's "select all →
  group" output). The ScanNCut refused to import files with many
  independent pieces; grouping fixes that. CLI gains `-n` /
  `--no-group` to opt out and emit one piece per shape.

### Changed

- Pure-Python thumbnail renderer (no Pillow). Inkscape extension zip
  shrinks from ~5 MB to ~150 KB and works against any Inkscape build,
  regardless of bundled Python version or architecture.
