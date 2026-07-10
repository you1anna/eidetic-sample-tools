"""Stable, path-independent sample inventory.

The inventory is deliberately separate from the existing acoustic feature
cache.  Content identity is SHA-256; paths are replaceable locations.
"""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import config


SCHEMA_VERSION = 1
SKIP_TOP = frozenset({"_EXPORT", "_TO-DELETE", "_QUARANTINE"})


@dataclass(frozen=True)
class InventoryLocation:
    path: Path
    sample_id: str
    zone: str
    source_name: str
    size: int
    mtime_ns: int
    scan_id: str
    exists: bool


@dataclass(frozen=True)
class ScanResult:
    scan_id: str
    file_count: int
    completed: bool


class LibraryDatabase:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys = on")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                create table if not exists scans (
                    scan_id text primary key,
                    root text not null,
                    started_at text not null,
                    completed_at text,
                    status text not null check(status in ('incomplete','complete')),
                    file_count integer not null default 0
                );
                create table if not exists assets (
                    sample_id text primary key,
                    size integer not null,
                    extension text not null,
                    first_seen_at text not null
                );
                create table if not exists hash_cache (
                    device integer not null,
                    inode integer not null,
                    size integer not null,
                    mtime_ns integer not null,
                    sample_id text not null,
                    primary key(device, inode, size, mtime_ns)
                );
                create table if not exists locations (
                    path text primary key,
                    sample_id text not null references assets(sample_id),
                    zone text not null,
                    source_name text not null,
                    size integer not null,
                    mtime_ns integer not null,
                    scan_id text not null references scans(scan_id),
                    exists_now integer not null
                );
                create table if not exists asset_features (
                    sample_id text primary key references assets(sample_id),
                    payload_json text not null default '{}',
                    audio_error text not null default ''
                );
                create table if not exists annotations (
                    sample_id text primary key references assets(sample_id),
                    proposed_role text not null default '',
                    trusted_role text not null default '',
                    sample_type text not null default '',
                    bpm text not null default '',
                    musical_key text not null default ''
                );
                create table if not exists tags (
                    sample_id text not null references assets(sample_id),
                    tag_group text not null,
                    tag text not null,
                    primary key(sample_id, tag_group, tag)
                );
                create table if not exists reviews (
                    sample_id text not null references assets(sample_id),
                    packet_id text not null,
                    decision text not null,
                    true_role text not null default '',
                    descriptor text not null default '',
                    notes text not null default '',
                    reviewed_at text not null,
                    primary key(sample_id, packet_id)
                );
                create table if not exists promotions (
                    sample_id text not null references assets(sample_id),
                    curated_path text not null,
                    source_path text not null,
                    promoted_at text not null,
                    run_id text not null default '',
                    primary key(sample_id, curated_path)
                );
                """
            )
            conn.execute(f"pragma user_version = {SCHEMA_VERSION}")

    def begin_scan(self, root: Path) -> str:
        scan_id = uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute(
                "insert into scans(scan_id,root,started_at,status) values(?,?,?,'incomplete')",
                (scan_id, str(root), _now()),
            )
        return scan_id

    def finish_scan(self, scan_id: str, file_count: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "update locations set exists_now=0 where scan_id<>?",
                (scan_id,),
            )
            conn.execute(
                "update scans set status='complete',completed_at=?,file_count=? where scan_id=?",
                (_now(), file_count, scan_id),
            )

    def scan_status(self, scan_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("select status from scans where scan_id=?", (scan_id,)).fetchone()
        return str(row["status"]) if row else None

    def latest_complete_scan(self) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "select scan_id from scans where status='complete' order by completed_at desc limit 1"
            ).fetchone()
        return str(row["scan_id"]) if row else None

    def cached_hash(self, stat: object) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "select sample_id from hash_cache where device=? and inode=? and size=? and mtime_ns=?",
                (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns),
            ).fetchone()
        return str(row["sample_id"]) if row else None

    def record_file(self, root: Path, path: Path, scan_id: str) -> InventoryLocation:
        stat = path.stat()
        sample_id = self.cached_hash(stat) or sha256_file(path)
        rel = path.relative_to(root)
        zone, source_name = _zone_and_source(rel)
        with self._connect() as conn:
            conn.execute(
                "insert or ignore into assets(sample_id,size,extension,first_seen_at) values(?,?,?,?)",
                (sample_id, stat.st_size, path.suffix.lower(), _now()),
            )
            conn.execute(
                "insert or replace into hash_cache(device,inode,size,mtime_ns,sample_id) values(?,?,?,?,?)",
                (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, sample_id),
            )
            conn.execute(
                """
                insert into locations(path,sample_id,zone,source_name,size,mtime_ns,scan_id,exists_now)
                values(?,?,?,?,?,?,?,1)
                on conflict(path) do update set
                  sample_id=excluded.sample_id, zone=excluded.zone,
                  source_name=excluded.source_name, size=excluded.size,
                  mtime_ns=excluded.mtime_ns, scan_id=excluded.scan_id, exists_now=1
                """,
                (rel.as_posix(), sample_id, zone, source_name, stat.st_size, stat.st_mtime_ns, scan_id),
            )
        return InventoryLocation(rel, sample_id, zone, source_name, stat.st_size, stat.st_mtime_ns, scan_id, True)

    def current_locations(self) -> list[InventoryLocation]:
        with self._connect() as conn:
            rows = conn.execute("select * from locations where exists_now=1 order by path").fetchall()
        return [_location(row) for row in rows]

    def location(self, path: Path) -> InventoryLocation:
        with self._connect() as conn:
            row = conn.execute("select * from locations where path=?", (path.as_posix(),)).fetchone()
        if row is None:
            raise KeyError(path)
        return _location(row)

    def assets(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("select sample_id from assets order by sample_id").fetchall()
        return [str(row["sample_id"]) for row in rows]

    def record_review(
        self, sample_id: str, packet_id: str, decision: str, true_role: str,
        descriptor: str, notes: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                insert or replace into reviews
                (sample_id,packet_id,decision,true_role,descriptor,notes,reviewed_at)
                values(?,?,?,?,?,?,?)
                """,
                (sample_id, packet_id, decision, true_role, descriptor, notes, _now()),
            )

    def record_promotion(
        self, sample_id: str, curated_path: Path, source_path: Path, run_id: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                insert into promotions
                (sample_id,curated_path,source_path,promoted_at,run_id) values(?,?,?,?,?)
                """,
                (sample_id, curated_path.as_posix(), source_path.as_posix(), _now(), run_id),
            )

    def promotions(self) -> list[dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute("select * from promotions order by promoted_at,curated_path").fetchall()
        return [dict(row) for row in rows]

    def record_tags(self, sample_id: str, tags: list[tuple[str, str]]) -> None:
        with self._connect() as conn:
            for group, tag in tags:
                conn.execute(
                    "insert or ignore into tags(sample_id,tag_group,tag) values(?,?,?)",
                    (sample_id, group, tag),
                )

    def tags_for(self, sample_id: str) -> list[tuple[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "select tag_group,tag from tags where sample_id=? order by tag_group,tag",
                (sample_id,),
            ).fetchall()
        return [(str(row["tag_group"]), str(row["tag"])) for row in rows]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _zone_and_source(rel: Path) -> tuple[str, str]:
    if not rel.parts:
        return "ROOT", ""
    zone = rel.parts[0] if rel.parts[0] in {"PACKS", "CATALOGUE", "CURATED"} else "ROOT"
    if zone in {"PACKS", "CATALOGUE", "CURATED"} and len(rel.parts) > 1:
        return zone, rel.parts[1]
    return zone, rel.parts[0]


def _location(row: sqlite3.Row) -> InventoryLocation:
    return InventoryLocation(
        path=Path(row["path"]), sample_id=str(row["sample_id"]), zone=str(row["zone"]),
        source_name=str(row["source_name"]), size=int(row["size"]),
        mtime_ns=int(row["mtime_ns"]), scan_id=str(row["scan_id"]),
        exists=bool(row["exists_now"]),
    )


def _iter_audio(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] in SKIP_TOP:
            continue
        if any(part.startswith(".") or part == "__MACOSX" for part in rel.parts):
            continue
        if path.suffix.lower() in config.SOURCE_EXTS:
            found.append(path)
    return sorted(found)


def scan_library(root: Path, database: LibraryDatabase) -> ScanResult:
    scan_id = database.begin_scan(root)
    count = 0
    for path in _iter_audio(root):
        database.record_file(root, path, scan_id)
        count += 1
    database.finish_scan(scan_id, count)
    return ScanResult(scan_id, count, True)
