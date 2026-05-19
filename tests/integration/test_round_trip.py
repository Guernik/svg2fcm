"""Byte-exact round-trip of every checked-in FCM fixture.

If this test ever fails, the encoder or parser has lost information. Any FCM
file we can read, we must be able to write back byte-identically.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from svg2fcm import encode_fcm, parse_fcm

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

FCM_SAMPLES = sorted(FIXTURES.glob("*.fcm"))


@pytest.mark.parametrize("sample_path", FCM_SAMPLES, ids=lambda p: p.name)
def test_round_trip_is_byte_exact(sample_path: Path) -> None:
    original = sample_path.read_bytes()
    fcm = parse_fcm(original)
    re_encoded = encode_fcm(fcm)
    assert re_encoded == original, (
        f"Round-trip mismatch for {sample_path.name}: "
        f"original={len(original)} bytes, re-encoded={len(re_encoded)} bytes"
    )


def test_at_least_one_fixture_exists() -> None:
    assert FCM_SAMPLES, "No .fcm fixture files found in tests/fixtures/"
