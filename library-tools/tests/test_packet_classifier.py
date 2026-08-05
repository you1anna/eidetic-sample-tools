import csv
import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from librarytools.packet_classifier import (
    AcousticEvidence,
    ClassifierConfig,
    Classification,
    RawCandidate,
    calibrate_config,
    clap_audio_inputs,
    classify_packet,
    feature_array,
    classify_evidence,
    rank_prompt_embeddings,
    rhythm_periodicity,
    score_benchmark,
    select_benchmark_rows,
    tokenise_path,
    write_benchmark_sheet,
    write_classifications,
)
from librarytools.inventory import LibraryDatabase, scan_library


def _evidence(
    duration: float,
    *,
    onset_density: float = 1.0,
    periodicity: float = 0.0,
    beat_confidence: float = 0.0,
) -> AcousticEvidence:
    return AcousticEvidence(
        duration_s=duration,
        onset_density=onset_density,
        crest=5.0,
        attack_ms=4.0,
        tail_ms=max(0.0, duration * 1000 - 4.0),
        silence_ratio=0.0,
        tempo_bpm=140.0 if periodicity else 0.0,
        beat_confidence=beat_confidence,
        periodicity=periodicity,
    )


@pytest.mark.parametrize("name", ["Waterfall,Med,Bottom.wav", "sm101_al_120_bottomtotop_G.wav"])
def test_bottom_tokens_never_imply_tom(name):
    assert "tom" not in tokenise_path(Path(name))
    result = classify_evidence(
        Path(name),
        _evidence(8.0, periodicity=0.8, beat_confidence=0.8),
        {"OUT_OF_BRIEF": 0.92, "TOM": 0.08},
    )
    assert result.content == "OUT_OF_BRIEF"
    assert result.audition_group == "out-of-brief"


def test_explicit_percussion_loop_is_not_a_one_shot():
    result = classify_evidence(
        Path("AU_HHT_140_percussion_loop_skullcap.wav"),
        _evidence(3.429, onset_density=5.0, periodicity=0.82, beat_confidence=0.75),
        {"PERCUSSION": 0.86, "FULL_DRUMS": 0.14},
    )
    assert result.form == "LOOP"
    assert result.content == "PERCUSSION"
    assert result.audition_group == "percussion-loops"


def test_full_drum_loop_is_separate_from_percussion_loop():
    result = classify_evidence(
        Path("tribal_full_drum_loop_140.wav"),
        _evidence(6.857, onset_density=7.0, periodicity=0.9, beat_confidence=0.9),
        {"FULL_DRUMS": 0.88, "PERCUSSION": 0.12},
    )
    assert result.form == "LOOP"
    assert result.audition_group == "full-drum-loops"


def test_long_conga_groove_remains_a_percussion_loop():
    result = classify_evidence(
        Path("conga_groove.wav"),
        _evidence(34.016, onset_density=4.0, periodicity=0.72, beat_confidence=0.8),
        {"PERCUSSION": 0.91, "FULL_DRUMS": 0.09},
    )
    assert result.form == "LOOP"
    assert result.audition_group == "percussion-loops"


def test_long_acapella_is_a_long_vocal_source():
    result = classify_evidence(
        Path("artist_acapella.wav"),
        _evidence(281.947, onset_density=2.0),
        {"VOCAL": 0.97, "OUT_OF_BRIEF": 0.03},
    )
    assert result.form == "LONG_FORM"
    assert result.content == "VOCAL"
    assert result.audition_group == "long-vocal-sources"


def test_parent_folder_named_loops_cannot_turn_short_hit_into_loop():
    result = classify_evidence(
        Path("PACKS/Loops/rim_07.wav"),
        _evidence(0.18, onset_density=0.0),
        {"RIM": 0.93, "PERCUSSION": 0.07},
    )
    assert result.form == "ONE_SHOT"
    assert result.audition_group == "rim-one-shots"


def test_prompt_embedding_ranking_uses_cosine_similarity():
    scores = rank_prompt_embeddings(
        np.array([1.0, 0.0]),
        {"RIM": np.array([1.0, 0.0]), "TOM": np.array([0.0, 1.0])},
    )
    assert scores == {"RIM": pytest.approx(1.0), "TOM": pytest.approx(0.0)}


def test_feature_array_accepts_transformers_five_pooling_output():
    output = SimpleNamespace(pooler_output=np.array([[0.25, 0.75]]))
    assert feature_array(output).tolist() == [[0.25, 0.75]]


def test_clap_audio_inputs_uses_transformers_five_audio_keyword():
    class Processor:
        def __call__(self, **kwargs):
            assert "audio" in kwargs
            assert "audios" not in kwargs
            return kwargs

    result = clap_audio_inputs(Processor(), [np.array([0.0])])
    assert result["sampling_rate"] == 48_000


def test_rhythm_periodicity_returns_zero_when_short_audio_has_no_valid_tempo_lag():
    assert rhythm_periodicity(np.array([1.0, 0.5]), sample_rate=22_050) == 0.0


def test_benchmark_gate_requires_22_forms_and_20_groups():
    rows = []
    for index in range(24):
        rows.append({
            "sample_id": f"{index:064x}",
            "true_form": "ONE_SHOT",
            "true_content": "PERCUSSION",
            "true_audition_group": "percussion-one-shots",
            "form": "ONE_SHOT" if index < 22 else "LOOP",
            "content": "PERCUSSION" if index < 20 else "TOM",
            "audition_group": "percussion-one-shots" if index < 20 else "tom-one-shots",
        })
    score = score_benchmark(rows)
    assert score.passed is True
    assert (score.form_correct, score.group_correct, score.total) == (22, 20, 24)
    rows[21]["form"] = "LOOP"
    assert score_benchmark(rows).passed is False


def test_benchmark_selection_is_24_unique_rows_across_six_strata():
    rows = []
    strata = [
        "form-boundary", "loop-content", "drum-one-shot", "vocal-form",
        "out-of-brief", "control",
    ]
    for stratum in strata:
        for index in range(6):
            rows.append({"sample_id": f"{stratum}-{index}", "stratum": stratum})
    selected = select_benchmark_rows(rows)
    assert len(selected) == 24
    assert len({row["sample_id"] for row in selected}) == 24
    assert {row["stratum"] for row in selected} == set(strata)


def test_writers_emit_stable_classification_and_benchmark_schemas(tmp_path):
    classification = Classification(
        sample_id="a" * 64,
        current_path=Path("PACKS/rim.wav"),
        form="ONE_SHOT",
        content="RIM",
        audition_group="rim-one-shots",
        form_confidence=0.91,
        content_confidence=0.88,
        evidence="duration_s=0.200",
        classifier_version="hybrid-v1",
    )
    classification_path = tmp_path / "classification.tsv"
    write_classifications(classification_path, [classification])
    row = next(csv.DictReader(classification_path.open(), delimiter="\t"))
    assert list(row) == [
        "sample_id", "current_path", "form", "content", "audition_group",
        "form_confidence", "content_confidence", "evidence", "classifier_version",
    ]
    benchmark_path = tmp_path / "benchmark-labels.tsv"
    write_benchmark_sheet(benchmark_path, [classification], {classification.sample_id: "control"})
    benchmark_row = next(csv.DictReader(benchmark_path.open(), delimiter="\t"))
    assert list(benchmark_row) == [
        "sample_id", "current_path", "stratum", "predicted_form", "predicted_content",
        "predicted_audition_group", "true_form", "true_content",
        "true_audition_group", "notes",
    ]


def test_calibration_prefers_semantics_over_a_misleading_filename_token():
    item = RawCandidate(
        sample_id="b" * 64,
        current_path=Path("PACKS/TOMS/bottom.wav"),
        evidence=_evidence(8.0, periodicity=0.7, beat_confidence=0.8),
        semantic_scores={"OUT_OF_BRIEF": 0.55, "TOM": 0.45},
    )
    truth = {
        item.sample_id: {
            "true_form": "LOOP",
            "true_content": "OUT_OF_BRIEF",
            "true_audition_group": "out-of-brief",
        }
    }
    config = calibrate_config([item], truth, configs=[
        ClassifierConfig(lexical_weight=0.20, periodicity_threshold=0.32, beat_threshold=0.20),
        ClassifierConfig(lexical_weight=0.00, periodicity_threshold=0.32, beat_threshold=0.20),
    ])
    assert config.lexical_weight == 0.0


def test_classify_packet_writes_candidate_benchmark_and_absolute_playlist(tmp_path, monkeypatch):
    import soundfile as sf

    root = tmp_path / "SAMPLES"
    for index in range(24):
        _audio = root / "PACKS" / "packet" / f"rim-{index:02d}.wav"
        _audio.parent.mkdir(parents=True, exist_ok=True)
        signal = np.zeros(256, dtype=np.float32)
        signal[index] = 0.1 + index / 100.0
        sf.write(_audio, signal, 22_050)
    db = LibraryDatabase(tmp_path / "library.sqlite")
    scan_library(root, db)
    packet = tmp_path / "packet"
    packet.mkdir()
    locations = db.current_locations()
    with (packet / "labels.tsv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=(
                "sample_id", "current_path", "suggested_role", "decision", "true_role",
                "descriptor", "tags", "notes",
            ),
            delimiter="\t",
        )
        writer.writeheader()
        for location in locations:
            writer.writerow({
                "sample_id": location.sample_id,
                "current_path": location.path,
                "suggested_role": "RIM",
            })
    (packet / "packet-meta.json").write_text(
        json.dumps({"schema_version": 2, "root": str(root)}) + "\n", encoding="utf-8",
    )

    monkeypatch.setattr(
        "librarytools.packet_classifier.measure_acoustic",
        lambda path, payload: _evidence(0.2),
    )

    class FakeScorer:
        revision = "fake-model-sha"

        def score(self, path):
            return {"RIM": 0.95, "PERCUSSION": 0.05}

    classifications, score = classify_packet(
        root, db, packet / "labels.tsv", packet / "benchmark-labels.tsv", FakeScorer(),
    )

    assert len(classifications) == 24
    assert score.ready is False and score.passed is False
    assert len(list(csv.DictReader((packet / "benchmark-labels.tsv").open(), delimiter="\t"))) == 24
    playlist = (packet / "benchmark.m3u8").read_text().splitlines()
    assert playlist[0] == "#EXTM3U"
    assert len(playlist[1:]) == 24
    assert all(Path(line).is_absolute() for line in playlist[1:])
    benchmark_playlists = packet / "benchmark-playlists"
    assert {
        path.name for path in benchmark_playlists.glob("*.m3u8")
    } == {f"{stratum}.m3u8" for stratum in (
        "form-boundary", "loop-content", "drum-one-shot", "vocal-form",
        "out-of-brief", "control",
    )}
    assert all(
        len((benchmark_playlists / f"{stratum}.m3u8").read_text().splitlines()) == 5
        for stratum in (
            "form-boundary", "loop-content", "drum-one-shot", "vocal-form",
            "out-of-brief", "control",
        )
    )
    metadata = json.loads((packet / "packet-meta.json").read_text())
    assert metadata["classifier"]["model_revision"] == "fake-model-sha"


@pytest.mark.skipif(os.environ.get("RUN_CLAP_INTEGRATION") != "1", reason="downloads/runs CLAP")
def test_real_clap_model_returns_all_content_probabilities(tmp_path):
    import soundfile as sf

    from librarytools.packet_classifier import ClapSemanticScorer, CONTENTS

    sample_rate = 48_000
    audio = np.sin(2 * np.pi * 220 * np.arange(sample_rate) / sample_rate).astype(np.float32)
    path = tmp_path / "tone.wav"
    sf.write(path, audio, sample_rate)
    scores = ClapSemanticScorer().score(path)
    assert set(scores) == CONTENTS
    assert sum(scores.values()) == pytest.approx(1.0)
