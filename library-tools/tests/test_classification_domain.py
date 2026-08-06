import pytest

from librarytools.classification.domain import ModelVote, audition_group


@pytest.mark.parametrize(
    ("form", "content", "expected"),
    [
        ("ONE_SHOT", "RIM", "rim-one-shots"),
        ("ONE_SHOT", "TOM", "tom-one-shots"),
        ("ONE_SHOT", "PERCUSSION", "percussion-one-shots"),
        ("LOOP", "PERCUSSION", "percussion-loops"),
        ("LOOP", "FULL_DRUMS", "full-drum-loops"),
        ("ONE_SHOT", "VOCAL", "vocal-stabs"),
        ("PHRASE", "VOCAL", "vocal-phrases"),
        ("LONG_FORM", "VOCAL", "long-vocal-sources"),
        ("LOOP", "OUT_OF_BRIEF", "out-of-brief"),
    ],
)
def test_audition_group_preserves_the_nine_public_categories(form, content, expected):
    assert audition_group(form, content) == expected


def test_model_vote_rejects_a_top_label_missing_from_its_scores():
    with pytest.raises(ValueError, match="top label"):
        ModelVote(
            model_id="example/model",
            model_revision="a" * 40,
            scores={"RIM": 0.7, "TOM": 0.3},
            top_label="PERCUSSION",
            top_score=0.7,
            margin=0.4,
        )
