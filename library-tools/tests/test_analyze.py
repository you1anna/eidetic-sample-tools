from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from librarytools import analyze


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


def test_source_registry_detects_ot_sets_curated_vendor_and_ignored_paths(tmp_path: Path):
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

    sets = analyze.detect_ot_sets(root)
    rows = analyze.build_source_registry(root, sets)
    by_path = {row.path.as_posix(): row for row in rows}

    assert sets[0].project_root == Path("PACKS/Caught on Tape 808+909")
    assert sets[0].audio_pool_root == Path("PACKS/Caught on Tape 808+909/AUDIO")
    assert sets[0].doc_path == Path("PACKS/Caught on Tape 808+909/Install Guide.pdf")
    assert by_path["PACKS/Caught on Tape 808+909/AUDIO/COT_BD_TapeSat.wav"].source_kind == "octatrack-set-audio"
    assert by_path["PACKS/Caught on Tape 808+909/AUDIO/COT_BD_TapeSat.wav"].processing_tag == "tape-saturated"
    assert by_path["PACKS/Caught on Tape 808+909/project.work"].source_kind == "octatrack-set-project"
    assert by_path["PACKS/Caught on Tape 808+909/Install Guide.pdf"].source_kind == "document"
    assert by_path["CURATED/KICKS/curated-kick.wav"].source_kind == "curated-sample"
    assert by_path["PACKS/Plain Vendor/Kicks/Vendor Kick.wav"].source_kind == "vendor-pack-audio"
    assert "PACKS/Caught on Tape 808+909/AUDIO/._COT_BD_TapeSat.wav" not in by_path
    assert "_EXPORT/DIGITAKT/skip.wav" not in by_path


def test_feature_rows_keep_curated_role_authority_and_processing_tags(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    _make(root / "CURATED" / "SYNTH-STAB-CHORD" / "Bass 303 Loop.wav")
    _make(root / "PACKS" / "Caught on Tape 808+909" / "AUDIO" / "COT_BD_TapeSat.wav")
    _make(root / "PACKS" / "Caught on Tape 808+909" / "project.work")

    rows = analyze.build_feature_rows(
        root,
        analyze.build_source_registry(root, analyze.detect_ot_sets(root)),
        probe_durations=False,
    )
    by_path = {row.path.as_posix(): row for row in rows}

    assert by_path["CURATED/SYNTH-STAB-CHORD/Bass 303 Loop.wav"].role == "SYNTH-STAB-CHORD"
    tape_row = by_path["PACKS/Caught on Tape 808+909/AUDIO/COT_BD_TapeSat.wav"]
    assert tape_row.processing_tag == "tape-saturated"
    assert "tape-saturated" in tape_row.character_tags
    assert "filename_suffix:TapeSat" in tape_row.tag_reasons


def test_kick_gate_regressions_cover_likely_review_reject_and_failed_audition_rows():
    assert analyze.kick_gate(_likely_kick("CURATED/KICKS/likely.wav")).kick_gate == "likely_kick"
    assert analyze.kick_gate(_review_kick("CURATED/KICKS/review.wav")).kick_gate == "review"
    assert analyze.kick_gate(_reject_kick("CURATED/KICKS/reject.wav")).kick_gate == "reject_as_kick"

    failed_audition_rows = [
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

    gates = {row.path.as_posix(): analyze.kick_gate(row).kick_gate for row in failed_audition_rows}

    assert not any(gate == "likely_kick" for gate in gates.values()), gates
    assert gates["CURATED/KICKS/kick-uss-kick-soft-power_samples.wav"] == "reject_as_kick"


def test_role_conflicts_cover_misfiled_kicks_but_ignore_bpm_alone():
    conflicts = analyze.curated_role_conflicts([
        _feature_row(
            "CURATED/KICKS/kick-clap-lastmin2-sp12f_samples.wav",
            sub_ratio=0.3, tail_ms=220, centroid_hz=1200, flatness=0.1,
            tags="short", source_kind="curated-sample",
        ),
        _feature_row(
            "CURATED/KICKS/kick-hh-oldtool4-sp12_samples.wav",
            sub_ratio=0.2, tail_ms=155, centroid_hz=4200, flatness=0.45,
            tags="short;clicky", source_kind="curated-sample",
        ),
        _feature_row(
            "CURATED/KICKS/kick-sample_sean.mp3",
            sub_ratio=0.86, tail_ms=243483, centroid_hz=90, flatness=0.02,
            tags="subby;rumble-long", source_kind="curated-sample",
        ),
        _feature_row(
            "CURATED/KICKS/kick-triangle-3-sp12r_samples.wav",
            sub_ratio=0.2, tail_ms=600, centroid_hz=3000, flatness=0.3,
            tags="", source_kind="curated-sample",
        ),
        _feature_row(
            "CURATED/KICKS/kick-scratch-vinyl09-sp12f_samples.wav",
            sub_ratio=0.4, tail_ms=180, centroid_hz=2000, flatness=0.2,
            tags="short", source_kind="curated-sample",
        ),
    ])
    by_path = {row.path.as_posix(): row for row in conflicts}

    assert by_path["CURATED/KICKS/kick-clap-lastmin2-sp12f_samples.wav"].issues == "CLAP-SNARE"
    assert by_path["CURATED/KICKS/kick-hh-oldtool4-sp12_samples.wav"].issues == "HATS-CYM"
    assert by_path["CURATED/KICKS/kick-sample_sean.mp3"].issues == "long-audio"
    assert by_path["CURATED/KICKS/kick-triangle-3-sp12r_samples.wav"].issues == "PERC"
    assert by_path["CURATED/KICKS/kick-scratch-vinyl09-sp12f_samples.wav"].issues == "FX-RISE-IMPACT"

    bpm_only = _feature_row(
        "CURATED/BASS/VETH1 Bassloops 124 BPM/VETH1 Bassloops 124 BPM 001 - A C D.wav",
        sub_ratio=0.8,
        tail_ms=1200,
        centroid_hz=120,
        flatness=0.02,
        tags="subby",
        source_kind="curated-sample",
        role="BASS",
    )
    assert analyze.curated_role_conflicts([bpm_only]) == []


def test_selection_keeps_only_likely_kicks_and_skips_demos_and_conflicts():
    likely = _likely_kick("CURATED/KICKS/likely.wav")
    review = _review_kick("CURATED/KICKS/review.wav")
    reject = _reject_kick("CURATED/KICKS/reject.wav")
    demo = replace(_likely_kick("CURATED/KICKS/AUDIO DEMO/likely-demo.wav"), source_kind="curated-sample")
    conflict = replace(
        _likely_kick("CURATED/KICKS/kick-cym-lastmin6st-sp12r_samples.wav"),
        source_kind="curated-sample",
    )

    clusters = analyze.cluster_within_role([likely, review, reject, demo, conflict])
    crates = analyze.build_crates([likely, review, reject, demo, conflict])
    cluster_paths = {row.path.as_posix() for row in clusters}
    crate_paths = {entry.path.as_posix() for entries in crates.values() for entry in entries}

    assert "CURATED/KICKS/likely.wav" in cluster_paths
    assert "CURATED/KICKS/likely.wav" in crate_paths
    for skipped in {
        "CURATED/KICKS/review.wav",
        "CURATED/KICKS/reject.wav",
        "CURATED/KICKS/AUDIO DEMO/likely-demo.wav",
        "CURATED/KICKS/kick-cym-lastmin6st-sp12r_samples.wav",
    }:
        assert skipped not in cluster_paths
        assert skipped not in crate_paths


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
    assert (out / "kick-audit-latest.tsv").exists()
    assert (out / "clusters-latest.tsv").exists()
    assert (out / "crates" / "digitakt" / "punchy-techno-kit.txt").exists()
    assert (out / "crates" / "octatrack" / "caught-on-tape-808-909-set.txt").exists()
    report = (out / "reports" / "pilot.md").read_text()
    assert "OT Sets: 1" in report
    assert "Feature Rows: 2" in report
    assert "## KICKS Gate" in report


def test_main_inventory_scan_adds_scan_and_sample_identity_to_feature_manifest(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    _make(root / "PACKS" / "Vendor" / "Kicks" / "Kick.wav")
    out = tmp_path / "pilot"
    db = tmp_path / "sample-library.sqlite"

    code = analyze.main([
        "--root", str(root), "--pilot", "--no-probe",
        "--profile", "eidetic-studio",
        "--library-db", str(db),
        "--output-dir", str(out),
    ])

    assert code == 0
    lines = (out / "sample-features-latest.tsv").read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("scan_id\tsample_id\tpath\t")
    fields = lines[1].split("\t")
    assert len(fields[0]) == 32
    assert len(fields[1]) == 64


def test_main_reports_path_drift_against_previous_feature_manifest(tmp_path: Path, capsys):
    root = tmp_path / "SAMPLES"
    _make(root / "PACKS" / "Vendor" / "new.wav")
    out = tmp_path / "pilot"
    out.mkdir()
    (out / "sample-features-latest.tsv").write_text(
        "path\trole\nCURATED/KICKS/old.wav\tKICKS\n", encoding="utf-8"
    )

    code = analyze.main([
        "--root", str(root), "--pilot", "--no-probe",
        "--library-db", str(tmp_path / "library.sqlite"),
        "--output-dir", str(out),
    ])

    assert code == 0
    output = capsys.readouterr().out
    assert "previous-only: 1" in output
    assert "current-only: 1" in output
