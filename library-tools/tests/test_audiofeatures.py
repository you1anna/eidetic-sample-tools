from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from librarytools import audiofeatures


SR = 22050


def _write(path: Path, data: np.ndarray, sr: int = SR) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, data.astype(np.float32), sr)
    return path


def test_extract_marks_low_sine_as_subby_tonal_and_dark(tmp_path: Path):
    t = np.arange(SR, dtype=np.float32) / SR
    path = _write(tmp_path / "sub.wav", 0.7 * np.sin(2 * np.pi * 50 * t))

    record = audiofeatures.extract(path)

    assert record.error is None
    assert record.duration_s == 1.0
    assert record.sub_ratio > 0.85
    assert record.flatness < 0.05
    assert record.centroid_hz < 90


def test_extract_marks_white_noise_as_bright_and_noisy(tmp_path: Path):
    rng = np.random.default_rng(7)
    path = _write(tmp_path / "noise.wav", rng.normal(0, 0.2, SR).astype(np.float32))

    record = audiofeatures.extract(path)

    assert record.error is None
    assert record.flatness > 0.45
    assert record.centroid_hz > 4500
    assert record.zcr > 0.35


def test_extract_distinguishes_click_from_sustained_pad(tmp_path: Path):
    click = np.zeros(SR, dtype=np.float32)
    click[100] = 1.0
    click_path = _write(tmp_path / "click.wav", click)
    pad_t = np.arange(2 * SR, dtype=np.float32) / SR
    fade = np.linspace(1.0, 0.0, 2 * SR, dtype=np.float32)
    pad_path = _write(tmp_path / "pad.wav", 0.4 * np.sin(2 * np.pi * 220 * pad_t) * fade)

    click_record = audiofeatures.extract(click_path)
    pad_record = audiofeatures.extract(pad_path)

    assert click_record.error is None
    assert pad_record.error is None
    assert click_record.attack_ms < 5
    assert click_record.tail_ms < 100
    assert pad_record.tail_ms > 1000
    assert pad_record.onset_density < 2.0
