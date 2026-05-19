"""FCM format model, parser, and writer.

This subpackage owns the Brother ScanNCut FCM binary format end-to-end: the
data model (:mod:`.model`), the byte-stream parser (:mod:`.parser`), and the
byte-exact encoder (:mod:`.writer`). Constants and bitflag tables live in
:mod:`.constants`.
"""

from __future__ import annotations
