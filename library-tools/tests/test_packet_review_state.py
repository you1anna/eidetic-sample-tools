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
    assert queue.gate().failed_sentinel_groups == ("percussion-one-shots",)


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


def test_completed_review_regenerates_benchmark_without_manual_tsv_edits(tmp_path) -> None:
    candidates = [_candidate(index) for index in range(24)]
    queue = ReviewQueue.build(candidates, "digest")
    for item in list(queue.pending()):
        queue.apply_decision(item.sample_id, item.predicted_form, item.predicted_content, "sentinel")
    path = tmp_path / "benchmark-labels.tsv"
    score = write_review_benchmark(path, queue)

    rows = list(csv.DictReader(path.open(encoding="utf-8"), delimiter="\t"))
    assert score.ready is True and score.passed is True
    assert len(rows) == 24
    assert all(row["true_form"] and row["true_content"] and row["true_audition_group"] for row in rows)


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
    session = ReviewSession.open(tmp_path / "review-state.json", candidates, digest)
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
    assert (tmp_path / "classification.tsv").is_file()
