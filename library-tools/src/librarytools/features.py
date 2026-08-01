"""Acoustic features keyed by content identity rather than by path.

The original feature cache (``sample-intelligence.sqlite``) is keyed by path, so it went
stale the moment the library was reorganised — its rows still name a layout that no longer
exists.  This module moves those measurements onto ``sample_id`` in the ``asset_features``
table, where they survive any future move, rename or restructure.

Nothing decodes twice if it can be avoided: ``shutil.move`` preserves size and mtime, so a
measurement taken before the reorganisation is still valid for the same bytes today.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from . import audiofeatures
from .featurecache import FEATURE_COLUMNS
from .inventory import LibraryDatabase

Payload = dict[str, float | None]


@dataclass(frozen=True)
class SyncResult:
    migrated: int = 0
    extracted: int = 0
    failed: int = 0
    skipped: int = 0

    @property
    def total(self) -> int:
        return self.migrated + self.extracted + self.failed + self.skipped


class LegacyFeatureIndex:
    """Lookup into the old path-keyed cache, keyed by things that survive a move.

    A move preserves ``(size, mtime)``, but that pair alone is not unique — a vendor pack
    unzipped in one go gives many same-size files an identical mtime.  610 such collisions
    cover 4,631 files here, so the pair is only trusted when every row sharing it agrees on
    the measurements.  Otherwise the basename must match too, and failing that the file is
    re-measured rather than given a neighbour's acoustics.
    """

    def __init__(self, cache_path: Path):
        self._by_triple: dict[tuple[int, float, str], Payload] = {}
        self._by_pair: dict[tuple[int, float], Payload | None] = {}
        if cache_path.is_file():
            self._load(cache_path)

    def _load(self, cache_path: Path) -> None:
        conn = sqlite3.connect(cache_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "select * from features where error is null or error = ''"
            ).fetchall()
        finally:
            conn.close()

        for row in rows:
            payload: Payload = {column: row[column] for column in FEATURE_COLUMNS}
            pair = (int(row["size"]), round(float(row["mtime"]), 3))
            name = str(row["path"]).rsplit("/", 1)[-1]
            self._by_triple[(*pair, name)] = payload
            if pair not in self._by_pair:
                self._by_pair[pair] = payload
            elif self._by_pair[pair] != payload:
                self._by_pair[pair] = None  # ambiguous: two files, different measurements

    def get(self, size: int, mtime_ns: int, name: str) -> Payload | None:
        pair = (size, round(mtime_ns / 1e9, 3))
        found = self._by_triple.get((*pair, name))
        if found is not None:
            return found
        return self._by_pair.get(pair)

    def __len__(self) -> int:
        return len(self._by_triple)


def _payload_from_record(record: object) -> Payload:
    return {column: getattr(record, column) for column in FEATURE_COLUMNS}


def load_payload(raw: str) -> Payload:
    return json.loads(raw)


def sync_features(
    root: Path,
    database: LibraryDatabase,
    locations: list[tuple[str, Path, int, int]],
    legacy_cache: Path | None = None,
    resume: bool = True,
) -> SyncResult:
    """Fill ``asset_features`` for every sample, migrating measurements where possible.

    ``locations`` is ``(sample_id, relative_path, size, mtime_ns)``.  Work is idempotent and
    resumable: samples already measured are skipped, so an interrupted run costs nothing.
    """
    index = LegacyFeatureIndex(legacy_cache) if legacy_cache else None
    done = database.feature_ids() if resume else set()

    migrated = extracted = failed = skipped = 0
    seen: set[str] = set()

    for sample_id, rel, size, mtime_ns in locations:
        if sample_id in seen:
            continue
        if sample_id in done:
            seen.add(sample_id)
            skipped += 1
            continue

        payload = index.get(size, mtime_ns, rel.name) if index else None
        if payload is not None:
            database.record_features(sample_id, json.dumps(payload))
            seen.add(sample_id)
            migrated += 1
            continue

        record = audiofeatures.extract(root / rel, cache_path=rel)
        if getattr(record, "error", None):
            database.record_features(sample_id, "{}", str(record.error))
            seen.add(sample_id)
            failed += 1
            continue

        database.record_features(sample_id, json.dumps(_payload_from_record(record)))
        seen.add(sample_id)
        extracted += 1

    return SyncResult(migrated=migrated, extracted=extracted, failed=failed, skipped=skipped)
