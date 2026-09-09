"""SQLite cache for sample audio feature extraction."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
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
    def __init__(self, path: Path, *, extractor_version: str = 'acoustic-v1'):
        self.path = path
        self.extractor_version = extractor_version
        self._ensure_schema()

    def get_or_none(self, path: Path, size: int, mtime: float, *, content_hash: str | None = None) -> FeatureRecord | None:
        with self._connect() as conn:
            if content_hash is not None:
                identity = conn.execute('select sha256 from feature_content where path=?', (path.as_posix(),)).fetchone()
                if identity is None or identity[0] != content_hash:
                    return None
            row = conn.execute(
                """select features.* from features join feature_versions using(path)
                   where path = ? and size = ? and mtime = ? and extractor_version = ?""",
                (path.as_posix(), size, mtime, self.extractor_version),
            ).fetchone()
        if row is None or row["error"]:
            return None
        return self._record_from_row(row)

    def upsert(self, record: FeatureRecord, *, content_hash: str = '') -> None:
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
            conn.execute('insert or replace into feature_versions(path,extractor_version) values(?,?)',
                         (record.path.as_posix(), self.extractor_version))
            conn.execute('insert or replace into feature_content(path,sha256) values(?,?)',
                         (record.path.as_posix(), content_hash))

    @contextmanager
    def _connect(self):
        from .locking import database_lock, library_lock
        state = next((p for p in self.path.resolve().parents if p.name == '.eidetic'), None)
        lock = library_lock(state.parent, purpose='feature cache') if state else database_lock(self.path)
        with lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path)
            conn.row_factory = sqlite3.Row
            try:
                with conn:
                    yield conn
            finally:
                conn.close()

    def _ensure_schema(self) -> None:
        feature_defs = ",\n                ".join(f"{column} REAL" for column in FEATURE_COLUMNS)
        with self._connect() as conn:
            existing = {row['name'] for row in conn.execute('pragma table_info(features)')}
            if existing and not existing >= {'path', 'size', 'mtime', 'error', *FEATURE_COLUMNS}:
                raise ValueError('unsupported legacy feature schema; preserve the cache and use a new path')
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
            conn.execute('''create table if not exists feature_versions (
                path text primary key, extractor_version text not null)''')
            conn.execute('''create table if not exists feature_content (
                path text primary key, sha256 text not null)''')

    @staticmethod
    def _value(record: FeatureRecord, column: str) -> object:
        value = getattr(record, column)
        return value.as_posix() if isinstance(value, Path) else value

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> FeatureRecord:
        values = {column: row[column] for column in ("size", "mtime", *FEATURE_COLUMNS, "error")}
        return FeatureRecord(path=Path(row["path"]), **values)
