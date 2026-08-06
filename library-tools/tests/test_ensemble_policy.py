from __future__ import annotations

from pathlib import Path

import pytest

from librarytools.classification.domain import AcousticEvidence, ModelVote
from librarytools.classification.ensemble import build_candidate, classify_form, resolve_content


def _evidence(**overrides) -> AcousticEvidence:
    values = {
        "duration_s": 0.8,
        "onset_density": 1.0,
        "crest": 4.0,
        "attack_ms": 2.0,
        "tail_ms": 100.0,
        "silence_ratio": 0.0,
        "tempo_bpm": 0.0,
        "beat_confidence": 0.0,
        "periodicity": 0.0,
        "onset_count": 1,
        "bar_fit_error": 1.0,
    }
    values.update(overrides)
    return AcousticEvidence(**values)


def _vote(model: str, scores: dict[str, float]) -> ModelVote:
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return ModelVote(model, "revision", scores, ordered[0][0], ordered[0][1], ordered[0][1] - ordered[1][1])


@pytest.mark.parametrize(
    ("evidence", "label", "resolved"),
    [
        (_evidence(duration_s=90.0), "LONG_FORM", True),
        (_evidence(duration_s=1.0, onset_count=2, periodicity=0.249), "ONE_SHOT", True),
        (_evidence(duration_s=1.001, onset_count=2, periodicity=0.249), "PHRASE", False),
        (_evidence(duration_s=0.9, onset_count=3, periodicity=0.249), "ONE_SHOT", False),
        (_evidence(duration_s=0.9, onset_count=2, periodicity=0.25), "ONE_SHOT", False),
        (
            _evidence(
                duration_s=6.0,
                onset_count=4,
                periodicity=0.40,
                beat_confidence=0.30,
                bar_fit_error=0.05,
            ),
            "LOOP",
            True,
        ),
        (
            _evidence(
                duration_s=6.0,
                onset_count=4,
                periodicity=0.40,
                beat_confidence=0.30,
                bar_fit_error=0.051,
            ),
            "LOOP",
            False,
        ),
    ],
)
def test_form_policy_uses_the_approved_numeric_boundaries(evidence, label, resolved) -> None:
    decision = classify_form(evidence)
    assert decision.label == label
    assert decision.resolved is resolved


def test_content_requires_two_strong_matching_votes() -> None:
    votes = (
        _vote("one", {"PERCUSSION": 0.60, "FULL_DRUMS": 0.25, "VOCAL": 0.15}),
        _vote("two", {"PERCUSSION": 0.55, "FULL_DRUMS": 0.30, "VOCAL": 0.15}),
    )
    decision = resolve_content(votes)
    assert (decision.label, decision.resolved) == ("PERCUSSION", True)
    assert decision.review_reasons == ()


def test_content_disagreement_and_weak_votes_are_reviewed() -> None:
    disagreement = resolve_content((
        _vote("one", {"PERCUSSION": 0.60, "OUT_OF_BRIEF": 0.20, "VOCAL": 0.20}),
        _vote("two", {"OUT_OF_BRIEF": 0.55, "PERCUSSION": 0.25, "VOCAL": 0.20}),
    ))
    assert disagreement.resolved is False
    assert "model-disagreement" in disagreement.review_reasons
    assert "out-of-brief-conflict" in disagreement.review_reasons

    weak = resolve_content((
        _vote("one", {"VOCAL": 0.44, "PERCUSSION": 0.37, "FULL_DRUMS": 0.19}),
        _vote("two", {"VOCAL": 0.50, "PERCUSSION": 0.43, "FULL_DRUMS": 0.07}),
    ))
    assert weak.resolved is False
    assert set(weak.review_reasons) == {"weak-model-score", "weak-model-margin"}


def test_filename_has_zero_decision_weight() -> None:
    evidence = _evidence()
    votes = (
        _vote("one", {"PERCUSSION": 0.65, "TOM": 0.20, "RIM": 0.15}),
        _vote("two", {"PERCUSSION": 0.62, "TOM": 0.21, "RIM": 0.17}),
    )
    first = build_candidate("id", Path("loops/bottomtotop-tom-loop.wav"), evidence, votes)
    second = build_candidate("id", Path("unlabelled/audio.wav"), evidence, votes)
    assert (first.form, first.content, first.audition_group, first.review_reasons) == (
        second.form,
        second.content,
        second.audition_group,
        second.review_reasons,
    )


def test_implausible_one_shot_full_kit_pair_is_reviewed() -> None:
    votes = (
        _vote("one", {"FULL_DRUMS": 0.70, "PERCUSSION": 0.20, "VOCAL": 0.10}),
        _vote("two", {"FULL_DRUMS": 0.65, "PERCUSSION": 0.20, "VOCAL": 0.15}),
    )
    candidate = build_candidate("id", Path("audio.wav"), _evidence(), votes)
    assert candidate.audition_group == "percussion-one-shots"
    assert "implausible-form-content" in candidate.review_reasons


@pytest.mark.parametrize(
    ("path", "evidence", "label", "expected_group"),
    [
        (
            "percussion.wav",
            _evidence(
                duration_s=6.0, onset_count=12, periodicity=0.7,
                beat_confidence=0.6, bar_fit_error=0.01,
            ),
            "PERCUSSION",
            "percussion-loops",
        ),
        (
            "drum-kit.wav",
            _evidence(
                duration_s=6.0, onset_count=16, periodicity=0.7,
                beat_confidence=0.6, bar_fit_error=0.01,
            ),
            "FULL_DRUMS",
            "full-drum-loops",
        ),
        (
            "one-shots/long-conga-groove.wav",
            _evidence(
                duration_s=12.0, onset_count=24, periodicity=0.8,
                beat_confidence=0.7, bar_fit_error=0.02,
            ),
            "PERCUSSION",
            "percussion-loops",
        ),
        ("vocals/acapella.wav", _evidence(duration_s=282.0), "VOCAL", "long-vocal-sources"),
        ("waterfall-acid.wav", _evidence(), "OUT_OF_BRIEF", "out-of-brief"),
        ("loops/single-hit.wav", _evidence(duration_s=0.3), "PERCUSSION", "percussion-one-shots"),
    ],
)
def test_known_packet_regressions_use_audio_axes(path, evidence, label, expected_group) -> None:
    votes = (
        _vote("one", {label: 0.70, "VOCAL" if label != "VOCAL" else "RIM": 0.20, "TOM": 0.10}),
        _vote("two", {label: 0.65, "VOCAL" if label != "VOCAL" else "RIM": 0.20, "TOM": 0.15}),
    )
    candidate = build_candidate("id", Path(path), evidence, votes)
    assert candidate.audition_group == expected_group
