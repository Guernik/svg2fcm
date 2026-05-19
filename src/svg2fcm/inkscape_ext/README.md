# svg2fcm — Inkscape extension

Save any Inkscape document as a **Brother ScanNCut FCM** file ready for
pen plotting, via **File → Save As → Brother ScanNCut FCM (*.fcm)**.

The generated `.fcm` is intended to be transferred straight to the
ScanNCut machine via USB flash drive — Canvas Workspace is not
required.

## Requirements

* Inkscape **1.2** or newer (any OS).
* No other dependencies — `svgelements` (pure-Python) is bundled in
  `_vendor/`. The thumbnail renderer is also pure-Python, so the
  extension works against any Inkscape build without compiled
  third-party wheels.

## Install

1. Download the release zip (`svg2fcm-inkscape-<version>.zip`).
2. Unzip its contents directly into your Inkscape user extensions
   folder (the folder must contain `svg2fcm.inx` at the top level —
   **not** nested inside another folder):

   | OS      | Path                                                                        |
   | ------- | --------------------------------------------------------------------------- |
   | Linux   | `~/.config/inkscape/extensions/`                                            |
   | macOS   | `~/Library/Application Support/org.inkscape.Inkscape/config/inkscape/extensions/` |
   | Windows | `%APPDATA%\inkscape\extensions\`                                            |

   Not sure where yours lives? Open Inkscape and go to **Edit →
   Preferences → System** — the **User extensions** field shows the
   exact path Inkscape scans.

3. **Restart Inkscape.**

## Use

1. Open any SVG in Inkscape.
2. **File → Save As…**
3. In the file-type dropdown, pick **Brother ScanNCut FCM (*.fcm)**.
4. Name the file and save.
5. Copy the `.fcm` to a USB flash drive, plug it into the ScanNCut,
   and load it from the machine's USB menu.

## How it converts your SVG

* SVG (0, 0) maps to the top-left of the ScanNCut **drawable area**
  (3 mm in from the mat edge — the corner of the red zone).
* All paths become "draw" operations (pen plot), not cut operations.
* Each top-level shape / sub-path becomes a separate piece labelled
  `A01`, `A02`, ….
* Text is **not** supported — convert text to paths first
  (**Path → Object to Path**) before saving.

## Troubleshooting

**The extension doesn't appear in the Save As dropdown**

* Make sure `svg2fcm.inx` is **directly** inside the extensions folder,
  not in a sub-folder.
* Restart Inkscape after copying the files.
* Check **Edit → Preferences → System → User extensions** to confirm
  the folder Inkscape is actually scanning.

**"Module not found" errors in Inkscape's extension error log**

* Confirm the `_vendor/` folder is present alongside `svg2fcm.inx` and
  contains both `svg2fcm/` and `svgelements/` subdirectories.

**The exported file imports at the wrong size in Canvas Workspace**

* This usually means your SVG was exported from another tool with
  unitless coordinates (Illustrator's default). The extension
  auto-detects this and assumes points (1 pt = 1/72 in). If your file
  declares `width="…mm"`/`height="…mm"` the size will match exactly.

## Issues

Please report bugs at the project repo with a minimal SVG that
reproduces the problem.

## License

`svg2fcm` is distributed under the [Mozilla Public License
2.0](https://www.mozilla.org/MPL/2.0/) — see the `LICENSE` file included
in this zip. Bundled third-party packages under `_vendor/` retain their
own licenses; see `THIRD_PARTY_LICENSES.md` for the inventory.

This extension is an independent project and is **not affiliated with
or endorsed by Brother Industries, Ltd. or the Inkscape Project**.
"Brother", "ScanNCut", "Canvas Workspace", and "Inkscape" are
trademarks of their respective owners.
