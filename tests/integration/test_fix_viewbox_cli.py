"""End-to-end tests for ``--fix-viewbox`` and ``--no-viewbox-fix``."""

from __future__ import annotations

import re
from pathlib import Path

from svg2fcm.cli import main

BAD_SVG = """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="297mm">
  <line x1="0" y1="0" x2="50" y2="50" stroke="black"/>
</svg>
"""


def _has_viewbox(svg_text: str) -> str | None:
    match = re.search(r'viewBox="([^"]+)"', svg_text)
    return match.group(1) if match else None


def test_fix_viewbox_rewrites_in_place(tmp_path: Path) -> None:
    src = tmp_path / "bad.svg"
    src.write_text(BAD_SVG, encoding="utf-8")

    rc = main([str(src), "--fix-viewbox"])
    assert rc == 0

    # ViewBox is computed from the content's bounding box, not from
    # width/height. The line in BAD_SVG spans (0,0)→(50,50).
    assert _has_viewbox(src.read_text(encoding="utf-8")) == "0 0 50 50"


def test_fix_viewbox_with_output_writes_copy(tmp_path: Path) -> None:
    src = tmp_path / "bad.svg"
    src.write_text(BAD_SVG, encoding="utf-8")
    dst = tmp_path / "fixed.svg"

    rc = main([str(src), "-o", str(dst), "--fix-viewbox"])
    assert rc == 0

    # Original is untouched.
    assert _has_viewbox(src.read_text(encoding="utf-8")) is None
    # Fixed copy has a viewBox matching the line's bounding box.
    assert _has_viewbox(dst.read_text(encoding="utf-8")) == "0 0 50 50"


def test_fix_viewbox_idempotent_in_place(tmp_path: Path) -> None:
    src = tmp_path / "good.svg"
    src.write_text(
        '<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" '
        'width="210mm" height="297mm" viewBox="0 0 210 297"/>',
        encoding="utf-8",
    )
    before = src.read_text(encoding="utf-8")

    rc = main([str(src), "--fix-viewbox"])
    assert rc == 0
    assert src.read_text(encoding="utf-8") == before


def test_conversion_fixes_viewbox_implicitly(tmp_path: Path) -> None:
    """Default conversion path silently injects a viewBox before encoding."""
    src = tmp_path / "design.svg"
    src.write_text(BAD_SVG, encoding="utf-8")

    rc = main([str(src)])
    assert rc == 0

    fcm = tmp_path / "design.fcm"
    assert fcm.exists()
    # The source on disk is untouched — fix happens in memory.
    assert _has_viewbox(src.read_text(encoding="utf-8")) is None


def test_no_viewbox_fix_skips_the_fix(tmp_path: Path) -> None:
    """``--no-viewbox-fix`` reproduces the pre-fix (wrong-scale) behavior."""
    src = tmp_path / "design.svg"
    src.write_text(BAD_SVG, encoding="utf-8")

    # The conversion still runs and produces a file (likely at the wrong
    # scale, but that's the user's choice). We just assert the flag is
    # honoured without erroring.
    rc = main([str(src), "--no-viewbox-fix"])
    assert rc == 0
    assert (tmp_path / "design.fcm").exists()
