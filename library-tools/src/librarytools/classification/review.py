"""Digest-bound exception review, sentinels and fail-closed publication gate."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from .benchmarks import (
    BENCHMARK_FIELDS,
    BenchmarkScore,
    benchmark_strata,
    score_benchmark,
    write_benchmark_audition,
)
from .domain import (
    AUDITION_GROUPS,
    CONTENTS,
    FORMS,
    CandidateClassification,
    Classification,
    ClassificationError,
    audition_group,
)
from .packets import write_classifications


@dataclass(frozen=True)
class ReviewItem:
    sample_id: str
    kind: str
    audition_group: str
    predicted_form: str
    predicted_content: str
    review_reasons: tuple[str, ...]


@dataclass(frozen=True)
class ReviewDecision:
    sample_id: str
    form: str
    content: str
    notes: str = ""


@dataclass(frozen=True)
class GateResult:
    ready: bool
    passed: bool
    unresolved: int
    classification_digest: str
    failed_sentinel_groups: tuple[str, ...] = ()


class ReviewQueue:
    def __init__(
        self,
        candidates: Sequence[CandidateClassification],
        classification_digest: str,
        base_items: Sequence[ReviewItem],
    ) -> None:
        self.classification_digest = classification_digest
        self._candidates = {candidate.sample_id: candidate for candidate in candidates}
        if len(self._candidates) != len(candidates):
            raise ClassificationError("review candidates contain duplicate sample IDs")
        self._base_items = tuple(base_items)
        self._decisions: list[ReviewDecision] = []

    @classmethod
    def build(
        cls,
        candidates: Sequence[CandidateClassification],
        classification_digest: str,
    ) -> ReviewQueue:
        exceptions = sorted(
            (candidate for candidate in candidates if candidate.review_reasons),
            key=lambda candidate: (
                min(candidate.form.confidence, candidate.content.confidence),
                candidate.sample_id,
            ),
        )
        items = [_item(candidate, "exception") for candidate in exceptions]
        automatic = [candidate for candidate in candidates if not candidate.review_reasons]
        for group in AUDITION_GROUPS:
            members = [candidate for candidate in automatic if candidate.audition_group == group]
            if not members:
                continue
            sentinel = min(
                members,
                key=lambda candidate: hashlib.sha256(
                    f"{classification_digest}:{candidate.sample_id}".encode("utf-8")
                ).hexdigest(),
            )
            items.append(_item(sentinel, "sentinel"))
        return cls(candidates, classification_digest, items)

    @property
    def items(self) -> tuple[ReviewItem, ...]:
        items = list(self._base_items)
        existing = {item.sample_id for item in items}
        for group in self.failed_sentinel_groups():
            reopened = sorted(
                (
                    candidate for candidate in self._candidates.values()
                    if candidate.automatic
                    and candidate.audition_group == group
                    and candidate.sample_id not in existing
                ),
                key=lambda candidate: candidate.sample_id,
            )
            items.extend(_item(candidate, "reopened") for candidate in reopened)
            existing.update(candidate.sample_id for candidate in reopened)
        return tuple(items)

    @property
    def decisions(self) -> tuple[ReviewDecision, ...]:
        return tuple(self._decisions)

    def pending(self) -> tuple[ReviewItem, ...]:
        decided = {decision.sample_id for decision in self._decisions}
        return tuple(item for item in self.items if item.sample_id not in decided)

    def apply_decision(self, sample_id: str, form: str, content: str, notes: str = "") -> None:
        if form not in FORMS or content not in CONTENTS:
            raise ClassificationError("review decision has an invalid form or content")
        if sample_id not in {item.sample_id for item in self.pending()}:
            raise ClassificationError(f"sample is not pending review: {sample_id}")
        self._decisions.append(ReviewDecision(sample_id, form, content, notes.strip()))

    def undo(self) -> ReviewDecision:
        if not self._decisions:
            raise ClassificationError("there is no review decision to undo")
        return self._decisions.pop()

    def failed_sentinel_groups(self) -> tuple[str, ...]:
        sentinels = {item.sample_id: item for item in self._base_items if item.kind == "sentinel"}
        groups: set[str] = set()
        for decision in self._decisions:
            sentinel = sentinels.get(decision.sample_id)
            if sentinel and (
                decision.form != sentinel.predicted_form
                or decision.content != sentinel.predicted_content
            ):
                groups.add(sentinel.audition_group)
        return tuple(group for group in AUDITION_GROUPS if group in groups)

    def gate(self) -> GateResult:
        unresolved = len(self.pending())
        return GateResult(
            ready=unresolved == 0,
            passed=unresolved == 0,
            unresolved=unresolved,
            classification_digest=self.classification_digest,
            failed_sentinel_groups=self.failed_sentinel_groups(),
        )

    def resolved_classifications(self) -> list[Classification]:
        if not self.gate().passed:
            raise ClassificationError("review gate is incomplete")
        decisions = {decision.sample_id: decision for decision in self._decisions}
        rows: list[Classification] = []
        for candidate in sorted(self._candidates.values(), key=lambda item: item.sample_id):
            decision = decisions.get(candidate.sample_id)
            form = decision.form if decision else candidate.form.label
            content = decision.content if decision else candidate.content.label
            rows.append(Classification(
                sample_id=candidate.sample_id,
                current_path=candidate.current_path,
                form=form,
                content=content,
                audition_group=audition_group(form, content),
                form_confidence=1.0 if decision else candidate.form.confidence,
                content_confidence=1.0 if decision else candidate.content.confidence,
                evidence=(
                    "human-review:" + (decision.notes or "confirmed")
                    if decision else "automatic-consensus"
                ),
                classifier_version="ensemble-v2",
            ))
        return rows


class ReviewSession:
    def __init__(self, path: Path, queue: ReviewQueue):
        self.path = path
        self.queue = queue

    @classmethod
    def open(
        cls,
        path: Path,
        candidates: Sequence[CandidateClassification],
        classification_digest: str,
    ) -> ReviewSession:
        queue = ReviewQueue.build(candidates, classification_digest)
        session = cls(path, queue)
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ClassificationError(f"invalid review state: {exc}") from exc
            if raw.get("schema_version") != 1 or raw.get("classification_digest") != classification_digest:
                raise ClassificationError("stale review state does not match current classification")
            try:
                for decision in raw.get("decisions", []):
                    queue.apply_decision(
                        str(decision["sample_id"]),
                        str(decision["form"]),
                        str(decision["content"]),
                        str(decision.get("notes", "")),
                    )
            except (KeyError, TypeError, ClassificationError) as exc:
                raise ClassificationError(f"invalid review state: {exc}") from exc
        else:
            session._save()
        return session

    def apply_decision(self, sample_id: str, form: str, content: str, notes: str = "") -> None:
        self.queue.apply_decision(sample_id, form, content, notes)
        self._save()

    def undo(self) -> ReviewDecision:
        decision = self.queue.undo()
        self._save()
        return decision

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {
            "schema_version": 1,
            "classification_digest": self.queue.classification_digest,
            "decisions": [asdict(decision) for decision in self.queue.decisions],
        }
        temporary.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)


def write_review_benchmark(path: Path, queue: ReviewQueue) -> BenchmarkScore:
    resolved = {row.sample_id: row for row in queue.resolved_classifications()}
    predicted = [
        Classification(
            sample_id=candidate.sample_id,
            current_path=candidate.current_path,
            form=candidate.form.label,
            content=candidate.content.label,
            audition_group=candidate.audition_group,
            form_confidence=candidate.form.confidence,
            content_confidence=candidate.content.confidence,
            evidence="candidate",
            classifier_version="ensemble-v2",
        )
        for candidate in queue._candidates.values()
    ]
    strata = benchmark_strata(predicted)
    decisions = {decision.sample_id: decision for decision in queue.decisions}
    saved: list[dict[str, str]] = []
    merged: list[dict[str, str]] = []
    for row in sorted(predicted, key=lambda item: item.sample_id):
        if row.sample_id not in strata:
            continue
        truth = resolved[row.sample_id]
        decision = decisions.get(row.sample_id)
        saved_row = {
            "sample_id": row.sample_id,
            "current_path": row.current_path.as_posix(),
            "stratum": strata[row.sample_id],
            "predicted_form": row.form,
            "predicted_content": row.content,
            "predicted_audition_group": row.audition_group,
            "true_form": truth.form,
            "true_content": truth.content,
            "true_audition_group": truth.audition_group,
            "notes": decision.notes if decision else "automatic consensus",
        }
        saved.append(saved_row)
        merged.append({
            **saved_row,
            "form": row.form,
            "content": row.content,
            "audition_group": row.audition_group,
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=BENCHMARK_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(saved)
    temporary.replace(path)
    return score_benchmark(merged)


def finalise_review(packet_dir: Path, queue: ReviewQueue) -> BenchmarkScore:
    """Publish completed human resolutions to derived packet files, never source audio."""
    gate = queue.gate()
    if not gate.passed:
        raise ClassificationError("review gate is incomplete")
    metadata_path = packet_dir / "packet-meta.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClassificationError(f"invalid packet metadata: {exc}") from exc
    if metadata.get("classification_digest") != queue.classification_digest:
        raise ClassificationError("packet metadata has a stale classification digest")

    write_classifications(packet_dir / "classification.tsv", queue.resolved_classifications())
    benchmark_path = packet_dir / "benchmark-labels.tsv"
    score = write_review_benchmark(benchmark_path, queue)
    root = metadata.get("root")
    if isinstance(root, str) and root:
        write_benchmark_audition(Path(root), benchmark_path)
    metadata["review"] = {
        "state": "complete",
        "ready": True,
        "passed": True,
        "unresolved": 0,
        "classification_digest": queue.classification_digest,
        "failed_sentinel_groups": list(gate.failed_sentinel_groups),
    }
    metadata["benchmark"] = {
        "path": benchmark_path.name,
        "ready": score.ready,
        "passed": score.passed,
        "form_correct": score.form_correct,
        "content_correct": score.content_correct,
        "group_correct": score.group_correct,
        "content_group_correct": score.content_group_correct,
        "total": score.total,
    }
    temporary = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
    temporary.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    temporary.replace(metadata_path)
    return score


def _item(candidate: CandidateClassification, kind: str) -> ReviewItem:
    return ReviewItem(
        sample_id=candidate.sample_id,
        kind=kind,
        audition_group=candidate.audition_group,
        predicted_form=candidate.form.label,
        predicted_content=candidate.content.label,
        review_reasons=candidate.review_reasons,
    )
