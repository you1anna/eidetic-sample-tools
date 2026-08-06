"""Local audio-derived classification for audition packets.

The classifier deliberately separates form (one-shot/loop/phrase/long-form) from
content (rim/tom/percussion/full drums/vocal/out-of-brief).  Path text is tokenised
and contributes only a small tie-breaking bonus; acoustic and CLAP evidence remain
the primary signals.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, replace
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
from .classification.domain import (
    AUDITION_GROUPS,
    CONTENTS,
    FORMS,
    AcousticEvidence,
    Classification,
    ClassificationError,
)
from .classification.models import (
    CONTENT_PROMPTS,
    MODEL_ID,
    MODEL_REVISION,
    ClapSemanticScorer,
    SemanticScorer,
    clap_audio_inputs,
    clap_excerpt_offsets,
    feature_array,
    rank_prompt_embeddings,
)
from .classification.packets import (
    CLASSIFICATION_FIELDS,
    read_classifications,
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
from .featurecache import FEATURE_COLUMNS
from .inventory import sha256_file


CLASSIFIER_VERSION = "hybrid-v1"

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
) -> tuple[list[Classification], BenchmarkScore]:
    """Classify a packet and create/score its 24-row ear benchmark."""
    scorer = scorer or ClapSemanticScorer()
    with labels_path.open(encoding="utf-8", newline="") as fh:
        label_reader = csv.DictReader(fh, delimiter="\t")
        label_rows = list(label_reader)
    cached = database.features()
    raw_candidates: list[RawCandidate] = []
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
        raw_candidates.append(RawCandidate(
            sample_id=raw["sample_id"],
            current_path=rel,
            evidence=evidence,
            semantic_scores=scorer.score(source),
        ))

    truth = _read_benchmark_truth(benchmark_path)
    config = (
        calibrate_config(raw_candidates, truth)
        if len(truth) == 24
        else DEFAULT_CONFIG
    )
    classifications = []
    for item in raw_candidates:
        predicted = classify_evidence(
            item.current_path, item.evidence, item.semantic_scores, config=config,
        )
        classifications.append(replace(
            predicted,
            sample_id=item.sample_id,
            current_path=item.current_path,
        ))

    # Revoke any previous pass before changing classifier-derived output.  If this
    # run fails afterwards, `playlists` must not trust a gate scored against older
    # predictions.
    meta_path = labels_path.parent / "packet-meta.json"
    metadata = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    previous_benchmark = metadata.get("benchmark")
    benchmark_metadata = dict(previous_benchmark) if isinstance(previous_benchmark, dict) else {}
    benchmark_metadata.update({"ready": False, "passed": False})
    metadata["benchmark"] = benchmark_metadata
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    classification_path = labels_path.parent / "classification.tsv"
    write_classifications(classification_path, classifications)
    by_id = {row.sample_id: row for row in classifications}
    if benchmark_path.is_file():
        benchmark_rows = refresh_benchmark_predictions(benchmark_path, by_id)
    else:
        strata = benchmark_strata(classifications)
        write_benchmark_sheet(benchmark_path, classifications, strata)
        benchmark_rows = read_benchmark_with_predictions(benchmark_path, by_id)
    _write_benchmark_audition(root, benchmark_path)
    score = score_benchmark(benchmark_rows)

    metadata.update({
        "schema_version": 2,
        "classifier": {
            "version": CLASSIFIER_VERSION,
            "model_id": MODEL_ID,
            "model_revision": scorer.revision,
            "config": asdict(config),
        },
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
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return classifications, score
