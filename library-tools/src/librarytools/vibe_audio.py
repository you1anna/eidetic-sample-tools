"""Bounded, local audio rendering for the experimental groove audition page.

Sources are only read. Callers own source identity checks and publication of the
derived files. All cuts are quantized to native frames before tempo processing;
every placement is rounded from the absolute beat clock, avoiding loop drift.
"""

from __future__ import annotations

from fractions import Fraction
import json
import math
from numbers import Real
from pathlib import Path
import subprocess

import numpy as np
import soundfile as sf

SAMPLE_RATE = 48000
MAX_SOURCE_SECONDS = 120
_FADE_FRAMES = 240  # Five milliseconds at the output rate.
# Source hashes must cover every audio byte consumed. Container/playlist formats
# such as concat and MOV can follow references to separately mutable files.
_AUDIO_DEMUXERS = "wav,aiff,flac,mp3,ogg"
_FIELDS = (
    "bpm", "bars", "anchor_start_s", "anchor_end_s", "anchor_bars",
    "vocal_start_s", "vocal_end_s", "vocal_fit_beats", "offset_beats",
    "repeat_beats", "anchor_gain_db", "vocal_gain_db",
)


class AudioError(ValueError):
    """Invalid audio, a recipe that cannot fit, or an unavailable local engine."""


def _run(command: list[str]) -> bytes:
    try:
        return subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=True, timeout=45,
        ).stdout
    except FileNotFoundError as exc:
        raise AudioError(
            f"{command[0]} is unavailable; install FFmpeg (including ffprobe) and add it to PATH."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioError(f"{command[0]} exceeded 45 seconds; choose a shorter local audio file.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", errors="replace").strip()[-1000:]
        if "not on whitelist" in detail.lower():
            raise AudioError(
                "Unsupported audio format; use a self-contained WAV, AIFF, FLAC, MP3 or Ogg file. "
                "Playlists and containers that can reference other files are not supported."
            ) from exc
        raise AudioError(f"{command[0]} could not process the audio: {detail or 'unknown engine error'}") from exc
    except OSError as exc:
        raise AudioError(f"Cannot run {command[0]}: {exc}") from exc


def ffmpeg_version() -> str:
    """Return the installed engine version used in preview cache identities."""
    lines = _run(["ffmpeg", "-version"]).decode("utf-8", errors="replace").splitlines()
    if not lines or not lines[0].startswith("ffmpeg version "):
        raise AudioError("FFmpeg did not report its version; check the installed ffmpeg executable.")
    return lines[0]


def _source_path(path: Path) -> Path:
    path = Path(path).resolve()
    if not path.is_file():
        raise AudioError(f"Source audio is missing or is not a regular file: {path}")
    return path


def probe_source(path: Path) -> dict:
    """Read the first audio stream's native rate, channels, duration and frames.

    FFprobe's native stream time base supplies frame counts when available;
    container duration is a fallback for formats without stream timestamps.
    Only self-contained audio demuxers are allowed, regardless of extension.
    Network protocols are also disabled.
    """
    path = _source_path(path)
    raw = _run([
        "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
        "-format_whitelist", _AUDIO_DEMUXERS,
        "-select_streams", "a:0", "-show_entries",
        "stream=sample_rate,channels,duration,duration_ts,time_base:format=duration",
        "-of", "json", str(path),
    ])
    try:
        data = json.loads(raw)
        stream = data["streams"][0]
        rate = int(stream["sample_rate"])
        channels = int(stream["channels"])
        if rate <= 0 or channels <= 0:
            raise ValueError("invalid audio format")
        if "duration_ts" in stream and "time_base" in stream:
            duration = Fraction(str(stream["duration_ts"])) * Fraction(stream["time_base"])
        else:
            duration = Fraction(str(stream.get("duration") or data.get("format", {}).get("duration")))
        frames = round(duration * rate)
        duration_s = frames / rate
        if frames <= 0 or not math.isfinite(duration_s):
            raise ValueError("empty or unknown duration")
    except (KeyError, IndexError, TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
        raise AudioError(f"Cannot probe a usable audio stream and duration in {path}; use a valid WAV, AIFF or FLAC file.") from exc
    if duration_s > MAX_SOURCE_SECONDS:
        raise AudioError(f"Source audio is {duration_s:.3f} seconds; choose a file no longer than 120 seconds: {path}")
    return {"duration_s": duration_s, "sample_rate": rate, "channels": channels, "frames": frames}


def _decode(path: Path, filters: str | None = None) -> np.ndarray:
    command = [
        "ffmpeg", "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe",
        "-format_whitelist", _AUDIO_DEMUXERS,
        "-i", str(path), "-map", "0:a:0", "-vn", "-sn", "-dn",
    ]
    if filters:
        command.extend(["-af", filters])
    # The additional frame reveals overlong decode output without allowing an
    # unbounded stdout allocation, even if a file's duration metadata is wrong.
    command.extend([
        "-t", str(MAX_SOURCE_SECONDS + 1 / SAMPLE_RATE),
        "-ar", str(SAMPLE_RATE), "-ac", "2", "-f", "f32le", "pipe:1",
    ])
    raw = _run(command)
    if not raw or len(raw) % 8:
        raise AudioError(f"FFmpeg decoded no complete stereo audio frames from {path}; choose another source or cut.")
    samples = np.frombuffer(raw, dtype="<f4").reshape(-1, 2).copy()
    if len(samples) > MAX_SOURCE_SECONDS * SAMPLE_RATE:
        raise AudioError("Decoded audio exceeds the 120-second limit; choose a shorter source or cut.")
    if not np.isfinite(samples).all():
        raise AudioError(f"Decoded audio contains nonfinite samples in {path}; repair or replace this source.")
    return samples


def decode_source(path: Path) -> np.ndarray:
    """Decode a source of at most 120 seconds to 48 kHz stereo float32."""
    path = _source_path(path)
    probe_source(path)
    return _decode(path)


def _number(name: str, value) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise AudioError(f"{name} must be a finite number.")
    try:
        value = float(value)
    except (ValueError, OverflowError) as exc:
        raise AudioError(f"{name} must be a finite number.") from exc
    if not math.isfinite(value):
        raise AudioError(f"{name} must be a finite number.")
    return 0.0 if value == 0 else value


def _tempo_ratio(role: str, source_seconds: float, target_seconds: float) -> float:
    if target_seconds <= 0:
        raise AudioError(f"{role} tempo fit must have a positive duration.")
    ratio = source_seconds / target_seconds
    if not 0.5 - 1e-12 <= ratio <= 2 + 1e-12:
        raise AudioError(f"{role} tempo ratio must be between 0.5 and 2; change the cut length or fitted beats/bars.")
    return min(2.0, max(0.5, ratio))


def validate_recipe(recipe: dict, anchor_duration_s: float, vocal_duration_s: float) -> dict:
    """Validate every required numeric field and return a canonical fresh dict."""
    if not isinstance(recipe, dict):
        raise AudioError("Recipe must be an object containing every audio control.")
    missing = set(_FIELDS) - recipe.keys()
    unknown = recipe.keys() - set(_FIELDS)
    if missing:
        raise AudioError(f"Recipe is missing fields: {', '.join(sorted(missing))}.")
    if unknown:
        raise AudioError(f"Recipe has unknown fields: {', '.join(sorted(map(str, unknown)))}.")
    canonical = {key: _number(key, recipe[key]) for key in _FIELDS}
    if not 60 <= canonical["bpm"] <= 180:
        raise AudioError("bpm must be between 60 and 180.")
    if canonical["bars"] != 8:
        raise AudioError("bars must be 8 for this pilot.")
    if canonical["anchor_bars"] not in (1, 2, 4, 8):
        raise AudioError("anchor_bars must be 1, 2, 4 or 8.")
    canonical["bars"] = 8
    canonical["anchor_bars"] = int(canonical["anchor_bars"])
    for role, duration in (("anchor", anchor_duration_s), ("vocal", vocal_duration_s)):
        duration = _number(f"{role} duration", duration)
        if not 0 < duration <= MAX_SOURCE_SECONDS:
            raise AudioError(f"{role} duration must be greater than zero and no more than 120 seconds.")
        start, end = canonical[f"{role}_start_s"], canonical[f"{role}_end_s"]
        if not 0 <= start < end <= duration:
            raise AudioError(f"{role} cut must satisfy 0 <= start < end <= source duration ({duration:.6f}s).")
        if not -36 <= canonical[f"{role}_gain_db"] <= 0:
            raise AudioError(f"{role}_gain_db must be between -36 and 0 dB.")
    for field in ("vocal_fit_beats", "offset_beats", "repeat_beats"):
        if not 0 <= canonical[field] <= 32:
            raise AudioError(f"{field} must be between 0 and 32 beats.")
    beat_seconds = 60 / canonical["bpm"]
    _tempo_ratio("anchor", canonical["anchor_end_s"] - canonical["anchor_start_s"],
                 canonical["anchor_bars"] * 4 * beat_seconds)
    vocal_seconds = canonical["vocal_end_s"] - canonical["vocal_start_s"]
    if canonical["vocal_fit_beats"]:
        target = canonical["vocal_fit_beats"] * beat_seconds
        _tempo_ratio("vocal", vocal_seconds, target)
        vocal_seconds = target
    if canonical["offset_beats"] * beat_seconds + vocal_seconds > 32 * beat_seconds + 1e-12:
        raise AudioError("Place a complete first vocal event inside the eight-bar scene; shorten the cut or reduce offset_beats.")
    if canonical["repeat_beats"] and canonical["repeat_beats"] * beat_seconds < vocal_seconds - 1e-12:
        raise AudioError("Vocal repetitions would overlap; increase repeat_beats or shorten the vocal event.")
    return canonical


def _cut_bounds(info: dict, recipe: dict, role: str) -> dict:
    rate = info["sample_rate"]
    start = round(recipe[f"{role}_start_s"] * rate)
    end = min(info["frames"], round(recipe[f"{role}_end_s"] * rate))
    if end <= start:
        raise AudioError(f"{role} cut contains no native audio frames; increase its length.")
    return {"start_frame": start, "end_frame": end, "sample_rate": rate}


def _length(samples: np.ndarray, frames: int) -> np.ndarray:
    result = np.zeros((frames, 2), dtype=np.float32)
    count = min(frames, len(samples))
    result[:count] = samples[:count]
    return result


def _fade(samples: np.ndarray) -> np.ndarray:
    length = min(_FADE_FRAMES, len(samples) // 2)
    if length:
        ramp = np.linspace(0, 1, length, dtype=np.float32)[:, None]
        samples[:length] *= ramp
        samples[-length:] *= ramp[::-1]
    return samples


def _render_cut(path: Path, bounds: dict, ratio: float, frames: int) -> np.ndarray:
    # atrim runs before resampling, so these refer to the source's native frames.
    filters = (
        f"atrim=start_sample={bounds['start_frame']}:end_sample={bounds['end_frame']},"
        f"asetpts=PTS-STARTPTS,aresample={SAMPLE_RATE}"
    )
    if ratio != 1:
        filters += f",atempo={ratio:.15g}"
    return _fade(_length(_decode(path, filters), frames))


def render_audio(anchor_path: Path, vocal_path: Path, recipe: dict, output_dir: Path) -> dict:
    """Create equal-length anchor/vocal/mix PCM24 WAVs and processing metadata.

    FFmpeg atempo may differ from the requested duration by a small algorithmic
    tail. Cuts are padded/trimmed to the beat-clock frame count, then faded. This
    timing guarantee does not establish perceptual quality; audition the result.
    Existing output files are never overwritten. Callers should render into a
    private temporary directory and publish only after their integrity checks.
    """
    anchor_path, vocal_path = _source_path(anchor_path), _source_path(vocal_path)
    anchor_info, vocal_info = probe_source(anchor_path), probe_source(vocal_path)
    recipe = validate_recipe(recipe, anchor_info["duration_s"], vocal_info["duration_s"])
    output_dir = Path(output_dir)
    names = ("anchor", "vocal", "mix")
    paths = {name: output_dir / f"{name}.wav" for name in names}
    if any(path.exists() or path.is_symlink() for path in paths.values()):
        raise AudioError("Render output already exists; choose a fresh output directory to avoid overwriting audio.")
    version = ffmpeg_version()
    cuts = {"anchor": _cut_bounds(anchor_info, recipe, "anchor"),
            "vocal": _cut_bounds(vocal_info, recipe, "vocal")}
    cut_seconds = {role: (cut["end_frame"] - cut["start_frame"]) / cut["sample_rate"]
                   for role, cut in cuts.items()}
    beat_seconds = 60 / recipe["bpm"]
    beat_frames = beat_seconds * SAMPLE_RATE
    scene_frames = round(32 * beat_frames)
    anchor_beats = recipe["anchor_bars"] * 4
    vocal_seconds = recipe["vocal_fit_beats"] * beat_seconds or cut_seconds["vocal"]
    ratios = {"anchor": _tempo_ratio("anchor", cut_seconds["anchor"], anchor_beats * beat_seconds),
              "vocal": _tempo_ratio("vocal", cut_seconds["vocal"], vocal_seconds)}
    anchor_segment = _render_cut(anchor_path, cuts["anchor"], ratios["anchor"], round(anchor_beats * beat_frames))
    vocal_segment = _render_cut(vocal_path, cuts["vocal"], ratios["vocal"], round(vocal_seconds * SAMPLE_RATE))
    anchor = np.zeros((scene_frames, 2), dtype=np.float32)
    vocal = np.zeros_like(anchor)
    for beat in range(0, 32, anchor_beats):
        start, end = round(beat * beat_frames), round((beat + anchor_beats) * beat_frames)
        anchor[start:end] = _length(anchor_segment, end - start)
    offset, interval = recipe["offset_beats"], recipe["repeat_beats"]
    vocal_frames = vocal_seconds * SAMPLE_RATE
    first_end = round(offset * beat_frames + vocal_frames)
    if len(vocal_segment) == 0 or first_end > scene_frames:
        raise AudioError("A complete vocal event must fit inside the scene after native-frame rounding; adjust the cut or offset.")
    if interval and interval * beat_frames < vocal_frames - 1e-9:
        raise AudioError("Vocal repetitions would overlap after frame rounding; increase repeat_beats.")
    index = 0
    while True:
        exact_start = (offset + index * interval) * beat_frames
        start, end = round(exact_start), round(exact_start + vocal_frames)
        if end > scene_frames:
            break
        vocal[start:end] = _length(vocal_segment, end - start)
        if not interval:
            break
        index += 1
    anchor *= 10 ** (recipe["anchor_gain_db"] / 20)
    vocal *= 10 ** (recipe["vocal_gain_db"] / 20)
    # Float source WAVs may legitimately exceed unity. Accumulate in float64
    # before common attenuation so even finite float32 extremes cannot overflow.
    mix = anchor.astype(np.float64) + vocal
    peak = max(float(np.max(np.abs(layer))) for layer in (anchor, vocal, mix))
    master_gain = min(1.0, 0.95 / peak) if peak else 1.0
    layers = {"anchor": anchor, "vocal": vocal, "mix": mix}
    created: list[Path] = []
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, layer in layers.items():
            with paths[name].open("xb") as handle:
                created.append(paths[name])
                sf.write(handle, layer * master_gain, SAMPLE_RATE, format="WAV", subtype="PCM_24")
    except (OSError, ValueError, sf.LibsndfileError) as exc:
        for path in created:
            path.unlink(missing_ok=True)
        raise AudioError(f"Cannot write preview WAVs to {output_dir}: {exc}") from exc
    return {
        "recipe": recipe, "sample_rate": SAMPLE_RATE, "channels": 2,
        "frames": scene_frames, "output_frames": scene_frames,
        "duration_s": scene_frames / SAMPLE_RATE, "source_cuts": cuts,
        "tempo_ratios": ratios, "ffmpeg_version": version, "master_gain": master_gain,
    }
