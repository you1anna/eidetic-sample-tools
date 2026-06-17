from __future__ import annotations

from pathlib import Path

from librarytools import probe


def test_duration_none_for_nonexistent_file():
    assert probe.duration(Path("/no/such/file.wav")) is None
