# svg2fcm

[![ci](https://github.com/emilioguernik/svg2fcm/actions/workflows/ci.yml/badge.svg)](https://github.com/emilioguernik/svg2fcm/actions/workflows/ci.yml)
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

Requires Python 3.10 or newer.

### System-wide CLI (recommended)

`svg2fcm` is a Python CLI; install it in an isolated venv with
[`pipx`](https://pipx.pypa.io/) so the `svg2fcm` command is available
from any directory:

```bash
# 1. One-time pipx setup (skip if you already have pipx):
brew install pipx                                  # macOS
# or: python3 -m pip install --user pipx           # Linux/Windows
pipx ensurepath                                    # add ~/.local/bin to PATH

# 2. Install svg2fcm from a checkout:
git clone https://github.com/emilioguernik/svg2fcm
cd svg2fcm
just install-cli                                   # = pipx install --force .
```

Remove with `just uninstall-cli` (or `pipx uninstall svg2fcm`).

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
svg2fcm input.svg output.fcm           # convert
svg2fcm -v input.svg output.fcm        # info-level logging
svg2fcm -vv input.svg output.fcm       # debug-level logging
svg2fcm -n input.svg output.fcm        # one piece per shape (legacy);
                                       # default groups everything into one
                                       # piece, which the machine imports
                                       # more reliably.
svg2fcm --version
```

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
