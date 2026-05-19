"""Extract the release-notes section for a given version from CHANGELOG.md.

Usage::

    python scripts/extract_changelog.py 0.1.1

Prints the block under the matching ``## [0.1.1]`` heading (any trailing
``— YYYY-MM-DD`` is fine) up to the next ``## `` heading, on stdout.
Exits non-zero if the section is missing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def extract(version: str) -> str:
    """Return the changelog body for ``version`` (without the heading)."""
    text = CHANGELOG.read_text(encoding="utf-8")
    # Match `## [<version>]` optionally followed by anything (date, etc.)
    # until the next top-level `## ` heading or end-of-file.
    pattern = re.compile(
        rf"^##\s+\[{re.escape(version)}\][^\n]*\n(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if match is None:
        raise SystemExit(f"No '## [{version}]' section found in {CHANGELOG}")
    return match.group(1).strip() + "\n"


def main() -> int:
    """Print the release notes for the version given on the command line."""
    if len(sys.argv) != 2:
        raise SystemExit("usage: extract_changelog.py <version>")
    sys.stdout.write(extract(sys.argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
