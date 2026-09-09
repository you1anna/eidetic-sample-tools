"""Durable operation evidence and conservative filesystem reconciliation.

A completed item means both its bytes and its database effects were checked.
The intent is fsynced first; a crash may leave a pending item, never lost intent.
Journals are append-preserved at the operation level and never deleted.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .inventory import LibraryDatabase


class OperationError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(value, fh, indent=2, sort_keys=True)
            fh.write('\n')
            fh.flush()
            os.fsync(fh.fileno())
        temp.replace(path)
        sync_directory(path.parent)
    finally:
        temp.unlink(missing_ok=True)


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def fingerprint(path: Path) -> dict:
    from .inventory import sha256_file
    if path.is_symlink():
        raise OperationError(f'symlink requires manual review: {path}')
    if path.is_file():
        return {'kind': 'file', 'sha256': sha256_file(path)}
    if path.is_dir():
        entries = []
        for child in sorted(path.rglob('*')):
            if child.is_symlink():
                raise OperationError(f'symlink requires manual review: {child}')
            entries.append([child.relative_to(path).as_posix(),
                            sha256_file(child) if child.is_file() else 'directory'])
        digest = hashlib.sha256(json.dumps(entries, separators=(',', ':')).encode()).hexdigest()
        return {'kind': 'directory', 'sha256': digest, 'entries': len(entries)}
    raise OperationError(f'missing source: {path}')


def contained(root: Path, relative: str | Path) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts:
        raise OperationError(f'operation path escapes library: {relative}')
    path = root / rel
    if not path.resolve().is_relative_to(root.resolve()):
        raise OperationError(f'operation path escapes library: {relative}')
    return path


def item_state(root: Path, item: dict) -> str:
    """Read-only byte check. Ambiguous copies or changed bytes never imply approval."""
    if item.get('action') == 'review':
        try:
            return 'ready' if fingerprint(contained(root, item['source'])) == item['fingerprint'] else 'conflict'
        except (OSError, OperationError):
            return 'conflict'
    source, destination = contained(root, item['source']), contained(root, item['destination'])
    expected = item['fingerprint']
    source_present = source.exists() or source.is_symlink()
    destination_present = destination.exists() or destination.is_symlink()
    try:
        source_ok = source_present and fingerprint(source) == expected
        destination_ok = destination_present and fingerprint(destination) == expected
    except (OSError, OperationError):
        return 'conflict'
    if source_present and not source_ok or destination_present and not destination_ok:
        return 'conflict'
    if destination_ok:
        if item['action'] == 'copy':
            return 'published' if source_ok else 'conflict'
        return 'published' if not source_present else 'conflict'
    return 'ready' if source_ok else 'missing'


def copy_exclusive(source: Path, destination: Path) -> None:
    """Stage and fsync a complete copy, then publish with an exclusive rename.

    A killed process can leave a hidden .partial staging file. It is retained
    for maintenance inspection and cannot be mistaken for a curated sample.
    """
    from .moves import _rename_exclusive
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f'.{destination.name}.eidetic-copy-', suffix='.partial',
                                dir=destination.parent)
    staging = Path(name)
    try:
        with source.open('rb') as src, os.fdopen(fd, 'wb') as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        shutil.copystat(source, staging)
        _rename_exclusive(staging, destination)
        sync_directory(destination.parent)
    finally:
        staging.unlink(missing_ok=True)


def sidecars(source: Path) -> list[str]:
    if not source.is_file():
        return []
    candidates = {Path(str(source) + '.asd'), source.with_suffix('.ot')}
    return [str(path) for path in sorted(candidates) if path.is_file()]


def journals(root: Path) -> list[tuple[Path, dict]]:
    directory = root / '.eidetic' / 'operations'
    result = []
    if directory.is_symlink() or (root / '.eidetic').is_symlink():
        raise OperationError(f'operation directory must not be a symlink: {directory}')
    if directory.exists():
        for path in sorted(directory.glob('*.json')):
            if path.is_symlink():
                raise OperationError(f'operation journal must not be a symlink: {path}')
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError) as exc:
                raise OperationError(f'unreadable operation journal {path}: {exc}') from exc
            if not isinstance(data, dict) or data.get('schema_version') != 1:
                raise OperationError(f'unsupported operation journal version: {path}')
            if data.get('kind') not in {'moves', 'promotion', 'undo-promotion'} or data.get('status') not in {'pending', 'complete'}:
                raise OperationError(f'unknown operation kind or status: {path}')
            identifier = data.get('operation_id')
            if (not isinstance(identifier, str) or len(identifier) != 32
                    or any(char not in '0123456789abcdef' for char in identifier)
                    or identifier != path.stem or not isinstance(data.get('items'), list)):
                raise OperationError(f'invalid operation journal: {path}')
            if data['kind'] == 'promotion' and any(key not in data for key in ('packet_id', 'run_id', 'labels_sha256')):
                raise OperationError(f'incomplete promotion evidence: {path}')
            if data['kind'] == 'moves' and not isinstance(data.get('undo_path'), str):
                raise OperationError(f'incomplete move evidence: {path}')
            for item in data['items']:
                if not isinstance(item, dict) or item.get('action') not in {'move', 'copy', 'review'} or item.get('status') not in {'pending', 'published', 'complete', 'exists', 'missing'}:
                    raise OperationError(f'invalid operation item: {path}')
                if not isinstance(item.get('source'), str) or (item['action'] != 'review' and not isinstance(item.get('destination'), str)):
                    raise OperationError(f'invalid operation paths: {path}')
                relative_paths = [item['source']] + ([item['destination']] if item['action'] != 'review' else [])
                if any(Path(value).is_absolute() or '..' in Path(value).parts for value in relative_paths):
                    raise OperationError(f'operation paths escape library: {path}')
                if item['status'] not in {'exists', 'missing'}:
                    expected = item.get('fingerprint')
                    digest = expected.get('sha256') if isinstance(expected, dict) else None
                    if (not isinstance(digest, str) or len(digest) != 64 or any(char not in '0123456789abcdef' for char in digest)
                            or expected.get('kind') not in {'file', 'directory'}):
                        raise OperationError(f'invalid operation fingerprint: {path}')
                if data['kind'] == 'promotion' and not isinstance(item.get('review'), dict):
                    raise OperationError(f'invalid operation review evidence: {path}')
            result.append((path, data))
    return result


def find_operation(root: Path, kind: str, key: str) -> tuple[Path, dict] | None:
    matches = [(path, data) for path, data in journals(root)
               if data['kind'] == kind and data.get('key') == key]
    if len(matches) > 1:
        raise OperationError(f'ambiguous operation identity: {kind} {key}')
    return matches[0] if matches else None


def require_settled(root: Path, *, excluding: str | None = None) -> None:
    pending = [data['operation_id'] for _, data in journals(root)
               if data['status'] != 'complete' and data['operation_id'] != excluding]
    if pending:
        raise OperationError(f'incomplete operation {pending[0]}; run sample-library recover before new work')


def create_operation(root: Path, kind: str, key: str, items: list[dict], **metadata) -> tuple[Path, dict]:
    from .state import library_identity
    require_settled(root)
    operation_id = uuid.uuid4().hex
    path = root / '.eidetic' / 'operations' / f'{operation_id}.json'
    data = {'schema_version': 1, 'operation_id': operation_id, 'kind': kind, 'key': key,
            'library_id': library_identity(root, create=True), 'created_at': _now(),
            'status': 'pending', 'items': items, **metadata}
    atomic_json(path, data)
    return path, data


def persist(path: Path, data: dict) -> None:
    data['updated_at'] = _now()
    atomic_json(path, data)


def validate_identity(root: Path, data: dict) -> None:
    from .state import library_identity
    if not root.is_dir() or library_identity(root) != data.get('library_id'):
        raise OperationError('operation library identity does not match attached root')


def execute_item(root: Path, item: dict) -> None:
    from . import moves
    state = item_state(root, item)
    if state in {'conflict', 'missing'}:
        raise OperationError(f'operation item {state}: missing or changed bytes at {item.get("source")} / {item.get("destination")}')
    if state == 'ready' and item['action'] != 'review':
        source = contained(root, item['source'])
        destination = contained(root, item['destination'])
        if item['action'] == 'copy':
            copy_exclusive(source, destination)
        else:
            status = moves.safe_move(source, destination)
            if status != 'moved':
                raise OperationError(f'operation move failed ({status}): {source}')
        if item_state(root, item) != 'published':
            raise OperationError(f'operation bytes changed during filesystem action: {source}')


def update_database(root: Path, data: dict, item: dict, database: LibraryDatabase) -> None:
    from .inventory import sha256_file
    if data['kind'] == 'promotion':
        row = item['review']
        database.record_review(row['sample_id'], data['packet_id'], row['decision'],
                               row['true_role'], row['descriptor'], row['notes'])
        database.record_tags(row['sample_id'], [tuple(tag) for tag in row['tags']], source='human')
        if item['action'] == 'copy':
            destination = contained(root, item['destination'])
            if sha256_file(destination) != row['sample_id']:
                raise OperationError(f'curated copy changed: {destination}')
            recorded = [p for p in database.promotions()
                        if p['sample_id'] == row['sample_id'] and p['curated_path'] == item['destination']]
            if recorded:
                if recorded[0].get('status', 'active') == 'active' and recorded[0]['run_id'] != data['run_id']:
                    raise OperationError(f'promotion history conflicts with operation: {destination}')
            if not recorded or recorded[0].get('status', 'active') == 'withdrawn':
                database.record_promotion(row['sample_id'], Path(item['destination']), Path(item['source']), data['run_id'])
            database.record_file(root, destination, item['scan_id'])
    elif data['kind'] == 'undo-promotion':
        database.mark_missing(Path(item['source']))
        database.mark_promotion_withdrawn(item['fingerprint']['sha256'], Path(item['source']))


def resume_operation(root: Path, path: Path, data: dict, database: LibraryDatabase | None = None, *,
                     write_legacy_undo: bool = False) -> None:
    validate_identity(root, data)
    require_settled(root, excluding=data['operation_id'])
    if data['kind'] in {'promotion', 'undo-promotion'} and database is None:
        raise OperationError('recovery requires the library database for curation operations')
    if database is not None:
        database.bind_root(root)
    for item in data['items']:
        if item.get('status') in {'exists', 'missing'}:
            continue  # preflight skips are evidence, never approval to retry an unreviewed move
        if item.get('status') == 'complete':
            expected_state = 'ready' if item['action'] == 'review' else 'published'
            if item_state(root, item) != expected_state:
                raise OperationError(f'completed operation has missing or changed bytes: {item.get("destination")}')
            if data['kind'] == 'promotion' and item['action'] == 'copy' and database is not None:
                active = [p for p in database.promotions() if p['curated_path'] == item['destination']
                          and p['sample_id'] == item['fingerprint']['sha256']
                          and p['run_id'] == data['run_id'] and p.get('status', 'active') == 'active']
                if not active:
                    raise OperationError('completed promotion has been withdrawn or superseded')
            continue
        execute_item(root, item)
        if item.get('status') != 'complete':
            item['status'] = 'published'
            persist(path, data)
            if database is not None:
                update_database(root, data, item, database)
            item['status'] = 'complete'
            persist(path, data)
    if data['kind'] == 'moves':
        write_undo(root, data, write_legacy=write_legacy_undo)
    data['status'] = 'complete'
    persist(path, data)


def _write_undo_once(path: Path, content: str) -> None:
    """Never replace different human evidence, even on a completed-operation retry."""
    if path.is_symlink():
        raise OperationError(f'undo path is a symlink: {path}')
    if path.exists():
        if not path.is_file() or path.read_text(encoding='utf-8') != content:
            raise OperationError(f'undo content differs from the operation: {path}')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    from .moves import _rename_exclusive
    fd, name = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        _rename_exclusive(Path(name), path)
        sync_directory(path.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def write_undo(root: Path, data: dict, *, write_legacy: bool = False) -> None:
    """Keep portable relative TSV evidence; only explicit plan runs export old paths.

    Generic recovery must never write an absolute path retained from another Mac.
    """
    complete = [item for item in data['items'] if item.get('status') == 'complete']
    canonical = root / '.eidetic' / 'operations' / f'{data["operation_id"]}.undo.tsv'
    content = ''.join(f'{item["destination"]}\t{item["source"]}\n' for item in complete)
    _write_undo_once(canonical, content)
    if write_legacy:
        undo = Path(data['undo_path'])
        if data.get('undo_relative'):
            undo = contained(root, data['undo_relative'])
        absolute = ''.join(f'{contained(root, item["destination"])}\t{contained(root, item["source"])}\n'
                           for item in complete)
        _write_undo_once(undo, absolute)


def recover_operations(root: Path, database: LibraryDatabase | None = None, *, apply: bool = False,
                       operation_id: str | None = None) -> list[dict]:
    from .locking import library_lock
    def run() -> list[dict]:
        selected = [(path, data) for path, data in journals(root)
                    if data['operation_id'] == operation_id or operation_id is None and data['status'] != 'complete']
        if operation_id and not selected:
            raise OperationError(f'unknown operation: {operation_id}')
        result = []
        for path, data in selected:
            validate_identity(root, data)
            states = ['skipped-' + item['status'] if item.get('status') in {'exists', 'missing'} else item_state(root, item)
                      for item in data['items']]
            report = {'operation_id': data['operation_id'], 'kind': data['kind'],
                      'status': data['status'], 'items': states, 'journal': str(path),
                      'recoverable': all(state in {'ready', 'published', 'skipped-exists', 'skipped-missing'} for state in states)}
            if data['kind'] == 'moves':
                report['undo'] = str(root / '.eidetic' / 'operations' / f'{data["operation_id"]}.undo.tsv')
            if apply:
                resume_operation(root, path, data, database)
                report['status'] = data['status']
            result.append(report)
        return result
    if not apply:
        return run()
    with library_lock(root, purpose='recover operations', allow_recovery=True):
        return run()
