"""Allow ``python -m svg2fcm`` to invoke the CLI."""

from __future__ import annotations

import sys

from svg2fcm.cli import main

if __name__ == "__main__":
    sys.exit(main())
