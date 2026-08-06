import numpy as np
import pytest

from librarytools.classification.models import rank_prompt_embeddings


def test_prompt_ranking_returns_cosine_similarity_by_label():
    scores = rank_prompt_embeddings(
        np.array([1.0, 0.0]),
        {"RIM": np.array([1.0, 0.0]), "TOM": np.array([0.0, 1.0])},
    )

    assert scores == {"RIM": pytest.approx(1.0), "TOM": pytest.approx(0.0)}
