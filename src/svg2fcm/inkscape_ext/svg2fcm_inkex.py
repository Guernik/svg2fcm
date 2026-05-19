"""Inkscape Output extension: write the current document as a ScanNCut FCM.

Registered via ``svg2fcm.inx`` and invoked by Inkscape when the user picks
"File → Save As → Brother ScanNCut FCM". The actual conversion logic lives
in the :mod:`svg2fcm` package; this shim just bridges Inkscape's
``OutputExtension`` API to that pipeline.

Vendored dependencies (``svg2fcm``, ``svgelements``, ``PIL``) live in the
adjacent ``_vendor/`` directory, populated by ``scripts/build_inkscape_ext.py``
at packaging time. We prepend ``_vendor/`` to ``sys.path`` so they win over
any conflicting installs in Inkscape's bundled Python.
"""

from __future__ import annotations

import os
import sys
from io import StringIO

_HERE = os.path.dirname(os.path.abspath(__file__))
_VENDOR = os.path.join(_HERE, "_vendor")
if os.path.isdir(_VENDOR) and _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)

import inkex  # noqa: E402  (must follow sys.path setup)

from svg2fcm.builder import build_fcm  # noqa: E402
from svg2fcm.fcm.writer import encode_fcm  # noqa: E402
from svg2fcm.svg.loader import load_svg  # noqa: E402
from svg2fcm.thumbnail import render_thumbnail  # noqa: E402


class Svg2FcmOutput(inkex.OutputExtension):
    """Inkscape Output extension that writes the active SVG as an FCM file."""

    def save(self, stream):  # type: ignore[no-untyped-def]
        """Render the current document to FCM bytes and write them to ``stream``."""
        svg_text = self.svg.tostring().decode("utf-8")
        shapes = load_svg(StringIO(svg_text))
        thumbnail = render_thumbnail(shapes)
        # Always group: the machine refuses files with many independent
        # pieces. The CLI exposes a -n/--no-group escape hatch; the
        # extension intentionally does not, to keep the GUI simple.
        fcm = build_fcm(shapes, thumbnail, group=True)
        stream.write(encode_fcm(fcm))


if __name__ == "__main__":
    Svg2FcmOutput().run()
