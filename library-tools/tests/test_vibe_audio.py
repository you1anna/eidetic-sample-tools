"""Synthetic integration checks for the bounded groove audition renderer."""

import hashlib
import importlib
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf


def audio():
    return importlib.import_module("librarytools.vibe_audio")


def recipe(**changes):
    result = {
        "bpm": 120,
        "bars": 8,
        "anchor_start_s": 0,
        "anchor_end_s": 2,
        "anchor_bars": 1,
        "vocal_start_s": 0,
        "vocal_end_s": 0.5,
        "vocal_fit_beats": 0,
        "offset_beats": 1,
        "repeat_beats": 0,
        "anchor_gain_db": 0,
        "vocal_gain_db": 0,
    }
    result.update(changes)
    return result


@pytest.fixture
def ffmpeg_available():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg and FFprobe are required for real audio integration tests")


def tone(path: Path, seconds=2.0, rate=44100, frequency=220, amplitude=0.4):
    signal = amplitude * np.sin(2 * np.pi * frequency * np.arange(round(seconds * rate)) / rate)
    sf.write(path, signal, rate, subtype="PCM_24")
    return path


def read(path):
    samples, rate = sf.read(path, always_2d=True, dtype="float32")
    assert rate == 48000
    return samples


def dominant_frequency(samples):
    signal = samples[:, 0]
    spectrum = np.abs(np.fft.rfft(signal * np.hanning(len(signal))))
    return np.argmax(spectrum) * 48000 / len(signal)


def test_probe_reports_native_frames_and_decode_produces_stereo_48k(tmp_path, ffmpeg_available):
    path = tone(tmp_path / "mono.wav", seconds=1.25)
    module = audio()
    details = module.probe_source(path)
    assert details["sample_rate"] == 44100
    assert details["channels"] == 1
    assert details["frames"] == 55125
    assert details["duration_s"] == 1.25
    decoded = module.decode_source(path)
    assert decoded.shape == (60000, 2)
    assert decoded.dtype == np.float32
    np.testing.assert_array_equal(decoded[:, 0], decoded[:, 1])
    assert dominant_frequency(decoded) == pytest.approx(220, abs=1)


def test_recipe_canonicalizes_without_mutating_input():
    supplied = recipe()
    validated = audio().validate_recipe(supplied, 2.0, 0.5)
    assert validated == supplied
    assert validated is not supplied
    assert isinstance(validated["bpm"], float)
    assert isinstance(validated["anchor_bars"], int)


def test_engine_version_is_available_for_cache_identity(ffmpeg_available):
    assert audio().ffmpeg_version().startswith("ffmpeg version ")


@pytest.mark.parametrize("changes,match", [
    ({"bpm": float("nan")}, "bpm"),
    ({"bpm": float("inf")}, "bpm"),
    ({"bpm": "120"}, "bpm"),
    ({"bars": True}, "bars"),
    ({"bars": 4}, "bars"),
    ({"bpm": 59}, "bpm"),
    ({"bpm": 181}, "bpm"),
    ({"anchor_bars": 3}, "anchor_bars"),
    ({"anchor_start_s": -0.1}, "anchor"),
    ({"anchor_end_s": 2.01}, "anchor"),
    ({"anchor_start_s": 2}, "anchor"),
    ({"anchor_end_s": 0.5}, "anchor.*tempo"),
    ({"anchor_bars": 8}, "anchor.*tempo"),
    ({"vocal_start_s": -1}, "vocal"),
    ({"vocal_end_s": 0}, "vocal"),
    ({"vocal_end_s": 0.6}, "vocal"),
    ({"vocal_fit_beats": -1}, "vocal_fit_beats"),
    ({"vocal_fit_beats": 0.1}, "vocal.*tempo"),
    ({"offset_beats": -1}, "offset_beats"),
    ({"offset_beats": 31.5}, "complete.*vocal|vocal.*scene"),
    ({"repeat_beats": -1}, "repeat_beats"),
    ({"repeat_beats": 0.5}, "overlap"),
    ({"anchor_gain_db": 0.1}, "anchor_gain_db"),
    ({"vocal_gain_db": -36.1}, "vocal_gain_db"),
    ({"vocal_gain_db": None}, "vocal_gain_db"),
    ({"unrecognised": 1}, "unknown|Unknown"),
])
def test_rejects_invalid_recipes(changes, match):
    module = audio()
    with pytest.raises(module.AudioError, match=match):
        module.validate_recipe(recipe(**changes), 2.0, 0.5)


def test_missing_fields_and_invalid_durations_are_actionable():
    module = audio()
    with pytest.raises(module.AudioError, match="missing|Missing"):
        module.validate_recipe({"bpm": 120}, 2, 0.5)
    with pytest.raises(module.AudioError, match="duration"):
        module.validate_recipe(recipe(), float("nan"), 0.5)


def test_render_fits_native_cut_preserves_pitch_and_exact_scene(tmp_path, ffmpeg_available):
    anchor = tone(tmp_path / "a.wav", seconds=4, rate=44100)
    vocal = tone(tmp_path / "v.wav", seconds=1, rate=32000, frequency=440)
    originals = [hashlib.sha256(path.read_bytes()).hexdigest() for path in (anchor, vocal)]
    output = tmp_path / "render"
    meta = audio().render_audio(anchor, vocal, recipe(
        anchor_start_s=0.5, anchor_end_s=3.5,
        vocal_start_s=0.25, vocal_end_s=0.75, vocal_fit_beats=0.5,
    ), output)
    assert meta["frames"] == 768000
    assert meta["tempo_ratios"] == {"anchor": 1.5, "vocal": 2.0}
    assert meta["source_cuts"]["anchor"] == {
        "start_frame": 22050, "end_frame": 154350, "sample_rate": 44100,
    }
    assert meta["source_cuts"]["vocal"] == {
        "start_frame": 8000, "end_frame": 24000, "sample_rate": 32000,
    }
    assert "ffmpeg version" in meta["ffmpeg_version"]
    layers = {name: read(output / f"{name}.wav") for name in ("anchor", "vocal", "mix")}
    for name, samples in layers.items():
        assert samples.shape == (768000, 2)
        assert sf.info(output / f"{name}.wav").subtype == "PCM_24"
    assert dominant_frequency(layers["anchor"][10000:85000]) == pytest.approx(220, abs=2)
    assert dominant_frequency(layers["vocal"][24500:35000]) == pytest.approx(440, abs=6)
    assert np.count_nonzero(layers["vocal"][:24000]) == 0
    assert np.count_nonzero(layers["vocal"][36000:]) == 0
    assert np.max(np.abs(layers["vocal"][24240:35000])) > 0.1
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in (anchor, vocal)] == originals


def test_repeats_only_complete_events_with_fades_and_shared_headroom(tmp_path, ffmpeg_available):
    anchor = tmp_path / "a.wav"
    vocal = tmp_path / "v.wav"
    sf.write(anchor, np.full(96000, 0.8), 48000, subtype="FLOAT")
    sf.write(vocal, np.full(19200, 0.8), 48000, subtype="FLOAT")
    output = tmp_path / "render"
    meta = audio().render_audio(anchor, vocal, recipe(
        vocal_end_s=0.4, offset_beats=1, repeat_beats=4,
    ), output)
    a, v, mix = [read(output / f"{name}.wav") for name in ("anchor", "vocal", "mix")]
    assert 0 < meta["master_gain"] < 1
    assert np.max(np.abs(mix)) <= 0.950001
    np.testing.assert_allclose(a + v, mix, atol=3e-7)
    for onset in (24000, 120000, 216000, 312000, 408000, 504000, 600000, 696000):
        assert v[onset, 0] == 0
        assert 0 < v[onset + 10, 0] < v[onset + 1000, 0]
        assert v[onset + 19199, 0] == 0
        assert np.count_nonzero(v[onset + 19200:onset + 25000]) == 0


def test_fractional_beat_clock_has_exact_scene_and_skips_partial_last_event(tmp_path, ffmpeg_available):
    anchor = tone(tmp_path / "a.wav")
    vocal = tone(tmp_path / "v.wav", seconds=0.5, frequency=440)
    output = tmp_path / "render"
    audio().render_audio(anchor, vocal, recipe(bpm=140, offset_beats=0, repeat_beats=31), output)
    a, v, mix = [read(output / f"{name}.wav") for name in ("anchor", "vocal", "mix")]
    assert a.shape == v.shape == mix.shape == (658286, 2)
    assert np.count_nonzero(v[24000:]) == 0
    for cycle in range(1, 8):
        assert a[round(cycle * 4 * 60 / 140 * 48000), 0] == 0


def test_touching_fitted_vocal_repeats_follow_fractional_beat_clock(tmp_path, ffmpeg_available):
    anchor = tone(tmp_path / "a.wav")
    vocal = tone(tmp_path / "v.wav", seconds=0.5, frequency=440)
    output = tmp_path / "render"
    audio().render_audio(anchor, vocal, recipe(
        bpm=137, vocal_fit_beats=1, offset_beats=0, repeat_beats=1,
    ), output)
    v = read(output / "vocal.wav")
    assert v.shape == (672701, 2)
    for beat in range(32):
        onset = round(beat * 60 / 137 * 48000)
        assert v[onset, 0] == 0
        assert np.max(np.abs(v[onset + 500:onset + 5000])) > 0.1


def test_native_cut_excludes_audio_outside_selected_region(tmp_path, ffmpeg_available):
    rate = 44100
    anchor = tmp_path / "a.wav"
    source = np.concatenate([
        np.full(rate, 0.8),
        0.4 * np.sin(2 * np.pi * 220 * np.arange(2 * rate) / rate),
        np.full(rate, -0.8),
    ])
    sf.write(anchor, source, rate, subtype="PCM_24")
    vocal = tone(tmp_path / "v.wav", seconds=0.5)
    output = tmp_path / "render"
    audio().render_audio(anchor, vocal, recipe(anchor_start_s=1, anchor_end_s=3), output)
    a = read(output / "anchor.wav")
    assert np.abs(np.mean(a)) < 1e-4
    assert np.max(np.abs(a)) < 0.45
    assert dominant_frequency(a[1000:95000]) == pytest.approx(220, abs=1)


def test_stretched_click_train_retains_beat_spacing(tmp_path, ffmpeg_available):
    anchor = tmp_path / "a.wav"
    source = np.zeros(3 * 48000, dtype=np.float32)
    pulse = np.sin(np.linspace(0, np.pi, 120, dtype=np.float32))
    for onset in (7200, 43200, 79200, 115200):
        source[onset:onset + 120] = pulse
    sf.write(anchor, source, 48000, subtype="PCM_24")
    vocal = tone(tmp_path / "v.wav", seconds=0.5)
    output = tmp_path / "render"
    audio().render_audio(anchor, vocal, recipe(anchor_end_s=3), output)
    a = read(output / "anchor.wav")[:96000, 0]
    onsets = []
    for expected in (4800, 28800, 52800, 76800):
        start = expected - 1600
        window = np.abs(a[start:expected + 1600])
        assert np.max(window) > 0.2
        onsets.append(start + int(np.argmax(window)))
    np.testing.assert_allclose(np.diff(onsets), [24000, 24000, 24000], atol=1500)


def test_extreme_finite_float_sources_still_produce_finite_unclipped_outputs(tmp_path, ffmpeg_available):
    anchor = tmp_path / "a.wav"
    vocal = tmp_path / "v.wav"
    sf.write(anchor, np.full((96000, 2), 2.5e38, dtype=np.float32), 48000, subtype="FLOAT")
    sf.write(vocal, np.full((24000, 2), 2.5e38, dtype=np.float32), 48000, subtype="FLOAT")
    output = tmp_path / "render"
    audio().render_audio(anchor, vocal, recipe(), output)
    for name in ("anchor", "vocal", "mix"):
        samples = read(output / f"{name}.wav")
        assert np.isfinite(samples).all()
        assert np.max(np.abs(samples)) <= 0.950001
    assert np.max(read(output / "mix.wav")) > 0.9


def test_refuses_existing_output_and_never_overwrites_sources(tmp_path, ffmpeg_available):
    anchor = tone(tmp_path / "anchor.wav")
    vocal = tone(tmp_path / "vocal.wav", seconds=0.5)
    original = anchor.read_bytes()
    module = audio()
    with pytest.raises(module.AudioError, match="exist|overwrite|source"):
        module.render_audio(anchor, vocal, recipe(), tmp_path)
    assert anchor.read_bytes() == original
    assert not (tmp_path / "mix.wav").exists()


def test_rejects_missing_invalid_and_overlong_sources(tmp_path, ffmpeg_available):
    module = audio()
    with pytest.raises(module.AudioError, match="source|Source"):
        module.probe_source(tmp_path / "missing.wav")
    invalid = tmp_path / "invalid.wav"
    invalid.write_text("not audio")
    with pytest.raises(module.AudioError, match="probe|audio"):
        module.probe_source(invalid)
    long = tmp_path / "long.wav"
    sf.write(long, np.zeros(121 * 8000), 8000)
    with pytest.raises(module.AudioError, match="120"):
        module.decode_source(long)


def test_missing_ffprobe_and_failed_ffmpeg_are_actionable(tmp_path, monkeypatch, ffmpeg_available):
    source = tone(tmp_path / "source.wav")
    module = audio()
    monkeypatch.setenv("PATH", "")
    with pytest.raises(module.AudioError, match="[Ff][Ff]probe.*install|[Ii]nstall.*[Ff][Ff]mpeg"):
        module.probe_source(source)
    monkeypatch.undo()
    actual_run = subprocess.run

    def fail_decoder(command, **kwargs):
        if Path(command[0]).name == "ffmpeg":
            raise subprocess.CalledProcessError(1, command, stderr=b"decoder unavailable")
        return actual_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", fail_decoder)
    with pytest.raises(module.AudioError, match="FFmpeg|ffmpeg"):
        module.decode_source(source)


@pytest.mark.parametrize("suffix", ["wav", "ffconcat"])
@pytest.mark.parametrize("operation", ["probe", "decode", "render"])
def test_rejects_playlist_sources_referencing_mutable_audio(
    tmp_path, ffmpeg_available, suffix, operation,
):
    root = tmp_path / "sources"
    root.mkdir()
    child = tone(tmp_path / "outside.wav")
    (root / "child.wav").symlink_to(child)
    manifest = root / f"anchor.{suffix}"
    manifest.write_text("ffconcat version 1.0\nfile 'child.wav'\nduration 2\n")
    source_hash = hashlib.sha256(manifest.read_bytes()).hexdigest()
    # The referenced audio can change while the registered source hash is fixed.
    tone(child, frequency=440)
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == source_hash
    vocal = tone(root / "vocal.wav", seconds=0.5)
    output = tmp_path / "render"
    module = audio()
    with pytest.raises(module.AudioError, match="self-contained"):
        if operation == "probe":
            module.probe_source(manifest)
        elif operation == "decode":
            module.decode_source(manifest)
        else:
            module.render_audio(manifest, vocal, recipe(), output)
    assert not output.exists()


def test_decoder_rejects_playlist_swapped_in_after_successful_probe(
    tmp_path, monkeypatch, ffmpeg_available,
):
    module = audio()
    source = tone(tmp_path / "source.wav")
    tone(tmp_path / "child.wav")
    real_probe = module.probe_source

    def probe_then_swap(path):
        result = real_probe(path)
        source.write_text("ffconcat version 1.0\nfile 'child.wav'\nduration 2\n")
        return result

    monkeypatch.setattr(module, "probe_source", probe_then_swap)
    with pytest.raises(module.AudioError, match="self-contained"):
        module.decode_source(source)


@pytest.mark.parametrize("extension", ["wav", "aiff", "flac", "mp3", "ogg"])
def test_self_contained_audio_formats_remain_supported(tmp_path, ffmpeg_available, extension):
    original = tone(tmp_path / "original.wav", seconds=1)
    source = tmp_path / f"source.{extension}"
    subprocess.run([
        "ffmpeg", "-nostdin", "-v", "error", "-i", str(original), str(source),
    ], check=True, capture_output=True)
    module = audio()
    assert module.probe_source(source)["duration_s"] == pytest.approx(1, abs=0.1)
    decoded = module.decode_source(source)
    assert decoded.shape[1] == 2
    assert dominant_frequency(decoded) == pytest.approx(220, abs=2)
