import csv
import hashlib
import math
import struct
import wave
from pathlib import Path

import pytest

from sampletools import config
from sampletools import export as export_mod
from sampletools.export import ExportError, build_crate_plan
from sampletools.probe import probe
from sampletools.probe import AudioInfo


def _source(root: Path, rel: str, payload: bytes) -> tuple[Path, str]:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest()


def _crate(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=("sample_id", "source_path", "role", "descriptor", "reason"),
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def _wav(path: Path, *, rate: int = 44_100, channels: int = 2) -> tuple[Path, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = bytearray()
    for index in range(rate // 20):
        value = int(10_000 * math.sin(2 * math.pi * 220 * index / rate))
        frames.extend(struct.pack("<h", value) * channels)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(channels)
        fh.setsampwidth(2)
        fh.setframerate(rate)
        fh.writeframes(bytes(frames))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_studio_native_device_rates_are_not_forced_to_common_denominator():
    assert config.get_spec("digitakt").rate == 48_000
    assert config.get_spec("tr8s").rate == 48_000
    assert config.get_spec("octatrack").rate == 44_100


def test_environment_selects_profile_when_cli_omits_it(monkeypatch):
    monkeypatch.setenv("MUSIC_TOOLS_PROFILE", "missing")
    with pytest.raises(KeyError, match="unknown studio profile"):
        config.get_profile_spec("digitakt", None)


def test_crate_plan_builds_device_specific_layouts_and_compact_names(tmp_path):
    root = tmp_path / "SAMPLES"
    _, sample_id = _source(root, "CURATED/KICK/kick.wav", b"kick")
    crate = _crate(tmp_path / "foundation-v1.tsv", [{
        "sample_id": sample_id,
        "source_path": "CURATED/KICK/kick.wav",
        "role": "KICK",
        "descriptor": "sub-dark-long-name",
        "reason": "favourite",
    }])

    digitakt = build_crate_plan(config.get_spec("digitakt"), crate, root)
    tr8s = build_crate_plan(config.get_spec("tr8s"), crate, root)
    octatrack = build_crate_plan(config.get_spec("octatrack"), crate, root)

    name = f"BD01_sub-dark_{sample_id[:4]}.wav"
    assert digitakt.items[0].out_rel == Path("foundation-v1/KICK") / name
    assert tr8s.items[0].out_rel == Path("ROLAND/TR-8S/SAMPLE/foundation-v1") / name
    assert octatrack.items[0].out_rel == Path("EIDETIC-CURATED/AUDIO/foundation-v1/KICK") / name
    assert len(name) <= 24


def test_crate_plan_rejects_changed_hash_before_conversion(tmp_path):
    root = tmp_path / "SAMPLES"
    source, sample_id = _source(root, "CURATED/KICK/a.wav", b"old")
    crate = _crate(tmp_path / "crate.tsv", [{
        "sample_id": sample_id, "source_path": "CURATED/KICK/a.wav",
        "role": "KICK", "descriptor": "short", "reason": "",
    }])
    source.write_bytes(b"changed")

    with pytest.raises(ExportError, match="hash changed"):
        build_crate_plan(config.get_spec("digitakt"), crate, root)


def test_digitakt_capacity_is_checked_before_conversion(tmp_path):
    root = tmp_path / "SAMPLES"
    rows = []
    for index in range(128):
        rel = f"CURATED/KICK/{index}.wav"
        _, sample_id = _source(root, rel, f"sample-{index}".encode())
        rows.append({
            "sample_id": sample_id, "source_path": rel, "role": "KICK",
            "descriptor": "short", "reason": "",
        })
    crate = _crate(tmp_path / "too-many.tsv", rows)

    with pytest.raises(ExportError, match="127"):
        build_crate_plan(config.get_spec("digitakt"), crate, root)


def test_drum_targets_reject_long_form_assets(tmp_path):
    root = tmp_path / "SAMPLES"
    _, sample_id = _source(root, "CURATED/DRUM-LOOP/loop.wav", b"loop")
    crate = _crate(tmp_path / "all-assets.tsv", [{
        "sample_id": sample_id, "source_path": "CURATED/DRUM-LOOP/loop.wav",
        "role": "DRUM-LOOP", "descriptor": "sparse", "reason": "",
    }])

    for device in ("digitakt", "tr8s"):
        with pytest.raises(ExportError, match="one-shot"):
            build_crate_plan(config.get_spec(device), crate, root)


def test_tr8s_total_duration_is_checked_before_conversion(tmp_path, monkeypatch):
    root = tmp_path / "SAMPLES"
    rows = []
    for index in range(2):
        rel = f"CURATED/KICK/{index}.wav"
        _, sample_id = _source(root, rel, f"sample-{index}".encode())
        rows.append({
            "sample_id": sample_id, "source_path": rel, "role": "KICK",
            "descriptor": "long", "reason": "",
        })
    crate = _crate(tmp_path / "long.tsv", rows)
    monkeypatch.setattr(export_mod.probe_mod, "probe", lambda _path: AudioInfo(48_000, 16, 1, 301.0))

    with pytest.raises(ExportError, match="600 seconds"):
        build_crate_plan(config.get_spec("tr8s"), crate, root)


def test_digitakt_crate_converts_to_native_mono_48k(tmp_path, monkeypatch):
    root = tmp_path / "SAMPLES"
    _, sample_id = _wav(root / "CURATED/KICK/a.wav")
    crate = _crate(tmp_path / "foundation-v1.tsv", [{
        "sample_id": sample_id, "source_path": "CURATED/KICK/a.wav",
        "role": "KICK", "descriptor": "short", "reason": "",
    }])
    spec = config.get_spec("digitakt")
    plan = build_crate_plan(spec, crate, root)
    monkeypatch.setattr(export_mod, "EXPORT_ROOT", tmp_path / "EXPORT")

    converted, skipped = export_mod.export_device(spec, plan=plan)
    output = tmp_path / "EXPORT" / "DIGITAKT" / plan.items[0].out_rel
    info = probe(output)

    assert (converted, skipped) == (1, 0)
    assert (info.rate, info.bits, info.channels) == (48_000, 16, 1)


def test_profile_crate_sync_preserves_hardware_root_layout(tmp_path, monkeypatch):
    export_root = tmp_path / "EXPORT"
    sample = export_root / "TR8S" / "ROLAND" / "TR-8S" / "SAMPLE" / "foundation-v1" / "BD01.wav"
    sample.parent.mkdir(parents=True)
    sample.write_bytes(b"wav")
    monkeypatch.setattr(export_mod, "EXPORT_ROOT", export_root)
    card = tmp_path / "CARD"
    card.mkdir()

    copied = export_mod.sync_to_card(config.get_spec("tr8s"), card)

    assert copied == 1
    assert (card / "ROLAND" / "TR-8S" / "SAMPLE" / "foundation-v1" / "BD01.wav").exists()
    assert not (card / "EIDETIC-TR8S").exists()
