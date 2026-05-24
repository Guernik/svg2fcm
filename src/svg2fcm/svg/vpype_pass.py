"""Optional vpype pre-processing pass.

Pipes the input SVG text through a user-supplied vpype pipeline string and
returns the resulting SVG text. vpype itself is an optional dependency —
import is deferred so users who don't pass ``--vpype`` never need it
installed.

vpype's SVG writer renames top-level ``<g>`` layers to its internal
numeric IDs (``1``, ``2``, …) and drops the source's ``id`` /
``inkscape:label`` values. To preserve the per-pen filenames downstream
(``benteveo_cyan.fcm`` instead of ``benteveo_1.fcm``), we capture the
original labels before the pass and re-apply them by document order
afterwards, when the layer count matches.
"""

from __future__ import annotations

import contextlib
import io
import logging
import shlex
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

from svg2fcm.exceptions import Svg2FcmError

logger = logging.getLogger(__name__)

SVG_NS = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"

_SVG_TAG = f"{{{SVG_NS}}}svg"
_G_TAG = f"{{{SVG_NS}}}g"
_LABEL_ATTR = f"{{{INKSCAPE_NS}}}label"


@contextlib.contextmanager
def _preserve_root_logger() -> Iterator[None]:
    """Snapshot the root logger's handlers/level around a vpype call.

    vpype's CLI calls ``logging.basicConfig(force=True)`` during command
    initialisation, which wipes the handlers svg2fcm installed (console
    + DEBUG capture). We save them before and restore them after so log
    messages emitted later in the same run still reach our handlers.
    """
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    try:
        yield
    finally:
        # Replace whatever vpype left in place with our originals.
        for h in list(root.handlers):
            root.removeHandler(h)
        for h in saved_handlers:
            root.addHandler(h)
        root.setLevel(saved_level)


class VpypeNotInstalledError(Svg2FcmError):
    """Raised when ``--vpype`` is used but vpype is not importable."""


class VpypePipelineError(Svg2FcmError):
    """Raised when the vpype pipeline itself fails."""


def run_vpype(svg_text: str, pipeline: str) -> str:
    """Run ``pipeline`` against ``svg_text`` via vpype, return new SVG text.

    ``pipeline`` is the verbatim vpype command string the user would type
    after ``vpype``, minus the ``read`` and ``write`` bookends — e.g.
    ``"linemerge --tolerance 0.1mm linesimplify"``. We supply ``read`` and
    ``write`` ourselves so the caller never has to think about temp paths.

    Layer labels from the source SVG (``id`` or ``inkscape:label`` on each
    top-level ``<g>``) are restored on the vpype output when the layer
    count is unchanged. If the pipeline adds, drops, or merges layers the
    remap is skipped and a warning is logged.
    """
    try:
        import vpype_cli
    except ImportError as exc:
        raise VpypeNotInstalledError(
            "--vpype requires the optional 'vpype' extra. "
            "Install with: pipx install --python python3.13 --force '.[vpype]'"
        ) from exc

    original_labels = _extract_top_level_labels(svg_text)
    logger.debug(
        "Captured %d top-level layer label(s) before vpype: %s",
        len(original_labels),
        original_labels or "<none>",
    )

    with tempfile.TemporaryDirectory(prefix="svg2fcm-vpype-") as tmp:
        in_path = Path(tmp) / "in.svg"
        out_path = Path(tmp) / "out.svg"
        in_path.write_text(svg_text, encoding="utf-8")

        full = f"read {shlex.quote(str(in_path))} {pipeline} write {shlex.quote(str(out_path))}"
        logger.debug("vpype invocation: %s", full)
        try:
            with _preserve_root_logger():
                vpype_cli.execute(full)
        except Exception as exc:  # vpype/click raise a variety of types
            raise VpypePipelineError(f"vpype pipeline failed: {exc}") from exc

        if not out_path.exists():
            raise VpypePipelineError(
                "vpype pipeline completed but produced no output SVG "
                "(did the pipeline include a non-SVG 'write'?)"
            )
        out_text = out_path.read_text(encoding="utf-8")

    return _restore_labels(out_text, original_labels)


def vpype_stat(svg_text: str) -> str:
    """Return the output of vpype's ``stat`` command on ``svg_text``.

    Runs ``read <tmp>.svg stat`` and captures stdout. Returns an empty
    string and logs a warning if vpype is not installed or the command
    fails — ``stat`` is purely informational, so we never let it abort
    the main conversion.
    """
    try:
        import vpype_cli
    except ImportError:
        return ""

    with tempfile.TemporaryDirectory(prefix="svg2fcm-vpype-stat-") as tmp:
        in_path = Path(tmp) / "in.svg"
        in_path.write_text(svg_text, encoding="utf-8")
        buf = io.StringIO()
        try:
            with _preserve_root_logger(), contextlib.redirect_stdout(buf):
                vpype_cli.execute(f"read {shlex.quote(str(in_path))} stat")
        except Exception as exc:
            logger.warning("vpype stat failed: %s", exc)
            return ""
        return buf.getvalue()


def _extract_top_level_labels(svg_text: str) -> list[str]:
    """Return the label of each top-level ``<g>`` in document order.

    Label priority matches :mod:`svg2fcm.svg.layers`: ``inkscape:label``
    first, then ``id``, then ``""``. Returns ``[]`` if the document
    doesn't parse — the vpype pass will surface a clearer error.
    """
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError:
        return []
    if root.tag != _SVG_TAG:
        return []
    return [
        child.get(_LABEL_ATTR) or child.get("id") or "" for child in root if child.tag == _G_TAG
    ]


def _restore_labels(svg_text: str, labels: list[str]) -> str:
    """Write ``labels`` back onto the top-level ``<g>`` elements of ``svg_text``.

    Only applies when the count of top-level ``<g>`` elements in the
    vpype output equals ``len(labels)`` — otherwise the pipeline changed
    the layer structure and we can't safely remap. In that case the
    vpype output is returned unchanged and a warning is logged.

    Empty labels are skipped so vpype's default (``inkscape:label="1"``,
    etc.) is left in place when the source had no name to begin with.
    """
    if not labels:
        return svg_text

    ET.register_namespace("", SVG_NS)
    ET.register_namespace("inkscape", INKSCAPE_NS)

    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError:
        return svg_text
    if root.tag != _SVG_TAG:
        return svg_text

    groups = [child for child in root if child.tag == _G_TAG]
    if len(groups) != len(labels):
        logger.warning(
            "vpype changed the layer count (%d -> %d); keeping vpype's default "
            "layer labels. Per-pen output filenames will use vpype's numbering.",
            len(labels),
            len(groups),
        )
        return svg_text

    remapped = 0
    for group, label in zip(groups, labels, strict=True):
        if not label:
            continue
        group.set(_LABEL_ATTR, label)
        group.set("id", label)
        remapped += 1
    logger.debug("Restored %d/%d layer label(s) onto vpype output", remapped, len(labels))

    body = ET.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + body
