from pathlib import Path

from librarytools.classification.domain import AcousticEvidence
from librarytools.classification.policy import classify_evidence, tokenise_path


def test_policy_matches_path_words_not_substrings() -> None:
    assert "tom" not in tokenise_path(Path("loops/bottomtotop.wav"))
    result = classify_evidence(
        Path("loops/bottomtotop.wav"),
        AcousticEvidence(
            duration_s=0.4,
            onset_density=2.0,
            crest=4.0,
            attack_ms=1.0,
            tail_ms=120.0,
            silence_ratio=0.0,
            tempo_bpm=0.0,
            beat_confidence=0.0,
            periodicity=0.0,
        ),
        {"PERCUSSION": 0.8, "TOM": 0.2},
    )
    assert result.content == "PERCUSSION"
