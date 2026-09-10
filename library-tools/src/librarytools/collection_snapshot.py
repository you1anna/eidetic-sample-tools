"""Guarded, portable metadata snapshots for unreviewed collection planning."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path, PurePosixPath
import re
import uuid

from .find import Query, load_index, matches_query
from .inventory import LibraryDatabase
from .schema import readonly_database
from .state import library_identity, resolve_library_db


def text(value, name, *, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()) or any(ord(c) < 32 for c in value):
        raise ValueError(f'invalid {name}: expected single-line text')
    return value


def identity(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('invalid sample or content identity: expected SHA-256')
    return value


def integer(value, name, minimum=0):
    if type(value) is not int or not minimum <= value <= 2**63 - 1:
        raise ValueError(f'invalid {name}: expected an integer >= {minimum}')
    return value


def relative_path(value):
    text(value, 'relative sample path')
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in {'.', '..'} for p in path.parts) or '\\' in value or path.as_posix() != value:
        raise ValueError('invalid relative sample path')
    return value


def query_data(query: Query) -> dict:
    if not isinstance(query, Query) or type(query.any_) is not bool or type(query.curated_only) is not bool:
        raise ValueError('invalid search query')
    groups = {}
    for key, values in query.groups.items():
        if key not in {'role', 'origin', 'style', 'gear', 'character'}:
            raise ValueError(f'unsupported search group: {key}')
        if not isinstance(values, (list, tuple)) or not values:
            raise ValueError('query group values must be a nonempty list')
        groups[key] = sorted({text(v, 'query value').lower() for v in values})
    if not isinstance(query.terms, (list, tuple)):
        raise ValueError('query terms must be a list')
    return {'terms': sorted({text(v, 'query term').lower() for v in query.terms}),
            'groups': dict(sorted(groups.items())), 'any': query.any_, 'curated_only': query.curated_only}


def capture(root: Path, query: Query, library_db: Path | None = None) -> dict:
    root = Path(root).resolve()
    query_spec = query_data(query)
    query = Query(tuple(query_spec['terms']), {k: tuple(v) for k, v in query_spec['groups'].items()},
                  query_spec['any'], query_spec['curated_only'])
    library_id = library_identity(root)
    if library_id is None:
        raise ValueError('library identity is missing; onboard the library first')
    database_path = resolve_library_db(root, library_db)
    # The existing read-only guard checks journals and the database fingerprint
    # across ALL component reads. A concurrent mutation aborts before publication.
    with readonly_database(database_path):
        db = LibraryDatabase(database_path, readonly=True)
        db.bind_root(root, create=False)
        scan_id = db.latest_complete_scan()
        if scan_id is None:
            raise ValueError('a complete inventory scan is required before planning')
        matches = load_index(db)
        aliases = {}
        for location in db.current_locations():
            aliases.setdefault(location.sample_id, []).append({
                'path': location.path.as_posix(), 'zone': location.zone,
                'size': location.size, 'mtime_ns': location.mtime_ns})
        candidates = []
        for match in matches:
            paths = sorted(aliases[match.sample_id], key=lambda a: a['path'])
            matching = [a for a in paths if matches_query(
                replace(match, path=Path(a['path']), zone=a['zone']), query)]
            if not matching:
                continue
            candidates.append({'sample_id': match.sample_id, 'path': matching[0]['path'],
                               'role': match.role, 'origin': match.origin,
                               'tags': list(match.tags), 'aliases': paths})
        snapshot = {'library_id': library_id, 'scan_id': scan_id, 'query': query_spec,
                    'indexed_identities': len(matches), 'audio_ranking': 'not_used',
                    'candidates': sorted(candidates, key=lambda row: row['sample_id'])}
    if library_identity(root) != library_id:
        raise ValueError('library identity changed during snapshot capture')
    validate_snapshot(snapshot)
    return snapshot


def validate_snapshot(value):
    keys = {'library_id', 'scan_id', 'query', 'indexed_identities', 'audio_ranking', 'candidates'}
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError('invalid collection snapshot structure')
    try:
        if str(uuid.UUID(value['library_id'])) != value['library_id']:
            raise ValueError('invalid library identity')
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('invalid library identity') from exc
    text(value['scan_id'], 'scan identity')
    integer(value['indexed_identities'], 'indexed identities')
    if value['audio_ranking'] != 'not_used':
        raise ValueError('unsupported audio ranking in metadata snapshot')
    query = value['query']
    if not isinstance(query, dict) or set(query) != {'terms', 'groups', 'any', 'curated_only'}:
        raise ValueError('invalid saved query')
    if not isinstance(query['groups'], dict):
        raise ValueError('invalid saved query groups')
    normalized = query_data(Query(query['terms'], query['groups'], query['any'], query['curated_only']))
    if normalized != query:
        raise ValueError('saved query is not canonical')
    rows = value['candidates']
    if not isinstance(rows, list) or len(rows) > value['indexed_identities']:
        raise ValueError('invalid candidate population')
    seen = set()
    paths = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'sample_id', 'path', 'role', 'origin', 'tags', 'aliases'}:
            raise ValueError('invalid candidate structure')
        sid = identity(row['sample_id'])
        if sid in seen:
            raise ValueError('duplicate candidate identity')
        seen.add(sid)
        relative_path(row['path'])
        text(row['role'], 'role')
        text(row['origin'], 'origin')
        if not isinstance(row['tags'], list) or any(not isinstance(t, str) for t in row['tags']):
            raise ValueError('invalid candidate tags')
        if sorted(set(row['tags'])) != row['tags']:
            raise ValueError('candidate tags are not canonical')
        for tag in row['tags']:
            text(tag, 'tag')
        aliases = row['aliases']
        if not isinstance(aliases, list) or not aliases:
            raise ValueError('candidate aliases are required')
        alias_paths = []
        for alias in aliases:
            if not isinstance(alias, dict) or set(alias) != {'path', 'zone', 'size', 'mtime_ns'}:
                raise ValueError('invalid candidate alias')
            path = relative_path(alias['path'])
            text(alias['zone'], 'zone')
            integer(alias['size'], 'sample size')
            integer(alias['mtime_ns'], 'sample modification time')
            if path in paths:
                raise ValueError('duplicate alias path in candidate population')
            paths[path] = sid
            alias_paths.append(path)
        if alias_paths != sorted(alias_paths) or row['path'] not in alias_paths:
            raise ValueError('invalid preferred candidate path or alias ordering')
    if [row['sample_id'] for row in rows] != sorted(seen):
        raise ValueError('candidate population is not canonical')
    return value
