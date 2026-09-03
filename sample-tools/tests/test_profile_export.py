import csv
import hashlib
import math
import struct
import wave
from pathlib import Path

import pytest

from sampletools import config
from sampletools import cli as cli_mod
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


def test_crate_plan_rejects_source_outside_curated(tmp_path):
    root = tmp_path / "SAMPLES"
    _, sample_id = _source(root, "CATALOGUE/KICK/a.wav", b"kick")
    crate = _crate(tmp_path / "crate.tsv", [{
        "sample_id": sample_id, "source_path": "CATALOGUE/KICK/a.wav",
        "role": "KICK", "descriptor": "short", "reason": "",
    }])

    with pytest.raises(ExportError, match="not under CURATED/"):
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


@pytest.mark.parametrize("device", ("octatrack", "tr8s"))
def test_crate_sync_copies_only_resolved_staged_files_in_native_layout(tmp_path, monkeypatch, device):
    root = tmp_path / "SAMPLES"
    _, sample_id = _source(root, "CURATED/KICK/kick.wav", b"kick")
    crate = _crate(tmp_path / "foundation.tsv", [{
        "sample_id": sample_id, "source_path": "CURATED/KICK/kick.wav",
        "role": "KICK", "descriptor": "short", "reason": "",
    }])
    spec = config.get_spec(device)
    plan = build_crate_plan(spec, crate, root)
    export_root = tmp_path / "EXPORT"
    selected = export_root / spec.export_dir / plan.items[0].out_rel
    selected.parent.mkdir(parents=True)
    selected.write_bytes(b"selected")
    (selected.parent / "stray.wav").write_bytes(b"stray")
    other_crate = selected.parents[1] / "other-crate" / "BD02.wav"
    other_crate.parent.mkdir(parents=True)
    other_crate.write_bytes(b"other")
    monkeypatch.setattr(export_mod, "EXPORT_ROOT", export_root)
    card = tmp_path / "CARD"
    card.mkdir()

    copied = export_mod.sync_to_card(spec, card, plan=plan)

    assert copied == 1
    assert (card / plan.items[0].out_rel).read_bytes() == b"selected"
    assert not (card / plan.items[0].out_rel.parent / "stray.wav").exists()
    assert not (card / other_crate.relative_to(export_root / spec.export_dir)).exists()


def test_empty_crate_sync_copies_no_stale_staged_files(tmp_path, monkeypatch):
    root = tmp_path / "SAMPLES"
    crate = _crate(tmp_path / "empty.tsv", [])
    spec = config.get_spec("tr8s")
    plan = build_crate_plan(spec, crate, root)
    export_root = tmp_path / "EXPORT"
    stale = export_root / "TR8S" / "ROLAND" / "TR-8S" / "SAMPLE" / "old" / "BD01.wav"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"stale")
    monkeypatch.setattr(export_mod, "EXPORT_ROOT", export_root)
    card = tmp_path / "CARD"
    card.mkdir()

    copied = export_mod.sync_to_card(spec, card, plan=plan)

    assert copied == 0
    assert not list(card.rglob("*.wav"))


def test_crate_sync_preflights_all_staged_files_before_copying(tmp_path, monkeypatch):
    root = tmp_path / "SAMPLES"
    _, kick_id = _source(root, "CURATED/KICK/kick.wav", b"kick")
    _, snare_id = _source(root, "CURATED/SNARE/snare.wav", b"snare")
    crate = _crate(tmp_path / "foundation.tsv", [
        {"sample_id": kick_id, "source_path": "CURATED/KICK/kick.wav", "role": "KICK", "descriptor": "short", "reason": ""},
        {"sample_id": snare_id, "source_path": "CURATED/SNARE/snare.wav", "role": "SNARE", "descriptor": "short", "reason": ""},
    ])
    spec = config.get_spec("octatrack")
    plan = build_crate_plan(spec, crate, root)
    export_root = tmp_path / "EXPORT"
    first = export_root / spec.export_dir / plan.items[0].out_rel
    first.parent.mkdir(parents=True)
    first.write_bytes(b"first")
    monkeypatch.setattr(export_mod, "EXPORT_ROOT", export_root)
    card = tmp_path / "CARD"
    card.mkdir()

    with pytest.raises(ExportError, match="missing staged export"):
        export_mod.sync_to_card(spec, card, plan=plan)

    assert not list(card.rglob("*.wav"))


def test_crate_sync_rejects_obstructed_destination_ancestor_before_copying(tmp_path, monkeypatch):
    root = tmp_path / "SAMPLES"
    _, kick_id = _source(root, "CURATED/KICK/kick.wav", b"kick")
    _, snare_id = _source(root, "CURATED/SNARE/snare.wav", b"snare")
    crate = _crate(tmp_path / "foundation.tsv", [
        {"sample_id": kick_id, "source_path": "CURATED/KICK/kick.wav", "role": "KICK", "descriptor": "short", "reason": ""},
        {"sample_id": snare_id, "source_path": "CURATED/SNARE/snare.wav", "role": "SNARE", "descriptor": "short", "reason": ""},
    ])
    spec = config.get_spec("octatrack")
    plan = build_crate_plan(spec, crate, root)
    export_root = tmp_path / "EXPORT"
    for item in plan.items:
        staged = export_root / spec.export_dir / item.out_rel
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(item.out_name.encode())
    monkeypatch.setattr(export_mod, "EXPORT_ROOT", export_root)
    card = tmp_path / "CARD"
    card.mkdir()
    obstruction = card / plan.items[1].out_rel.parent
    obstruction.parent.mkdir(parents=True)
    obstruction.write_bytes(b"not-a-directory")

    with pytest.raises(ExportError, match="destination ancestor is not a directory"):
        export_mod.sync_to_card(spec, card, plan=plan)

    assert not (card / plan.items[0].out_rel).exists()


def test_crate_sync_overwrites_existing_destination_file(tmp_path, monkeypatch):
    root = tmp_path / "SAMPLES"
    _, sample_id = _source(root, "CURATED/KICK/kick.wav", b"kick")
    crate = _crate(tmp_path / "foundation.tsv", [{
        "sample_id": sample_id, "source_path": "CURATED/KICK/kick.wav",
        "role": "KICK", "descriptor": "short", "reason": "",
    }])
    spec = config.get_spec("octatrack")
    plan = build_crate_plan(spec, crate, root)
    export_root = tmp_path / "EXPORT"
    staged = export_root / spec.export_dir / plan.items[0].out_rel
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"new")
    monkeypatch.setattr(export_mod, "EXPORT_ROOT", export_root)
    card = tmp_path / "CARD"
    destination = card / plan.items[0].out_rel
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"old")

    copied = export_mod.sync_to_card(spec, card, plan=plan)

    assert copied == 1
    assert destination.read_bytes() == b"new"


def test_crate_sync_rejects_staged_symlink_escape(tmp_path, monkeypatch):
    root = tmp_path / "SAMPLES"
    _, sample_id = _source(root, "CURATED/KICK/kick.wav", b"kick")
    crate = _crate(tmp_path / "foundation.tsv", [{
        "sample_id": sample_id, "source_path": "CURATED/KICK/kick.wav",
        "role": "KICK", "descriptor": "short", "reason": "",
    }])
    spec = config.get_spec("tr8s")
    plan = build_crate_plan(spec, crate, root)
    export_root = tmp_path / "EXPORT"
    staged = export_root / spec.export_dir / plan.items[0].out_rel
    staged.parent.mkdir(parents=True)
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"outside")
    staged.symlink_to(outside)
    monkeypatch.setattr(export_mod, "EXPORT_ROOT", export_root)
    card = tmp_path / "CARD"
    card.mkdir()

    with pytest.raises(ExportError, match="escapes export root"):
        export_mod.sync_to_card(spec, card, plan=plan)

    assert not list(card.rglob("*.wav"))


def test_crate_sync_rejects_card_symlink_escape(tmp_path, monkeypatch):
    root = tmp_path / "SAMPLES"
    _, sample_id = _source(root, "CURATED/KICK/kick.wav", b"kick")
    crate = _crate(tmp_path / "foundation.tsv", [{
        "sample_id": sample_id, "source_path": "CURATED/KICK/kick.wav",
        "role": "KICK", "descriptor": "short", "reason": "",
    }])
    spec = config.get_spec("tr8s")
    plan = build_crate_plan(spec, crate, root)
    export_root = tmp_path / "EXPORT"
    staged = export_root / spec.export_dir / plan.items[0].out_rel
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"selected")
    monkeypatch.setattr(export_mod, "EXPORT_ROOT", export_root)
    card = tmp_path / "CARD"
    card.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (card / "ROLAND").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ExportError, match="escapes card root"):
        export_mod.sync_to_card(spec, card, plan=plan)

    assert not list(outside.rglob("*.wav"))


def test_legacy_flat_sync_keeps_device_wrapper(tmp_path, monkeypatch):
    export_root = tmp_path / "EXPORT"
    staged = export_root / "OCTATRACK" / "BD01.wav"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"flat")
    monkeypatch.setattr(export_mod, "EXPORT_ROOT", export_root)
    card = tmp_path / "CARD"
    card.mkdir()

    copied = export_mod.sync_to_card(config.get_spec("octatrack"), card)

    assert copied == 1
    assert (card / "EIDETIC-OCTATRACK" / "BD01.wav").read_bytes() == b"flat"


def test_cli_crate_sync_uses_preexisting_selected_stage_only(tmp_path, monkeypatch, capsys):
    root = tmp_path / "SAMPLES"
    _, sample_id = _source(root, "CURATED/KICK/kick.wav", b"kick")
    crate = _crate(tmp_path / "foundation.tsv", [{
        "sample_id": sample_id, "source_path": "CURATED/KICK/kick.wav",
        "role": "KICK", "descriptor": "short", "reason": "",
    }])
    spec = config.get_spec("octatrack")
    plan = build_crate_plan(spec, crate, root)
    export_root = tmp_path / "EXPORT"
    selected = export_root / spec.export_dir / plan.items[0].out_rel
    selected.parent.mkdir(parents=True)
    selected.write_bytes(b"selected")
    (selected.parent / "stale.wav").write_bytes(b"stale")
    monkeypatch.setattr(export_mod, "EXPORT_ROOT", export_root)
    monkeypatch.setattr(cli_mod, "EXPORT_ROOT", export_root)
    monkeypatch.setattr(cli_mod.export_mod, "build_crate_plan", lambda _spec, _crate: plan)
    card = tmp_path / "CARD"
    card.mkdir()

    rc = cli_mod._run_export("octatrack", dry_run=False, force=False, sync=str(card), profile=None, crate=crate)

    assert rc == 0
    assert (card / plan.items[0].out_rel).read_bytes() == b"selected"
    assert not (card / plan.items[0].out_rel.parent / "stale.wav").exists()
    assert "skipped (exists): 1" in capsys.readouterr().out


def test_cli_dry_run_reports_selected_crate_scope_without_writing(tmp_path, monkeypatch, capsys):
    root = tmp_path / "SAMPLES"
    _, sample_id = _source(root, "CURATED/KICK/kick.wav", b"kick")
    crate = _crate(tmp_path / "foundation.tsv", [{
        "sample_id": sample_id, "source_path": "CURATED/KICK/kick.wav",
        "role": "KICK", "descriptor": "short", "reason": "",
    }])
    spec = config.get_spec("octatrack")
    plan = build_crate_plan(spec, crate, root)
    export_root = tmp_path / "EXPORT"
    monkeypatch.setattr(export_mod, "EXPORT_ROOT", export_root)
    monkeypatch.setattr(cli_mod, "EXPORT_ROOT", export_root)
    monkeypatch.setattr(cli_mod.export_mod, "build_crate_plan", lambda _spec, _crate: plan)
    card = tmp_path / "CARD"
    card.mkdir()

    rc = cli_mod._run_export("octatrack", dry_run=True, force=False, sync=str(card), profile=None, crate=crate)

    assert rc == 0
    assert "would sync 1 selected crate file(s)" in capsys.readouterr().out
    assert not list(export_root.rglob("*.wav"))
    assert not list(card.rglob("*.wav"))


def test_cli_returns_error_for_sync_preflight_failure(tmp_path, monkeypatch, capsys):
    root = tmp_path / "SAMPLES"
    _, kick_id = _source(root, "CURATED/KICK/kick.wav", b"kick")
    _, snare_id = _source(root, "CURATED/SNARE/snare.wav", b"snare")
    crate = _crate(tmp_path / "foundation.tsv", [
        {"sample_id": kick_id, "source_path": "CURATED/KICK/kick.wav", "role": "KICK", "descriptor": "short", "reason": ""},
        {"sample_id": snare_id, "source_path": "CURATED/SNARE/snare.wav", "role": "SNARE", "descriptor": "short", "reason": ""},
    ])
    spec = config.get_spec("octatrack")
    plan = build_crate_plan(spec, crate, root)
    export_root = tmp_path / "EXPORT"
    for item in plan.items:
        staged = export_root / spec.export_dir / item.out_rel
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(b"selected")
    monkeypatch.setattr(export_mod, "EXPORT_ROOT", export_root)
    monkeypatch.setattr(cli_mod, "EXPORT_ROOT", export_root)
    monkeypatch.setattr(cli_mod.export_mod, "build_crate_plan", lambda _spec, _crate: plan)
    card = tmp_path / "CARD"
    card.mkdir()
    obstruction = card / plan.items[1].out_rel.parent
    obstruction.parent.mkdir(parents=True)
    obstruction.symlink_to(card / "absent", target_is_directory=True)

    rc = cli_mod._run_export("octatrack", dry_run=False, force=False, sync=str(card), profile=None, crate=crate)

    assert rc == 2
    assert "--sync failed:" in capsys.readouterr().err
    assert not (card / plan.items[0].out_rel).exists()
