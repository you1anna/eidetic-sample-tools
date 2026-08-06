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
    read_benchmark_truth,
    refresh_benchmark_predictions,
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
from .packets import resolution_digest, withdraw_published_playlists, write_classifications


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
    kind: str = "legacy"
    audition_group: str = ""


@dataclass(frozen=True)
class GateResult:
    ready: bool
    passed: bool
    unresolved: int
    classification_digest: str
    failed_sentinel_groups: tuple[str, ...] = ()
    escalated_sentinel_groups: tuple[str, ...] = ()


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
        benchmark_sample_ids: Sequence[str] = (),
    ) -> ReviewQueue:
        exceptions = sorted(
            (candidate for candidate in candidates if candidate.review_reasons),
            key=lambda candidate: (
                min(candidate.form.confidence, candidate.content.confidence),
                candidate.sample_id,
            ),
        )
        items = [_item(candidate, "exception") for candidate in exceptions]
        existing = {item.sample_id for item in items}
        for sample_id in benchmark_sample_ids:
            candidate = next(
                (item for item in candidates if item.sample_id == sample_id), None,
            )
            if candidate is None:
                raise ClassificationError(f"benchmark sample is absent from candidates: {sample_id}")
            if sample_id not in existing:
                items.append(_item(candidate, "benchmark"))
                existing.add(sample_id)
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
            if sentinel.sample_id not in existing:
                items.append(_item(sentinel, "sentinel"))
                existing.add(sentinel.sample_id)
        return cls(candidates, classification_digest, items)

    @property
    def items(self) -> tuple[ReviewItem, ...]:
        items = list(self._base_items)
        existing = {item.sample_id for item in items}
        reopen_groups = set(self.failed_sentinel_groups()) | set(self.trusted_mismatch_groups())
        for group in (value for value in AUDITION_GROUPS if value in reopen_groups):
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
        covered_groups = set(self.covered_sentinel_groups())
        return tuple(
            item for item in self.items
            if item.sample_id not in decided
            and not (item.kind == "sentinel" and item.audition_group in covered_groups)
        )

    def apply_decision(self, sample_id: str, form: str, content: str, notes: str = "") -> None:
        if form not in FORMS or content not in CONTENTS:
            raise ClassificationError("review decision has an invalid form or content")
        item = next((item for item in self.pending() if item.sample_id == sample_id), None)
        if item is None:
            raise ClassificationError(f"sample is not pending review: {sample_id}")
        self._decisions.append(ReviewDecision(
            sample_id,
            form,
            content,
            notes.strip(),
            item.kind,
            item.audition_group,
        ))

    def restore_decision(self, decision: ReviewDecision) -> None:
        """Restore a digest-bound or explicitly carried human decision by sample identity."""
        if decision.form not in FORMS or decision.content not in CONTENTS:
            raise ClassificationError("review decision has an invalid form or content")
        if decision.sample_id not in self._candidates:
            raise ClassificationError(f"review decision sample is absent: {decision.sample_id}")
        if decision.sample_id in {item.sample_id for item in self._decisions}:
            raise ClassificationError(f"duplicate review decision: {decision.sample_id}")
        self._decisions.append(ReviewDecision(
            decision.sample_id,
            decision.form,
            decision.content,
            decision.notes.strip(),
            decision.kind,
            decision.audition_group,
        ))

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

    def trusted_mismatch_groups(self) -> tuple[str, ...]:
        groups: set[str] = set()
        for decision in self._decisions:
            candidate = self._candidates[decision.sample_id]
            if candidate.automatic and (
                decision.form != candidate.form.label
                or decision.content != candidate.content.label
            ):
                groups.add(candidate.audition_group)
        return tuple(group for group in AUDITION_GROUPS if group in groups)

    def covered_sentinel_groups(self) -> tuple[str, ...]:
        """Reuse an ear-confirmed automatic sample as group coverage after tuning."""
        excluded = set(self.failed_sentinel_groups()) | set(self.trusted_mismatch_groups())
        groups: set[str] = set()
        for decision in self._decisions:
            candidate = self._candidates[decision.sample_id]
            if (
                candidate.automatic
                and decision.kind == "sentinel"
                and decision.audition_group == candidate.audition_group
                and decision.form == candidate.form.label
                and decision.content == candidate.content.label
                and candidate.audition_group not in excluded
            ):
                groups.add(candidate.audition_group)
        return tuple(group for group in AUDITION_GROUPS if group in groups)

    def resolution_digest(self) -> str:
        return resolution_digest(
            self.classification_digest,
            [
                {
                    "sample_id": decision.sample_id,
                    "form": decision.form,
                    "content": decision.content,
                }
                for decision in self._decisions
            ],
        )

    def gate(self) -> GateResult:
        pending = self.pending()
        unresolved = len(pending)
        escalated = self.failed_sentinel_groups()
        active_failed = tuple(
            group for group in escalated
            if any(item.audition_group == group for item in pending)
        )
        return GateResult(
            ready=unresolved == 0,
            passed=unresolved == 0,
            unresolved=unresolved,
            classification_digest=self.classification_digest,
            failed_sentinel_groups=active_failed,
            escalated_sentinel_groups=escalated,
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
    def begin(
        cls,
        path: Path,
        candidates: Sequence[CandidateClassification],
        classification_digest: str,
        *,
        restart: bool = False,
        carry_decisions: bool = False,
        benchmark_sample_ids: Sequence[str] = (),
    ) -> ReviewSession:
        """Start a classifier run without silently discarding human review work."""
        carried_decisions: list[object] = []
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ClassificationError(f"invalid review state: {exc}") from exc
            previous_digest = str(raw.get("classification_digest", ""))
            if previous_digest and previous_digest != classification_digest:
                decisions = raw.get("decisions", [])
                if decisions and not restart and not carry_decisions:
                    raise ClassificationError(
                        "review state contains human decisions; rerun with --carry-review to reuse "
                        "them or --restart-review to archive them"
                    )
                if decisions:
                    if carry_decisions:
                        carried_decisions = list(decisions)
                    archive_dir = path.parent / "archive" / "review-state"
                    archive_dir.mkdir(parents=True, exist_ok=True)
                    target = archive_dir / f"{previous_digest}.json"
                    suffix = 1
                    while target.exists():
                        target = archive_dir / f"{previous_digest}-{suffix}.json"
                        suffix += 1
                    path.replace(target)
                else:
                    path.unlink()
        session = cls.open(
            path,
            candidates,
            classification_digest,
            benchmark_sample_ids=benchmark_sample_ids,
        )
        if carried_decisions:
            for raw_decision in carried_decisions:
                try:
                    session.queue.restore_decision(ReviewDecision(
                        sample_id=str(raw_decision["sample_id"]),
                        form=str(raw_decision["form"]),
                        content=str(raw_decision["content"]),
                        notes=str(raw_decision.get("notes", "")),
                        kind=str(raw_decision.get("kind", "legacy")),
                        audition_group=str(raw_decision.get("audition_group", "")),
                    ))
                except (KeyError, TypeError, ClassificationError) as exc:
                    raise ClassificationError(f"cannot carry review decision: {exc}") from exc
            session._save()
        return session

    @classmethod
    def open(
        cls,
        path: Path,
        candidates: Sequence[CandidateClassification],
        classification_digest: str,
        benchmark_sample_ids: Sequence[str] = (),
    ) -> ReviewSession:
        queue = ReviewQueue.build(
            candidates,
            classification_digest,
            benchmark_sample_ids=benchmark_sample_ids,
        )
        session = cls(path, queue)
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ClassificationError(f"invalid review state: {exc}") from exc
            schema_version = raw.get("schema_version")
            if schema_version not in {1, 2} or raw.get("classification_digest") != classification_digest:
                raise ClassificationError("stale review state does not match current classification")
            try:
                for decision in raw.get("decisions", []):
                    base_item = next(
                        (
                            item for item in queue._base_items
                            if item.sample_id == str(decision["sample_id"])
                        ),
                        None,
                    )
                    queue.restore_decision(ReviewDecision(
                        str(decision["sample_id"]),
                        str(decision["form"]),
                        str(decision["content"]),
                        str(decision.get("notes", "")),
                        str(decision.get("kind", base_item.kind if base_item else "legacy")),
                        str(decision.get(
                            "audition_group",
                            base_item.audition_group if base_item else "",
                        )),
                    ))
            except (KeyError, TypeError, ClassificationError) as exc:
                raise ClassificationError(f"invalid review state: {exc}") from exc
            if schema_version == 1:
                session._save()
        else:
            session._save()
        return session

    def apply_decision(self, sample_id: str, form: str, content: str, notes: str = "") -> None:
        self.queue.apply_decision(sample_id, form, content, notes)
        self._save()

    def undo(self) -> ReviewDecision:
        decision = self.queue.undo()
        self._save()
        self._invalidate_completion()
        return decision

    def _invalidate_completion(self) -> None:
        metadata_path = self.path.parent / "packet-meta.json"
        if not metadata_path.is_file():
            return
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ClassificationError(f"invalid packet metadata: {exc}") from exc
        gate = self.queue.gate()
        metadata["review"] = {
            "state": "pending",
            "ready": False,
            "passed": False,
            "unresolved": gate.unresolved,
            "classification_digest": self.queue.classification_digest,
            "failed_sentinel_groups": list(gate.failed_sentinel_groups),
            "escalated_sentinel_groups": list(gate.escalated_sentinel_groups),
        }
        benchmark = metadata.get("benchmark")
        if isinstance(benchmark, dict):
            benchmark.update({"ready": False, "passed": False})
        if metadata.get("audio_playlists_published"):
            withdraw_published_playlists(
                self.path.parent,
                str(metadata.get("published_digest") or self.queue.classification_digest),
            )
        metadata["audio_playlists_published"] = False
        metadata.pop("resolution_digest", None)
        metadata.pop("published_digest", None)
        temporary = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
        temporary.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        temporary.replace(metadata_path)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {
            "schema_version": 2,
            "classification_digest": self.queue.classification_digest,
            "decisions": [asdict(decision) for decision in self.queue.decisions],
        }
        temporary.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)


def write_review_benchmark(path: Path, queue: ReviewQueue) -> BenchmarkScore:
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
    try:
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            if tuple(reader.fieldnames or ()) != BENCHMARK_FIELDS:
                raise ClassificationError("benchmark-labels.tsv has an unexpected schema")
            benchmark_rows = list(reader)
    except OSError as exc:
        raise ClassificationError(f"cannot read frozen benchmark: {exc}") from exc
    if len(benchmark_rows) != 24:
        raise ClassificationError("frozen benchmark must contain exactly 24 samples")
    predicted_by_id = {row.sample_id: row for row in predicted}
    decisions = {decision.sample_id: decision for decision in queue.decisions}
    saved: list[dict[str, str]] = []
    merged: list[dict[str, str]] = []
    for raw in benchmark_rows:
        row = predicted_by_id.get(raw["sample_id"])
        if row is None or Path(raw["current_path"]) != row.current_path:
            raise ClassificationError(f"frozen benchmark sample is stale: {raw['sample_id']}")
        decision = decisions.get(row.sample_id)
        if decision is None:
            raise ClassificationError(
                f"benchmark sample lacks an explicit human decision: {row.sample_id}"
            )
        true_group = audition_group(decision.form, decision.content)
        saved_row = {
            "sample_id": row.sample_id,
            "current_path": row.current_path.as_posix(),
            "stratum": raw["stratum"],
            "predicted_form": row.form,
            "predicted_content": row.content,
            "predicted_audition_group": row.audition_group,
            "true_form": decision.form,
            "true_content": decision.content,
            "true_audition_group": true_group,
            "notes": decision.notes,
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

    if metadata.get("audio_playlists_published"):
        withdraw_published_playlists(
            packet_dir,
            str(metadata.get("published_digest") or queue.classification_digest),
        )

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
        "resolution_digest": queue.resolution_digest(),
        "failed_sentinel_groups": list(gate.failed_sentinel_groups),
        "escalated_sentinel_groups": list(gate.escalated_sentinel_groups),
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
    metadata["resolution_digest"] = queue.resolution_digest()
    metadata["audio_playlists_published"] = False
    metadata.pop("published_digest", None)
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
