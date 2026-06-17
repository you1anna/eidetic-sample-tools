from __future__ import annotations

from pathlib import Path

from librarytools import probe


def test_duration_none_for_nonexistent_file():
    assert probe.duration(Path("/no/such/file.wav")) is None


def test_duration_none_when_ffprobe_run_raises_oserror(monkeypatch, tmp_path):
    import subprocess as _sp
    target = tmp_path / "x.wav"
    target.write_text("not really audio")

    monkeypatch.setattr(probe.shutil, "which", lambda _: "/usr/bin/ffprobe")
    def _boom(*a, **k):
        raise FileNotFoundError("ffprobe vanished")
    monkeypatch.setattr(probe.subprocess, "run", _boom)

    assert probe.duration(target) is None
