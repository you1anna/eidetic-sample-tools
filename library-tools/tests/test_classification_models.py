import numpy as np
import pytest

from librarytools.classification.models import (
    CONTENT_PROMPTS,
    ClapScorer,
    ModelSpec,
    batches_of,
    rank_prompt_embeddings,
)


def test_prompt_ranking_returns_cosine_similarity_by_label():
    scores = rank_prompt_embeddings(
        np.array([1.0, 0.0]),
        {"RIM": np.array([1.0, 0.0]), "TOM": np.array([0.0, 1.0])},
    )

    assert scores == {"RIM": pytest.approx(1.0), "TOM": pytest.approx(0.0)}


def test_content_prompts_explicitly_contrast_top_loops_and_full_drum_kits():
    percussion = " ".join(CONTENT_PROMPTS["PERCUSSION"]).lower()
    full_drums = " ".join(CONTENT_PROMPTS["FULL_DRUMS"]).lower()
    vocal = " ".join(CONTENT_PROMPTS["VOCAL"]).lower()

    assert "top loop" in percussion
    assert "without kick or snare" in percussion
    assert "kick" in full_drums and "snare" in full_drums and "hi-hat" in full_drums
    assert "not a top loop" in full_drums
    assert "clearly audible human voice" in vocal
    assert "processed vocal stab" in vocal
    assert "vocal loop" in vocal
    assert "synth stab" in " ".join(CONTENT_PROMPTS["OUT_OF_BRIEF"]).lower()


def test_clap_scorer_builds_a_typed_vote_from_fixed_embeddings():
    vote = ClapScorer(ModelSpec("fake/model", "revision", 2)).score(
        np.array([1.0, 0.0]),
        {"RIM": np.array([1.0, 0.0]), "TOM": np.array([0.0, 1.0])},
    )

    assert vote.model_id == "fake/model"
    assert vote.model_revision == "revision"
    assert vote.top_label == "RIM"
    assert vote.top_score > 0.99
    assert vote.margin > 0.99


def test_model_inputs_are_batched_without_exceeding_eight() -> None:
    assert list(batches_of(list(range(19)), 8)) == [
        list(range(8)),
        list(range(8, 16)),
        list(range(16, 19)),
    ]
