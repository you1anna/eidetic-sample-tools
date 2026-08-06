"""Stable taxonomy and typed values for packet classification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


FORMS = frozenset({"ONE_SHOT", "LOOP", "PHRASE", "LONG_FORM"})
CONTENTS = frozenset({"RIM", "TOM", "PERCUSSION", "FULL_DRUMS", "VOCAL", "OUT_OF_BRIEF"})
AUDITION_GROUPS = (
    "rim-one-shots",
    "tom-one-shots",
    "percussion-one-shots",
    "percussion-loops",
    "full-drum-loops",
    "vocal-stabs",
    "vocal-phrases",
    "long-vocal-sources",
    "out-of-brief",
)


class ClassificationError(ValueError):
    """Invalid classifier input, state or derived packet data."""


@dataclass(frozen=True)
class AcousticEvidence:
    duration_s: float
    onset_density: float
    crest: float
    attack_ms: float
    tail_ms: float
    silence_ratio: float
    tempo_bpm: float
    beat_confidence: float
    periodicity: float
    onset_count: int = 0
    bar_fit_error: float = 1.0


@dataclass(frozen=True)
class AxisDecision:
    label: str
    confidence: float
    resolved: bool
    review_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateClassification:
    sample_id: str
    current_path: Path
    evidence: AcousticEvidence
    votes: tuple[ModelVote, ...]
    form: AxisDecision
    content: AxisDecision
    audition_group: str
    review_reasons: tuple[str, ...]

    @property
    def automatic(self) -> bool:
        return not self.review_reasons


@dataclass(frozen=True)
class Classification:
    sample_id: str
    current_path: Path
    form: str
    content: str
    audition_group: str
    form_confidence: float
    content_confidence: float
    evidence: str
    classifier_version: str = "hybrid-v1"


@dataclass(frozen=True)
class ModelVote:
    model_id: str
    model_revision: str
    scores: Mapping[str, float]
    top_label: str
    top_score: float
    margin: float

    def __post_init__(self) -> None:
        if self.top_label not in self.scores:
            raise ValueError("top label is absent from model scores")


def audition_group(form: str, content: str) -> str:
    """Map independent axes into the stable nine-category audition taxonomy."""
    if form not in FORMS:
        raise ValueError(f"invalid form: {form}")
    if content not in CONTENTS:
        raise ValueError(f"invalid content: {content}")
    if content == "OUT_OF_BRIEF":
        return "out-of-brief"
    if content == "VOCAL":
        if form == "LONG_FORM":
            return "long-vocal-sources"
        return "vocal-stabs" if form == "ONE_SHOT" else "vocal-phrases"
    if form in {"LOOP", "PHRASE", "LONG_FORM"}:
        return "full-drum-loops" if content == "FULL_DRUMS" else "percussion-loops"
    if content == "RIM":
        return "rim-one-shots"
    if content == "TOM":
        return "tom-one-shots"
    return "percussion-one-shots"
