"""Revision-keyed, float16 SQLite storage for reusable audio embeddings."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .domain import ClassificationError


@dataclass(frozen=True)
class EmbeddingKey:
    sample_id: str
    model_id: str
    model_revision: str
    excerpt_policy: str

    def __post_init__(self) -> None:
        if not all((self.sample_id, self.model_id, self.model_revision, self.excerpt_policy)):
            raise ClassificationError("embedding cache keys must not be empty")


class EmbeddingCache:
    """Store model embeddings in the existing library database without replacing its schema."""

    def __init__(self, path: Path):
        from ..inventory import LibraryDatabase
        self.path = Path(path)
        self.database = LibraryDatabase(self.path)

    def _connect(self):
        return self.database._connect()

    def get(self, key: EmbeddingKey, *, expected_dimensions: int | None = None) -> np.ndarray | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                select dimensions,dtype,embedding from audio_embeddings
                where sample_id=? and model_id=? and model_revision=? and excerpt_policy=?
                """,
                (key.sample_id, key.model_id, key.model_revision, key.excerpt_policy),
            ).fetchone()
        if row is None:
            return None
        dimensions = int(row["dimensions"])
        payload = bytes(row["embedding"])
        if (
            row["dtype"] != "float16"
            or len(payload) != dimensions * np.dtype(np.float16).itemsize
            or (expected_dimensions is not None and dimensions != expected_dimensions)
        ):
            raise ClassificationError(
                f"corrupt cached embedding for {key.sample_id} using {key.model_id}"
            )
        vector = np.frombuffer(payload, dtype=np.float16).astype(np.float32)
        if not np.all(np.isfinite(vector)) or not float(np.linalg.norm(vector)):
            raise ClassificationError(
                f"corrupt cached embedding for {key.sample_id} using {key.model_id}"
            )
        return vector

    def put(self, key: EmbeddingKey, embedding: np.ndarray) -> None:
        self.put_many([(key, embedding)])

    def put_many(self, items: list[tuple[EmbeddingKey, np.ndarray]]) -> None:
        """Persist one completed inference batch in a single transaction."""
        prepared: list[tuple[EmbeddingKey, np.ndarray]] = []
        for key, embedding in items:
            vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
            if vector.size == 0 or not np.all(np.isfinite(vector)):
                raise ClassificationError("embedding must be a non-empty finite vector")
            prepared.append((key, vector.astype(np.float16)))
        if not prepared:
            return
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.executemany(
                """
                insert into audio_embeddings
                (sample_id,model_id,model_revision,excerpt_policy,dimensions,dtype,embedding,
                 created_at,updated_at)
                values(?,?,?,?,?,'float16',?,?,?)
                on conflict(sample_id,model_id,model_revision,excerpt_policy) do update set
                  dimensions=excluded.dimensions,
                  dtype=excluded.dtype,
                  embedding=excluded.embedding,
                  updated_at=excluded.updated_at
                """,
                [
                    (
                        key.sample_id,
                        key.model_id,
                        key.model_revision,
                        key.excerpt_policy,
                        int(compact.size),
                        compact.tobytes(),
                        now,
                        now,
                    )
                    for key, compact in prepared
                ],
            )

    def get_prompt_set(
        self,
        model_id: str,
        model_revision: str,
        prompt_policy: str,
        *,
        expected_dimensions: int | None = None,
    ) -> dict[str, np.ndarray] | None:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select label,dimensions,dtype,embedding from prompt_embeddings
                where model_id=? and model_revision=? and prompt_policy=? order by label
                """,
                (model_id, model_revision, prompt_policy),
            ).fetchall()
        if not rows:
            return None
        restored: dict[str, np.ndarray] = {}
        for row in rows:
            dimensions = int(row["dimensions"])
            payload = bytes(row["embedding"])
            if (
                row["dtype"] != "float16"
                or len(payload) != dimensions * 2
                or (expected_dimensions is not None and dimensions != expected_dimensions)
            ):
                raise ClassificationError(
                    f"corrupt cached prompt embedding for {model_id}:{row['label']}"
                )
            vector = np.frombuffer(payload, dtype=np.float16).astype(np.float32)
            if not np.all(np.isfinite(vector)) or not float(np.linalg.norm(vector)):
                raise ClassificationError(
                    f"corrupt cached prompt embedding for {model_id}:{row['label']}"
                )
            restored[str(row["label"])] = vector
        return restored

    def put_prompt_set(
        self,
        model_id: str,
        model_revision: str,
        prompt_policy: str,
        embeddings: dict[str, np.ndarray],
    ) -> None:
        if not model_id or not model_revision or not prompt_policy or not embeddings:
            raise ClassificationError("prompt embedding identity and values must not be empty")
        prepared: list[tuple[str, np.ndarray]] = []
        for label, embedding in sorted(embeddings.items()):
            vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
            if not label or vector.size == 0 or not np.all(np.isfinite(vector)):
                raise ClassificationError("prompt embeddings must be named, finite vectors")
            prepared.append((label, vector.astype(np.float16)))
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.executemany(
                """
                insert into prompt_embeddings
                (model_id,model_revision,prompt_policy,label,dimensions,dtype,embedding,
                 created_at,updated_at)
                values(?,?,?,?,?,'float16',?,?,?)
                on conflict(model_id,model_revision,prompt_policy,label) do update set
                  dimensions=excluded.dimensions,
                  dtype=excluded.dtype,
                  embedding=excluded.embedding,
                  updated_at=excluded.updated_at
                """,
                [
                    (
                        model_id,
                        model_revision,
                        prompt_policy,
                        label,
                        int(vector.size),
                        vector.tobytes(),
                        now,
                        now,
                    )
                    for label, vector in prepared
                ],
            )
