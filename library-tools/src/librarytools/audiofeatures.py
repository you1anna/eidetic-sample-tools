"""Lightweight acoustic features for read-only sample analysis."""

from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

from .featurecache import FeatureRecord

TARGET_SR = 22_050
EPSILON = 1e-12

try:  # optional guard: non-audio tools should still import without Tier-1 deps.
    import numpy as np
except ImportError:  # pragma: no cover - exercised only in dependency-missing installs.
    np = None  # type: ignore[assignment]

try:
    import soundfile as sf
except ImportError:  # pragma: no cover - exercised only in dependency-missing installs.
    sf = None  # type: ignore[assignment]


def extract(path: Path, cache_path: Path | None = None) -> FeatureRecord:
    """Extract Tier-1 features, returning an error record rather than raising."""
    record_path = cache_path or path
    try:
        stat = path.stat()
    except OSError as exc:
        return FeatureRecord(path=record_path, size=0, mtime=0.0, error=str(exc))

    if np is None:
        return FeatureRecord(
            path=record_path,
            size=stat.st_size,
            mtime=stat.st_mtime,
            error="numpy is not installed",
        )

    try:
        audio, sample_rate = _decode(path)
        if len(audio) == 0:
            raise ValueError("decoded audio is empty")
        audio = _resample(audio, sample_rate, TARGET_SR)
        values = features_from_mono(audio, TARGET_SR)
        return FeatureRecord(path=record_path, size=stat.st_size, mtime=stat.st_mtime, **values)
    except Exception as exc:  # noqa: BLE001 - cache decode failures as data, do not crash.
        return FeatureRecord(path=record_path, size=stat.st_size, mtime=stat.st_mtime, error=str(exc))


def features_from_mono(audio, sample_rate: int) -> dict[str, float]:
    """Compute inspectable features from mono float audio."""
    if np is None:  # pragma: no cover - guarded by extract, kept for direct calls.
        raise RuntimeError("numpy is not installed")
    mono = np.asarray(audio, dtype=np.float32)
    mono = np.nan_to_num(mono, copy=False)
    if mono.ndim != 1:
        raise ValueError("features_from_mono expects a one-dimensional signal")
    duration_s = len(mono) / sample_rate if sample_rate else 0.0
    abs_audio = np.abs(mono)
    peak = float(np.max(abs_audio)) if len(abs_audio) else 0.0
    rms = float(np.sqrt(np.mean(np.square(mono)))) if len(mono) else 0.0
    crest = float(peak / rms) if rms > EPSILON else 0.0
    silence = _silence_features(abs_audio, peak, sample_rate)
    spectral = _spectral_features(mono, sample_rate)
    return {
        "duration_s": duration_s,
        "peak": peak,
        "rms": rms,
        "crest": crest,
        **silence,
        **spectral,
        "onset_density": _onset_density(mono, sample_rate, duration_s),
        "zcr": _zcr(mono),
    }


def _decode(path: Path):
    soundfile_error: Exception | None = None
    if sf is not None:
        try:
            audio, sample_rate = sf.read(path, dtype="float32", always_2d=False)
            return _mono(audio), int(sample_rate)
        except Exception as exc:  # noqa: BLE001 - ffmpeg fallback handles format gaps.
            soundfile_error = exc
    try:
        return _decode_ffmpeg(path), TARGET_SR
    except Exception as exc:  # noqa: BLE001
        if soundfile_error is not None:
            raise ValueError(f"soundfile failed: {soundfile_error}; ffmpeg failed: {exc}") from exc
        raise


def _decode_ffmpeg(path: Path):
    if np is None:  # pragma: no cover
        raise RuntimeError("numpy is not installed")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")
    result = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-i",
            str(path),
            "-ac",
            "1",
            "-ar",
            str(TARGET_SR),
            "-f",
            "f32le",
            "-",
        ],
        capture_output=True,
        check=True,
    )
    return np.frombuffer(result.stdout, dtype="<f4").astype(np.float32)


def _mono(audio):
    if np is None:  # pragma: no cover
        raise RuntimeError("numpy is not installed")
    arr = np.asarray(audio, dtype=np.float32)
    if arr.ndim == 2:
        arr = np.mean(arr, axis=1)
    return arr


def _resample(audio, source_sr: int, target_sr: int):
    if np is None:  # pragma: no cover
        raise RuntimeError("numpy is not installed")
    if source_sr == target_sr:
        return np.asarray(audio, dtype=np.float32)
    if source_sr <= 0 or len(audio) == 0:
        return np.asarray(audio, dtype=np.float32)
    duration = len(audio) / source_sr
    target_len = max(1, int(round(duration * target_sr)))
    source_x = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    target_x = np.linspace(0.0, 1.0, num=target_len, endpoint=False)
    return np.interp(target_x, source_x, audio).astype(np.float32)


def _silence_features(abs_audio, peak: float, sample_rate: int) -> dict[str, float]:
    if np is None:  # pragma: no cover
        raise RuntimeError("numpy is not installed")
    if peak <= EPSILON or len(abs_audio) == 0:
        return {
            "attack_ms": 0.0,
            "tail_ms": 0.0,
            "head_silence_ms": 0.0,
            "tail_silence_ms": 0.0,
        }
    threshold = max(peak * 0.01, EPSILON)
    active = np.flatnonzero(abs_audio >= threshold)
    if len(active) == 0:
        return {
            "attack_ms": 0.0,
            "tail_ms": 0.0,
            "head_silence_ms": 0.0,
            "tail_silence_ms": 0.0,
        }
    first = int(active[0])
    last = int(active[-1])
    peak_index = int(np.argmax(abs_audio))
    attack_candidates = np.flatnonzero(abs_audio[first:] >= peak * 0.9)
    attack_index = first + int(attack_candidates[0]) if len(attack_candidates) else peak_index
    return {
        "attack_ms": max(0.0, (attack_index - first) / sample_rate * 1000.0),
        "tail_ms": max(0.0, (last - peak_index) / sample_rate * 1000.0),
        "head_silence_ms": first / sample_rate * 1000.0,
        "tail_silence_ms": (len(abs_audio) - 1 - last) / sample_rate * 1000.0,
    }


def _spectral_features(audio, sample_rate: int) -> dict[str, float]:
    if np is None:  # pragma: no cover
        raise RuntimeError("numpy is not installed")
    if len(audio) == 0:
        return {
            "centroid_hz": 0.0,
            "flatness": 0.0,
            "sub_ratio": 0.0,
            "low_ratio": 0.0,
            "mid_ratio": 0.0,
            "high_ratio": 0.0,
        }
    windowed = audio * np.hanning(len(audio))
    magnitudes = np.abs(np.fft.rfft(windowed))
    power = np.square(magnitudes)
    freqs = np.fft.rfftfreq(len(windowed), d=1.0 / sample_rate)
    total_power = float(np.sum(power))
    total_magnitude = float(np.sum(magnitudes))
    if total_power <= EPSILON or total_magnitude <= EPSILON:
        return {
            "centroid_hz": 0.0,
            "flatness": 0.0,
            "sub_ratio": 0.0,
            "low_ratio": 0.0,
            "mid_ratio": 0.0,
            "high_ratio": 0.0,
        }
    flatness = float(math.exp(float(np.mean(np.log(power + EPSILON)))) / (float(np.mean(power)) + EPSILON))
    return {
        "centroid_hz": float(np.sum(freqs * magnitudes) / total_magnitude),
        "flatness": flatness,
        "sub_ratio": _band_ratio(power, freqs, 0.0, 120.0, total_power),
        "low_ratio": _band_ratio(power, freqs, 0.0, 250.0, total_power),
        "mid_ratio": _band_ratio(power, freqs, 250.0, 4_000.0, total_power),
        "high_ratio": _band_ratio(power, freqs, 4_000.0, sample_rate / 2.0 + 1.0, total_power),
    }


def _band_ratio(power, freqs, low: float, high: float, total_power: float) -> float:
    if np is None:  # pragma: no cover
        raise RuntimeError("numpy is not installed")
    mask = (freqs >= low) & (freqs < high)
    return float(np.sum(power[mask]) / total_power) if total_power > EPSILON else 0.0


def _onset_density(audio, sample_rate: int, duration_s: float) -> float:
    if np is None:  # pragma: no cover
        raise RuntimeError("numpy is not installed")
    if duration_s <= EPSILON or len(audio) < 1024:
        return 0.0
    frame = 1024
    hop = 512
    envelope = []
    for start in range(0, len(audio) - frame + 1, hop):
        chunk = audio[start:start + frame]
        envelope.append(float(np.sqrt(np.mean(np.square(chunk)))))
    if len(envelope) < 3:
        return 0.0
    env = np.asarray(envelope, dtype=np.float32)
    flux = np.maximum(0.0, np.diff(env))
    if len(flux) == 0 or float(np.max(flux)) <= EPSILON:
        return 0.0
    threshold = float(np.mean(flux) + np.std(flux))
    peaks = 0
    for idx in range(1, len(flux) - 1):
        if flux[idx] > threshold and flux[idx] >= flux[idx - 1] and flux[idx] >= flux[idx + 1]:
            peaks += 1
    if len(flux) == 1 and flux[0] > threshold:
        peaks = 1
    return peaks / duration_s


def _zcr(audio) -> float:
    if np is None:  # pragma: no cover
        raise RuntimeError("numpy is not installed")
    if len(audio) < 2:
        return 0.0
    signs = np.signbit(audio)
    return float(np.mean(signs[1:] != signs[:-1]))
