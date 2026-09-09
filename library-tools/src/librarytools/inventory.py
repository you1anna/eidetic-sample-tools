"""Stable, path-independent sample inventory.

The inventory is deliberately separate from the existing acoustic feature
cache.  Content identity is SHA-256; paths are replaceable locations.
"""

from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import config


from .schema import SCHEMA_VERSION, MigrationRequired, SchemaError, initialize_database, inspect_database, readonly_database
from .locking import library_lock, database_lock
from .state import library_identity
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
    def __init__(self, path: Path, *, readonly: bool = False):
        self.path = Path(path)
        self.readonly = readonly
        self._root: Path | None = None
        self._bound_identity: str | None = None
        if self.path.exists():
            info = inspect_database(self.path)
            if info['detected_version'] != SCHEMA_VERSION or info['declared_version'] != SCHEMA_VERSION:
                raise MigrationRequired(f"library database needs explicit migration: sample-library migrate --library-db {self.path}")
        elif readonly:
            raise SchemaError(f'library database not found: {self.path}')
        else:
            # Database constructors remain compatible for new explicit paths.
            with database_lock(self.path, purpose='initialise database'):
                if not self.path.exists():
                    initialize_database(self.path)
                else:
                    info = inspect_database(self.path)
                    if info['detected_version'] != SCHEMA_VERSION:
                        raise MigrationRequired('library database requires migration')
        with readonly_database(self.path) as conn:
            identity = conn.execute('select library_id,root_hint from library_identity where singleton=1').fetchone()
        if identity is not None:
            self._bound_identity = identity['library_id']
            candidate = self.path.resolve().parent.parent if self.path.parent.name == '.eidetic' else Path(identity['root_hint'])
            if candidate.is_dir() and library_identity(candidate) == identity['library_id']:
                self._root = candidate

    @contextmanager
    def _connect(self):
        if self.readonly:
            with readonly_database(self.path) as conn:
                if conn.execute('pragma user_version').fetchone()[0] != SCHEMA_VERSION:
                    raise SchemaError('database schema changed; reopen with the compatible release')
                yield conn
            return
        if self._bound_identity is not None:
            if self._root is None:
                raise ValueError('bound library root is unavailable; attach it and bind_root before writing')
            if library_identity(self._root) != self._bound_identity:
                raise ValueError('library identity changed since this database was opened')
        lock = library_lock(self._root) if self._root is not None else database_lock(self.path)
        with lock:
            conn = sqlite3.connect(self.path.resolve().as_uri() + '?mode=rw', uri=True)
            conn.row_factory = sqlite3.Row
            conn.execute('pragma foreign_keys=on')
            try:
                if conn.execute('pragma user_version').fetchone()[0] != SCHEMA_VERSION:
                    raise SchemaError('database schema changed; reopen with the compatible release')
                identity = conn.execute('select library_id from library_identity where singleton=1').fetchone()
                if identity is not None and identity[0] != self._bound_identity:
                    raise ValueError('database library identity changed since it was opened')
                with conn:
                    yield conn
            finally:
                conn.close()

    def bind_root(self, root: Path, create: bool = True) -> str:
        root = Path(root).resolve()
        marker = library_identity(root, create=False)
        with readonly_database(self.path) as conn:
            row = conn.execute('select library_id,root_hint from library_identity where singleton=1').fetchone()
        if row is not None and marker != row['library_id']:
            raise ValueError('library identity does not match this database; attach the original library or reconcile state')
        if self.readonly or not create:
            if row is None or marker is None:
                raise ValueError('library identity is missing; initialise or migrate the library explicitly')
            self._root = root
            return marker
        if marker is None:
            if not create:
                raise ValueError('library identity is missing; initialise or migrate the library explicitly')
            marker = library_identity(root, create=True)
        self._root = root
        with library_lock(root, purpose='bind library', allow_recovery=True):
            with self._connect() as conn:
                conn.execute('insert into library_identity(singleton,library_id,root_hint) values(1,?,?) '
                             'on conflict(singleton) do update set root_hint=excluded.root_hint',
                             (marker, str(root)))
        self._root = root
        self._bound_identity = marker
        return marker

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
            scan = conn.execute('select * from scans where scan_id=?', (scan_id,)).fetchone()
            if scan is None or scan['status'] != 'incomplete':
                raise ValueError('only an incomplete scan can be published')
            root = Path(scan['root'])
            if not root.is_dir():
                raise ValueError(f'library root became unavailable: {root}')
            observations = conn.execute('select * from scan_observations where scan_id=?', (scan_id,)).fetchall()
            if len(observations) != file_count:
                raise ValueError('scan observation count does not match completed traversal')
            for row in observations:
                stat = (root / row['path']).stat()
                if (stat.st_size, stat.st_mtime_ns) != (row['size'], row['mtime_ns']):
                    raise ValueError(f"file changed before scan publication: {row['path']}")
            # BEGIN before first update keeps old locations visible until all are ready.
            conn.execute('begin immediate')
            conn.execute('update locations set exists_now=0')
            for row in observations:
                conn.execute('insert or ignore into assets(sample_id,size,extension,first_seen_at) values(?,?,?,?)',
                             (row['sample_id'], row['size'], row['extension'], _now()))
                self._publish_location(conn, row)
            # Preserve the discrepancy after inventory retirement; a fresh scan
            # must never turn a missing approved copy into a clean history.
            observed = {row['path']: row['sample_id'] for row in observations}
            for promotion in conn.execute("select * from promotions where status<>'withdrawn'").fetchall():
                status = 'active' if observed.get(promotion['curated_path']) == promotion['sample_id'] else 'missing'
                if promotion['status'] != status:
                    conn.execute('update promotions set status=? where sample_id=? and curated_path=?',
                                 (status, promotion['sample_id'], promotion['curated_path']))
                    conn.execute('insert into promotion_events(sample_id,curated_path,run_id,status,recorded_at) values(?,?,?,?,?)',
                                 (promotion['sample_id'], promotion['curated_path'], promotion['run_id'], status, _now()))
            conn.execute("update scans set status='complete',completed_at=?,file_count=? where scan_id=?",
                         (_now(), file_count, scan_id))
            conn.execute('delete from scan_observations where scan_id=?', (scan_id,))

    @staticmethod
    def _publish_location(conn, row):
        conn.execute("""insert into locations(path,sample_id,zone,source_name,size,mtime_ns,scan_id,exists_now)
                        values(?,?,?,?,?,?,?,1) on conflict(path) do update set
                        sample_id=excluded.sample_id,zone=excluded.zone,source_name=excluded.source_name,
                        size=excluded.size,mtime_ns=excluded.mtime_ns,scan_id=excluded.scan_id,exists_now=1""",
                     tuple(row[key] for key in ('path','sample_id','zone','source_name','size','mtime_ns','scan_id')))

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
        root = Path(root).resolve()
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f'audio path escapes the library or is a symlink: {path}')
        stat = path.stat()
        # Device/inode/mtime are not content identity across Macs. Verify actual bytes.
        sample_id = sha256_file(path)
        after = path.stat()
        if (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_ino):
            raise ValueError(f'audio changed while hashing: {path}')
        rel = path.resolve().relative_to(root)
        zone, source_name = _zone_and_source(rel)
        row = dict(path=rel.as_posix(), sample_id=sample_id, zone=zone, source_name=source_name,
                   size=stat.st_size, mtime_ns=stat.st_mtime_ns, scan_id=scan_id)
        with self._connect() as conn:
            scan = conn.execute('select root,status from scans where scan_id=?', (scan_id,)).fetchone()
            if scan is None:
                raise ValueError(f'unknown scan: {scan_id}')
            if scan['status'] == 'incomplete':
                if Path(scan['root']).resolve() != root:
                    raise ValueError('scan root does not match observation root')
                conn.execute('insert or replace into scan_observations '
                             '(path,sample_id,zone,source_name,size,mtime_ns,scan_id,extension) values(?,?,?,?,?,?,?,?)',
                             (*row.values(), path.suffix.lower()))
            else:
                # Approved promotions add one location using an existing completed scan.
                conn.execute('insert or ignore into assets(sample_id,size,extension,first_seen_at) values(?,?,?,?)',
                             (sample_id, stat.st_size, path.suffix.lower(), _now()))
                self._publish_location(conn, row)
        return InventoryLocation(rel, sample_id, zone, source_name, stat.st_size, stat.st_mtime_ns, scan_id, True)

    def current_locations(self) -> list[InventoryLocation]:
        with self._connect() as conn:
            rows = conn.execute("select * from locations where exists_now=1 order by path").fetchall()
        return [_location(row) for row in rows]

    def mark_missing(self, path: Path) -> None:
        """Retire a known location after a successful move out of the library."""
        with self._connect() as conn:
            conn.execute("update locations set exists_now=0 where path=?", (path.as_posix(),))

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
            conn.execute('insert into review_events(sample_id,packet_id,decision,true_role,descriptor,notes,reviewed_at) values(?,?,?,?,?,?,?)',
                         (sample_id, packet_id, decision, true_role, descriptor, notes, _now()))

    def favourite_descriptions(self) -> dict[tuple[str, str], str]:
        """Latest approved description for each sample and canonical role."""
        with self._connect() as conn:
            rows = conn.execute(
                """select sample_id,true_role,descriptor from reviews
                   where decision='favourite' order by reviewed_at,rowid"""
            ).fetchall()
        return {(row["sample_id"], row["true_role"]): row["descriptor"] for row in rows}

    def record_promotion(
        self, sample_id: str, curated_path: Path, source_path: Path, run_id: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                insert into promotions
                (sample_id,curated_path,source_path,promoted_at,run_id) values(?,?,?,?,?)
                on conflict(sample_id,curated_path) do update set source_path=excluded.source_path,
                promoted_at=excluded.promoted_at,run_id=excluded.run_id,status='active',withdrawn_at=''
                """,
                (sample_id, curated_path.as_posix(), source_path.as_posix(), _now(), run_id),
            )
            conn.execute('insert into promotion_events(sample_id,curated_path,run_id,status,recorded_at) values(?,?,?,?,?)',
                         (sample_id, curated_path.as_posix(), run_id, 'active', _now()))

    def promotions(self, *, include_inactive: bool = True) -> list[dict[str, object]]:
        with self._connect() as conn:
            where = "" if include_inactive else " where status='active'"
            rows = conn.execute("select * from promotions" + where + " order by promoted_at,curated_path").fetchall()
        return [dict(row) for row in rows]

    def set_promotion_status(self, sample_id: str, curated_path: Path, status: str) -> None:
        if status not in {'active', 'withdrawn', 'missing'}:
            raise ValueError(f'invalid promotion status: {status}')
        with self._connect() as conn:
            row = conn.execute('select run_id,status from promotions where sample_id=? and curated_path=?',
                               (sample_id, curated_path.as_posix())).fetchone()
            if row is None:
                raise ValueError('promotion not recorded')
            if row['status'] == status:
                return
            conn.execute('update promotions set status=?,withdrawn_at=? where sample_id=? and curated_path=?',
                         (status, _now() if status == 'withdrawn' else '', sample_id, curated_path.as_posix()))
            conn.execute('insert into promotion_events(sample_id,curated_path,run_id,status,recorded_at) values(?,?,?,?,?)',
                         (sample_id, curated_path.as_posix(), row['run_id'], status, _now()))

    def mark_promotion_withdrawn(self, sample_id: str, curated_path: Path) -> None:
        self.set_promotion_status(sample_id, curated_path, 'withdrawn')

    def record_origin(
        self, sample_id: str, origin: str, confidence: str, method: str, token: str = "",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                insert or replace into origins
                (sample_id,origin,confidence,method,token) values(?,?,?,?,?)
                """,
                (sample_id, origin, confidence, method, token),
            )

    def origins(self) -> dict[str, tuple[str, str, str]]:
        """Return ``sample_id -> (origin, confidence, method)`` for every resolved asset."""
        with self._connect() as conn:
            rows = conn.execute("select sample_id,origin,confidence,method from origins").fetchall()
        return {
            str(row["sample_id"]): (str(row["origin"]), str(row["confidence"]), str(row["method"]))
            for row in rows
        }

    def record_features(self, sample_id: str, payload_json: str, audio_error: str = "", *,
                        extractor_version: str = 'acoustic-v1', provenance: str = 'measured') -> None:
        with self._connect() as conn:
            conn.execute(
                """
                insert or replace into asset_features
                (sample_id,payload_json,audio_error,extractor_version,provenance,updated_at) values(?,?,?,?,?,?)
                """,
                (sample_id, payload_json, audio_error, extractor_version, provenance, _now()),
            )

    def features(self, *, extractor_version: str = 'acoustic-v1') -> dict[str, str]:
        """Return ``sample_id -> payload_json`` for assets whose extraction succeeded."""
        with self._connect() as conn:
            rows = conn.execute(
                "select sample_id,payload_json from asset_features where audio_error='' and extractor_version=?",
                (extractor_version,),
            ).fetchall()
        return {str(row["sample_id"]): str(row["payload_json"]) for row in rows}

    def feature_ids(self, *, extractor_version: str | None = None, successful_only: bool = False) -> set[str]:
        query = 'select sample_id from asset_features where 1=1'
        parameters = []
        if extractor_version is not None:
            query += ' and extractor_version=?'
            parameters.append(extractor_version)
        if successful_only:
            query += " and audio_error=''"
        with self._connect() as conn:
            rows = conn.execute(query, parameters).fetchall()
        return {str(row['sample_id']) for row in rows}

    def feature_metadata(self) -> dict[str, dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute('select sample_id,extractor_version,provenance,audio_error,updated_at from asset_features').fetchall()
        return {row['sample_id']: dict(row) for row in rows}

    def record_pick(self, sample_id: str, kit_id: str, query: str, kept: bool = True) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                insert or replace into picks
                (sample_id,kit_id,query,kept,recorded_at) values(?,?,?,?,?)
                """,
                (sample_id, kit_id, query, 1 if kept else 0, _now()),
            )
            conn.execute('insert into pick_events(sample_id,kit_id,query,kept,recorded_at) values(?,?,?,?,?)',
                         (sample_id, kit_id, query, 1 if kept else 0, _now()))

    def pick_counts(self) -> dict[str, int]:
        """Return ``sample_id -> times kept in a kit`` — the accreted preference signal."""
        with self._connect() as conn:
            rows = conn.execute(
                "select sample_id,count(*) c from picks where kept=1 group by sample_id"
            ).fetchall()
        return {str(row["sample_id"]): int(row["c"]) for row in rows}

    def clear_tags(self) -> None:
        """Drop every materialised tag so the vocabulary can be regenerated from rules."""
        with self._connect() as conn:
            conn.execute("delete from tags where source='generated'")

    def record_tags(self, sample_id: str, tags: list[tuple[str, str]], *, source: str = 'generated') -> None:
        with self._connect() as conn:
            for group, tag in tags:
                conn.execute(
                    "insert or ignore into tags(sample_id,tag_group,tag,source) values(?,?,?,?)",
                    (sample_id, group, tag, source),
                )

    def replace_generated_tags(self, mapping: dict[str, list[tuple[str, str]]], *, vocabulary_digest: str = '') -> None:
        """Publish a whole vocabulary run atomically, retaining human/legacy tags."""
        with self._connect() as conn:
            conn.execute("delete from tags where source='generated'")
            for sample_id, tags in mapping.items():
                conn.executemany("insert or ignore into tags(sample_id,tag_group,tag,source) values(?,?,?,'generated')",
                                 [(sample_id, group, tag) for group, tag in tags])
            conn.execute("insert or replace into state_metadata(key,value) values('vocabulary_digest',?)",
                         (vocabulary_digest,))

    def tags_for(self, sample_id: str) -> list[tuple[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "select distinct tag_group,tag from tags where sample_id=? order by tag_group,tag",
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
    def raise_error(error):
        raise error
    # Path.rglob can suppress permission errors; os.walk's onerror must abort.
    for directory, dirs, names in os.walk(root, onerror=raise_error, followlinks=False):
        base = Path(directory)
        dirs[:] = sorted(name for name in dirs if not name.startswith('.') and name != '__MACOSX'
                         and not (base == root and name in SKIP_TOP))
        if any((base / name).is_symlink() for name in dirs):
            raise ValueError(f'audio directory symlink requires explicit reconciliation: {base}')
        for name in names:
            path = base / name
            if name.startswith('.') or path.suffix.lower() not in config.SOURCE_EXTS:
                continue
            if path.is_symlink():
                raise ValueError(f'audio symlink cannot be inventoried safely: {path}')
            if path.is_file():
                found.append(path)
    return sorted(found)


def scan_library(root: Path, database: LibraryDatabase) -> ScanResult:
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f'library root is unavailable: {root}')
    # Bind before creating a lock on an unrelated root, preserving mismatch inputs.
    database.bind_root(root)
    with library_lock(root, purpose='scan library'):
        scan_id = database.begin_scan(root)
        count = 0
        for path in _iter_audio(root):
            database.record_file(root, path, scan_id)
            count += 1
        database.finish_scan(scan_id, count)
    return ScanResult(scan_id, count, True)
