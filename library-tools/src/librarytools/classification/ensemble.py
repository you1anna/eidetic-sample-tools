"""Conservative, filename-independent form and content resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .domain import (
    AcousticEvidence,
    AxisDecision,
    CandidateClassification,
    ClassificationError,
    ModelVote,
    audition_group,
)


MODEL_WEIGHT_CONFIGS = (
    (0.2, 0.8),
    (0.35, 0.65),
    (0.5, 0.5),
    (0.65, 0.35),
    (0.8, 0.2),
)


@dataclass(frozen=True)
class EnsembleCalibration:
    weights: tuple[float, float]
    form_correct: int
    content_correct: int
    content_group_correct: int
    confidence_margin: float
    total: int
    filename_weight: float = 0.0


def classify_form(evidence: AcousticEvidence) -> AxisDecision:
    """Return a best guess, resolving only the approved acoustic boundaries."""
    if evidence.duration_s >= 90.0:
        return AxisDecision("LONG_FORM", 0.95, True)

    one_shot = (
        evidence.onset_count <= 2
        and evidence.periodicity < 0.25
        and (
            evidence.duration_s <= 1.0
            or (evidence.silence_ratio >= 0.80 and evidence.tail_ms <= 500.0)
        )
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


def _weighted_content_scores(
    votes: Sequence[ModelVote],
    weights: Sequence[float],
) -> list[tuple[str, float]]:
    if len(votes) != 2:
        raise ClassificationError("content resolution requires exactly two model votes")
    if len(weights) != len(votes) or any(weight < 0 for weight in weights) or not sum(weights):
        raise ClassificationError("model weights must be non-negative and match both votes")
    normalised = [weight / sum(weights) for weight in weights]
    labels = sorted({label for vote in votes for label in vote.scores})
    averaged = {
        label: sum(
            weight * float(vote.scores.get(label, 0.0))
            for vote, weight in zip(votes, normalised, strict=True)
        )
        for label in labels
    }
    return sorted(averaged.items(), key=lambda item: (-item[1], item[0]))


def resolve_content(
    votes: Sequence[ModelVote],
    weights: Sequence[float] = (0.5, 0.5),
) -> AxisDecision:
    ordered = _weighted_content_scores(votes, weights)
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


def select_model_weights(
    items: Sequence[tuple[str, AcousticEvidence, Sequence[ModelVote]]],
    truth: Mapping[str, Mapping[str, str]],
    configs: Sequence[tuple[float, float]] = MODEL_WEIGHT_CONFIGS,
) -> EnsembleCalibration:
    """Choose fixed two-model weights against a complete ear-labelled cohort."""
    eligible = [item for item in items if item[0] in truth]
    if not eligible:
        return EnsembleCalibration((0.5, 0.5), 0, 0, 0, 0.0, 0)
    results: list[EnsembleCalibration] = []
    for weights in configs:
        form_correct = 0
        content_correct = 0
        content_group_correct = 0
        confidence_margin = 0.0
        for sample_id, evidence, votes in eligible:
            heard = truth[sample_id]
            form = classify_form(evidence).label
            content = resolve_content(votes, weights).label
            group = audition_group(form, content)
            form_correct += form == heard.get("true_form")
            content_match = content == heard.get("true_content")
            content_correct += content_match
            content_group_correct += (
                content_match and group == heard.get("true_audition_group")
            )
            ordered = _weighted_content_scores(votes, weights)
            confidence_margin += ordered[0][1] - ordered[1][1]
        results.append(EnsembleCalibration(
            tuple(weights),
            form_correct,
            content_correct,
            content_group_correct,
            confidence_margin,
            len(eligible),
        ))
    return max(
        results,
        key=lambda result: (
            result.form_correct,
            result.content_correct,
            result.confidence_margin,
            -abs(result.weights[0] - result.weights[1]),
            -result.weights[0],
        ),
    )


def build_candidate(
    sample_id: str,
    current_path: Path,
    evidence: AcousticEvidence,
    votes: Sequence[ModelVote],
    weights: Sequence[float] = (0.5, 0.5),
) -> CandidateClassification:
    """Build a reviewable candidate; path text is deliberately never consulted."""
    form = classify_form(evidence)
    content = resolve_content(votes, weights)
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
