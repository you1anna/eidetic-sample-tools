"""SQLite cache for sample audio feature extraction."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


FEATURE_COLUMNS: tuple[str, ...] = (
    "duration_s",
    "peak",
    "rms",
    "crest",
    "attack_ms",
    "tail_ms",
    "head_silence_ms",
    "tail_silence_ms",
    "centroid_hz",
    "flatness",
    "sub_ratio",
    "low_ratio",
    "mid_ratio",
    "high_ratio",
    "onset_density",
    "zcr",
)


@dataclass(frozen=True)
class FeatureRecord:
    path: Path
    size: int
    mtime: float
    duration_s: float | None = None
    peak: float | None = None
    rms: float | None = None
    crest: float | None = None
    attack_ms: float | None = None
    tail_ms: float | None = None
    head_silence_ms: float | None = None
    tail_silence_ms: float | None = None
    centroid_hz: float | None = None
    flatness: float | None = None
    sub_ratio: float | None = None
    low_ratio: float | None = None
    mid_ratio: float | None = None
    high_ratio: float | None = None
    onset_density: float | None = None
    zcr: float | None = None
    error: str | None = None


class FeatureCache:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def get_or_none(self, path: Path, size: int, mtime: float) -> FeatureRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "select * from features where path = ? and size = ? and mtime = ?",
                (path.as_posix(), size, mtime),
            ).fetchone()
        if row is None or row["error"]:
            return None
        return self._record_from_row(row)

    def upsert(self, record: FeatureRecord) -> None:
        columns = ("path", "size", "mtime", *FEATURE_COLUMNS, "error")
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(f"{column} = excluded.{column}" for column in columns[1:])
        values = [self._value(record, column) for column in columns]
        with self._connect() as conn:
            conn.execute(
                f"""
                insert into features ({", ".join(columns)})
                values ({placeholders})
                on conflict(path) do update set {updates}
                """,
                values,
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        feature_defs = ",\n                ".join(f"{column} REAL" for column in FEATURE_COLUMNS)
        with self._connect() as conn:
            conn.execute(
                f"""
                create table if not exists features (
                    path TEXT PRIMARY KEY,
                    size INTEGER NOT NULL,
                    mtime REAL NOT NULL,
                    {feature_defs},
                    error TEXT
                )
                """
            )

    @staticmethod
    def _value(record: FeatureRecord, column: str) -> object:
        value = getattr(record, column)
        return value.as_posix() if isinstance(value, Path) else value

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> FeatureRecord:
        values = {column: row[column] for column in ("size", "mtime", *FEATURE_COLUMNS, "error")}
        return FeatureRecord(path=Path(row["path"]), **values)
