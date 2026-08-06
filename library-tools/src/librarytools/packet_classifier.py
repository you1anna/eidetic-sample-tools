"""Local audio-derived classification for audition packets.

The replacement classifier separates acoustic form from two-model semantic
content consensus. Path text is retained only in audit output and has zero
decision weight. The legacy single-scorer path remains injectable for compatibility tests.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Mapping

from . import audiofeatures
from .classification.benchmarks import (
    BENCHMARK_FIELDS,
    BENCHMARK_STRATA,
    BenchmarkScore,
    benchmark_strata,
    read_benchmark_truth as _read_benchmark_truth,
    read_benchmark_with_predictions,
    refresh_benchmark_predictions,
    score_benchmark,
    select_benchmark_rows,
    write_benchmark_audition as _write_benchmark_audition,
    write_benchmark_sheet,
)
from .classification.acoustics import measure_acoustic, rhythm_periodicity
from .classification.cache import EmbeddingCache
from .classification.domain import (
    AUDITION_GROUPS,
    CONTENTS,
    FORMS,
    AcousticEvidence,
    Classification,
    ClassificationError,
    audition_group,
)
from .classification.ensemble import build_candidate, classify_form, select_model_weights
from .classification.models import (
    CONTENT_PROMPTS,
    MODEL_ID,
    MODEL_REVISION,
    MODEL_SPECS,
    PROMPT_POLICY,
    ClapSemanticScorer,
    SemanticScorer,
    clap_audio_inputs,
    clap_excerpt_offsets,
    feature_array,
    rank_prompt_embeddings,
)
from .classification.packets import (
    CLASSIFICATION_FIELDS,
    classification_digest,
    read_classifications,
    withdraw_published_playlists,
    write_classification_audit,
    write_classifications,
)
from .classification.policy import (
    CALIBRATION_CONFIGS,
    DEFAULT_CONFIG,
    ClassifierConfig,
    RawCandidate,
    calibrate_config,
    classify_evidence,
    tokenise_path,
)
from .classification.workers import SampleRef, generate_model_votes
from .classification.review import ReviewSession, finalise_review
from .classification.workers import EXCERPT_POLICY
from .featurecache import FEATURE_COLUMNS
from .inventory import sha256_file


CLASSIFIER_VERSION = "ensemble-v2"

PacketClassifierError = ClassificationError


def verify_packet_source(root: Path, database, sample_id: str, path: Path) -> Path:
    root = root.resolve()
    source = (root / path).resolve()
    if not source.is_relative_to(root):
        raise PacketClassifierError(f"sample path escapes root: {path}")
    try:
        location = database.location(path)
    except KeyError as exc:
        raise PacketClassifierError(f"sample is absent from inventory: {path}") from exc
    if not location.exists or location.sample_id != sample_id:
        raise PacketClassifierError(f"stale sample identity for: {path}")
    if not source.is_file():
        raise PacketClassifierError(f"sample is missing: {path}")
    if sha256_file(source) != sample_id:
        raise PacketClassifierError(f"hash changed since inventory scan: {path}")
    return source


def classify_packet(
    root: Path,
    database,
    labels_path: Path,
    benchmark_path: Path,
    scorer: SemanticScorer | None = None,
    *,
    restart_review: bool = False,
    carry_review: bool = False,
) -> tuple[list[Classification], BenchmarkScore]:
    """Classify a packet and create/score its 24-row ear benchmark."""
    with labels_path.open(encoding="utf-8", newline="") as fh:
        label_reader = csv.DictReader(fh, delimiter="\t")
        label_rows = list(label_reader)
    cached = database.features()
    measured: list[tuple[str, Path, Path, AcousticEvidence]] = []
    for raw in label_rows:
        rel = Path(raw["current_path"])
        source = verify_packet_source(root, database, raw["sample_id"], rel)
        payload = json.loads(cached.get(raw["sample_id"], "{}"))
        if not payload:
            record = audiofeatures.extract(source, cache_path=rel)
            if record.error:
                raise PacketClassifierError(f"cannot analyse {rel}: {record.error}")
            payload = {column: getattr(record, column) for column in FEATURE_COLUMNS}
        evidence = measure_acoustic(source, payload)
        measured.append((raw["sample_id"], rel, source, evidence))

    if scorer is not None:
        classifications = []
        for sample_id, rel, source, evidence in measured:
            scores = {
                label: max(0.0, float(value))
                for label, value in scorer.score(source).items()
            }
            if not scores or not sum(scores.values()):
                raise PacketClassifierError("semantic scorer returned no usable audio scores")
            content, content_score = max(scores.items(), key=lambda item: (item[1], item[0]))
            form = classify_form(evidence)
            classifications.append(Classification(
                sample_id=sample_id,
                current_path=rel,
                form=form.label,
                content=content,
                audition_group=audition_group(form.label, content),
                form_confidence=form.confidence,
                content_confidence=content_score / sum(scores.values()),
                evidence="audio-only injected semantic scorer",
                classifier_version="audio-only-test-adapter",
            ))
        classifier_metadata = {
            "version": "audio-only-test-adapter",
            "model_id": MODEL_ID,
            "model_revision": scorer.revision,
            "filename_weight": 0.0,
        }
        candidates = None
        candidate_digest = None
    else:
        sample_refs = [SampleRef(sample_id, source) for sample_id, _, source, _ in measured]
        votes_by_id, reports = generate_model_votes(
            MODEL_SPECS,
            sample_refs,
            EmbeddingCache(database.path),
        )
        benchmark_truth = _read_benchmark_truth(benchmark_path)
        calibration = select_model_weights(
            [
                (sample_id, evidence, votes_by_id[sample_id])
                for sample_id, _, _, evidence in measured
            ],
            benchmark_truth if len(benchmark_truth) == 24 else {},
        )
        classifications = []
        candidates = []
        for sample_id, rel, _, evidence in measured:
            candidate = build_candidate(
                sample_id,
                rel,
                evidence,
                votes_by_id[sample_id],
                calibration.weights,
            )
            candidates.append(candidate)
            detail = (
                f"duration_s={evidence.duration_s:.3f};onset_count={evidence.onset_count};"
                f"periodicity={evidence.periodicity:.3f};beat_confidence="
                f"{evidence.beat_confidence:.3f};bar_fit_error={evidence.bar_fit_error:.4f};"
                "models="
                + ",".join(
                    f"{vote.model_id}:{vote.top_label}:{vote.top_score:.3f}:{vote.margin:.3f}"
                    for vote in candidate.votes
                )
                + ";review="
                + (",".join(candidate.review_reasons) or "none")
            )
            classifications.append(Classification(
                sample_id=sample_id,
                current_path=rel,
                form=candidate.form.label,
                content=candidate.content.label,
                audition_group=candidate.audition_group,
                form_confidence=candidate.form.confidence,
                content_confidence=candidate.content.confidence,
                evidence=detail,
                classifier_version=CLASSIFIER_VERSION,
            ))
        classifier_metadata = {
            "version": CLASSIFIER_VERSION,
            "filename_weight": 0.0,
            "ensemble_calibration": asdict(calibration),
            "prompt_policy": PROMPT_POLICY,
            "models": [
                {
                    "model_id": report.model_id,
                    "model_revision": report.model_revision,
                    "cache_hits": report.cache_hits,
                    "embedded": report.embedded,
                    "batch_sizes": list(report.batch_sizes),
                    "excerpt_policy": report.excerpt_policy,
                    "prompt_cache_hit": report.prompt_cache_hit,
                    "wall_time_s": round(report.wall_time_s, 3),
                    "peak_rss_mb": round(report.peak_rss_mb, 1),
                }
                for report in reports
            ],
        }
        digest_context = {
            "classifier_version": CLASSIFIER_VERSION,
            "feature_schema": list(FEATURE_COLUMNS),
            "models": [
                {"model_id": spec.model_id, "model_revision": spec.revision}
                for spec in MODEL_SPECS
            ],
            "excerpt_policy": EXCERPT_POLICY,
            "prompt_policy": PROMPT_POLICY,
            "ensemble_weights": list(calibration.weights),
            "filename_weight": 0.0,
        }
        candidate_digest = None

    # Revoke any previous pass before changing classifier-derived output.  If this
    # run fails afterwards, `playlists` must not trust a gate scored against older
    # predictions.
    meta_path = labels_path.parent / "packet-meta.json"
    metadata = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    previous_benchmark = metadata.get("benchmark")
    benchmark_metadata = dict(previous_benchmark) if isinstance(previous_benchmark, dict) else {}
    benchmark_metadata.update({"ready": False, "passed": False})
    metadata["benchmark"] = benchmark_metadata
    if metadata.get("audio_playlists_published"):
        withdraw_published_playlists(
            labels_path.parent,
            str(metadata.get("published_digest") or metadata.get("classification_digest", "")),
        )
    metadata["audio_playlists_published"] = False
    metadata.pop("published_digest", None)
    metadata.pop("resolution_digest", None)
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    classification_path = labels_path.parent / "classification.tsv"
    write_classifications(classification_path, classifications)
    by_id = {row.sample_id: row for row in classifications}
    if candidates is not None:
        if not restart_review and len(_read_benchmark_truth(benchmark_path)) == 24:
            benchmark_rows = refresh_benchmark_predictions(benchmark_path, by_id)
        else:
            strata = benchmark_strata(classifications)
            write_benchmark_sheet(benchmark_path, classifications, strata)
            benchmark_rows = read_benchmark_with_predictions(benchmark_path, by_id)
        benchmark_sample_ids = tuple(row["sample_id"] for row in benchmark_rows)
        digest_context["benchmark_sample_ids"] = list(benchmark_sample_ids)
        candidate_digest = classification_digest(candidates, digest_context)
        write_classification_audit(
            labels_path.parent / "classification-audit.jsonl",
            candidates,
        )
        session = ReviewSession.begin(
            labels_path.parent / "review-state.json",
            candidates,
            candidate_digest,
            restart=restart_review,
            carry_decisions=carry_review,
            benchmark_sample_ids=benchmark_sample_ids,
        )
    elif benchmark_path.is_file():
        benchmark_rows = refresh_benchmark_predictions(benchmark_path, by_id)
    else:
        strata = benchmark_strata(classifications)
        write_benchmark_sheet(benchmark_path, classifications, strata)
        benchmark_rows = read_benchmark_with_predictions(benchmark_path, by_id)
    _write_benchmark_audition(root, benchmark_path)
    score = score_benchmark(benchmark_rows)

    metadata.update({
        "schema_version": 3 if candidates is not None else 2,
        "classifier": classifier_metadata,
        "benchmark": {
            "path": benchmark_path.name,
            "ready": score.ready,
            "passed": score.passed,
            "form_correct": score.form_correct,
            "content_correct": score.content_correct,
            "group_correct": score.group_correct,
            "content_group_correct": score.content_group_correct,
            "total": score.total,
        },
    })
    if candidates is not None and candidate_digest is not None:
        gate = session.queue.gate()
        metadata["classification_digest"] = candidate_digest
        metadata["classification_context"] = digest_context
        metadata["review"] = {
            "state": "complete" if gate.passed else "pending",
            "ready": gate.ready,
            "passed": gate.passed,
            "unresolved": gate.unresolved,
            "classification_digest": gate.classification_digest,
            "failed_sentinel_groups": list(gate.failed_sentinel_groups),
            "escalated_sentinel_groups": list(gate.escalated_sentinel_groups),
        }
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    if candidates is not None and session.queue.gate().passed:
        score = finalise_review(labels_path.parent, session.queue)
    return classifications, score
