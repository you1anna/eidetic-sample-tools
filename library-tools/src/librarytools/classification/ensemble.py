"""Conservative, filename-independent form and content resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .domain import (
    AcousticEvidence,
    AxisDecision,
    CandidateClassification,
    ClassificationError,
    ModelVote,
    audition_group,
)


def classify_form(evidence: AcousticEvidence) -> AxisDecision:
    """Return a best guess, resolving only the approved acoustic boundaries."""
    if evidence.duration_s >= 90.0:
        return AxisDecision("LONG_FORM", 0.95, True)

    one_shot = (
        evidence.duration_s <= 1.0
        and evidence.onset_count <= 2
        and evidence.periodicity < 0.25
    )
    if one_shot:
        confidence = min(0.98, 0.86 + max(0.0, 1.0 - evidence.duration_s) * 0.10)
        return AxisDecision("ONE_SHOT", confidence, True)

    loop = (
        evidence.onset_count >= 4
        and evidence.periodicity >= 0.40
        and evidence.beat_confidence >= 0.30
        and evidence.bar_fit_error <= 0.05
    )
    if loop:
        strength = min(evidence.periodicity, evidence.beat_confidence)
        return AxisDecision("LOOP", min(0.98, 0.76 + strength * 0.25), True)

    if evidence.duration_s <= 1.0:
        label = "ONE_SHOT"
    elif evidence.onset_count >= 4 and (
        evidence.periodicity >= 0.25 or evidence.beat_confidence >= 0.20
    ):
        label = "LOOP"
    else:
        label = "PHRASE"
    return AxisDecision(label, 0.50, False, ("form-boundary",))


def resolve_content(votes: Sequence[ModelVote]) -> AxisDecision:
    if len(votes) != 2:
        raise ClassificationError("content resolution requires exactly two model votes")
    labels = sorted({label for vote in votes for label in vote.scores})
    averaged = {
        label: sum(float(vote.scores.get(label, 0.0)) for vote in votes) / len(votes)
        for label in labels
    }
    ordered = sorted(averaged.items(), key=lambda item: (-item[1], item[0]))
    best_guess = ordered[0][0]
    reasons: list[str] = []
    if votes[0].top_label != votes[1].top_label:
        reasons.append("model-disagreement")
    if min(vote.top_score for vote in votes) < 0.45:
        reasons.append("weak-model-score")
    if min(vote.margin for vote in votes) < 0.08:
        reasons.append("weak-model-margin")
    out_votes = [vote.top_label == "OUT_OF_BRIEF" for vote in votes]
    if any(out_votes) and not all(out_votes):
        reasons.append("out-of-brief-conflict")
    resolved = not reasons
    confidence = min(vote.top_score for vote in votes) if resolved else ordered[0][1]
    return AxisDecision(best_guess, confidence, resolved, tuple(reasons))


def build_candidate(
    sample_id: str,
    current_path: Path,
    evidence: AcousticEvidence,
    votes: Sequence[ModelVote],
) -> CandidateClassification:
    """Build a reviewable candidate; path text is deliberately never consulted."""
    form = classify_form(evidence)
    content = resolve_content(votes)
    reasons = list(form.review_reasons + content.review_reasons)
    if (
        (content.label == "FULL_DRUMS" and form.label == "ONE_SHOT")
        or (content.label in {"RIM", "TOM"} and form.label != "ONE_SHOT")
    ):
        reasons.append("implausible-form-content")
    return CandidateClassification(
        sample_id=sample_id,
        current_path=current_path,
        evidence=evidence,
        votes=tuple(votes),
        form=form,
        content=content,
        audition_group=audition_group(form.label, content.label),
        review_reasons=tuple(dict.fromkeys(reasons)),
    )
