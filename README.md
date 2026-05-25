# svg2fcm

[![ci](https://github.com/guernik/svg2fcm/actions/workflows/ci.yml/badge.svg)](https://github.com/guernik/svg2fcm/actions/workflows/ci.yml)
[![license: MPL-2.0](https://img.shields.io/badge/license-MPL--2.0-blue.svg)](LICENSE)
[![python: 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

> Convert SVG files directly into Brother ScanNCut **FCM** files for pen
> plotting.

`svg2fcm` reads any SVG file and writes a `.fcm` file the Brother ScanNCut
machine accepts and draws with a pen. It's designed for SVGs that are large
enough to make Canvas Workspace unresponsive — the kind with hundreds or
thousands of paths — so the whole workflow is **SVG → FCM → USB stick →
machine**, no Canvas Workspace round-trip required.

> 🛠 **Status:** The core pipeline (parser, writer, SVG ingestion,
> CLI) is working and validated against Canvas Workspace and a real
> ScanNCut machine. An **Inkscape extension** is also available — see
> [Inkscape extension](#inkscape-extension) below. Bug reports and
> reproducers welcome.

## What's supported

- `<line>`, `<polyline>`, `<polygon>`, `<rect>`, `<circle>`, `<ellipse>`,
  `<path>` (with all `M L C Q A Z` commands) — anything `svgelements` can
  flatten to a path.
- Nested `<g>` groups, all common `transform=` attributes.
- Sub-paths inside one `<path>` (each becomes its own piece).
- Inline `style="…"` plus `stroke=`/`stroke-width=` attributes.
- Multiple shapes; each becomes a separately labelled piece (`A01`,
  `A02`, …).

## Not supported in v1

- `<text>` — convert text to paths first in Inkscape/Illustrator. (Outline
  the text before exporting.)
- Gradients, patterns, filters, masks, `clip-path`, raster `<image>`.
- CSS class selectors (only inline `style=` is read).
- Animations, `<symbol>`/`<use>` not flattened by svgelements.

## Install

Requires Python 3.10 or newer. The recommended install also pulls in
[vpype](https://vpype.readthedocs.io/) for plotter-oriented pre-processing
(`--vpype`); vpype currently supports Python 3.11–3.13, so install
svg2fcm under one of those if you want it. Plain svg2fcm without vpype
works on any Python ≥3.10.

### System-wide CLI (recommended)

`svg2fcm` is a Python CLI; install it in an isolated venv with
[`pipx`](https://pipx.pypa.io/) so the `svg2fcm` command is available
from any directory:

```bash
# 1. One-time pipx setup (skip if you already have pipx):
brew install pipx                                  # macOS
# or: python3 -m pip install --user pipx           # Linux/Windows
pipx ensurepath                                    # add ~/.local/bin to PATH

# 2. Install svg2fcm + vpype from a checkout (recommended):
git clone https://github.com/emilioguernik/svg2fcm
cd svg2fcm
pipx install --python python3.13 --force '.[vpype]'

# Or, without vpype (any Python ≥3.10):
just install-cli                                   # = pipx install --force .
```

Already installed without vpype and want to add it later? Reinstall under
a vpype-compatible Python and re-include the extra:

```bash
pipx uninstall svg2fcm
pipx install --python python3.13 --force '/path/to/svg2fcm[vpype]'
```

Remove with `just uninstall-cli` (or `pipx uninstall svg2fcm`).

### Shell completions

Completion scripts for **bash**, **zsh**, and **fish** live in
[`completions/`](completions/). From a repo checkout, the easiest way to
install them is:

```bash
just completions-install
```

That copies the fish script into `~/.config/fish/completions/` (if
fish is present) and prints the one-line snippet to paste into
`~/.bashrc` or `~/.zshrc` for the other two shells. The scripts have no
runtime dependencies — they're plain shell, sourced once per shell
startup.

### From source (development)

For hacking on the project itself:

```bash
git clone https://github.com/emilioguernik/svg2fcm
cd svg2fcm
just install        # creates .venv with -e ".[dev]"
just check          # ruff + mypy --strict + pytest
```

## Usage

```bash
svg2fcm input.svg                       # convert -> input.fcm next to the SVG
svg2fcm input.svg -o output.fcm         # convert to an explicit path
svg2fcm input.svg -o ./out/             # write into a directory (uses input stem)
svg2fcm -v  input.svg                   # info-level logging
svg2fcm -vv input.svg                   # debug-level logging
svg2fcm -n  input.svg                   # one piece per shape (legacy);
                                        # default groups everything into one
                                        # piece, which the machine imports
                                        # more reliably.
svg2fcm input.svg --vpype "linemerge linesimplify"   # pre-process via vpype
                                        # (install with the [vpype] extra)
svg2fcm input.svg --no-log              # skip the per-run result.log file
svg2fcm --version
```

### Multi-pen (Inkscape layers)

If the SVG contains two or more Inkscape layers (one per pen), `svg2fcm`
emits one `.fcm` per layer, named `<input-stem>_<layer-label>.fcm`:

```bash
svg2fcm benteveo_multi_pen.svg
# -> benteveo_multi_pen_1.fcm
# -> benteveo_multi_pen_2.fcm
# -> benteveo_multi_pen_3.fcm
# -> benteveo_multi_pen_4.fcm

svg2fcm benteveo_multi_pen.svg -o ./out/   # all four files into ./out/
```

A single Inkscape layer is treated as a single-pen design (one `.fcm`,
no `_<label>` suffix).

### Per-run result.log

Every run drops a `<input-stem>_result.log` file next to the generated
`.fcm` outputs. It contains the invocation, viewBox-fix status, layer
detection, per-layer conversion details, and — when `--vpype` is used —
the vpype pipeline plus `vpype ... stat` output on both the source and
the vpype'd SVG. The log is captured at DEBUG level regardless of the
console verbosity, so it's a complete record even when stdout was quiet.

Pass `--no-log` to skip it.

### Pre-processing with vpype

If you installed svg2fcm with the `[vpype]` extra (see [Install](#install)),
you can pipe the input SVG through any [vpype](https://vpype.readthedocs.io/)
pipeline before it's converted to FCM — useful for plotter-oriented tweaks
like merging coincident endpoints, simplifying curves, reordering paths to
cut down on pen travel, or cropping to a page size:

```bash
svg2fcm input.svg --vpype "linemerge --tolerance 0.1mm linesimplify linesort"
```

The string after `--vpype` is passed verbatim to vpype, minus the
`read`/`write` bookends (svg2fcm supplies those itself). Anything that
works in a normal `vpype read … write …` pipeline works here, including
third-party vpype plugins installed into the same venv.

If `--vpype` is used without the extra installed, svg2fcm exits with a
clear error pointing back to this section. Everything else in the CLI
works regardless.

### Fixing missing `viewBox`

Some SVG generators (DrawingBot V3, certain plotter exporters) emit
files with `width="210mm"` / `height="297mm"` but **no `viewBox`**.
Such files render at the wrong scale in Illustrator, browsers, and
Canvas Workspace. `svg2fcm` detects this and **silently injects a
correct `viewBox`** in memory before encoding the `.fcm` — you don't
have to do anything.

You can also fix the SVG itself (e.g. so it opens correctly in
Illustrator) without producing an `.fcm`:

```bash
svg2fcm bad.svg --fix-viewbox             # rewrite bad.svg in place
svg2fcm bad.svg -o fixed.svg --fix-viewbox # leave bad.svg untouched
svg2fcm input.svg --no-viewbox-fix        # opt out of the implicit fix
```

The viewBox is computed from the actual coordinate range of the path
data (with all group transforms baked in), not just from `width`/`height`.

Transfer the `.fcm` to your ScanNCut machine using a USB flash drive
([Brother docs](https://support.canvasworkspace.brother.com/en/connection/)).
The machine loads `.fcm` files directly from the USB picker — no Canvas
Workspace step required.

## Inkscape extension

Prefer a GUI? An Inkscape Output extension is bundled with each release:
**File → Save As → Brother ScanNCut FCM (\*.fcm)**.

Get the zip one of two ways:

- **Download** `svg2fcm-inkscape-<version>.zip` from the
  [Releases page](https://github.com/emilioguernik/svg2fcm/releases), or
- **Build it locally** from a checkout with `just package-inkscape` —
  the zip lands at `dist/svg2fcm-inkscape-<version>.zip`. Useful if you
  want to ship the extension off your own machine without depending on
  a published release.

Then install it:

1. Unzip the contents into your Inkscape user extensions folder
   (the folder must contain `svg2fcm.inx` directly, not nested):

   | OS      | Path                                                                              |
   | ------- | --------------------------------------------------------------------------------- |
   | Linux   | `~/.config/inkscape/extensions/`                                                  |
   | macOS   | `~/Library/Application Support/org.inkscape.Inkscape/config/inkscape/extensions/` |
   | Windows | `%APPDATA%\inkscape\extensions\`                                                  |

2. Restart Inkscape. The new entry appears in **File → Save As**.

Requires Inkscape 1.2+. All dependencies (`svgelements`, `Pillow`) are
vendored into the zip — no extra `pip install` needed. Full install +
troubleshooting docs are inside the zip (`README.md`) and in
[`src/svg2fcm/inkscape_ext/README.md`](src/svg2fcm/inkscape_ext/README.md).

## How it works

```
SVG ──► [svg.loader]   ──► IR shapes (mm) ──► [builder] ──► FcmFile ──► [fcm.writer] ──► .fcm bytes
                                                       │
                                  [thumbnail] ─────────┘
                                  (88×88 1-bit BMP preview)
```

- **`svg2fcm.svg.loader`** uses `svgelements` to flatten transforms and
  expand primitives into a uniform path representation, then groups runs
  of the same segment kind (line vs cubic Bézier) into FCM outlines.
- **`svg2fcm.builder`** emits one piece per top-level shape, matching
  Canvas Workspace's convention, and applies the 3 mm UI offset that
  Canvas Workspace uses internally.
- **`svg2fcm.fcm.writer`** produces deterministic, byte-exact FCM output.
  The encoder/parser pair round-trip every checked-in sample file
  byte-for-byte.

For the binary format itself, see [`docs/FCM_FORMAT.md`](docs/FCM_FORMAT.md).

## Coordinate conventions

- SVG units are interpreted as millimetres (`ppi=25.4` passed to
  `svgelements`).
- FCM stores coordinates as signed 32-bit integers in units of **1/100 mm**.
- The ScanNCut mat working area is **296.67 × 298.80 mm**.
- Canvas Workspace's position UI shows the **top-left of the bounding
  box**. For `<circle cx="50" cy="50" r="25">`, Canvas Workspace will
  display "position (25, 25), 50 × 50" — that's the same geometry, just
  named differently.

## Development

The repo uses a [`justfile`](justfile) for common tasks. Run `just` for
the recipe list:

```
just install    # create venv, install -e ".[dev]"
just check      # ruff + mypy --strict + pytest
just fmt        # apply ruff autofixes
just build      # build wheel + sdist into dist/
just clean      # remove caches and build artefacts
```

CI runs the full gate on macOS, Linux, and Windows × Python 3.10/3.11/3.12.

## Roadmap

- **v0.2** — ✅ Inkscape extension (`File → Save As → ScanNCut FCM`).
- **v0.3** — Optional colour-split: one `.fcm` per SVG stroke colour for
  multi-pen drawings.
- **Future** — `<text>` support via font-to-path, `clip-path` flattening,
  optional cut output.

See [`CHANGELOG.md`](CHANGELOG.md) for release notes.

## Contributing

PRs welcome. Please read [`CONTRIBUTING.md`](CONTRIBUTING.md). Bug
reports with a minimal SVG reproducer are the most useful kind of
contribution.

## Credits

The binary-format spec under [`docs/FCM_FORMAT.md`](docs/FCM_FORMAT.md)
is based on
[`justjanne/fcmlib`](https://github.com/justjanne/fcmlib), an upstream
MPL-2.0 reference implementation validated against 1000+ Canvas
Workspace samples. Both projects use MPL-2.0, so this derivative work
is licence-compatible.

## Disclaimer

`svg2fcm` is an independent, community-built project. It is **not
affiliated with, endorsed by, or sponsored by Brother Industries, Ltd.,
Inkscape, or the Mozilla Foundation**. "Brother", "ScanNCut", and
"Canvas Workspace" are trademarks of Brother Industries, Ltd. "Inkscape"
is a trademark of the Inkscape Project. All other trademarks are the
property of their respective owners and are used here only for
descriptive purposes to identify file formats and interoperability
targets.

The FCM binary format is not publicly documented by Brother. The
description in [`docs/FCM_FORMAT.md`](docs/FCM_FORMAT.md) was derived
from public reference implementations and from observation of files
produced by Canvas Workspace, solely for the purpose of **achieving
interoperability** between independently-created software and the
ScanNCut machine — a use generally permitted under 17 U.S.C. §1201(f)
(US DMCA) and Article 6 of EU Directive 2009/24/EC.

### Use at your own risk

`svg2fcm` generates files that drive physical hardware. Always inspect
the output (e.g. with the on-machine preview) before running a job, and
keep an eye on the first few seconds of any new file — bad geometry can
snap a pen, mis-feed the mat, or otherwise damage the machine or
materials. As stated in the MPL-2.0, the software is provided **"as is",
without warranty of any kind**, and the authors are not liable for any
damage to hardware, materials, or work.

## License

[Mozilla Public License 2.0](LICENSE).
