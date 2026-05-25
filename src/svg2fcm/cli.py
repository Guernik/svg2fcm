"""Command-line interface: ``svg2fcm input.svg [output]``.

The CLI auto-detects Inkscape layers. With **two or more** layers it emits
one ``.fcm`` per layer named ``<input-stem>_<layer-label>.fcm`` into the
output directory (defaulting to the input file's directory). With zero or
one layer it writes a single ``.fcm`` exactly as before.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import logging
import logging.handlers
import re
import sys
from pathlib import Path

from svg2fcm import __version__
from svg2fcm.builder import build_fcm
from svg2fcm.exceptions import Svg2FcmError
from svg2fcm.fcm.writer import encode_fcm
from svg2fcm.svg.layers import Layer, split_layers
from svg2fcm.svg.loader import load_svg, load_svg_from_string
from svg2fcm.svg.viewbox import ensure_viewbox
from svg2fcm.svg.vpype_pass import run_vpype, vpype_stat
from svg2fcm.thumbnail import render_thumbnail

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="svg2fcm",
        description=(
            "Convert an SVG file to a Brother ScanNCut FCM file for pen plotting. "
            "If the SVG contains multiple Inkscape layers, one FCM is emitted per "
            "layer; the output argument is then treated as a directory (defaulting "
            "to the input file's directory)."
        ),
    )
    parser.add_argument("input", type=Path, help="path to the input .svg file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help=(
            "output destination. In normal conversion mode this is a .fcm file "
            "(single/no-layer SVG) or a directory (multi-layer SVG); defaults "
            "to the input's directory with the .svg extension replaced by "
            ".fcm. In --fix-viewbox mode this is the path of the fixed SVG "
            "copy; if omitted, the input is rewritten in place."
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="enable DEBUG logging (per-shape, per-layer detail)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="suppress INFO logging; only show warnings and errors",
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
        "--fix-viewbox",
        action="store_true",
        help=(
            "fix-only mode: inject a viewBox into the input SVG (computed from "
            "its width/height) and exit without producing an FCM. With no output "
            "argument the input is rewritten in place; with an output argument "
            "the fixed copy is written there and the input is left untouched."
        ),
    )
    parser.add_argument(
        "--no-viewbox-fix",
        action="store_true",
        help=(
            "skip the implicit viewBox fix that normally runs before conversion. "
            "Use only if you know the source SVG already has a correct viewBox "
            "and you want to rule out the fixer as a variable."
        ),
    )
    parser.add_argument(
        "--vpype",
        type=str,
        default=None,
        metavar="PIPELINE",
        help=(
            "pre-process the SVG through a vpype pipeline before conversion. "
            "Pass the pipeline as a single quoted string, exactly as you would "
            "type it after `vpype` on the command line, minus the read/write "
            'bookends (e.g. --vpype "linemerge --tolerance 0.1mm linesimplify"). '
            "Requires the optional vpype extra: `pip install svg2fcm[vpype]`."
        ),
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help=(
            "skip writing the per-run <input-stem>_result.log file. By default "
            "svg2fcm drops a DEBUG-level log next to the FCM outputs documenting "
            "the invocation, viewBox fix, vpype pipeline + stats, and per-layer "
            "details — handy for debugging surprising machine behaviour."
        ),
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser.parse_args(argv)


_LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"
_FILE_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def _setup_logging(*, verbose: bool, quiet: bool) -> logging.handlers.MemoryHandler | None:
    """Configure console logging and attach a DEBUG-level capture buffer.

    Returns the capture handler so :func:`main` can later flush it to
    ``<stem>_result.log``. Returns ``None`` only if there's no root
    logger to attach to (never happens in practice — kept for typing).
    """
    if verbose:
        console_level = logging.DEBUG
    elif quiet:
        console_level = logging.WARNING
    else:
        console_level = logging.INFO

    # Wipe any pre-existing handlers so reruns inside the same process
    # (tests) don't accumulate duplicates.
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(logging.DEBUG)

    console = logging.StreamHandler()
    console.setLevel(console_level)
    console.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(console)

    # Capacity well above any expected per-run record count; flushTarget
    # stays None until we know the output path. We never auto-flush on
    # level either — main() does the explicit flush.
    capture = logging.handlers.MemoryHandler(capacity=100_000, flushLevel=logging.CRITICAL + 1)
    capture.setLevel(logging.DEBUG)
    capture.setFormatter(logging.Formatter(_FILE_LOG_FORMAT))
    root.addHandler(capture)
    return capture


def _write_result_log(
    capture: logging.handlers.MemoryHandler,
    log_path: Path,
    header_lines: list[str],
) -> None:
    """Render captured log records + header into ``log_path``."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = capture.formatter or logging.Formatter(_FILE_LOG_FORMAT)
    body_lines = [fmt.format(rec) for rec in capture.buffer]
    log_path.write_text("\n".join([*header_lines, "", *body_lines]) + "\n", encoding="utf-8")


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
    logger.debug("Wrote %d bytes to %s", len(data), output_path)
    return len(shapes)


def _convert_from_text(svg_text: str, output_path: Path, *, group: bool) -> int:
    """Like :func:`convert`, but takes an in-memory SVG string."""
    shapes = load_svg_from_string(svg_text)
    logger.debug("Loaded %d shape(s) from in-memory SVG", len(shapes))
    thumbnail = render_thumbnail(shapes)
    fcm = build_fcm(shapes, thumbnail, group=group)
    data = encode_fcm(fcm)
    output_path.write_bytes(data)
    logger.debug("Wrote %d bytes to %s", len(data), output_path)
    return len(shapes)


_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_label(label: str) -> str:
    """Make ``label`` safe to use as a filename component.

    Collapses runs of disallowed characters (whitespace, path separators,
    punctuation) to a single ``_``, then trims leading/trailing ``_``/``.``.
    Returns ``""`` if nothing survives — caller falls back to an index.
    """
    cleaned = _SANITIZE_RE.sub("_", label).strip("._")
    return cleaned


def _resolve_output_dir(arg: Path | None, input_path: Path, layer_count: int) -> Path:
    """Resolve the output directory for multi-layer mode.

    Raises :class:`SystemExit` (via :func:`argparse.ArgumentParser.error`-style
    flow) is the caller's job; here we just raise :class:`Svg2FcmError` on
    bad input so :func:`main` can format the message.
    """
    if arg is None:
        return input_path.parent
    if arg.exists() and arg.is_dir():
        return arg
    if arg.suffix.lower() == ".fcm":
        raise Svg2FcmError(
            f"input SVG has {layer_count} Inkscape layers; pass a directory "
            f"as the output argument instead of a .fcm file (got {arg!s})"
        )
    return arg


def _run_single(
    input_path: Path,
    output_arg: Path | None,
    svg_text: str,
    layers: list[Layer],
    *,
    group: bool,
) -> tuple[int, Path]:
    """Single-output path: 0 or 1 Inkscape layers.

    Output filename defaults to ``<input-stem>.fcm`` in the input's
    directory. An explicit output argument may be a file or a directory.
    Always converts from ``svg_text`` (which may already have been
    viewBox-fixed in memory), not by re-reading ``input_path``.

    Returns ``(exit_code, log_dir)`` so the caller can drop a
    ``<stem>_result.log`` alongside the FCM.
    """
    if output_arg is None:
        out_path = input_path.with_suffix(".fcm")
    elif output_arg.exists() and output_arg.is_dir():
        out_path = output_arg / input_path.with_suffix(".fcm").name
    else:
        out_path = output_arg
    out_path.parent.mkdir(parents=True, exist_ok=True)

    text_to_convert = layers[0].svg_text if layers else svg_text
    n = _convert_from_text(text_to_convert, out_path, group=group)
    print(f"Converted {n} shape(s): {input_path} -> {out_path}")
    return 0, out_path.parent


def _run_multi(
    input_path: Path,
    output_arg: Path | None,
    layers: list[Layer],
    *,
    group: bool,
) -> tuple[int, Path]:
    """Multi-output path: 2+ Inkscape layers, one FCM per layer.

    Returns ``(exit_code, log_dir)`` so the caller can drop a
    ``<stem>_result.log`` into the same directory.
    """
    out_dir = _resolve_output_dir(output_arg, input_path, len(layers))
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = input_path.stem
    seen: set[str] = set()
    written: list[Path] = []
    total_shapes = 0

    for layer in layers:
        suffix = _sanitize_label(layer.label) or f"layer{layer.index}"
        # Guard against duplicate labels collapsing onto the same file.
        candidate = suffix
        bump = 2
        while candidate in seen:
            candidate = f"{suffix}_{bump}"
            bump += 1
        seen.add(candidate)

        out_path = out_dir / f"{stem}_{candidate}.fcm"
        n = _convert_from_text(layer.svg_text, out_path, group=group)
        total_shapes += n
        written.append(out_path)
        logger.info(
            "Layer %r (%d/%d): %d shape(s) -> %s",
            layer.label,
            layer.index,
            len(layers),
            n,
            out_path,
        )

    print(
        f"Wrote {len(written)} file(s) from {len(layers)} layer(s) in {input_path} "
        f"({total_shapes} shape(s) total) -> {out_dir}"
    )
    return 0, out_dir


def _run_fix_viewbox(input_path: Path, output_arg: Path | None) -> int:
    """Standalone ``--fix-viewbox`` mode: write a viewBox-fixed SVG and stop."""
    svg_text = input_path.read_text(encoding="utf-8")
    fixed, modified = ensure_viewbox(svg_text)

    if output_arg is None:
        out_path = input_path
        in_place = True
    else:
        out_path = output_arg
        in_place = False
        out_path.parent.mkdir(parents=True, exist_ok=True)

    if not modified:
        if in_place:
            print(f"Nothing to fix: {input_path} already has a viewBox.")
            return 0
        # Still write the copy so the user gets the file they asked for.
        out_path.write_text(fixed, encoding="utf-8")
        print(f"Nothing to fix: copied {input_path} -> {out_path} unchanged.")
        return 0

    out_path.write_text(fixed, encoding="utf-8")
    if in_place:
        print(f"Fixed viewBox in place: {out_path}")
    else:
        print(f"Wrote viewBox-fixed copy: {input_path} -> {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``svg2fcm`` and ``python -m svg2fcm``.

    Returns:
        Process exit code. ``0`` on success, ``1`` on expected failures
        (invalid SVG, unwriteable output), ``2`` on argparse errors.
    """
    args = _parse_args(argv)
    capture = _setup_logging(verbose=args.verbose, quiet=args.quiet)
    group = not args.no_group

    header_lines = [
        f"svg2fcm {__version__} — run at {_dt.datetime.now().isoformat(timespec='seconds')}",
        f"invocation: {' '.join(sys.argv)}",
        f"input: {args.input}",
        f"options: group={group}, fix_viewbox={not args.no_viewbox_fix}, vpype={args.vpype!r}",
    ]

    log_dir: Path | None = None
    exit_code = 0
    try:
        if args.fix_viewbox:
            return _run_fix_viewbox(args.input, args.output)

        svg_text = args.input.read_text(encoding="utf-8")

        if args.vpype:
            logger.info("Running vpype pipeline: %s", args.vpype)
            stat_before = vpype_stat(svg_text)
            if stat_before:
                logger.debug("vpype stat (before pipeline):\n%s", stat_before.rstrip())
            svg_text = run_vpype(svg_text, args.vpype)
            stat_after = vpype_stat(svg_text)
            if stat_after:
                logger.debug("vpype stat (after pipeline):\n%s", stat_after.rstrip())

        if not args.no_viewbox_fix:
            svg_text, modified = ensure_viewbox(svg_text)
            if modified:
                logger.info(
                    "Injected viewBox into %s before conversion (pass --no-viewbox-fix to disable)",
                    args.input,
                )
            else:
                logger.debug("viewBox already present (or could not be computed); no fix applied")
        else:
            logger.debug("viewBox fix skipped by --no-viewbox-fix")

        layers = split_layers(svg_text)
        if len(layers) <= 1:
            exit_code, log_dir = _run_single(args.input, args.output, svg_text, layers, group=group)
        else:
            exit_code, log_dir = _run_multi(args.input, args.output, layers, group=group)
        return exit_code
    except Svg2FcmError as exc:
        logger.error("%s", exc)
        exit_code = 1
        return 1
    except OSError as exc:
        logger.error("I/O error: %s", exc)
        exit_code = 1
        return 1
    finally:
        if capture is not None and not args.no_log and log_dir is not None:
            log_path = log_dir / f"{args.input.stem}_result.log"
            try:
                _write_result_log(capture, log_path, [*header_lines, f"exit_code: {exit_code}"])
            except OSError as exc:
                # The log is a courtesy — never let it break a successful run.
                logger.warning("Could not write result log to %s: %s", log_path, exc)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
