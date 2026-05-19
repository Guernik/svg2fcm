"""Build the distributable Inkscape extension zip.

Run from the repo root::

    python scripts/build_inkscape_ext.py

Produces ``dist/svg2fcm-inkscape-<version>.zip`` containing:

* ``svg2fcm.inx`` — Inkscape manifest
* ``svg2fcm_inkex.py`` — entry point
* ``README.md`` — end-user install/usage
* ``LICENSE`` — svg2fcm's MPL-2.0 license
* ``THIRD_PARTY_LICENSES.md`` — attribution for vendored deps
* ``_vendor/svg2fcm/`` — runtime package (no tests/CI/inkscape_ext)
* ``_vendor/svgelements/`` — only third-party runtime dep (pure-Python)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_PKG = REPO_ROOT / "src" / "svg2fcm"
EXT_SRC = SRC_PKG / "inkscape_ext"
DIST_DIR = REPO_ROOT / "dist"


def _read_version() -> str:
    init = (SRC_PKG / "__init__.py").read_text(encoding="utf-8")
    for line in init.splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise RuntimeError("__version__ not found in svg2fcm/__init__.py")


def _copy_runtime_pkg(dest_root: Path) -> None:
    """Copy ``src/svg2fcm/`` into ``_vendor/svg2fcm/`` minus dev-only bits."""
    target = dest_root / "svg2fcm"

    def _ignore(_src: str, names: list[str]) -> list[str]:
        return [n for n in names if n in {"inkscape_ext", "__pycache__"}]

    shutil.copytree(SRC_PKG, target, ignore=_ignore)


def _pip_install_deps(dest_root: Path) -> None:
    """Install pure-Python runtime deps (currently just svgelements) into ``dest_root``.

    We deliberately do **not** vendor Pillow: it ships compiled C
    extensions whose ABI must match Inkscape's bundled Python interpreter
    (which varies by platform and Inkscape version). The thumbnail
    renderer in :mod:`svg2fcm.thumbnail` is pure-Python for this reason.
    """
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            "--target",
            str(dest_root),
            "--no-compile",
            "svgelements>=1.9.6",
        ],
    )


def _strip_vendor_noise(vendor_dir: Path) -> None:
    """Remove ``.pyc`` files and ``__pycache__``/``tests`` directories.

    ``.dist-info`` directories are kept (slimmed down) because they carry
    the LICENSE / METADATA files we need for attribution compliance with
    the vendored package's license terms.
    """
    keep_in_dist_info = {"LICENSE", "LICENSE.txt", "LICENSE.md", "METADATA", "NOTICE"}
    for path in list(vendor_dir.rglob("*")):
        if not path.exists():
            continue
        if path.is_dir() and (path.name == "__pycache__" or path.name == "tests"):
            shutil.rmtree(path, ignore_errors=True)
        elif (path.is_file() and path.suffix == ".pyc") or (
            path.is_file()
            and path.parent.name.endswith(".dist-info")
            and path.name not in keep_in_dist_info
        ):
            path.unlink(missing_ok=True)


def _write_third_party_notice(staging: Path, vendor: Path) -> None:
    """Emit a top-level THIRD_PARTY_LICENSES.md pointing at vendored licenses."""
    entries: list[str] = []
    for dist_info in sorted(vendor.glob("*.dist-info")):
        pkg = dist_info.name.rsplit("-", 1)[0]
        license_file = next(
            (p for p in dist_info.iterdir() if p.name in {"LICENSE", "LICENSE.txt", "LICENSE.md"}),
            None,
        )
        if license_file is None:
            continue
        rel = license_file.relative_to(staging)
        entries.append(f"- **{pkg}** — see `{rel}`")

    body = (
        "# Third-party licenses\n\n"
        "The Inkscape extension bundle vendors the following third-party\n"
        "packages. Each is redistributed under its original license; the\n"
        "license text is included alongside the package in `_vendor/`.\n\n"
        + ("\n".join(entries) if entries else "_No third-party packages vendored._")
        + "\n\nsvg2fcm itself is licensed under the Mozilla Public License 2.0;\n"
        "see the top-level `LICENSE` file in this zip.\n"
    )
    (staging / "THIRD_PARTY_LICENSES.md").write_text(body, encoding="utf-8")


def build(output_dir: Path | None = None) -> Path:
    """Build the Inkscape extension zip and return its path."""
    version = _read_version()
    output_dir = output_dir or DIST_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"svg2fcm-inkscape-{version}.zip"

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "svg2fcm-inkscape"
        staging.mkdir()

        # Top-level extension files.
        for name in ("svg2fcm.inx", "svg2fcm_inkex.py", "README.md"):
            shutil.copy2(EXT_SRC / name, staging / name)

        # Ship svg2fcm's own license alongside the extension.
        shutil.copy2(REPO_ROOT / "LICENSE", staging / "LICENSE")

        # Vendored deps.
        vendor = staging / "_vendor"
        vendor.mkdir()
        _copy_runtime_pkg(vendor)
        _pip_install_deps(vendor)
        _strip_vendor_noise(vendor)
        _write_third_party_notice(staging, vendor)

        # Zip it up (deterministic-ish: sorted file order).
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(staging.rglob("*")):
                zf.write(path, path.relative_to(staging.parent))

    return zip_path


def main() -> int:
    """Build the extension zip and print its path."""
    out = build()
    print(f"Built {out} ({out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
