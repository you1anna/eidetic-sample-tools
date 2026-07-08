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
    source_kind: str = "vendor-pack-audio",
    role: str = "KICKS",
    sample_type: str = "one-shot",
    duration: float = 0.5,
    peak: float = 0.9,
    rms: float = 0.3,
    crest: float = 3.0,
    attack_ms: float = 4.0,
    low_ratio: float | None = None,
    mid_ratio: float | None = None,
    high_ratio: float = 0.05,
    onset_density: float = 1.0,
    zcr: float = 0.02,
    audio_error: str = "",
) -> analyze.FeatureRow:
    return analyze.FeatureRow(
        path=Path(path),
        source_kind=source_kind,
        source_name="Vendor",
        role=role,
        sample_type=sample_type,
        bpm="",
        key="",
        tempo_fit="unknown",
        duration=duration,
        duration_s=duration,
        peak=peak,
        rms=rms,
        crest=crest,
        attack_ms=attack_ms,
        tail_ms=tail_ms,
        head_silence_ms=0.0,
        tail_silence_ms=10.0,
        centroid_hz=centroid_hz,
        flatness=flatness,
        sub_ratio=sub_ratio,
        low_ratio=sub_ratio if low_ratio is None else low_ratio,
        mid_ratio=max(0.0, 1.0 - sub_ratio) if mid_ratio is None else mid_ratio,
        high_ratio=high_ratio,
        onset_density=onset_density,
        zcr=zcr,
        audio_error=audio_error,
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
    # KICKS now runs through the high-precision gate, which rejects clicky/noise
    # vectors. Use PERC (an ungated role) to exercise the role-agnostic k-means
    # machinery with deliberately divergent vectors.
    subby = [
        _feature_row(
            f"PACKS/Vendor/Perc/Sub {idx}.wav",
            role="PERC",
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
            f"PACKS/Vendor/Perc/Click {idx}.wav",
            role="PERC",
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
    assert first_by_path["PACKS/Vendor/Perc/Sub 0.wav"].cluster_label == "subby-short"
    assert first_by_path["PACKS/Vendor/Perc/Click 0.wav"].cluster_label == "clicky"
    assert (
        first_by_path["PACKS/Vendor/Perc/Sub 0.wav"].cluster_label
        != first_by_path["PACKS/Vendor/Perc/Click 0.wav"].cluster_label
    )
    representatives = [row for row in first if row.is_representative]
    assert len(representatives) == 2


def test_cluster_labels_fall_back_to_acoustic_traits_when_tags_are_empty():
    # PERC (ungated) so the noise group survives to test acoustic-trait labelling.
    rows = analyze.cluster_within_role([
        _feature_row("PACKS/Vendor/Perc/Sub 0.wav", role="PERC", sub_ratio=0.85, tail_ms=120, centroid_hz=80, flatness=0.02, tags=""),
        _feature_row("PACKS/Vendor/Perc/Sub 1.wav", role="PERC", sub_ratio=0.86, tail_ms=121, centroid_hz=81, flatness=0.02, tags=""),
        _feature_row("PACKS/Vendor/Perc/Noise 0.wav", role="PERC", sub_ratio=0.05, tail_ms=40, centroid_hz=4500, flatness=0.75, tags=""),
        _feature_row("PACKS/Vendor/Perc/Noise 1.wav", role="PERC", sub_ratio=0.05, tail_ms=41, centroid_hz=4510, flatness=0.75, tags=""),
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


def test_curated_role_conflicts_report_misfiled_kick_markers():
    rows = [
        _feature_row(
            "CURATED/KICKS/kick-clap-lastmin2-sp12f_samples.wav",
            sub_ratio=0.3,
            tail_ms=220,
            centroid_hz=1200,
            flatness=0.1,
            tags="short",
            source_kind="curated-sample",
        ),
        _feature_row(
            "CURATED/KICKS/kick-hh-oldtool4-sp12_samples.wav",
            sub_ratio=0.2,
            tail_ms=155,
            centroid_hz=4200,
            flatness=0.45,
            tags="short;clicky",
            source_kind="curated-sample",
        ),
        _feature_row(
            "CURATED/KICKS/kick-sample_sean.mp3",
            sub_ratio=0.86,
            tail_ms=243483,
            centroid_hz=90,
            flatness=0.02,
            tags="subby;rumble-long",
            source_kind="curated-sample",
        ),
        _feature_row(
            "CURATED/KICKS/kick-triangle-3-sp12r_samples.wav",
            sub_ratio=0.2,
            tail_ms=600,
            centroid_hz=3000,
            flatness=0.3,
            tags="",
            source_kind="curated-sample",
        ),
        _feature_row(
            "CURATED/KICKS/kick-scratch-vinyl09-sp12f_samples.wav",
            sub_ratio=0.4,
            tail_ms=180,
            centroid_hz=2000,
            flatness=0.2,
            tags="short",
            source_kind="curated-sample",
        ),
        _feature_row(
            "CURATED/KICKS/kick-dsm1-bd-c-tape2-r1_sa909_samples.wav",
            sub_ratio=0.98,
            tail_ms=1350,
            centroid_hz=80,
            flatness=0.02,
            tags="subby;rumble-long",
            source_kind="curated-sample",
        ),
    ]

    conflicts = analyze.curated_role_conflicts(rows)

    by_path = {row.path.as_posix(): row for row in conflicts}
    assert set(by_path) == {
        "CURATED/KICKS/kick-clap-lastmin2-sp12f_samples.wav",
        "CURATED/KICKS/kick-hh-oldtool4-sp12_samples.wav",
        "CURATED/KICKS/kick-sample_sean.mp3",
        "CURATED/KICKS/kick-triangle-3-sp12r_samples.wav",
        "CURATED/KICKS/kick-scratch-vinyl09-sp12f_samples.wav",
    }
    assert by_path["CURATED/KICKS/kick-clap-lastmin2-sp12f_samples.wav"].issues == "CLAP-SNARE"
    assert by_path["CURATED/KICKS/kick-hh-oldtool4-sp12_samples.wav"].issues == "HATS-CYM"
    assert by_path["CURATED/KICKS/kick-sample_sean.mp3"].issues == "long-audio"
    assert by_path["CURATED/KICKS/kick-triangle-3-sp12r_samples.wav"].issues == "PERC"
    assert by_path["CURATED/KICKS/kick-scratch-vinyl09-sp12f_samples.wav"].issues == "FX-RISE-IMPACT"


def test_write_curated_role_conflicts_outputs_review_manifest(tmp_path: Path):
    conflicts = [
        analyze.CuratedRoleConflict(
            path=Path("CURATED/KICKS/kick-clap.wav"),
            current_role="KICKS",
            issues="CLAP-SNARE",
            reasons="CLAP-SNARE:clap",
            suggested_action="review-or-quarantine",
        )
    ]
    out = tmp_path / "conflicts.tsv"

    analyze.write_curated_role_conflicts(out, conflicts)

    rows = list(csv.DictReader(out.open(), delimiter="\t"))
    assert rows[0]["path"] == "CURATED/KICKS/kick-clap.wav"
    assert rows[0]["issues"] == "CLAP-SNARE"
    assert rows[0]["suggested_action"] == "review-or-quarantine"


def test_write_kick_audit_outputs_required_columns(tmp_path: Path):
    rows = [
        analyze.KickGateRow(
            path=Path("CURATED/KICKS/solid.wav"),
            current_role="KICKS",
            sample_type="one-shot",
            duration_s=0.31,
            attack_ms=4.0,
            tail_ms=180.0,
            sub_ratio=0.82,
            low_ratio=0.91,
            mid_ratio=0.08,
            high_ratio=0.01,
            centroid_hz=180.0,
            flatness=0.02,
            onset_density=0.5,
            zcr=0.02,
            kick_gate="likely_kick",
            confidence="high",
            reasons="sub_ratio=0.82;crest=8",
            review_action="audition-as-kick",
        )
    ]
    out = tmp_path / "kick-audit-latest.tsv"

    analyze.write_kick_audit(out, rows)

    written = list(csv.DictReader(out.open(), delimiter="\t"))
    assert written[0]["path"] == "CURATED/KICKS/solid.wav"
    assert written[0]["kick_gate"] == "likely_kick"
    assert written[0]["review_action"] == "audition-as-kick"


def test_kick_gate_marks_strong_compact_low_transient_as_likely():
    row = _feature_row(
        "CURATED/KICKS/solid-low-transient.wav",
        source_kind="curated-sample",
        sub_ratio=0.82,
        low_ratio=0.91,
        high_ratio=0.01,
        tail_ms=180.0,
        centroid_hz=180.0,
        flatness=0.02,
        tags="subby;short",
        duration=0.31,
        crest=8.0,
        attack_ms=3.5,
        onset_density=0.4,
        zcr=0.02,
    )

    gate = analyze.kick_gate(row)

    assert gate.kick_gate == "likely_kick"
    assert gate.confidence == "high"
    assert gate.review_action == "audition-as-kick"


def test_kick_gate_rejects_role_conflicts_and_loops():
    clap = _feature_row(
        "CURATED/KICKS/kick-clap-lastmin2-sp12f_samples.wav",
        source_kind="curated-sample",
        sub_ratio=0.3,
        low_ratio=0.3,
        high_ratio=0.2,
        tail_ms=220,
        centroid_hz=1200,
        flatness=0.1,
        tags="short",
    )
    loop = _feature_row(
        "CURATED/KICKS/Kick Loops/Kick020.wav",
        source_kind="curated-sample",
        sub_ratio=0.8,
        low_ratio=0.9,
        high_ratio=0.02,
        tail_ms=900,
        centroid_hz=140,
        flatness=0.02,
        tags="subby;rumble-long",
        sample_type="loop",
        duration=4.0,
        crest=5.5,
        onset_density=5.0,
    )

    assert analyze.kick_gate(clap).kick_gate == "reject_as_kick"
    assert analyze.kick_gate(loop).kick_gate == "reject_as_kick"


def test_kick_gate_routes_missing_or_borderline_audio_to_review():
    missing = _feature_row(
        "CURATED/KICKS/unreadable.wav",
        source_kind="curated-sample",
        sub_ratio=0.0,
        low_ratio=0.0,
        high_ratio=0.0,
        tail_ms=0.0,
        centroid_hz=0.0,
        flatness=0.0,
        tags="",
        audio_error="decode failed",
    )
    borderline = _feature_row(
        "CURATED/KICKS/borderline-low.wav",
        source_kind="curated-sample",
        sub_ratio=0.44,
        low_ratio=0.5,
        high_ratio=0.08,
        tail_ms=260,
        centroid_hz=900,
        flatness=0.08,
        tags="short",
        duration=0.45,
        crest=6.0,
    )

    assert analyze.kick_gate(missing).kick_gate == "review"
    assert analyze.kick_gate(missing).review_action == "decode-or-manual-review"
    assert analyze.kick_gate(borderline).kick_gate == "review"


def test_kick_gate_does_not_pass_failed_kicks_audition_representatives():
    # Real CURATED/KICKS rows and their measured acoustic values, pulled from
    # manifests/.../sample-features-latest.tsv. These are the known failure
    # categories from the ear-check: clap/snare, hat/cymbal, kick loop, bass/
    # synth, long impact, and a clean-named noisy one-shot. None may pass as a
    # likely_kick. The last (kick-uss-kick-soft-power) has no conflicting name
    # token and is caught purely by the acoustic ladder (high zcr) — it is
    # representative #8 in the current refreshed audition packet.
    rows = [
        _feature_row(
            "CURATED/KICKS/kick-clap-dmax1-sp1200r_samples.wav",
            source_kind="curated-sample", tags="",
            sub_ratio=0.00015, low_ratio=0.0018, mid_ratio=0.891, high_ratio=0.107,
            tail_ms=136.1, centroid_hz=3298.99, flatness=0.153,
            duration=0.293, attack_ms=0.227, onset_density=0.0, zcr=0.292, crest=10.47,
        ),
        _feature_row(
            "CURATED/KICKS/kick-hh-45bpm01-sp12r_samples.wav",
            source_kind="curated-sample", tags="",
            sub_ratio=0.093, low_ratio=0.20, mid_ratio=0.20, high_ratio=0.60,
            tail_ms=63.8, centroid_hz=5469.28, flatness=0.392,
            duration=0.112, attack_ms=6.03, onset_density=0.0, zcr=0.324, crest=8.06,
        ),
        _feature_row(
            "CURATED/KICKS/kick-cym-bamvin1-sp12_samples.wav",
            source_kind="curated-sample", tags="",
            sub_ratio=0.00008, low_ratio=0.0002, mid_ratio=0.252, high_ratio=0.748,
            tail_ms=1863.58, centroid_hz=5823.67, flatness=0.236,
            duration=2.126, attack_ms=43.63, onset_density=0.0, zcr=0.448, crest=5.89,
        ),
        _feature_row(
            "CURATED/KICKS/kick-sd-45bpm01-sp12r_samples.wav",
            source_kind="curated-sample", tags="",
            sub_ratio=0.17, low_ratio=0.879, mid_ratio=0.081, high_ratio=0.040,
            tail_ms=100.68, centroid_hz=3417.04, flatness=0.045,
            duration=0.135, attack_ms=4.22, onset_density=0.0, zcr=0.082, crest=3.86,
        ),
        _feature_row(
            "CURATED/KICKS/GR8_001_TUNED_KICKS/LOOPS/Aggressive Kicks/Aggressive_Kick_A#1.aif",
            source_kind="curated-sample", tags="subby;rumble-long", sample_type="loop",
            sub_ratio=0.842, low_ratio=0.965, mid_ratio=0.035, high_ratio=0.0000164,
            tail_ms=1436.92, centroid_hz=404.688, flatness=0.0000295,
            duration=1.92, attack_ms=2.86, onset_density=1.5625, zcr=0.0064, crest=1.94,
        ),
        _feature_row(
            "CURATED/KICKS/kick-bd-sh101-1-sp1200f_samples.wav",
            source_kind="curated-sample", tags="subby;short",
            sub_ratio=0.9998, low_ratio=0.99998, mid_ratio=0.0000213, high_ratio=0.0000001,
            tail_ms=168.571, centroid_hz=90.12, flatness=0.0000003,
            duration=0.269, attack_ms=14.51, onset_density=0.0, zcr=0.0061, crest=3.66,
        ),
        _feature_row(
            "CURATED/KICKS/kick-chime-door1-sp12f_samples.wav",
            source_kind="curated-sample", tags="",
            sub_ratio=0.0000007, low_ratio=0.0000124, mid_ratio=0.99999, high_ratio=0.00000004,
            tail_ms=1431.2, centroid_hz=611.94, flatness=0.0000001,
            duration=2.124, attack_ms=1.59, onset_density=0.0, zcr=0.048, crest=4.32,
        ),
        _feature_row(
            "CURATED/KICKS/kick-uss-kick-soft-power_samples.wav",
            source_kind="curated-sample", tags="subby;short",
            sub_ratio=0.994, low_ratio=0.99994, mid_ratio=0.00006, high_ratio=0.0000000001,
            tail_ms=135.918, centroid_hz=64.29, flatness=0.0000000005,
            duration=2.02249, attack_ms=9.43, onset_density=0.494, zcr=0.364, crest=6.45,
        ),
    ]

    gates = {row.path.as_posix(): analyze.kick_gate(row).kick_gate for row in rows}

    assert not any(gate == "likely_kick" for gate in gates.values()), gates
    # The clean-named noisy one-shot has no conflicting name token; only the
    # acoustic ladder catches it.
    assert gates["CURATED/KICKS/kick-uss-kick-soft-power_samples.wav"] == "reject_as_kick"


def _likely_kick(path: str) -> analyze.FeatureRow:
    return _feature_row(
        path,
        source_kind="curated-sample",
        sub_ratio=0.82,
        low_ratio=0.91,
        high_ratio=0.02,
        tail_ms=160.0,
        centroid_hz=150.0,
        flatness=0.02,
        tags="subby;short",
        duration=0.31,
        crest=8.0,
        attack_ms=3.2,
        onset_density=0.4,
        zcr=0.02,
    )


def _review_kick(path: str) -> analyze.FeatureRow:
    return _feature_row(
        path,
        source_kind="curated-sample",
        sub_ratio=0.44,
        low_ratio=0.5,
        high_ratio=0.08,
        tail_ms=260.0,
        centroid_hz=900.0,
        flatness=0.08,
        tags="short",
        duration=0.45,
        crest=6.0,
    )


def _reject_kick(path: str) -> analyze.FeatureRow:
    # Clean name, kick-like low end, but very high zcr -> reject via the acoustic
    # ladder (mirrors the real kick-uss-kick-soft-power false positive).
    return _feature_row(
        path,
        source_kind="curated-sample",
        sub_ratio=0.99,
        low_ratio=0.99,
        high_ratio=0.001,
        tail_ms=140.0,
        centroid_hz=70.0,
        flatness=0.001,
        tags="subby;short",
        duration=0.5,
        crest=6.0,
        attack_ms=9.0,
        onset_density=0.5,
        zcr=0.36,
    )


def test_kick_audit_includes_only_kicks_candidates_sorted_by_path():
    hats = _feature_row(
        "CURATED/HATS-CYM/hat-good.wav",
        source_kind="curated-sample",
        role="HATS-CYM",
        sub_ratio=0.1,
        low_ratio=0.2,
        high_ratio=0.5,
        tail_ms=120.0,
        centroid_hz=6000.0,
        flatness=0.4,
        tags="metallic",
    )
    review = _review_kick("CURATED/KICKS/aaa-review.wav")
    likely = _likely_kick("CURATED/KICKS/zzz-likely.wav")

    audit = analyze.kick_audit([likely, hats, review])

    assert [row.path.as_posix() for row in audit] == [
        "CURATED/KICKS/aaa-review.wav",
        "CURATED/KICKS/zzz-likely.wav",
    ]
    assert [row.kick_gate for row in audit] == ["review", "likely_kick"]


def test_cluster_within_role_excludes_reject_as_kick_but_keeps_review():
    # High-precision first pass drops only reject_as_kick; likely and review
    # KICKS rows stay eligible to cluster.
    rows = [
        _likely_kick("CURATED/KICKS/likely-a.wav"),
        _review_kick("CURATED/KICKS/review-b.wav"),
        _reject_kick("CURATED/KICKS/reject-c.wav"),
    ]

    clusters = analyze.cluster_within_role(rows)

    paths = {row.path.as_posix() for row in clusters}
    assert "CURATED/KICKS/likely-a.wav" in paths
    assert "CURATED/KICKS/review-b.wav" in paths
    assert "CURATED/KICKS/reject-c.wav" not in paths


def test_build_crates_excludes_reject_as_kick():
    likely = _likely_kick("CURATED/KICKS/likely.wav")
    review = _review_kick("CURATED/KICKS/review.wav")
    reject = _reject_kick("CURATED/KICKS/reject.wav")

    crates = analyze.build_crates([likely, review, reject])

    all_paths = {entry.path.as_posix() for entries in crates.values() for entry in entries}
    assert "CURATED/KICKS/likely.wav" in all_paths
    assert "CURATED/KICKS/review.wav" in all_paths
    assert "CURATED/KICKS/reject.wav" not in all_paths


def test_curated_role_conflicts_do_not_treat_bpm_alone_as_drum_loop():
    rows = [
        _feature_row(
            "CURATED/BASS/VETH1 Bassloops 124 BPM/VETH1 Bassloops 124 BPM 001 - A C D.wav",
            sub_ratio=0.8,
            tail_ms=1200,
            centroid_hz=120,
            flatness=0.02,
            tags="subby",
            source_kind="curated-sample",
            role="BASS",
        )
    ]

    assert analyze.curated_role_conflicts(rows) == []


def test_cluster_within_role_skips_curated_role_conflicts():
    rows = analyze.cluster_within_role([
        _feature_row(
            "CURATED/KICKS/Good Kick 0.wav",
            sub_ratio=0.85,
            tail_ms=120,
            centroid_hz=80,
            flatness=0.02,
            tags="subby;short",
            source_kind="curated-sample",
        ),
        _feature_row(
            "CURATED/KICKS/Good Kick 1.wav",
            sub_ratio=0.86,
            tail_ms=121,
            centroid_hz=81,
            flatness=0.02,
            tags="subby;short",
            source_kind="curated-sample",
        ),
        _feature_row(
            "CURATED/KICKS/kick-cym-lastmin6st-sp12r_samples.wav",
            sub_ratio=0.1,
            tail_ms=800,
            centroid_hz=5000,
            flatness=0.5,
            tags="",
            source_kind="curated-sample",
        ),
    ])

    paths = {row.path.as_posix() for row in rows}
    assert "CURATED/KICKS/Good Kick 0.wav" in paths
    assert "CURATED/KICKS/kick-cym-lastmin6st-sp12r_samples.wav" not in paths


def test_cluster_within_role_skips_one_shot_role_loop_folders():
    rows = analyze.cluster_within_role([
        _feature_row(
            "PACKS/Vendor/Kicks/Good Kick 0.wav",
            sub_ratio=0.85,
            tail_ms=120,
            centroid_hz=80,
            flatness=0.02,
            tags="subby;short",
        ),
        _feature_row(
            "PACKS/Vendor/Kicks/Good Kick 1.wav",
            sub_ratio=0.86,
            tail_ms=121,
            centroid_hz=81,
            flatness=0.02,
            tags="subby;short",
        ),
        _feature_row(
            "PACKS/filterheadz-hardgroove-techno/Kick Loops/Kick020.wav",
            sub_ratio=0.9,
            tail_ms=900,
            centroid_hz=100,
            flatness=0.02,
            tags="subby;rumble-long",
        ),
    ])

    paths = {row.path.as_posix() for row in rows}
    assert "PACKS/Vendor/Kicks/Good Kick 0.wav" in paths
    assert "PACKS/filterheadz-hardgroove-techno/Kick Loops/Kick020.wav" not in paths


def test_write_clusters_outputs_representative_tsv(tmp_path: Path):
    # PERC (ungated) so both synthetic groups survive to the clusters manifest.
    rows = analyze.cluster_within_role([
        _feature_row("PACKS/Vendor/Perc/Sub 0.wav", role="PERC", sub_ratio=0.85, tail_ms=120, centroid_hz=80, flatness=0.02, tags="subby;short"),
        _feature_row("PACKS/Vendor/Perc/Sub 1.wav", role="PERC", sub_ratio=0.86, tail_ms=121, centroid_hz=81, flatness=0.02, tags="subby;short"),
        _feature_row("PACKS/Vendor/Perc/Click 0.wav", role="PERC", sub_ratio=0.05, tail_ms=40, centroid_hz=4500, flatness=0.75, tags="clicky"),
        _feature_row("PACKS/Vendor/Perc/Click 1.wav", role="PERC", sub_ratio=0.05, tail_ms=41, centroid_hz=4510, flatness=0.75, tags="clicky"),
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
    assert (out / "curated-role-conflicts-latest.tsv").exists()
    assert (out / "clusters-latest.tsv").exists()
    assert (out / "kick-audit-latest.tsv").exists()
    assert (out / "crates" / "digitakt" / "punchy-techno-kit.txt").exists()
    assert (out / "crates" / "octatrack" / "caught-on-tape-808-909-set.txt").exists()
    report = (out / "reports" / "pilot.md").read_text()
    assert "OT Sets: 1" in report
    assert "Feature Rows: 2" in report
    assert "## KICKS Gate" in report


def test_report_includes_kick_gate_counts(tmp_path: Path):
    audit = [
        analyze.kick_gate(_likely_kick("CURATED/KICKS/likely.wav")),
        analyze.kick_gate(_review_kick("CURATED/KICKS/review.wav")),
    ]
    out = tmp_path / "report.md"

    analyze.write_report(out, [], [], [], {}, kick_audit_rows=audit)

    report = out.read_text()
    assert "## KICKS Gate\n- likely_kick: 1\n- review: 1" in report
