"""Validated SQLite schema generations and explicit, backed-up migrations."""
from __future__ import annotations

import re
import sqlite3
from contextlib import closing, contextmanager
from functools import lru_cache
from pathlib import Path

SCHEMA_VERSION = 5


class SchemaError(ValueError):
    """Unknown, corrupt, or unsupported database; never repaired implicitly."""


class MigrationRequired(SchemaError):
    """A recognised historic schema needs an explicit migration."""


MIGRATIONS = {
1: """create table if not exists scans (
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
                );""",
2: """create table if not exists origins (
                    sample_id text primary key references assets(sample_id),
                    origin text not null,
                    confidence text not null,
                    method text not null,
                    token text not null default ''
                );
create table if not exists picks (
                    sample_id text not null references assets(sample_id),
                    kit_id text not null,
                    query text not null default '',
                    kept integer not null default 1,
                    recorded_at text not null,
                    primary key(sample_id, kit_id)
                );""",
3: """create table if not exists audio_embeddings (
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
                );""",
4: """create table if not exists prompt_embeddings (
                    model_id text not null,
                    model_revision text not null,
                    prompt_policy text not null,
                    label text not null,
                    dimensions integer not null check(dimensions > 0),
                    dtype text not null check(dtype = 'float16'),
                    embedding blob not null,
                    created_at text not null,
                    updated_at text not null,
                    primary key(model_id, model_revision, prompt_policy, label)
                );""",
5: """
create table library_identity (
 singleton integer primary key check(singleton=1),
 library_id text not null unique,
 root_hint text not null
);
create table scan_observations (
 scan_id text not null references scans(scan_id), path text not null,
 sample_id text not null, zone text not null, source_name text not null,
 size integer not null, mtime_ns integer not null, extension text not null,
 primary key(scan_id,path)
);
alter table asset_features add column extractor_version text not null default '';
alter table asset_features add column provenance text not null default 'legacy';
alter table asset_features add column updated_at text not null default '';
alter table promotions add column status text not null default 'active' check(status in ('active','withdrawn','missing'));
alter table promotions add column withdrawn_at text not null default '';
create table promotion_events (
 event_id integer primary key, sample_id text not null references assets(sample_id),
 curated_path text not null, run_id text not null, status text not null,
 recorded_at text not null
);
insert into promotion_events(sample_id,curated_path,run_id,status,recorded_at)
 select sample_id,curated_path,run_id,'active',promoted_at from promotions;
alter table tags rename to legacy_tags;
create table tags (
 sample_id text not null references assets(sample_id), tag_group text not null,
 tag text not null, source text not null default 'generated',
 primary key(sample_id,tag_group,tag,source)
);
insert into tags(sample_id,tag_group,tag,source) select sample_id,tag_group,tag,'legacy' from legacy_tags;
drop table legacy_tags;
create table state_metadata (key text primary key, value text not null);
create table review_events (
 event_id integer primary key, sample_id text not null references assets(sample_id),
 packet_id text not null, decision text not null, true_role text not null,
 descriptor text not null, notes text not null, reviewed_at text not null,
 provenance text not null default 'human'
);
insert into review_events(sample_id,packet_id,decision,true_role,descriptor,notes,reviewed_at,provenance)
 select sample_id,packet_id,decision,true_role,descriptor,notes,reviewed_at,'legacy' from reviews;
create table pick_events (
 event_id integer primary key, sample_id text not null references assets(sample_id),
 kit_id text not null, query text not null, kept integer not null,
 recorded_at text not null, provenance text not null default 'human'
);
insert into pick_events(sample_id,kit_id,query,kept,recorded_at,provenance)
 select sample_id,kit_id,query,kept,recorded_at,'legacy' from picks;
create index locations_asset_current on locations(sample_id,exists_now);
create index scans_completion on scans(status,completed_at);
"""
}


def _execute_migration(conn, version):
    # executescript implicitly commits; individual statements preserve one transaction.
    for statement in MIGRATIONS[version].split(';'):
        if statement.strip():
            conn.execute(statement)
    conn.execute(f'pragma user_version={version}')


def _shape(conn):
    tables = [r[0] for r in conn.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
    result = {}
    for table in tables:
        quoted = '"' + table.replace('"', '""') + '"'
        columns = tuple(tuple(row)[1:] for row in conn.execute(f'pragma table_info({quoted})'))
        fks = tuple(tuple(row)[2:] for row in conn.execute(f'pragma foreign_key_list({quoted})'))
        # Include keys, defaults, nullability and foreign keys, not merely column names.
        indexes = []
        for row in conn.execute(f'pragma index_list({quoted})'):
            if row[2]:
                index = '"' + row[1].replace('"', '""') + '"'
                indexes.append(tuple(r[2] for r in conn.execute(f'pragma index_info({index})')))
        sql = conn.execute("select sql from sqlite_master where type='table' and name=?", (table,)).fetchone()[0]
        checks = tuple(re.sub(r'\s+', '', clause.lower()) for clause in re.findall(r'check\s*\((.*?)\)', sql, re.I | re.S))
        result[table] = (columns, fks, tuple(sorted(indexes)), checks)
    return result


@lru_cache(maxsize=5)
def _expected_shape(version):
    with closing(sqlite3.connect(':memory:')) as conn:
        for step in range(1, version + 1):
            _execute_migration(conn, step)
        return _shape(conn)


@contextmanager
def readonly_database(path):
    """No sidecar creation, no implicit recovery, no ignoring pending journals."""
    from .promotion_health import _database_state
    path = Path(path).resolve()
    if not path.is_file():
        raise SchemaError(f'library database not found: {path}')
    before = _database_state(path)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('pragma query_only=on')
        yield conn
    if _database_state(path) != before:
        raise SchemaError('library database changed during inspection; retry when idle')


def inspect_connection(conn):
    declared = conn.execute('pragma user_version').fetchone()[0]
    if declared > SCHEMA_VERSION:
        raise SchemaError(f'newer schema version {declared}; this release supports {SCHEMA_VERSION}')
    if declared < 1:
        raise SchemaError('unversioned database; preserve and reconcile it before migration')
    if conn.execute("select name from sqlite_master where type in ('view','trigger')").fetchone():
        raise SchemaError('unknown database structure: unexpected views or triggers')
    integrity = conn.execute('pragma integrity_check').fetchone()[0]
    if integrity != 'ok':
        raise SchemaError(f'database integrity check failed: {integrity}')
    actual = _shape(conn)
    candidates = [v for v in range(1, SCHEMA_VERSION + 1) if actual == _expected_shape(v)]
    if not candidates or (declared == SCHEMA_VERSION and candidates != [SCHEMA_VERSION]):
        raise SchemaError('unknown database structure; schema version stamp is not trustworthy')
    if conn.execute('pragma foreign_key_check').fetchone():
        raise SchemaError('database contains foreign-key inconsistencies; reconcile before migration')
    return {'declared_version': declared, 'detected_version': candidates[-1], 'integrity': 'ok'}


def inspect_database(path):
    try:
        with readonly_database(path) as conn:
            return inspect_connection(conn)
    except sqlite3.DatabaseError as exc:
        raise SchemaError(f'cannot inspect library database: {exc}') from exc


def initialize_database(path):
    """Create the current schema in an empty database under the caller's lock."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute('begin immediate')
        if conn.execute("select name from sqlite_master where type='table'").fetchone():
            raise SchemaError('database appeared during initialisation; retry without overwriting')
        for step in range(1, SCHEMA_VERSION + 1):
            _execute_migration(conn, step)


def migrate_database(path, *, root=None, backup_dir=None, apply=False, include=()):
    """Preview ordered migrations, or apply them with a verified original backup."""
    path = Path(path).resolve()
    original = inspect_database(path)
    start = original['detected_version']
    report = {**original, 'database': str(path), 'schema_version': SCHEMA_VERSION,
              'steps': list(range(start + 1, SCHEMA_VERSION + 1)), 'apply': apply}
    if not apply:
        return report
    from .lifecycle import backup_bundle
    from .locking import library_lock, database_lock
    from .inventory import LibraryDatabase
    from datetime import datetime, timezone
    if root is not None and not Path(root).is_dir():
        raise ValueError(f'library root is unavailable: {root}')
    lock = library_lock(root, purpose='migrate') if root is not None else database_lock(path, purpose='migrate')
    with lock:
        if inspect_database(path) != original:
            raise SchemaError('database changed after migration preview')
        destination = Path(backup_dir) if backup_dir else path.parent / 'backups' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        backup_bundle(path, destination, root=root, include=include)
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute('pragma foreign_keys=on')
            conn.execute('begin immediate')
            if inspect_connection(conn) != original:
                raise SchemaError('database changed before migration transaction')
            for step in report['steps']:
                _execute_migration(conn, step)
            # Correct misleading historic stamps even if shape already matches.
            conn.execute(f'pragma user_version={SCHEMA_VERSION}')
            inspect_connection(conn)
        if root is not None:
            LibraryDatabase(path).bind_root(Path(root))
        report['backup'] = str(destination)
    return report
