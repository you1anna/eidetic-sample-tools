from __future__ import annotations

import csv
from pathlib import Path

from librarytools import analyze


def _make(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    return path


def test_detect_ot_set_registers_project_audio_and_docs(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    pack = root / "PACKS" / "Caught on Tape 808+909"
    _make(pack / "project.work")
    _make(pack / "bank01.work")
    _make(pack / "arr01.work")
    _make(pack / "pattern.strd")
    _make(pack / "AUDIO" / "COT_BD_Orig.wav")
    _make(pack / "Install Guide.pdf")

    sets = analyze.detect_ot_sets(root)

    assert len(sets) == 1
    assert sets[0].set_name == "Caught on Tape 808+909"
    assert sets[0].project_root == Path("PACKS/Caught on Tape 808+909")
    assert sets[0].audio_pool_root == Path("PACKS/Caught on Tape 808+909/AUDIO")
    assert sets[0].project_file_count == 3
    assert sets[0].strd_file_count == 1
    assert sets[0].audio_file_count == 1
    assert sets[0].doc_path == Path("PACKS/Caught on Tape 808+909/Install Guide.pdf")
    assert sets[0].handling_policy == "preserve-set"


def test_write_ot_sets_outputs_tsv(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    pack = root / "PACKS" / "Cult of SP1200"
    _make(pack / "project.work")
    _make(pack / "AUDIO" / "SP_Kick_TapeSat.wav")
    out = tmp_path / "ot-sets.tsv"

    analyze.write_ot_sets(out, analyze.detect_ot_sets(root))

    rows = list(csv.DictReader(out.open(), delimiter="\t"))
    assert rows[0]["set_name"] == "Cult of SP1200"
    assert rows[0]["inferred_device"] == "octatrack"
    assert rows[0]["handling_policy"] == "preserve-set"


def test_parse_processing_suffixes():
    assert analyze.parse_processing_suffix(Path("COT_BD_Orig.wav")) == (
        "original", "filename_suffix:Orig",
    )
    assert analyze.parse_processing_suffix(Path("COT_BD_Tape.wav")) == (
        "tape", "filename_suffix:Tape",
    )
    assert analyze.parse_processing_suffix(Path("COT_BD_TapeSat.wav")) == (
        "tape-saturated", "filename_suffix:TapeSat",
    )
    assert analyze.parse_processing_suffix(Path("COT_BD_X.wav")) == (
        "processed", "filename_suffix:X",
    )
    assert analyze.parse_processing_suffix(Path("COT_BD_X2.wav")) == (
        "processed-more", "filename_suffix:X2",
    )
    assert analyze.parse_processing_suffix(Path("plain-kick.wav")) == ("", "")


def test_source_registry_classifies_sources_and_ignores_noise(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    ot = root / "PACKS" / "Caught on Tape 808+909"
    _make(ot / "project.work")
    _make(ot / "bank01.work")
    _make(ot / "pattern.strd")
    _make(ot / "AUDIO" / "COT_BD_TapeSat.wav")
    _make(ot / "Install Guide.pdf")
    _make(ot / "AUDIO" / "._COT_BD_TapeSat.wav")
    _make(root / "CURATED" / "KICKS" / "curated-kick.wav")
    _make(root / "PACKS" / "Plain Vendor" / "Kicks" / "Vendor Kick.wav")
    _make(root / "_EXPORT" / "DIGITAKT" / "skip.wav")

    rows = analyze.build_source_registry(root, analyze.detect_ot_sets(root))
    by_path = {row.path.as_posix(): row for row in rows}

    assert by_path["PACKS/Caught on Tape 808+909/AUDIO/COT_BD_TapeSat.wav"].source_kind == "octatrack-set-audio"
    assert by_path["PACKS/Caught on Tape 808+909/AUDIO/COT_BD_TapeSat.wav"].processing_tag == "tape-saturated"
    assert by_path["PACKS/Caught on Tape 808+909/project.work"].source_kind == "octatrack-set-project"
    assert by_path["PACKS/Caught on Tape 808+909/Install Guide.pdf"].source_kind == "document"
    assert by_path["CURATED/KICKS/curated-kick.wav"].source_kind == "curated-sample"
    assert by_path["PACKS/Plain Vendor/Kicks/Vendor Kick.wav"].source_kind == "vendor-pack-audio"
    assert "PACKS/Caught on Tape 808+909/AUDIO/._COT_BD_TapeSat.wav" not in by_path
    assert "_EXPORT/DIGITAKT/skip.wav" not in by_path


def test_write_source_registry_outputs_tsv(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    _make(root / "PACKS" / "Plain Vendor" / "Kicks" / "Vendor Kick.wav")
    out = tmp_path / "source-registry.tsv"

    analyze.write_source_registry(
        out, analyze.build_source_registry(root, analyze.detect_ot_sets(root))
    )

    rows = list(csv.DictReader(out.open(), delimiter="\t"))
    assert rows[0]["path"] == "PACKS/Plain Vendor/Kicks/Vendor Kick.wav"
    assert rows[0]["source_kind"] == "vendor-pack-audio"


def test_build_feature_rows_reuses_review_roles_and_processing_tags(tmp_path: Path, monkeypatch):
    root = tmp_path / "SAMPLES"
    src = _make(root / "PACKS" / "Caught on Tape 808+909" / "AUDIO" / "COT_BD_TapeSat.wav")
    _make(root / "PACKS" / "Caught on Tape 808+909" / "project.work")
    monkeypatch.setattr(analyze.probe, "duration", lambda path: 0.42 if path == src else None)
    registry = analyze.build_source_registry(root, analyze.detect_ot_sets(root))

    rows = analyze.build_feature_rows(root, registry, probe_durations=True)

    assert len(rows) == 1
    assert rows[0].path == Path("PACKS/Caught on Tape 808+909/AUDIO/COT_BD_TapeSat.wav")
    assert rows[0].role == "KICKS"
    assert rows[0].sample_type == "one-shot"
    assert rows[0].duration == 0.42
    assert "short" in rows[0].character_tags
    assert "tape-saturated" in rows[0].character_tags
    assert "filename_suffix:TapeSat" in rows[0].tag_reasons


def test_character_tags_use_path_bpm_and_duration_signals(tmp_path: Path, monkeypatch):
    root = tmp_path / "SAMPLES"
    kick = _make(root / "PACKS" / "Vendor" / "Sub Kicks" / "Sub Kick.wav")
    hat = _make(root / "PACKS" / "Vendor" / "Metallic Hats" / "Tight Hat.wav")
    loop = _make(root / "PACKS" / "Vendor" / "Drum Loops" / "Sparse Top Loop 132 BPM.wav")
    durations = {kick: 0.5, hat: 0.2, loop: 4.0}
    monkeypatch.setattr(analyze.probe, "duration", lambda path: durations[path])
    registry = analyze.build_source_registry(root, analyze.detect_ot_sets(root))

    rows = {
        row.path.as_posix(): row
        for row in analyze.build_feature_rows(root, registry, probe_durations=True)
    }

    assert rows["PACKS/Vendor/Sub Kicks/Sub Kick.wav"].character_tags == "subby;short"
    assert rows["PACKS/Vendor/Metallic Hats/Tight Hat.wav"].character_tags == "metallic;tight"
    assert rows["PACKS/Vendor/Drum Loops/Sparse Top Loop 132 BPM.wav"].character_tags == "sparse;top-132"


def test_write_features_outputs_tsv(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    _make(root / "PACKS" / "Vendor" / "Kicks" / "Kick.wav")
    out = tmp_path / "features.tsv"
    registry = analyze.build_source_registry(root, analyze.detect_ot_sets(root))
    features = analyze.build_feature_rows(root, registry, probe_durations=False)

    analyze.write_features(out, features)

    rows = list(csv.DictReader(out.open(), delimiter="\t"))
    assert rows[0]["path"] == "PACKS/Vendor/Kicks/Kick.wav"
    assert rows[0]["role"] == "KICKS"
    assert "path:kick" in rows[0]["review_reason"]
