from __future__ import annotations

import csv
from pathlib import Path

from librarytools import analyze
from librarytools.featurecache import FeatureRecord


def _make(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    return path


def _feature_row(
    path: str,
    *,
    sub_ratio: float,
    tail_ms: float,
    centroid_hz: float,
    flatness: float,
    tags: str,
) -> analyze.FeatureRow:
    return analyze.FeatureRow(
        path=Path(path),
        source_kind="vendor-pack-audio",
        source_name="Vendor",
        role="KICKS",
        sample_type="one-shot",
        bpm="",
        key="",
        tempo_fit="unknown",
        duration=0.5,
        duration_s=0.5,
        peak=0.9,
        rms=0.3,
        crest=3.0,
        attack_ms=4.0,
        tail_ms=tail_ms,
        head_silence_ms=0.0,
        tail_silence_ms=10.0,
        centroid_hz=centroid_hz,
        flatness=flatness,
        sub_ratio=sub_ratio,
        low_ratio=sub_ratio,
        mid_ratio=max(0.0, 1.0 - sub_ratio),
        high_ratio=0.05,
        onset_density=1.0,
        zcr=0.02,
        audio_error="",
        proposed_name=Path(path).stem,
        review_reason="test",
        processing_tag="",
        processing_reason="",
        character_tags=tags,
        tag_reasons="test",
    )


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


def test_detect_ot_set_handles_sibling_audio_pool_layout(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    set_root = root / "Elektron Pack" / "Readable Set Root"
    control_root = set_root / "Cult Of SP1200"
    _make(control_root / "project.work")
    _make(control_root / "bank01.work")
    _make(set_root / "AUDIO" / "SP_Kick.wav")
    _make(set_root.parent / "install.pdf")

    sets = analyze.detect_ot_sets(root)

    assert len(sets) == 1
    assert sets[0].set_name == "Cult Of SP1200"
    assert sets[0].project_root == Path("Elektron Pack/Readable Set Root")
    assert sets[0].audio_pool_root == Path("Elektron Pack/Readable Set Root/AUDIO")
    assert sets[0].project_file_count == 2
    assert sets[0].audio_file_count == 1
    assert sets[0].doc_path == Path("Elektron Pack/install.pdf")


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


def test_source_registry_handles_top_level_vendor_and_sibling_ot_audio(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    set_root = root / "Elektron Pack" / "Readable Set Root"
    control_root = set_root / "Cult Of SP1200"
    _make(control_root / "project.work")
    _make(set_root / "AUDIO" / "SP_Kick.wav")
    _make(root / "Top Level Vendor" / "Kicks" / "Kick.wav")

    rows = analyze.build_source_registry(root, analyze.detect_ot_sets(root))
    by_path = {row.path.as_posix(): row for row in rows}

    assert by_path["Elektron Pack/Readable Set Root/AUDIO/SP_Kick.wav"].source_kind == "octatrack-set-audio"
    assert by_path["Elektron Pack/Readable Set Root/Cult Of SP1200/project.work"].source_kind == "octatrack-set-project"
    assert by_path["Top Level Vendor/Kicks/Kick.wav"].source_kind == "vendor-pack-audio"


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


def test_curated_role_folder_is_authoritative_for_feature_rows(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    _make(
        root
        / "CURATED"
        / "SYNTH-STAB-CHORD"
        / "Systematic.Sounds.Robert.Babicz.Hands.On.303"
        / "Bass 303 Loop.wav"
    )
    registry = analyze.build_source_registry(root, analyze.detect_ot_sets(root))

    rows = analyze.build_feature_rows(root, registry, probe_durations=False)

    assert rows[0].path == Path(
        "CURATED/SYNTH-STAB-CHORD/Systematic.Sounds.Robert.Babicz.Hands.On.303/Bass 303 Loop.wav"
    )
    assert rows[0].role == "SYNTH-STAB-CHORD"


def test_no_kick_loop_in_curated_drum_loops_stays_drum_loop(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    _make(root / "CURATED" / "DRUM-LOOPS" / "TR-8 Grooves" / "S2S_125BPM_Loop 10_No Kick.wav")
    registry = analyze.build_source_registry(root, analyze.detect_ot_sets(root))

    rows = analyze.build_feature_rows(root, registry, probe_durations=False)

    assert rows[0].role == "DRUM-LOOPS"


def test_build_feature_rows_adds_acoustic_features_and_reasons(tmp_path: Path, monkeypatch):
    root = tmp_path / "SAMPLES"
    kick = _make(root / "PACKS" / "Vendor" / "Kicks" / "Kick.wav")
    registry = analyze.build_source_registry(root, analyze.detect_ot_sets(root))
    calls = []

    def fake_extract(path: Path, cache_path: Path | None = None) -> FeatureRecord:
        calls.append((path, cache_path))
        stat = path.stat()
        return FeatureRecord(
            path=cache_path or path,
            size=stat.st_size,
            mtime=stat.st_mtime,
            duration_s=0.42,
            peak=0.9,
            rms=0.3,
            crest=3.0,
            attack_ms=3.0,
            tail_ms=120.0,
            head_silence_ms=0.0,
            tail_silence_ms=12.0,
            centroid_hz=90.0,
            flatness=0.02,
            sub_ratio=0.72,
            low_ratio=0.82,
            mid_ratio=0.15,
            high_ratio=0.03,
            onset_density=1.0,
            zcr=0.01,
        )

    monkeypatch.setattr(analyze.audiofeatures, "extract", fake_extract)

    rows = analyze.build_feature_rows(
        root,
        registry,
        audio_features=True,
        cache_path=tmp_path / "features.sqlite",
    )

    assert calls == [(kick, Path("PACKS/Vendor/Kicks/Kick.wav"))]
    assert rows[0].duration == 0.42
    assert rows[0].sub_ratio == 0.72
    assert rows[0].tail_ms == 120.0
    assert rows[0].character_tags == "subby;short;clicky"
    assert "sub_ratio=0.72" in rows[0].tag_reasons
    assert "tail_ms=120" in rows[0].tag_reasons


def test_build_crates_keeps_digitakt_and_tr8s_one_shot_oriented(tmp_path: Path, monkeypatch):
    root = tmp_path / "SAMPLES"
    kick = _make(root / "PACKS" / "Vendor" / "Kicks" / "Kick 909.wav")
    hat = _make(root / "PACKS" / "Vendor" / "Hats" / "Tight Hat.wav")
    loop = _make(root / "PACKS" / "Vendor" / "Drum Loops" / "Top Loop 132 BPM.wav")
    durations = {kick: 0.4, hat: 0.2, loop: 4.0}
    monkeypatch.setattr(analyze.probe, "duration", lambda path: durations[path])
    registry = analyze.build_source_registry(root, analyze.detect_ot_sets(root))
    features = analyze.build_feature_rows(root, registry, probe_durations=True)

    crates = analyze.build_crates(features)

    digitakt_paths = [entry.path.as_posix() for entry in crates["digitakt/punchy-techno-kit.txt"]]
    tr8s_paths = [entry.path.as_posix() for entry in crates["tr8s/909-plus-weird-perc.txt"]]
    ableton_paths = [entry.path.as_posix() for entry in crates["ableton/dub-techno-favourites.txt"]]
    assert "PACKS/Vendor/Kicks/Kick 909.wav" in digitakt_paths
    assert "PACKS/Vendor/Hats/Tight Hat.wav" in tr8s_paths
    assert "PACKS/Vendor/Drum Loops/Top Loop 132 BPM.wav" not in digitakt_paths
    assert "PACKS/Vendor/Drum Loops/Top Loop 132 BPM.wav" in ableton_paths


def test_digitakt_crate_balances_one_shot_roles_before_filling(tmp_path: Path, monkeypatch):
    root = tmp_path / "SAMPLES"
    durations = {}
    for idx in range(40):
        path = _make(root / "PACKS" / "Vendor" / "Claps" / f"Clap {idx:02d}.wav")
        durations[path] = 0.3
    kick = _make(root / "PACKS" / "Vendor" / "Kicks" / "Kick 909.wav")
    hat = _make(root / "PACKS" / "Vendor" / "Hats" / "Hat Tight.wav")
    perc = _make(root / "PACKS" / "Vendor" / "Perc" / "Perc Tom.wav")
    durations[kick] = durations[hat] = durations[perc] = 0.3
    monkeypatch.setattr(analyze.probe, "duration", lambda path: durations[path])
    registry = analyze.build_source_registry(root, analyze.detect_ot_sets(root))
    features = analyze.build_feature_rows(root, registry, probe_durations=True)

    crates = analyze.build_crates(features)

    digitakt_paths = [entry.path.as_posix() for entry in crates["digitakt/punchy-techno-kit.txt"]]
    assert "PACKS/Vendor/Kicks/Kick 909.wav" in digitakt_paths
    assert "PACKS/Vendor/Hats/Hat Tight.wav" in digitakt_paths
    assert "PACKS/Vendor/Perc/Perc Tom.wav" in digitakt_paths


def test_device_crates_skip_demos_unfriendly_formats_and_mismatched_curated_roles(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    _make(root / "CURATED" / "KICKS" / "Kick Good.wav")
    _make(root / "CURATED" / "KICKS" / "AUDIO DEMO" / "Kick Demo.mp3")
    _make(root / "CURATED" / "DRONE-ATMOS" / "Hat From Atmos.wav")
    _make(root / "CURATED" / "HATS-CYM" / "Hat Good.wav")
    registry = analyze.build_source_registry(root, analyze.detect_ot_sets(root))
    features = analyze.build_feature_rows(root, registry, probe_durations=False)

    crates = analyze.build_crates(features)

    digitakt_paths = [entry.path.as_posix() for entry in crates["digitakt/punchy-techno-kit.txt"]]
    assert "CURATED/KICKS/Kick Good.wav" in digitakt_paths
    assert "CURATED/HATS-CYM/Hat Good.wav" in digitakt_paths
    assert "CURATED/KICKS/AUDIO DEMO/Kick Demo.mp3" not in digitakt_paths
    assert "CURATED/DRONE-ATMOS/Hat From Atmos.wav" not in digitakt_paths


def test_cluster_within_role_separates_synthetic_audio_groups_deterministically():
    subby = [
        _feature_row(
            f"PACKS/Vendor/Kicks/Sub {idx}.wav",
            sub_ratio=0.85 + idx * 0.01,
            tail_ms=120 + idx,
            centroid_hz=80 + idx,
            flatness=0.02,
            tags="subby;short",
        )
        for idx in range(3)
    ]
    clicky = [
        _feature_row(
            f"PACKS/Vendor/Kicks/Click {idx}.wav",
            sub_ratio=0.05,
            tail_ms=40 + idx,
            centroid_hz=4500 + idx * 10,
            flatness=0.75,
            tags="clicky",
        )
        for idx in range(3)
    ]

    first = analyze.cluster_within_role(subby + clicky)
    second = analyze.cluster_within_role(list(reversed(subby + clicky)))

    first_by_path = {row.path.as_posix(): row for row in first}
    second_by_path = {row.path.as_posix(): row for row in second}
    assert first_by_path == second_by_path
    assert first_by_path["PACKS/Vendor/Kicks/Sub 0.wav"].cluster_label == "subby-short"
    assert first_by_path["PACKS/Vendor/Kicks/Click 0.wav"].cluster_label == "clicky"
    assert (
        first_by_path["PACKS/Vendor/Kicks/Sub 0.wav"].cluster_label
        != first_by_path["PACKS/Vendor/Kicks/Click 0.wav"].cluster_label
    )
    representatives = [row for row in first if row.is_representative]
    assert len(representatives) == 2


def test_cluster_labels_fall_back_to_acoustic_traits_when_tags_are_empty():
    rows = analyze.cluster_within_role([
        _feature_row("PACKS/Vendor/Kicks/Sub 0.wav", sub_ratio=0.85, tail_ms=120, centroid_hz=80, flatness=0.02, tags=""),
        _feature_row("PACKS/Vendor/Kicks/Sub 1.wav", sub_ratio=0.86, tail_ms=121, centroid_hz=81, flatness=0.02, tags=""),
        _feature_row("PACKS/Vendor/Kicks/Noise 0.wav", sub_ratio=0.05, tail_ms=40, centroid_hz=4500, flatness=0.75, tags=""),
        _feature_row("PACKS/Vendor/Kicks/Noise 1.wav", sub_ratio=0.05, tail_ms=41, centroid_hz=4510, flatness=0.75, tags=""),
    ])

    labels = {row.cluster_label for row in rows}

    assert labels == {"subby-tonal-short", "bright-noisy-short"}


def test_cluster_within_role_skips_demo_preview_candidates():
    rows = analyze.cluster_within_role([
        _feature_row("CURATED/KICKS/Good Kick 0.wav", sub_ratio=0.85, tail_ms=120, centroid_hz=80, flatness=0.02, tags="subby;short"),
        _feature_row("CURATED/KICKS/Good Kick 1.wav", sub_ratio=0.86, tail_ms=121, centroid_hz=81, flatness=0.02, tags="subby;short"),
        _feature_row("CURATED/KICKS/AUDIO DEMO/TUNED KICKS DEMO.mp3", sub_ratio=0.87, tail_ms=122, centroid_hz=82, flatness=0.02, tags="subby;short"),
    ])

    paths = {row.path.as_posix() for row in rows}
    assert "CURATED/KICKS/Good Kick 0.wav" in paths
    assert "CURATED/KICKS/AUDIO DEMO/TUNED KICKS DEMO.mp3" not in paths


def test_write_clusters_outputs_representative_tsv(tmp_path: Path):
    rows = analyze.cluster_within_role([
        _feature_row("PACKS/Vendor/Kicks/Sub 0.wav", sub_ratio=0.85, tail_ms=120, centroid_hz=80, flatness=0.02, tags="subby;short"),
        _feature_row("PACKS/Vendor/Kicks/Sub 1.wav", sub_ratio=0.86, tail_ms=121, centroid_hz=81, flatness=0.02, tags="subby;short"),
        _feature_row("PACKS/Vendor/Kicks/Click 0.wav", sub_ratio=0.05, tail_ms=40, centroid_hz=4500, flatness=0.75, tags="clicky"),
        _feature_row("PACKS/Vendor/Kicks/Click 1.wav", sub_ratio=0.05, tail_ms=41, centroid_hz=4510, flatness=0.75, tags="clicky"),
    ])
    out = tmp_path / "clusters.tsv"

    analyze.write_clusters(out, rows)

    written = list(csv.DictReader(out.open(), delimiter="\t"))
    assert {row["cluster_label"] for row in written} == {"subby-short", "clicky"}
    assert sum(row["is_representative"] == "yes" for row in written) == 2


def test_build_crates_includes_octatrack_set_install_plan(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    ot = root / "PACKS" / "Caught on Tape 808+909"
    _make(ot / "project.work")
    _make(ot / "AUDIO" / "COT_BD_Orig.wav")
    sets = analyze.detect_ot_sets(root)
    registry = analyze.build_source_registry(root, sets)
    features = analyze.build_feature_rows(root, registry, probe_durations=False)

    crates = analyze.build_crates(features, ot_sets=sets)

    set_plan = crates["octatrack/caught-on-tape-808-909-set.txt"]
    audio_pool = crates["octatrack/dub-loop-bed-132.txt"]
    assert set_plan[0].path == Path("PACKS/Caught on Tape 808+909")
    assert set_plan[0].reason == "install-as-set;preserve-set"
    assert audio_pool[0].path == Path("PACKS/Caught on Tape 808+909/AUDIO/COT_BD_Orig.wav")


def test_write_crates_outputs_manifest_text_files(tmp_path: Path):
    crates = {
        "digitakt/punchy-techno-kit.txt": [
            analyze.CrateEntry(Path("PACKS/Vendor/Kicks/Kick.wav"), "KICKS;short")
        ]
    }

    analyze.write_crates(tmp_path, crates)

    written = tmp_path / "crates" / "digitakt" / "punchy-techno-kit.txt"
    assert written.exists()
    assert "PACKS/Vendor/Kicks/Kick.wav" in written.read_text()


def test_main_writes_full_pilot_artifacts_without_moving_sources(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    ot_audio = _make(root / "PACKS" / "Caught on Tape 808+909" / "AUDIO" / "COT_BD_TapeSat.wav")
    _make(root / "PACKS" / "Caught on Tape 808+909" / "project.work")
    vendor = _make(root / "PACKS" / "Vendor" / "Hats" / "Tight Hat.wav")
    out = tmp_path / "pilot"

    code = analyze.main([
        "--root", str(root),
        "--pilot",
        "--no-probe",
        "--output-dir", str(out),
    ])

    assert code == 0
    assert ot_audio.exists()
    assert vendor.exists()
    assert (out / "ot-sets-latest.tsv").exists()
    assert (out / "source-registry-latest.tsv").exists()
    assert (out / "sample-features-latest.tsv").exists()
    assert (out / "clusters-latest.tsv").exists()
    assert (out / "crates" / "digitakt" / "punchy-techno-kit.txt").exists()
    assert (out / "crates" / "octatrack" / "caught-on-tape-808-909-set.txt").exists()
    report = (out / "reports" / "pilot.md").read_text()
    assert "OT Sets: 1" in report
    assert "Feature Rows: 2" in report
