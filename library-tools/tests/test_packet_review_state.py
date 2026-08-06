from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from librarytools.classification.domain import AcousticEvidence, ModelVote
from librarytools.classification.ensemble import build_candidate
from librarytools.classification.packets import (
    classification_digest,
    read_classification_audit,
    resolution_digest,
    write_classification_audit,
)
from librarytools.classification.review import (
    ReviewQueue,
    ReviewSession,
    finalise_review,
    write_review_benchmark,
)
from librarytools.classification.domain import ClassificationError


def _vote(model: str, label: str, top: float = 0.7, second: float = 0.2) -> ModelVote:
    fallback = "TOM" if label != "TOM" else "PERCUSSION"
    scores = {label: top, fallback: second, "VOCAL": 1.0 - top - second}
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return ModelVote(model, "revision", scores, ordered[0][0], ordered[0][1], ordered[0][1] - ordered[1][1])


def _candidate(index: int, *, label: str = "PERCUSSION", ambiguous: bool = False):
    evidence = AcousticEvidence(
        duration_s=1.4 if ambiguous else 0.4,
        onset_density=1.0,
        crest=4.0,
        attack_ms=2.0,
        tail_ms=100.0,
        silence_ratio=0.0,
        tempo_bpm=0.0,
        beat_confidence=0.0,
        periodicity=0.0,
        onset_count=1,
        bar_fit_error=1.0,
    )
    return build_candidate(
        f"{index:064x}",
        Path(f"PACK/{index}.wav"),
        evidence,
        (_vote("one", label), _vote("two", label)),
    )


def test_digest_and_audit_bind_context_and_every_model_vote(tmp_path) -> None:
    candidates = [_candidate(1), _candidate(2, ambiguous=True)]
    digest = classification_digest(candidates, {"prompt_policy": "v1"})
    assert digest == classification_digest(candidates, {"prompt_policy": "v1"})
    assert digest != classification_digest(candidates, {"prompt_policy": "v2"})

    path = tmp_path / "classification-audit.jsonl"
    write_classification_audit(path, candidates)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert all('"schema_version":1' in line for line in lines)
    assert all(line.count('"model_id"') == 2 for line in lines)
    assert read_classification_audit(path) == sorted(candidates, key=lambda item: item.sample_id)


def test_queue_contains_all_exceptions_and_one_deterministic_sentinel_per_group() -> None:
    candidates = [_candidate(1), _candidate(2), _candidate(3, ambiguous=True)]
    first = ReviewQueue.build(candidates, "digest")
    second = ReviewQueue.build(list(reversed(candidates)), "digest")
    assert [(item.sample_id, item.kind) for item in first.items] == [
        (f"{3:064x}", "exception"),
        next((item.sample_id, "sentinel") for item in first.items if item.kind == "sentinel"),
    ]
    assert [(item.sample_id, item.kind) for item in first.items] == [
        (item.sample_id, item.kind) for item in second.items
    ]


def test_queue_requires_explicit_decisions_for_every_frozen_benchmark_sample() -> None:
    candidates = [_candidate(index) for index in range(30)]
    required = tuple(candidate.sample_id for candidate in candidates[:24])

    queue = ReviewQueue.build(candidates, "digest", benchmark_sample_ids=required)

    assert set(required) <= {item.sample_id for item in queue.items}
    assert all(
        any(item.sample_id == sample_id and item.kind in {"exception", "benchmark"} for item in queue.items)
        for sample_id in required
    )


def test_failed_sentinel_reopens_its_automatic_group() -> None:
    candidates = [_candidate(1), _candidate(2), _candidate(3)]
    queue = ReviewQueue.build(candidates, "digest")
    sentinel = next(item for item in queue.items if item.kind == "sentinel")
    queue.apply_decision(sentinel.sample_id, "ONE_SHOT", "TOM", "heard a tom")

    pending = queue.pending()
    assert {item.sample_id for item in pending} == {
        candidate.sample_id for candidate in candidates if candidate.sample_id != sentinel.sample_id
    }
    assert {item.kind for item in pending} == {"reopened"}
    assert queue.gate().passed is False

    for item in list(pending):
        queue.apply_decision(item.sample_id, "ONE_SHOT", "PERCUSSION", "checked")
    assert queue.gate().passed is True
    assert queue.gate().failed_sentinel_groups == ()
    assert queue.gate().escalated_sentinel_groups == ("percussion-one-shots",)


def test_review_session_persists_resumes_undoes_and_rejects_stale_digest(tmp_path) -> None:
    state_path = tmp_path / "review-state.json"
    candidates = [_candidate(1, ambiguous=True), _candidate(2)]
    session = ReviewSession.open(state_path, candidates, "digest-one")
    first = session.queue.pending()[0]
    session.apply_decision(first.sample_id, first.predicted_form, first.predicted_content, "ok")

    resumed = ReviewSession.open(state_path, candidates, "digest-one")
    assert first.sample_id not in {item.sample_id for item in resumed.queue.pending()}
    resumed.undo()
    assert first.sample_id in {item.sample_id for item in resumed.queue.pending()}
    with pytest.raises(ClassificationError, match="stale review state"):
        ReviewSession.open(state_path, candidates, "digest-two")


def test_beginning_new_run_replaces_empty_state_but_preserves_human_decisions(tmp_path) -> None:
    state_path = tmp_path / "review-state.json"
    candidates = [_candidate(1, ambiguous=True), _candidate(2)]
    ReviewSession.open(state_path, candidates, "digest-one")
    restarted = ReviewSession.begin(state_path, candidates, "digest-two")
    assert restarted.queue.classification_digest == "digest-two"

    item = restarted.queue.pending()[0]
    restarted.apply_decision(item.sample_id, item.predicted_form, item.predicted_content, "heard")
    with pytest.raises(ClassificationError, match="--restart-review"):
        ReviewSession.begin(state_path, candidates, "digest-three")

    forced = ReviewSession.begin(state_path, candidates, "digest-three", restart=True)
    assert forced.queue.decisions == ()
    assert list((tmp_path / "archive" / "review-state").glob("digest-two*.json"))


def test_tuning_run_can_carry_same_sample_human_decisions_to_new_digest(tmp_path) -> None:
    state_path = tmp_path / "review-state.json"
    candidates = [_candidate(1), _candidate(2), _candidate(3)]
    first = ReviewSession.open(state_path, candidates, "digest-one")
    sentinel = first.queue.pending()[0]
    first.apply_decision(
        sentinel.sample_id, sentinel.predicted_form, sentinel.predicted_content, "heard",
    )

    carried = ReviewSession.begin(
        state_path, candidates, "digest-two", carry_decisions=True,
    )

    assert carried.queue.decisions[0].sample_id == sentinel.sample_id
    assert carried.queue.decisions[0].notes == "heard"
    assert list((tmp_path / "archive" / "review-state").glob("digest-one*.json"))


def test_carried_confirmation_covers_a_fresh_blind_sentinel_in_the_same_group(tmp_path) -> None:
    state_path = tmp_path / "review-state.json"
    candidates = [_candidate(1), _candidate(2), _candidate(3)]
    first = ReviewSession.open(state_path, candidates, "digest-one")
    sentinel = first.queue.pending()[0]
    first.apply_decision(
        sentinel.sample_id, sentinel.predicted_form, sentinel.predicted_content, "heard",
    )
    different_digest = next(
        f"digest-{index}"
        for index in range(2, 100)
        if ReviewQueue.build(candidates, f"digest-{index}").pending()[0].sample_id
        != sentinel.sample_id
    )

    carried = ReviewSession.begin(
        state_path, candidates, different_digest, carry_decisions=True,
    )

    assert carried.queue.pending() == ()
    assert carried.queue.gate().passed is True


def test_only_a_proven_blind_sentinel_can_cover_a_fresh_sentinel(tmp_path) -> None:
    state_path = tmp_path / "review-state.json"
    candidates = [_candidate(1), _candidate(2), _candidate(3)]
    required = (candidates[0].sample_id,)
    first = ReviewSession.open(
        state_path, candidates, "digest-one", benchmark_sample_ids=required,
    )
    benchmark = next(item for item in first.queue.pending() if item.kind == "benchmark")
    first.apply_decision(
        benchmark.sample_id, benchmark.predicted_form, benchmark.predicted_content, "heard",
    )

    carried = ReviewSession.begin(
        state_path,
        candidates,
        "digest-two",
        benchmark_sample_ids=required,
        carry_decisions=True,
    )

    assert any(item.kind == "sentinel" for item in carried.queue.pending())


def test_completed_review_regenerates_benchmark_without_manual_tsv_edits(tmp_path) -> None:
    candidates = [_candidate(index) for index in range(24)]
    required = tuple(candidate.sample_id for candidate in candidates)
    queue = ReviewQueue.build(candidates, "digest", benchmark_sample_ids=required)
    for item in list(queue.pending()):
        queue.apply_decision(item.sample_id, item.predicted_form, item.predicted_content, "sentinel")
    path = tmp_path / "benchmark-labels.tsv"
    _write_blank_benchmark(path, candidates)
    score = write_review_benchmark(path, queue)

    rows = list(csv.DictReader(path.open(encoding="utf-8"), delimiter="\t"))
    assert score.ready is True and score.passed is True
    assert len(rows) == 24
    assert all(row["true_form"] and row["true_content"] and row["true_audition_group"] for row in rows)


def test_completed_tuning_review_preserves_existing_benchmark_membership_and_strata(tmp_path) -> None:
    candidates = [_candidate(index) for index in range(24)]
    queue = ReviewQueue.build(
        candidates, "digest", benchmark_sample_ids=tuple(item.sample_id for item in candidates),
    )
    for item in list(queue.pending()):
        queue.apply_decision(item.sample_id, item.predicted_form, item.predicted_content, "heard")
    path = tmp_path / "benchmark-labels.tsv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=(
            "sample_id", "current_path", "stratum", "predicted_form", "predicted_content",
            "predicted_audition_group", "true_form", "true_content",
            "true_audition_group", "notes",
        ), delimiter="\t")
        writer.writeheader()
        for index, candidate in enumerate(reversed(candidates)):
            writer.writerow({
                "sample_id": candidate.sample_id,
                "current_path": candidate.current_path,
                "stratum": (
                    "form-boundary", "loop-content", "drum-one-shot", "vocal-form",
                    "out-of-brief", "control",
                )[index // 4],
                "predicted_form": candidate.form.label,
                "predicted_content": candidate.content.label,
                "predicted_audition_group": candidate.audition_group,
                "true_form": candidate.form.label,
                "true_content": candidate.content.label,
                "true_audition_group": candidate.audition_group,
                "notes": "heard",
            })

    score = write_review_benchmark(path, queue)
    rows = list(csv.DictReader(path.open(encoding="utf-8"), delimiter="\t"))

    assert score.passed is True
    assert [row["sample_id"] for row in rows] == [
        candidate.sample_id for candidate in reversed(candidates)
    ]
    assert [row["stratum"] for row in rows] == [
        stratum for stratum in (
            "form-boundary", "loop-content", "drum-one-shot", "vocal-form",
            "out-of-brief", "control",
        ) for _ in range(4)
    ]


def test_finalise_review_writes_classifications_and_digest_bound_gate(tmp_path) -> None:
    candidates = [_candidate(index) for index in range(24)]
    context = {"prompt_policy": "v1"}
    digest = classification_digest(candidates, context)
    write_classification_audit(tmp_path / "classification-audit.jsonl", candidates)
    (tmp_path / "packet-meta.json").write_text(json.dumps({
        "schema_version": 3,
        "root": str(tmp_path),
        "classification_digest": digest,
        "classification_context": context,
    }), encoding="utf-8")
    required = tuple(candidate.sample_id for candidate in candidates)
    _write_blank_benchmark(tmp_path / "benchmark-labels.tsv", candidates)
    session = ReviewSession.open(
        tmp_path / "review-state.json", candidates, digest, benchmark_sample_ids=required,
    )
    for item in list(session.queue.pending()):
        session.apply_decision(
            item.sample_id, item.predicted_form, item.predicted_content, "confirmed",
        )

    score = finalise_review(tmp_path, session.queue)

    metadata = json.loads((tmp_path / "packet-meta.json").read_text(encoding="utf-8"))
    assert score.passed is True
    assert metadata["review"]["passed"] is True
    assert metadata["review"]["classification_digest"] == digest
    assert metadata["benchmark"]["passed"] is True
    assert metadata["resolution_digest"] == session.queue.resolution_digest()
    assert (tmp_path / "classification.tsv").is_file()

    playlists = tmp_path / "playlists"
    playlists.mkdir()
    (playlists / "README.md").write_text("published\n", encoding="utf-8")
    (playlists / "rim-one-shots.m3u8").write_text("#EXTM3U\n/rim.wav\n", encoding="utf-8")
    (tmp_path / "audition.m3u8").write_text("#EXTM3U\n/rim.wav\n", encoding="utf-8")
    metadata["audio_playlists_published"] = True
    metadata["published_digest"] = metadata["resolution_digest"]
    (tmp_path / "packet-meta.json").write_text(
        json.dumps(metadata), encoding="utf-8",
    )

    session.undo()
    invalidated = json.loads((tmp_path / "packet-meta.json").read_text(encoding="utf-8"))
    assert invalidated["review"]["passed"] is False
    assert invalidated["benchmark"]["passed"] is False
    assert invalidated["audio_playlists_published"] is False
    assert "resolution_digest" not in invalidated
    assert "published_digest" not in invalidated
    stale = tmp_path / "archive" / "stale-publications" / metadata["published_digest"]
    assert (stale / "playlists" / "rim-one-shots.m3u8").is_file()
    assert (stale / "audition.m3u8").is_file()
    assert not playlists.exists()
    assert not (tmp_path / "audition.m3u8").exists()


def test_resolution_digest_changes_with_human_form_or_content() -> None:
    candidate = "a" * 64
    first = resolution_digest("candidate-digest", [{
        "sample_id": candidate, "form": "ONE_SHOT", "content": "RIM",
    }])
    second = resolution_digest("candidate-digest", [{
        "sample_id": candidate, "form": "ONE_SHOT", "content": "TOM",
    }])
    assert first != second


def _write_blank_benchmark(path: Path, candidates) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=(
            "sample_id", "current_path", "stratum", "predicted_form", "predicted_content",
            "predicted_audition_group", "true_form", "true_content",
            "true_audition_group", "notes",
        ), delimiter="\t")
        writer.writeheader()
        strata = (
            "form-boundary", "loop-content", "drum-one-shot", "vocal-form",
            "out-of-brief", "control",
        )
        for index, candidate in enumerate(candidates):
            writer.writerow({
                "sample_id": candidate.sample_id,
                "current_path": candidate.current_path,
                "stratum": strata[index // 4],
                "predicted_form": candidate.form.label,
                "predicted_content": candidate.content.label,
                "predicted_audition_group": candidate.audition_group,
            })
