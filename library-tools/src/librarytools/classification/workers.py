"""Cache-first, sequential model execution with short-lived production workers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from .cache import EmbeddingCache, EmbeddingKey
from .domain import ClassificationError
from .models import ClapEmbeddingRuntime, EmbeddingRuntime, ModelSpec


EXCERPT_POLICY = "three-10s-v1"


@dataclass(frozen=True)
class SampleRef:
    sample_id: str
    path: Path


@dataclass(frozen=True)
class WorkerReport:
    model_id: str
    model_revision: str
    cache_hits: int
    embedded: int
    batch_sizes: tuple[int, ...]
    excerpt_policy: str = EXCERPT_POLICY


class EmbeddingWorker:
    """Run inline for injected test runtimes, otherwise in a short-lived subprocess."""

    def __init__(
        self,
        runtime_factory: Callable[[ModelSpec], EmbeddingRuntime] | None = None,
    ) -> None:
        self._runtime_factory = runtime_factory

    def run(
        self,
        spec: ModelSpec,
        samples: Sequence[SampleRef],
        cache: EmbeddingCache,
        *,
        batch_size: int = 8,
        threads: int = 8,
    ) -> WorkerReport:
        if not 1 <= batch_size <= 8:
            raise ClassificationError("model batch size must be between 1 and 8")
        if threads <= 0:
            raise ClassificationError("model worker thread count must be positive")
        if self._runtime_factory is not None:
            return self._run_inline(spec, samples, cache, batch_size=batch_size, threads=threads)
        return self._run_subprocess(spec, samples, cache, batch_size=batch_size, threads=threads)

    def _run_inline(
        self,
        spec: ModelSpec,
        samples: Sequence[SampleRef],
        cache: EmbeddingCache,
        *,
        batch_size: int,
        threads: int,
    ) -> WorkerReport:
        misses: list[SampleRef] = []
        cache_hits = 0
        for sample in samples:
            cached = cache.get(_key(sample, spec))
            if cached is None:
                misses.append(sample)
            elif cached.size != spec.embedding_dimensions:
                raise ClassificationError(
                    f"cached {spec.model_id} embedding has {cached.size} dimensions; "
                    f"expected {spec.embedding_dimensions}"
                )
            else:
                cache_hits += 1

        if not misses:
            return WorkerReport(spec.model_id, spec.revision, cache_hits, 0, ())

        os.environ["OMP_NUM_THREADS"] = str(threads)
        os.environ["MKL_NUM_THREADS"] = str(threads)
        runtime = self._runtime_factory(spec)  # type: ignore[misc]
        batch_sizes: list[int] = []
        embedded = 0
        for offset in range(0, len(misses), batch_size):
            batch = misses[offset:offset + batch_size]
            vectors = runtime.embed([sample.path for sample in batch])
            if len(vectors) != len(batch):
                raise ClassificationError(
                    f"{spec.model_id} returned {len(vectors)} vectors for {len(batch)} samples"
                )
            items: list[tuple[EmbeddingKey, np.ndarray]] = []
            for sample, raw_vector in zip(batch, vectors, strict=True):
                vector = np.asarray(raw_vector, dtype=np.float32).reshape(-1)
                if vector.size != spec.embedding_dimensions:
                    raise ClassificationError(
                        f"{spec.model_id} returned {vector.size} dimensions; "
                        f"expected {spec.embedding_dimensions}"
                    )
                items.append((_key(sample, spec), vector))
            cache.put_many(items)
            batch_sizes.append(len(batch))
            embedded += len(batch)
        return WorkerReport(
            spec.model_id,
            spec.revision,
            cache_hits,
            embedded,
            tuple(batch_sizes),
        )

    def _run_subprocess(
        self,
        spec: ModelSpec,
        samples: Sequence[SampleRef],
        cache: EmbeddingCache,
        *,
        batch_size: int,
        threads: int,
    ) -> WorkerReport:
        job = {
            "spec": asdict(spec),
            "samples": [
                {"sample_id": sample.sample_id, "path": str(sample.path)} for sample in samples
            ],
            "cache_path": str(cache.path),
            "batch_size": batch_size,
            "threads": threads,
        }
        with tempfile.TemporaryDirectory(prefix="sample-classifier-worker-") as temporary:
            directory = Path(temporary)
            job_path = directory / "job.json"
            report_path = directory / "report.json"
            job_path.write_text(json.dumps(job), encoding="utf-8")
            environment = os.environ.copy()
            environment.update({"OMP_NUM_THREADS": str(threads), "MKL_NUM_THREADS": str(threads)})
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "librarytools.classification.worker_entry",
                    str(job_path),
                    str(report_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            if completed.returncode:
                detail = completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else ""
                raise ClassificationError(
                    f"model worker failed for {spec.model_id}: {detail or 'unknown error'}"
                )
            if completed.stdout.strip():
                raise ClassificationError("model worker emitted unexpected standard output")
            try:
                raw = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ClassificationError(f"model worker returned an invalid report: {exc}") from exc
        return WorkerReport(
            model_id=str(raw["model_id"]),
            model_revision=str(raw["model_revision"]),
            cache_hits=int(raw["cache_hits"]),
            embedded=int(raw["embedded"]),
            batch_sizes=tuple(int(value) for value in raw["batch_sizes"]),
            excerpt_policy=str(raw["excerpt_policy"]),
        )


def run_models_sequentially(
    specs: Sequence[ModelSpec],
    samples: Sequence[SampleRef],
    cache: EmbeddingCache,
    *,
    worker_factory: Callable[[], object] = EmbeddingWorker,
    batch_size: int = 8,
    threads: int = 8,
) -> list[object]:
    """Complete and release one worker before constructing the next."""
    reports: list[object] = []
    for spec in specs:
        worker = worker_factory()
        reports.append(
            worker.run(spec, samples, cache, batch_size=batch_size, threads=threads)  # type: ignore[attr-defined]
        )
        del worker
    return reports


def _key(sample: SampleRef, spec: ModelSpec) -> EmbeddingKey:
    return EmbeddingKey(sample.sample_id, spec.model_id, spec.revision, EXCERPT_POLICY)


def run_real_worker_job(job_path: Path, report_path: Path) -> None:
    """Worker-process entry: persist vectors to SQLite and write metadata only."""
    raw = json.loads(job_path.read_text(encoding="utf-8"))
    spec = ModelSpec(**raw["spec"])
    samples = [SampleRef(str(item["sample_id"]), Path(item["path"])) for item in raw["samples"]]
    report = EmbeddingWorker(runtime_factory=ClapEmbeddingRuntime).run(
        spec,
        samples,
        EmbeddingCache(Path(raw["cache_path"])),
        batch_size=int(raw["batch_size"]),
        threads=int(raw["threads"]),
    )
    report_path.write_text(json.dumps(asdict(report), sort_keys=True), encoding="utf-8")
