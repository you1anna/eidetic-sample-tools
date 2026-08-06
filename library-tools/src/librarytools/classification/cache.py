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
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                create table if not exists audio_embeddings (
                    sample_id text not null,
                    model_id text not null,
                    model_revision text not null,
                    excerpt_policy text not null,
                    dimensions integer not null check(dimensions > 0),
                    dtype text not null check(dtype = 'float16'),
                    embedding blob not null,
                    created_at text not null,
                    updated_at text not null,
                    primary key(sample_id, model_id, model_revision, excerpt_policy)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def get(self, key: EmbeddingKey) -> np.ndarray | None:
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
        if row["dtype"] != "float16" or len(payload) != dimensions * np.dtype(np.float16).itemsize:
            raise ClassificationError(
                f"corrupt cached embedding for {key.sample_id} using {key.model_id}"
            )
        return np.frombuffer(payload, dtype=np.float16).astype(np.float32)

    def put(self, key: EmbeddingKey, embedding: np.ndarray) -> None:
        vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
        if vector.size == 0 or not np.all(np.isfinite(vector)):
            raise ClassificationError("embedding must be a non-empty finite vector")
        compact = vector.astype(np.float16)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
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
                (
                    key.sample_id,
                    key.model_id,
                    key.model_revision,
                    key.excerpt_policy,
                    int(compact.size),
                    compact.tobytes(),
                    now,
                    now,
                ),
            )
