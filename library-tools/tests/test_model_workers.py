from __future__ import annotations

from pathlib import Path
import os
import time

import numpy as np
import pytest

from librarytools.classification.cache import EmbeddingCache, EmbeddingKey
from librarytools.classification.models import MODEL_SPECS, ModelSpec
from librarytools.classification.workers import (
    EmbeddingWorker,
    SampleRef,
    generate_model_votes,
    run_models_sequentially,
)


class FakeRuntime:
    def __init__(self, dimensions: int, fail_batch: int | None = None):
        self.dimensions = dimensions
        self.fail_batch = fail_batch
        self.batches: list[list[Path]] = []

    def embed(self, paths: list[Path]) -> list[np.ndarray]:
        self.batches.append(paths)
        if self.fail_batch == len(self.batches):
            raise RuntimeError("synthetic model failure")
        return [np.full(self.dimensions, index + 1.0) for index, _ in enumerate(paths)]


class VoteRuntime:
    def __init__(self, dimensions: int):
        self.dimensions = dimensions

    def embed(self, paths: list[Path]) -> list[np.ndarray]:
        return [np.array([1.0, 0.0]) for _ in paths]

    def embed_prompts(self, prompts):
        return {
            label: np.array([1.0, 0.0]) if label == "RIM" else np.array([0.0, 1.0])
            for label in prompts
        }


def _samples(count: int) -> list[SampleRef]:
    return [SampleRef(f"sample-{index}", Path(f"/{index}.wav")) for index in range(count)]


def test_model_revisions_are_fully_pinned() -> None:
    assert [(item.model_id, item.revision) for item in MODEL_SPECS] == [
        (
            "laion/clap-htsat-unfused",
            "8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a",
        ),
        (
            "laion/larger_clap_music_and_speech",
            "195c3a3e68faebb3e2088b9a79e79b43ddbda76b",
        ),
    ]


def test_worker_is_cache_first_and_commits_batches_of_at_most_eight(tmp_path) -> None:
    cache = EmbeddingCache(tmp_path / "library.sqlite")
    spec = ModelSpec("fake/model", "revision", embedding_dimensions=4)
    samples = _samples(10)
    cache.put(
        EmbeddingKey("sample-0", spec.model_id, spec.revision, "three-10s-v1"),
        np.ones(4),
    )
    runtime = FakeRuntime(4)
    report = EmbeddingWorker(runtime_factory=lambda _: runtime).run(
        spec, samples, cache, batch_size=8, threads=8,
    )

    assert report.cache_hits == 1
    assert report.embedded == 9
    assert report.batch_sizes == (8, 1)
    assert [len(batch) for batch in runtime.batches] == [8, 1]
    assert all(
        cache.get(EmbeddingKey(sample.sample_id, spec.model_id, spec.revision, "three-10s-v1"))
        is not None
        for sample in samples
    )


def test_completed_batches_survive_worker_failure_and_are_reused(tmp_path) -> None:
    cache = EmbeddingCache(tmp_path / "library.sqlite")
    spec = ModelSpec("fake/model", "revision", embedding_dimensions=4)
    samples = _samples(10)
    with pytest.raises(RuntimeError, match="synthetic model failure"):
        EmbeddingWorker(runtime_factory=lambda _: FakeRuntime(4, fail_batch=2)).run(
            spec, samples, cache, batch_size=8,
        )

    retry_runtime = FakeRuntime(4)
    report = EmbeddingWorker(runtime_factory=lambda _: retry_runtime).run(
        spec, samples, cache, batch_size=8,
    )
    assert report.cache_hits == 8
    assert report.embedded == 2
    assert [len(batch) for batch in retry_runtime.batches] == [2]


def test_default_worker_uses_a_short_lived_process_without_model_load_on_cache_hit(tmp_path) -> None:
    cache = EmbeddingCache(tmp_path / "library.sqlite")
    spec = ModelSpec("fake/model", "revision", embedding_dimensions=4)
    sample = SampleRef("sample-0", Path("/already-cached.wav"))
    cache.put(
        EmbeddingKey(sample.sample_id, spec.model_id, spec.revision, "three-10s-v1"),
        np.ones(4),
    )

    report = EmbeddingWorker().run(spec, [sample], cache)

    assert report.cache_hits == 1
    assert report.embedded == 0


def test_models_execute_strictly_sequentially(tmp_path) -> None:
    cache = EmbeddingCache(tmp_path / "library.sqlite")
    active: list[str] = []
    events: list[str] = []

    class TrackingWorker:
        def run(self, spec, samples, cache, **kwargs):
            assert active == []
            active.append(spec.model_id)
            events.append(f"start:{spec.model_id}")
            active.pop()
            events.append(f"stop:{spec.model_id}")
            return spec.model_id

    specs = [ModelSpec("one", "r1", 4), ModelSpec("two", "r2", 4)]
    assert run_models_sequentially(specs, [], cache, worker_factory=TrackingWorker) == ["one", "two"]
    assert events == ["start:one", "stop:one", "start:two", "stop:two"]


def test_model_votes_are_scored_from_persistent_audio_and_prompt_embeddings(tmp_path) -> None:
    cache = EmbeddingCache(tmp_path / "library.sqlite")
    specs = (ModelSpec("one", "r1", 2), ModelSpec("two", "r2", 2))
    samples = [SampleRef("sample", Path("/sample.wav"))]
    votes, reports = generate_model_votes(
        specs,
        samples,
        cache,
        worker_factory=lambda: EmbeddingWorker(
            runtime_factory=lambda spec: VoteRuntime(spec.embedding_dimensions)
        ),
        prompts={"RIM": ("rim",), "TOM": ("tom",)},
    )

    assert [vote.model_id for vote in votes["sample"]] == ["one", "two"]
    assert all(vote.top_label == "RIM" for vote in votes["sample"])
    assert all(report.embedded == 1 for report in reports)

    cached_votes, cached_reports = generate_model_votes(
        specs,
        samples,
        cache,
        worker_factory=lambda: EmbeddingWorker(
            runtime_factory=lambda spec: (_ for _ in ()).throw(AssertionError("model loaded"))
        ),
        prompts={"RIM": ("rim",), "TOM": ("tom",)},
    )
    assert cached_votes == votes
    assert all(report.cache_hits == 1 and report.embedded == 0 for report in cached_reports)


@pytest.mark.skipif(
    os.environ.get("RUN_DUAL_CLAP_INTEGRATION") != "1",
    reason="downloads and runs both pinned CLAP checkpoints",
)
def test_real_workers_persist_both_pinned_model_embeddings(tmp_path) -> None:
    import soundfile as sf

    sample_rate = 48_000
    path = tmp_path / "tone.wav"
    sf.write(path, np.sin(2 * np.pi * 220 * np.arange(sample_rate) / sample_rate), sample_rate)
    cache = EmbeddingCache(tmp_path / "library.sqlite")
    votes, reports = generate_model_votes(MODEL_SPECS, [SampleRef("tone", path)], cache)

    assert [report.embedded for report in reports] == [1, 1]
    assert len(votes["tone"]) == 2
    for spec in MODEL_SPECS:
        vector = cache.get(EmbeddingKey("tone", spec.model_id, spec.revision, "three-10s-v1"))
        assert vector is not None
        assert vector.shape == (spec.embedding_dimensions,)

    started = time.perf_counter()
    cached_votes, cached_reports = generate_model_votes(
        MODEL_SPECS, [SampleRef("tone", path)], cache,
    )
    assert time.perf_counter() - started < 10.0
    assert cached_votes == votes
    assert [report.cache_hits for report in cached_reports] == [1, 1]
    assert [report.embedded for report in cached_reports] == [0, 0]
