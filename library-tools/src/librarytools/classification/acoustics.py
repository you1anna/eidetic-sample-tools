"""Bounded acoustic measurements used by the packet classifier."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import numpy as np

from .domain import AcousticEvidence, ClassificationError


def rhythm_periodicity(onset, sample_rate: int) -> float:
    if len(onset) < 4:
        return 0.0
    import librosa

    autocorrelation = librosa.autocorrelate(onset, max_size=len(onset))
    if len(autocorrelation) <= 1 or autocorrelation[0] <= 0:
        return 0.0
    min_lag = max(1, int(round(60.0 * sample_rate / (240.0 * 512))))
    max_lag = min(
        len(autocorrelation),
        int(round(60.0 * sample_rate / (50.0 * 512))) + 1,
    )
    if max_lag <= min_lag:
        return 0.0
    return float(np.max(autocorrelation[min_lag:max_lag]) / autocorrelation[0])


def infer_bar_fit_error(duration_s: float, tempo_bpm: float) -> float:
    """Return relative error from the nearest whole number of four-beat bars."""
    if duration_s <= 0.0 or tempo_bpm <= 0.0:
        return 1.0
    bar_duration = 240.0 / tempo_bpm
    bar_count = max(1, round(duration_s / bar_duration))
    fitted_duration = bar_count * bar_duration
    return min(1.0, abs(duration_s - fitted_duration) / fitted_duration)


def measure_acoustic(path: Path, payload: Mapping[str, float | None]) -> AcousticEvidence:
    """Combine the identity-keyed cache with bounded librosa rhythm measurements."""
    try:
        import librosa
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ClassificationError(
            "audio classification requires the audio-classifier extra (librosa)"
        ) from exc

    audio, sample_rate = librosa.load(path, sr=22_050, mono=True, duration=120.0)
    onset = librosa.onset.onset_strength(y=audio, sr=sample_rate)
    if len(onset) >= 4 and float(np.max(onset)) > 0.0:
        onset_count = len(librosa.onset.onset_detect(onset_envelope=onset, sr=sample_rate))
        tempo_raw, beats = librosa.beat.beat_track(
            onset_envelope=onset, sr=sample_rate, units="frames",
        )
        tempo = float(np.asarray(tempo_raw).reshape(-1)[0])
        periodicity = rhythm_periodicity(onset, sample_rate)
        beat_confidence = min(1.0, max(0.0, periodicity) * min(1.0, len(beats) / 8.0))
    else:
        tempo = periodicity = beat_confidence = 0.0
        onset_count = 0

    duration = float(payload.get("duration_s") or (len(audio) / sample_rate if sample_rate else 0.0))
    head = float(payload.get("head_silence_ms") or 0.0)
    tail_silence = float(payload.get("tail_silence_ms") or 0.0)
    silence_ratio = min(1.0, (head + tail_silence) / max(duration * 1000.0, 1.0))
    return AcousticEvidence(
        duration_s=duration,
        onset_density=float(payload.get("onset_density") or 0.0),
        crest=float(payload.get("crest") or 0.0),
        attack_ms=float(payload.get("attack_ms") or 0.0),
        tail_ms=float(payload.get("tail_ms") or 0.0),
        silence_ratio=silence_ratio,
        tempo_bpm=tempo,
        beat_confidence=beat_confidence,
        periodicity=max(0.0, min(1.0, periodicity)),
        onset_count=onset_count,
        bar_fit_error=infer_bar_fit_error(duration, tempo),
    )
