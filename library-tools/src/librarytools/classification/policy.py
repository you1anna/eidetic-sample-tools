"""Deterministic classification policy, separate from audio/model I/O."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .domain import AcousticEvidence, Classification, ClassificationError, CONTENTS, audition_group


_TOKEN_CONTENT: dict[str, frozenset[str]] = {
    "RIM": frozenset({"rim", "rimshot"}),
    "TOM": frozenset({"tom", "toms"}),
    "PERCUSSION": frozenset({
        "perc", "percussion", "conga", "congas", "bongo", "bongos", "shaker",
        "clave", "cowbell", "djembe", "tribal",
    }),
    "FULL_DRUMS": frozenset({"drum", "drums", "beat", "beats", "groove"}),
    "VOCAL": frozenset({"vocal", "vocals", "vox", "voice", "acapella", "rap"}),
    "OUT_OF_BRIEF": frozenset({
        "acid", "synth", "bassline", "waterfall", "nature", "field", "atmosphere",
        "ambient", "melody", "chord",
    }),
}


@dataclass(frozen=True)
class ClassifierConfig:
    lexical_weight: float
    periodicity_threshold: float
    beat_threshold: float


@dataclass(frozen=True)
class RawCandidate:
    sample_id: str
    current_path: Path
    evidence: AcousticEvidence
    semantic_scores: Mapping[str, float]


DEFAULT_CONFIG = ClassifierConfig(
    lexical_weight=0.08,
    periodicity_threshold=0.32,
    beat_threshold=0.20,
)
CALIBRATION_CONFIGS = tuple(
    ClassifierConfig(lexical_weight, periodicity, beat)
    for lexical_weight in (0.00, 0.02, 0.04, 0.08)
    for periodicity in (0.25, 0.32, 0.40)
    for beat in (0.10, 0.20, 0.30)
)


def calibrate_config(
    items: Sequence[RawCandidate],
    truth: Mapping[str, Mapping[str, str]],
    configs: Sequence[ClassifierConfig] = CALIBRATION_CONFIGS,
) -> ClassifierConfig:
    if not configs:
        raise ClassificationError("calibration requires at least one candidate configuration")
    ranked: list[tuple[tuple[float, ...], ClassifierConfig]] = []
    for config in configs:
        form_correct = content_correct = group_correct = content_group_correct = 0
        margins: list[float] = []
        for item in items:
            expected = truth.get(item.sample_id)
            if not expected:
                continue
            predicted = classify_evidence(
                item.current_path, item.evidence, item.semantic_scores, config=config,
            )
            form_correct += predicted.form == expected.get("true_form")
            content_correct += predicted.content == expected.get("true_content")
            group_correct += predicted.audition_group == expected.get("true_audition_group")
            content_group_correct += (
                predicted.content == expected.get("true_content")
                and predicted.audition_group == expected.get("true_audition_group")
            )
            margins.append(min(predicted.form_confidence, predicted.content_confidence))
        mean_margin = sum(margins) / len(margins) if margins else 0.0
        objective = (
            float(form_correct), float(content_group_correct), float(content_correct), mean_margin,
            -config.lexical_weight,
        )
        ranked.append((objective, config))
    return max(ranked, key=lambda item: item[0])[1]


def tokenise_path(path: Path) -> frozenset[str]:
    """Return whole lowercase tokens; substrings such as bottom/tom never match."""
    return frozenset(re.findall(r"[a-z]+|[0-9]+", path.as_posix().lower()))


def _normalise_scores(scores: Mapping[str, float]) -> dict[str, float]:
    values = {name: max(0.0, float(scores.get(name, 0.0))) for name in CONTENTS}
    total = sum(values.values())
    if total <= 0.0:
        return {name: 1.0 / len(CONTENTS) for name in CONTENTS}
    return {name: value / total for name, value in values.items()}


def _content(
    path: Path,
    semantic_scores: Mapping[str, float],
    config: ClassifierConfig,
) -> tuple[str, float, dict[str, float]]:
    scores = _normalise_scores(semantic_scores)
    tokens = tokenise_path(path)
    adjusted = {
        name: score + (config.lexical_weight if tokens & _TOKEN_CONTENT[name] else 0.0)
        for name, score in scores.items()
    }
    ordered = sorted(adjusted.items(), key=lambda item: (-item[1], item[0]))
    content = ordered[0][0]
    margin = max(0.0, ordered[0][1] - ordered[1][1])
    confidence = min(1.0, max(scores[content], 0.5 + margin / 2.0))
    return content, confidence, adjusted


def _form(
    path: Path,
    evidence: AcousticEvidence,
    config: ClassifierConfig,
) -> tuple[str, float]:
    duration = evidence.duration_s
    filename_tokens = tokenise_path(Path(path.name))
    loop_hint = "loop" in filename_tokens or "loops" in filename_tokens
    rhythmic = (
        evidence.periodicity >= config.periodicity_threshold
        and evidence.beat_confidence >= config.beat_threshold
    )

    if duration >= 90.0:
        return "LONG_FORM", min(1.0, 0.90 + min(duration - 90.0, 100.0) / 1000.0)
    if duration <= 2.0:
        return "ONE_SHOT", min(1.0, 0.76 + (2.0 - duration) * 0.10)
    if rhythmic or (loop_hint and evidence.onset_density >= 1.0):
        strength = max(evidence.periodicity, evidence.beat_confidence)
        return "LOOP", min(0.98, 0.62 + strength * 0.35)
    return "PHRASE", min(0.85, 0.55 + min(duration, 30.0) / 150.0)


def classify_evidence(
    path: Path,
    evidence: AcousticEvidence,
    semantic_scores: Mapping[str, float],
    *,
    config: ClassifierConfig = DEFAULT_CONFIG,
) -> Classification:
    content, content_confidence, adjusted = _content(path, semantic_scores, config)
    form, form_confidence = _form(path, evidence, config)
    group = audition_group(form, content)
    top_scores = sorted(adjusted.items(), key=lambda item: (-item[1], item[0]))[:2]
    detail = (
        f"duration_s={evidence.duration_s:.3f};onset_density={evidence.onset_density:.3f};"
        f"tempo_bpm={evidence.tempo_bpm:.2f};beat_confidence={evidence.beat_confidence:.3f};"
        f"periodicity={evidence.periodicity:.3f};semantic="
        + ",".join(f"{name}:{score:.3f}" for name, score in top_scores)
    )
    return Classification(
        sample_id="",
        current_path=path,
        form=form,
        content=content,
        audition_group=group,
        form_confidence=form_confidence,
        content_confidence=content_confidence,
        evidence=detail,
    )
