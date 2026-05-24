# Changelog

All notable changes to **svg2fcm** are recorded here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] — 2026-05-23

### Added

- **`--vpype PIPELINE`**. Pre-process the input SVG through a vpype
  pipeline before conversion. The string is passed verbatim to vpype
  (minus the `read`/`write` bookends), so the full vpype command surface
  including third-party plugins is available — e.g.
  `svg2fcm in.svg --vpype "linemerge --tolerance 0.1mm linesimplify linesort"`.
  Original Inkscape/`id` layer labels are restored across the vpype
  round-trip so per-pen FCM filenames stay human-readable.
- **`[vpype]` optional extra** (`pip install 'svg2fcm[vpype]'` /
  `pipx install --python python3.13 --force '.[vpype]'`). vpype is
  marker-scoped to Python 3.11–3.13; the base install remains
  available on Python 3.10–3.14.
- **`-q` / `--quiet`** flag to suppress INFO logging.

### Changed

- Default log level is now **INFO** (was WARNING). Multi-layer runs
  print one progress line per layer by default.
- `-v` / `--verbose` is now a single boolean enabling **DEBUG** (was a
  counted flag where `-v` meant INFO and `-vv` meant DEBUG).
- New DEBUG traces cover vpype invocation, label remap, and layer
  detection.

## [0.2.1] — 2026-05-20

### Changed

- Release workflow (`.github/workflows/release.yml`) now runs
  `pre-commit run --all-files` and `pytest -q` as gates before
  building artifacts or publishing the GitHub Release. A failing lint
  or test aborts the release.

## [0.2.0] — 2026-05-20

### Added

- **Multi-pen split.** When the input SVG is partitioned into top-level
  groups (Inkscape layers *or* DrawingBot/Vpype/Illustrator-style
  `<g id="…">`), `svg2fcm` emits one `.fcm` per group, named
  `<input-stem>_<label>.fcm` next to the input. Mixed documents (only
  some groups labelled) fall through to single-output mode.
- **Implicit viewBox fix.** Source SVGs that declare `width`/`height`
  in physical units but no `viewBox` (common from DrawingBot V3) are
  silently fixed in memory before conversion, using the post-transform
  content bounding box rather than the declared width/height. Pass
  `--no-viewbox-fix` to opt out.
- **Standalone `--fix-viewbox` mode** that rewrites the SVG with the
  synthesised viewBox and exits without producing an FCM. Combined
  with `-o`, writes a fixed copy and leaves the input untouched.
- **Pre-commit hooks** (ruff, ruff-format, mypy `--strict`, plus the
  standard hygiene set). `just hooks-install` activates them locally;
  CI enforces the same gate via a `pre-commit` job.
- **Tag-triggered GitHub Release workflow** (`.github/workflows/release.yml`).
  Pushing a `v*` tag builds the wheel, sdist, and Inkscape extension
  zip and publishes a Release with notes extracted from this changelog.
- **Bash, zsh, and fish shell completions** under `completions/`, plus
  a `just completions-install` recipe.
- **Disclaimer + interoperability notice** in README and
  `docs/FCM_FORMAT.md`, and a CONTRIBUTING.md inbound = outbound
  license clause.

### Changed

- **BREAKING:** the output destination is now `-o`/`--output` instead
  of a second positional argument. With no flag, single-pen designs
  default to `<input-stem>.fcm` next to the source; multi-pen designs
  default to the input's directory.
- Inkscape extension bundle now ships `LICENSE` and
  `THIRD_PARTY_LICENSES.md` alongside the vendored `svgelements`
  package's own license.
- Sample SVGs under `samples/` now include a provenance README.

## [0.1.1] — 2026-05-19

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
