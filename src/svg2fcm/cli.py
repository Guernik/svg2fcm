"""Command-line interface: ``svg2fcm input.svg output.fcm``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from svg2fcm import __version__
from svg2fcm.builder import build_fcm
from svg2fcm.exceptions import Svg2FcmError
from svg2fcm.fcm.writer import encode_fcm
from svg2fcm.svg.loader import load_svg
from svg2fcm.thumbnail import render_thumbnail

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="svg2fcm",
        description=("Convert an SVG file to a Brother ScanNCut FCM file for pen plotting."),
    )
    parser.add_argument("input", type=Path, help="path to the input .svg file")
    parser.add_argument("output", type=Path, help="path to the output .fcm file")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="increase verbosity (use -vv for debug)",
    )
    parser.add_argument(
        "-n",
        "--no-group",
        action="store_true",
        help=(
            "emit one piece per shape (legacy behaviour). The default groups "
            "every shape into a single piece, which the ScanNCut machine "
            "imports more reliably for designs with many shapes."
        ),
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser.parse_args(argv)


def _setup_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def convert(input_path: Path, output_path: Path, *, group: bool = True) -> int:
    """Convert ``input_path`` (SVG) to ``output_path`` (FCM).

    Args:
        input_path: Source SVG file.
        output_path: Destination FCM file.
        group: When ``True`` (default), bundle all shapes into a single
            grouped piece — matches Canvas Workspace's "select all →
            group" output and improves machine import reliability.

    Returns:
        Number of shapes written.
    """
    shapes = load_svg(input_path)
    logger.info("Loaded %d shape(s) from %s", len(shapes), input_path)
    thumbnail = render_thumbnail(shapes)
    fcm = build_fcm(shapes, thumbnail, group=group)
    data = encode_fcm(fcm)
    output_path.write_bytes(data)
    logger.info("Wrote %d bytes to %s", len(data), output_path)
    return len(shapes)


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``svg2fcm`` and ``python -m svg2fcm``.

    Returns:
        Process exit code. ``0`` on success, ``1`` on expected failures
        (invalid SVG, unwriteable output), ``2`` on argparse errors.
    """
    args = _parse_args(argv)
    _setup_logging(args.verbose)
    try:
        n = convert(args.input, args.output, group=not args.no_group)
    except Svg2FcmError as exc:
        logger.error("%s", exc)
        return 1
    except OSError as exc:
        logger.error("I/O error: %s", exc)
        return 1
    print(f"Converted {n} shape(s): {args.input} -> {args.output}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
