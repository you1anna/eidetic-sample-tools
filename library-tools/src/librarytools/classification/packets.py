"""Versioned packet schemas and atomic derived-file persistence."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Mapping, Sequence

from .domain import (
    AUDITION_GROUPS,
    AcousticEvidence,
    AxisDecision,
    CONTENTS,
    FORMS,
    Classification,
    ClassificationError,
    CandidateClassification,
    ModelVote,
)


CLASSIFICATION_FIELDS = (
    "sample_id", "current_path", "form", "content", "audition_group",
    "form_confidence", "content_confidence", "evidence", "classifier_version",
)


def candidate_audit_record(candidate: CandidateClassification) -> dict[str, object]:
    return {
        "schema_version": 1,
        "sample_id": candidate.sample_id,
        "current_path": candidate.current_path.as_posix(),
        "acoustic": asdict(candidate.evidence),
        "models": [
            {
                "model_id": vote.model_id,
                "model_revision": vote.model_revision,
                "scores": dict(sorted(vote.scores.items())),
                "top_label": vote.top_label,
                "top_score": vote.top_score,
                "margin": vote.margin,
            }
            for vote in candidate.votes
        ],
        "candidate": {
            "form": asdict(candidate.form),
            "content": asdict(candidate.content),
            "audition_group": candidate.audition_group,
        },
        "review_reasons": list(candidate.review_reasons),
    }


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def classification_digest(
    candidates: Sequence[CandidateClassification],
    context: dict[str, object],
) -> str:
    records = [candidate_audit_record(item) for item in sorted(candidates, key=lambda row: row.sample_id)]
    sample_ids = [str(record["sample_id"]) for record in records]
    if len(sample_ids) != len(set(sample_ids)):
        raise ClassificationError("classification candidates contain duplicate sample IDs")
    payload = {"schema_version": 1, "context": context, "candidates": records}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def resolution_digest(
    candidate_digest: str,
    resolutions: Sequence[Mapping[str, str]],
) -> str:
    """Bind human form/content resolutions to one candidate classifier snapshot."""
    records = sorted(
        (
            {
                "sample_id": str(item.get("sample_id", "")),
                "form": str(item.get("form", "")),
                "content": str(item.get("content", "")),
            }
            for item in resolutions
        ),
        key=lambda item: item["sample_id"],
    )
    sample_ids = [item["sample_id"] for item in records]
    if not candidate_digest or any(not value for value in sample_ids):
        raise ClassificationError("resolution digest requires candidate and sample identities")
    if len(sample_ids) != len(set(sample_ids)):
        raise ClassificationError("resolution digest contains duplicate sample IDs")
    payload = {
        "schema_version": 1,
        "classification_digest": candidate_digest,
        "resolutions": records,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def withdraw_published_playlists(
    packet_dir: Path,
    publication_digest: str,
) -> Path | None:
    """Atomically withdraw playable packet links into a recoverable stale archive."""
    sources = [packet_dir / "playlists", packet_dir / "audition.m3u8"]
    sources = [path for path in sources if path.exists() or path.is_symlink()]
    if not sources:
        return None

    digest = str(publication_digest)
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        digest = hashlib.sha256(digest.encode("utf-8")).hexdigest()
    parent = packet_dir / "archive" / "stale-publications"
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / digest
    suffix = 2
    while target.exists() or target.is_symlink():
        target = parent / f"{digest}-{suffix}"
        suffix += 1
    staging = parent / f".{target.name}.incomplete"
    while staging.exists() or staging.is_symlink():
        staging = parent / f".{target.name}.{suffix}.incomplete"
        suffix += 1
    staging.mkdir()
    moved: list[tuple[Path, Path]] = []
    try:
        for source in sources:
            destination = staging / source.name
            source.replace(destination)
            moved.append((source, destination))
        staging.replace(target)
    except OSError as exc:
        for source, destination in reversed(moved):
            if destination.exists() or destination.is_symlink():
                destination.replace(source)
        if staging.exists():
            staging.rmdir()
        raise ClassificationError(f"cannot withdraw stale playlist publication: {exc}") from exc
    return target


def write_classification_audit(
    path: Path,
    candidates: Sequence[CandidateClassification],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    lines = [
        _canonical_json(candidate_audit_record(candidate))
        for candidate in sorted(candidates, key=lambda row: row.sample_id)
    ]
    temporary.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    temporary.replace(path)


def read_classification_audit(path: Path) -> list[CandidateClassification]:
    if not path.is_file():
        raise ClassificationError(f"classification audit is missing: {path}")
    candidates: list[CandidateClassification] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            raw = json.loads(line)
            if raw.get("schema_version") != 1:
                raise ValueError("unexpected schema version")
            sample_id = str(raw["sample_id"])
            if sample_id in seen:
                raise ValueError("duplicate sample ID")
            acoustic = AcousticEvidence(**raw["acoustic"])
            votes = tuple(
                ModelVote(
                    model_id=str(vote["model_id"]),
                    model_revision=str(vote["model_revision"]),
                    scores={str(key): float(value) for key, value in vote["scores"].items()},
                    top_label=str(vote["top_label"]),
                    top_score=float(vote["top_score"]),
                    margin=float(vote["margin"]),
                )
                for vote in raw["models"]
            )
            candidate_raw = raw["candidate"]
            form_raw = candidate_raw["form"]
            content_raw = candidate_raw["content"]
            form = AxisDecision(
                str(form_raw["label"]),
                float(form_raw["confidence"]),
                bool(form_raw["resolved"]),
                tuple(str(value) for value in form_raw.get("review_reasons", [])),
            )
            content = AxisDecision(
                str(content_raw["label"]),
                float(content_raw["confidence"]),
                bool(content_raw["resolved"]),
                tuple(str(value) for value in content_raw.get("review_reasons", [])),
            )
            candidate = CandidateClassification(
                sample_id=sample_id,
                current_path=Path(raw["current_path"]),
                evidence=acoustic,
                votes=votes,
                form=form,
                content=content,
                audition_group=str(candidate_raw["audition_group"]),
                review_reasons=tuple(str(value) for value in raw.get("review_reasons", [])),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ClassificationError(
                f"classification audit row {line_number} is invalid: {exc}"
            ) from exc
        seen.add(sample_id)
        candidates.append(candidate)
    return candidates


def write_classifications(path: Path, rows: Sequence[Classification]) -> None:
    """Atomically write the stable classification TSV snapshot."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CLASSIFICATION_FIELDS, delimiter="\t")
        writer.writeheader()
        for row in rows:
            data = asdict(row)
            data["current_path"] = row.current_path.as_posix()
            data["form_confidence"] = f"{row.form_confidence:.6f}"
            data["content_confidence"] = f"{row.content_confidence:.6f}"
            writer.writerow(data)
    temporary.replace(path)


def read_classifications(path: Path) -> list[Classification]:
    if not path.is_file():
        raise ClassificationError(
            f"classification.tsv is missing beside {path.parent / 'labels.tsv'}"
        )
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if tuple(reader.fieldnames or ()) != CLASSIFICATION_FIELDS:
            raise ClassificationError("classification.tsv has an unexpected schema")
        rows: list[Classification] = []
        seen: set[str] = set()
        for index, raw in enumerate(reader, start=2):
            sample_id = raw["sample_id"]
            if sample_id in seen:
                raise ClassificationError(f"classification.tsv row {index}: duplicate sample_id")
            if raw["form"] not in FORMS or raw["content"] not in CONTENTS:
                raise ClassificationError(
                    f"classification.tsv row {index}: invalid form/content"
                )
            if raw["audition_group"] not in AUDITION_GROUPS:
                raise ClassificationError(
                    f"classification.tsv row {index}: invalid audition_group"
                )
            seen.add(sample_id)
            rows.append(Classification(
                sample_id=sample_id,
                current_path=Path(raw["current_path"]),
                form=raw["form"],
                content=raw["content"],
                audition_group=raw["audition_group"],
                form_confidence=float(raw["form_confidence"]),
                content_confidence=float(raw["content_confidence"]),
                evidence=raw["evidence"],
                classifier_version=raw["classifier_version"],
            ))
    return rows
