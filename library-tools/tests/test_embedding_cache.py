from __future__ import annotations

import sqlite3

import numpy as np
import pytest

from librarytools.classification.cache import EmbeddingCache, EmbeddingKey
from librarytools.classification.domain import ClassificationError
from librarytools.inventory import LibraryDatabase


def test_embedding_cache_is_additive_and_revision_keyed(tmp_path) -> None:
    database_path = tmp_path / "library.sqlite"
    LibraryDatabase(database_path)
    with sqlite3.connect(database_path) as conn:
        assert conn.execute(
            "select name from sqlite_master where type='table' and name='audio_embeddings'"
        ).fetchone() == ("audio_embeddings",)
    cache = EmbeddingCache(database_path)
    key = EmbeddingKey("sample-1", "model-a", "revision-1", "three-10s-v1")
    expected = np.linspace(-1.0, 1.0, 512, dtype=np.float32)

    cache.put(key, expected)

    restored = cache.get(key)
    assert restored is not None
    assert restored.dtype == np.float32
    np.testing.assert_allclose(restored, expected, atol=5e-4)
    assert cache.get(EmbeddingKey("sample-1", "model-a", "revision-2", "three-10s-v1")) is None
    assert cache.get(EmbeddingKey("sample-1", "model-a", "revision-1", "one-10s-v1")) is None

    with sqlite3.connect(database_path) as conn:
        assert conn.execute("select count(*) from assets").fetchone()[0] == 0
        stored_bytes = conn.execute(
            "select length(embedding) from audio_embeddings"
        ).fetchone()[0]
    assert stored_bytes == 512 * np.dtype(np.float16).itemsize


def test_embedding_cache_rejects_corrupt_dimension_metadata(tmp_path) -> None:
    database_path = tmp_path / "library.sqlite"
    cache = EmbeddingCache(database_path)
    key = EmbeddingKey("sample-1", "model-a", "revision-1", "three-10s-v1")
    cache.put(key, np.ones(4, dtype=np.float32))
    with sqlite3.connect(database_path) as conn:
        conn.execute("update audio_embeddings set dimensions=5")

    with pytest.raises(ClassificationError, match="corrupt cached embedding"):
        cache.get(key)


@pytest.mark.parametrize("value", [np.nan, np.inf, 0.0])
def test_embedding_cache_rejects_non_finite_or_zero_vectors(tmp_path, value) -> None:
    database_path = tmp_path / "library.sqlite"
    cache = EmbeddingCache(database_path)
    key = EmbeddingKey("sample-1", "model-a", "revision-1", "three-10s-v1")
    cache.put(key, np.ones(4, dtype=np.float32))
    with sqlite3.connect(database_path) as conn:
        payload = np.full(4, value, dtype=np.float16).tobytes()
        conn.execute("update audio_embeddings set embedding=?", (payload,))

    with pytest.raises(ClassificationError, match="corrupt cached embedding"):
        cache.get(key, expected_dimensions=4)


def test_prompt_embeddings_are_revision_and_policy_keyed(tmp_path) -> None:
    cache = EmbeddingCache(tmp_path / "library.sqlite")
    expected = {
        "RIM": np.array([1.0, 0.0], dtype=np.float32),
        "TOM": np.array([0.0, 1.0], dtype=np.float32),
    }
    cache.put_prompt_set("model", "revision-1", "prompts-v1", expected)

    restored = cache.get_prompt_set("model", "revision-1", "prompts-v1")
    assert restored is not None
    assert set(restored) == {"RIM", "TOM"}
    np.testing.assert_allclose(restored["RIM"], expected["RIM"], atol=5e-4)
    assert cache.get_prompt_set("model", "revision-2", "prompts-v1") is None
    assert cache.get_prompt_set("model", "revision-1", "prompts-v2") is None
