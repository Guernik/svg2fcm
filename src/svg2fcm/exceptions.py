"""Exception hierarchy for svg2fcm.

All errors raised by library code derive from :class:`Svg2FcmError`, so callers
(the CLI, the Inkscape extension shim, third-party consumers) can catch the base
class to handle anything we throw.
"""

from __future__ import annotations


class Svg2FcmError(Exception):
    """Base class for every exception raised by svg2fcm."""


class FcmParseError(Svg2FcmError):
    """Raised when a byte stream cannot be parsed as an FCM file."""


class FcmEncodeError(Svg2FcmError):
    """Raised when an :class:`~svg2fcm.fcm.model.FcmFile` cannot be serialised."""


class InvalidSvgError(Svg2FcmError):
    """Raised when an SVG document cannot be loaded or contains unsupported features."""


class GeometryOutOfBoundsError(Svg2FcmError):
    """Raised when SVG geometry falls outside the ScanNCut mat area."""
