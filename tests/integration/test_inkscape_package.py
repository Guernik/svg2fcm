"""Smoke test for the Inkscape extension packager.

Runs ``scripts/build_inkscape_ext.py`` end-to-end into a temp dir and
asserts the zip exists with the expected layout. Network-touching:
``pip install --target`` pulls ``svgelements`` from PyPI, so this test
is skipped when offline.
"""

from __future__ import annotations

import socket
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_inkscape_ext import build  # noqa: E402


def _has_network() -> bool:
    try:
        socket.create_connection(("pypi.org", 443), timeout=2).close()
    except OSError:
        return False
    return True


@pytest.mark.skipif(not _has_network(), reason="needs PyPI access for pip install --target")
def test_packager_produces_expected_zip(tmp_path: Path) -> None:
    zip_path = build(output_dir=tmp_path)
    assert zip_path.exists()
    assert zip_path.stat().st_size > 100_000  # vendored deps make it sizeable

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())

    required = {
        "svg2fcm-inkscape/svg2fcm.inx",
        "svg2fcm-inkscape/svg2fcm_inkex.py",
        "svg2fcm-inkscape/README.md",
        "svg2fcm-inkscape/_vendor/svg2fcm/__init__.py",
        "svg2fcm-inkscape/_vendor/svg2fcm/cli.py",
        "svg2fcm-inkscape/_vendor/svg2fcm/thumbnail.py",
        "svg2fcm-inkscape/_vendor/svgelements/__init__.py",
    }
    missing = required - names
    assert not missing, f"missing from zip: {missing}"

    # We deliberately do NOT vendor Pillow — compiled C extensions whose
    # ABI must match Inkscape's bundled Python. The thumbnail renderer
    # is pure-Python now.
    assert not any("_vendor/PIL/" in n for n in names)

    # The runtime package must not re-include its own inkscape_ext folder
    # (would create a recursion when re-packaged).
    assert not any("_vendor/svg2fcm/inkscape_ext" in n for n in names)
