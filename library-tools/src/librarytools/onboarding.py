"""Independent machine setup and immutable capture of later local history.

The SSD remains authoritative. Capturing an older machine preserves evidence;
it never merges its decisions into, or replaces, an existing portable index.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import uuid
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .inventory import LibraryDatabase
from .lifecycle import _copy_file, _hash, adopt_database
from .locking import library_lock
from .operations import atomic_json, sync_directory
from .schema import SCHEMA_VERSION, inspect_database, migrate_database, readonly_database
from .state import library_identity, state_directory

FORMAT_VERSION = 1


def _now():
    return datetime.now(timezone.utc).isoformat()


def _metadata(root):
    path = state_directory(root) / 'onboarding.json'
    if not path.exists():
        return {'format_version': FORMAT_VERSION, 'library_id': library_identity(root),
                'coverage': 'incomplete', 'machines': {}, 'deferred_machines': [], 'captures': {}}
    if path.is_symlink():
        raise ValueError('onboarding metadata must not be a symlink')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('format_version') != FORMAT_VERSION or not all(isinstance(data.get(key), dict) for key in ('machines', 'captures')) or not isinstance(data.get('deferred_machines'), list):
        raise ValueError('unsupported or invalid onboarding metadata')
    if data.get('coverage') != 'incomplete' or not all(isinstance(name, str) for name in data['deferred_machines']):
        raise ValueError('invalid onboarding history coverage')
    for machine in data['machines'].values():
        if not isinstance(machine, dict) or not isinstance(machine.get('history_status'), str) or not isinstance(machine.get('capture_ids'), list):
            raise ValueError('invalid onboarding machine record')
        if any(not isinstance(key, str) or key not in data['captures'] for key in machine['capture_ids']):
            raise ValueError('onboarding machine references missing historical captures')
    for receipt in data['captures'].values():
        if not isinstance(receipt, dict) or not all(isinstance(receipt.get(key), str) for key in ('machine', 'archive', 'source_fingerprint', 'manifest_sha256')):
            raise ValueError('invalid historical capture receipt')
        if receipt.get('source_database') is not None and not isinstance(receipt['source_database'], str):
            raise ValueError('invalid historical source database')
        if not isinstance(receipt.get('source_inputs'), list) or not all(isinstance(path, str) for path in receipt['source_inputs']) or not isinstance(receipt.get('source_files'), dict):
            raise ValueError('invalid historical evidence inputs')
        for expected in receipt['source_files'].values():
            if not isinstance(expected, dict) or not isinstance(expected.get('sha256'), str) or not isinstance(expected.get('size'), int) or expected['size'] < 0:
                raise ValueError('invalid historical source file checksum')
    if data.get('library_id') != library_identity(root):
        raise ValueError('onboarding metadata belongs to another library identity')
    return data


def _state_path(root, relative):
    state = state_directory(root)
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts or not relative.parts:
        raise ValueError('historical archive path escapes portable state')
    path = state
    for part in relative.parts:
        path /= part
        if path.is_symlink():
            raise ValueError('historical archive ancestors must not be symlinks')
    if not path.resolve().is_relative_to(state):
        raise ValueError('historical archive path escapes portable state')
    return path


def _included_files(path, database):
    """Enumerate exactly the retained input set, including newly added files."""
    if path.is_symlink() or not path.exists():
        raise ValueError(f'evidence path is missing or a symlink: {path}')
    found = []
    if path.is_file():
        files = [path]
    else:
        files = []
        def fail(error):
            raise error
        for directory, dirs, names in os.walk(path, followlinks=False, onerror=fail):
            base = Path(directory)
            dirs[:] = sorted(name for name in dirs if name not in {'backups', 'cache', 'caches', 'tmp'})
            if any((base / name).is_symlink() for name in dirs):
                raise ValueError(f'evidence directory contains a symlink: {base}')
            files.extend(base / name for name in sorted(names))
    for file in files:
        if (database is not None and file.resolve() == database) or file.name == 'writer.lock' or file.name.endswith(('.writer.lock', '-wal', '-shm', '-journal')):
            continue
        if file.is_symlink() or not file.is_file():
            raise ValueError(f'evidence must be an ordinary file: {file}')
        if file.suffix.lower() in config.SOURCE_EXTS:
            raise ValueError(f'audio is not historical state; choose evidence paths without audio: {file}')
        suffix = Path(file.name) if path.is_file() else Path(path.name) / file.relative_to(path)
        before = file.stat()
        with file.open('rb') as stream:
            sqlite_file = stream.read(16) == b'SQLite format 3\x00'
        with readonly_database(file) if sqlite_file else nullcontext():
            digest = _hash(file)
        after = file.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError(f'evidence changed while reading: {file}')
        found.append((file, (Path('imports') / suffix).as_posix(), digest, after.st_size))
    return found


def source_snapshot(database, includes):
    """Read a versioned database and complete explicit evidence sets without writes."""
    database = Path(database).resolve() if database is not None else None
    paths = sorted({Path(path).resolve() for path in includes}, key=str)
    if len({path.name for path in paths}) != len(paths):
        raise ValueError('evidence inputs must have distinct directory/file names')
    digest = None
    database_size = None
    schema = None
    if database is not None:
        schema = inspect_database(database)
        with readonly_database(database):
            digest = _hash(database)
            database_size = database.stat().st_size
    files = []
    for path in paths:
        files.extend({'source': str(file), 'path': relative, 'sha256': sha, 'size': size}
                     for file, relative, sha, size in _included_files(path, database))
    files.sort(key=lambda row: row['path'])
    content = {'database_sha256': digest,
               'files': [{key: row[key] for key in ('path', 'sha256', 'size')} for row in files]}
    fingerprint = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'database': str(database) if database else None, 'database_sha256': digest, 'database_size': database_size,
            'includes': [str(path) for path in paths], 'files': files,
            'fingerprint': fingerprint, 'schema': schema}


def _verify_capture(root, receipt):
    archive = _state_path(root, receipt['archive'])
    manifest_path = archive / 'manifest.json'
    if _hash(manifest_path) != receipt['manifest_sha256']:
        raise ValueError('historical archive manifest changed; preserve and reconcile the evidence')
    return _verify_archive(archive, receipt['source_files'], receipt['source_fingerprint'])


def _verify_archive(archive, expected_files, fingerprint):
    manifest_path = archive / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if not isinstance(manifest, dict) or manifest.get('format_version') != FORMAT_VERSION or not isinstance(manifest.get('files'), dict):
        raise ValueError('unsupported historical archive format')
    if manifest.get('source_fingerprint') != fingerprint or manifest['files'] != expected_files:
        raise ValueError('historical archive does not contain the complete expected source snapshot')
    actual_files = {path.relative_to(archive / 'state').as_posix() for path in (archive / 'state').rglob('*') if path.is_file()}
    if actual_files != set(expected_files):
        raise ValueError('historical archive file set does not match the source snapshot')
    for name, expected in manifest['files'].items():
        file = archive / 'state' / name
        if Path(name).is_absolute() or '..' in Path(name).parts or file.is_symlink() or not file.resolve().is_relative_to(archive.resolve()):
            raise ValueError('historical archive contains an unsafe path')
        if not file.is_file() or file.stat().st_size != expected['size'] or _hash(file) != expected['sha256']:
            raise ValueError(f'historical archive checksum mismatch: {name}')
    if 'library.sqlite' in manifest['files']:
        inspect_database(archive / 'state/library.sqlite')
    return manifest


def _available_source_inputs(receipts):
    """Keep all known evidence available here, regardless of machine label."""
    inputs = set()
    for receipt in receipts:
        for name in receipt['source_inputs']:
            path = Path(name)
            if path.is_symlink():
                raise ValueError(f'historical evidence input must not be a symlink: {path}')
            if path.exists():
                inputs.add(path)
    return inputs


def captured_source_matches(root, legacy):
    """One verified receipt must cover all currently available local evidence."""
    try:
        metadata = _metadata(root)
        candidates = [receipt for receipt in metadata['captures'].values()
                      if receipt.get('source_database') == str(Path(legacy).resolve())]
        inputs = _available_source_inputs(candidates)
        snapshot = source_snapshot(legacy, inputs)
        for receipt in reversed(candidates):
            if (set(snapshot['includes']).issubset(receipt['source_inputs'])
                    and snapshot['fingerprint'] == receipt['source_fingerprint']):
                _verify_capture(root, receipt)
                return True
    except (ValueError, OSError, KeyError, TypeError):
        return False
    return False


def assert_captured_sources_current(root):
    """Check recorded source paths that are accessible on this machine.

    Missing paths can belong to an unavailable machine. They keep coverage
    incomplete but never prevent using the current SSD on the available one.
    """
    if not (state_directory(root) / 'onboarding.json').exists():
        return
    metadata = _metadata(root)
    databases = {receipt['source_database'] for receipt in metadata['captures'].values()
                 if receipt.get('source_database')}
    for source in databases:
        if Path(source).is_file() and not captured_source_matches(root, Path(source)):
            raise ValueError(f'local historical evidence changed or its archive is unverified: {source}; repeat sample-library onboard to preserve it before using implicit defaults')
    files_only = {tuple(receipt['source_inputs']) for receipt in metadata['captures'].values()
                  if not receipt.get('source_database')}
    for inputs in files_only:
        if not any(Path(path).exists() for path in inputs):
            continue
        snapshot = source_snapshot(None, inputs)
        matching = [receipt for receipt in metadata['captures'].values()
                    if receipt['source_database'] is None and receipt['source_fingerprint'] == snapshot['fingerprint']]
        if not matching:
            raise ValueError('local historical files changed; repeat sample-library onboard to preserve them')
        _verify_capture(root, matching[-1])


def history_report(root):
    if not (state_directory(root) / 'onboarding.json').exists():
        return None
    metadata = _metadata(root)
    return {'coverage': metadata['coverage'], 'deferred_machines': metadata['deferred_machines'],
            'machines': metadata['machines'], 'captured_sources': len(metadata['captures']),
            'note': 'Preserved historical decisions await human reconciliation; the portable library remains usable.'}


def _publish_capture(root, machine, snapshot):
    namespace = hashlib.sha256(machine.encode()).hexdigest()[:12]
    relative = Path('history') / namespace / snapshot['fingerprint']
    archive = _state_path(root, relative)
    expected_files = {row['path']: {'sha256': row['sha256'], 'size': row['size']} for row in snapshot['files']}
    if snapshot['database'] is not None:
        expected_files['library.sqlite'] = {'sha256': snapshot['database_sha256'], 'size': snapshot['database_size']}
    if not archive.exists():
        archive.parent.mkdir(parents=True, exist_ok=True)
        _state_path(root, relative)
        staging = _state_path(root, relative.parent / ('.capture-' + uuid.uuid4().hex))
        (staging / 'state').mkdir(parents=True)
        if snapshot['database'] is not None:
            # Archival sources must be settled; preserve their exact original
            # bytes while refusing journals or concurrent database changes.
            with readonly_database(Path(snapshot['database'])):
                _copy_file(Path(snapshot['database']), staging / 'state/library.sqlite')
        for row in snapshot['files']:
            _copy_file(Path(row['source']), staging / 'state' / row['path'])
        if source_snapshot(snapshot['database'], snapshot['includes'])['fingerprint'] != snapshot['fingerprint']:
            raise ValueError('local historical evidence changed during capture; retained partial evidence requires a fresh onboarding run')
        atomic_json(staging / 'manifest.json', {
            'format_version': FORMAT_VERSION, 'source_database': snapshot['database'],
            'source_fingerprint': snapshot['fingerprint'], 'created_at': _now(), 'files': expected_files})
        _verify_archive(staging, expected_files, snapshot['fingerprint'])
        for file in (staging / 'state').rglob('*'):
            if file.is_file():
                with file.open('rb') as stream:
                    os.fsync(stream.fileno())
        for directory, _, _ in os.walk(staging, topdown=False):
            sync_directory(Path(directory))
        _state_path(root, relative)
        staging.rename(archive)
        sync_directory(archive.parent)
    _verify_archive(archive, expected_files, snapshot['fingerprint'])
    receipt = {'machine': machine, 'host_hint': socket.gethostname(),
               'source_database': snapshot['database'], 'source_inputs': snapshot['includes'],
               'source_fingerprint': snapshot['fingerprint'], 'archive': relative.as_posix(),
               'source_files': expected_files,
               'manifest_sha256': _hash(archive / 'manifest.json'), 'captured_at': _now(),
               'status': 'preserved_pending_reconciliation'}
    _verify_capture(root, receipt)
    return namespace + ':' + snapshot['fingerprint'], receipt


def _initialize(root, machine):
    """Publish a fresh identity/database with an explicit, retryable execution record."""
    state = state_directory(root)
    pending = state / 'adoption.json'
    record = json.loads(pending.read_text()) if pending.exists() else None
    if record is None:
        record = {'format_version': 1, 'operation': 'onboard-initialize', 'status': 'pending',
                  'machine': machine, 'library_id': str(uuid.uuid4()), 'created_at': _now()}
        atomic_json(pending, record)
    if not isinstance(record, dict) or record.get('operation') != 'onboard-initialize' or record.get('machine') != machine:
        raise ValueError('different initialization or adoption is pending; repeat its original command')
    _validate_initialization(record)
    identity = library_identity(root)
    if identity is not None and identity != record['library_id']:
        raise ValueError('initialization identity differs from its retained execution record')
    if identity is None:
        atomic_json(state / 'library.json', {'format_version': 1, 'library_id': record['library_id'],
                                           'created_at': record['created_at']})
    database = LibraryDatabase(state / 'library.sqlite')
    database.bind_root(root)
    record['status'] = 'complete'
    record['completed_at'] = _now()
    atomic_json(pending, record)


def _validate_initialization(record):
    if not isinstance(record.get('created_at'), str) or not record['created_at'] or not isinstance(record.get('library_id'), str):
        raise ValueError('invalid retained initialization record')
    try:
        uuid.UUID(record['library_id'])
    except (ValueError, TypeError) as exc:
        raise ValueError('invalid initialization library identity') from exc


def onboard(root: Path, machine: str, *, defer_machines=(), legacy_db: Path | None = None,
            include=(), backup_dir: Path | None = None, apply: bool = False):
    """Preview or apply setup for this machine, preserving deferred history.

    Existing portable decisions stay authoritative. Historical captures await
    reconciliation without blocking work; interrupted publication must resume.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f'library root is unavailable: {root}')
    if not machine.strip() or any(not name.strip() for name in defer_machines):
        raise ValueError('machine labels must not be empty')
    state = state_directory(root)
    portable = state / 'library.sqlite'
    metadata = _metadata(root)
    searched = getattr(config, 'LEGACY_MANIFEST_DIR', config.MANIFEST_DIR) / 'sample-library.sqlite'
    source = Path(legacy_db).resolve() if legacy_db is not None else (searched.resolve() if searched.is_file() else None)
    if source == portable:
        source = None
    inputs = {Path(path).resolve() for path in include}
    known = searched.parent.resolve()
    if known.is_dir() and not known.is_relative_to(root) and (source is None or source.is_relative_to(known)):
        # This is the known local manifests directory, never a filesystem crawl.
        _included_files(known, source)  # Reject unsuitable evidence rather than omit it silently.
        inputs.add(known)
    if source is not None:
        # Absolute paths can coincide across Macs. Preserve every known input
        # available here, while leaving unavailable foreign roots deferred.
        inputs.update(_available_source_inputs(
            receipt for receipt in metadata['captures'].values()
            if receipt.get('source_database') == str(source)))
    if any(path == root or root.is_relative_to(path) or path.is_relative_to(state) for path in inputs):
        raise ValueError('include historical evidence outside the active portable state, never the audio library itself')
    snapshot = source_snapshot(source, inputs)
    pending_file = state / 'adoption.json'
    pending = json.loads(pending_file.read_text()) if pending_file.is_file() else None
    if pending is not None and not isinstance(pending, dict):
        raise ValueError('invalid adoption metadata')
    initializing = pending is not None and pending.get('status') != 'complete' and pending.get('operation') == 'onboard-initialize'
    adopting = pending is not None and pending.get('status') != 'complete' and not initializing
    if pending is not None and pending.get('format_version') != 1:
        raise ValueError('unsupported adoption metadata')
    if initializing:
        _validate_initialization(pending)
        action = 'initialize'
        if pending.get('machine') != machine:
            raise ValueError('another machine initialization is pending; repeat the original command')
    elif adopting:
        action = 'adopt'
    elif portable.exists():
        info = inspect_database(portable)
        if info['detected_version'] != SCHEMA_VERSION or info['declared_version'] != SCHEMA_VERSION:
            action = 'migrate'
        else:
            LibraryDatabase(portable, readonly=True).bind_root(root, create=False)
            action = 'reuse'
    else:
        if library_identity(root) is not None:
            raise ValueError('library identity exists without its database; restore it before onboarding')
        action = 'adopt' if source is not None else 'initialize'
    if source is not None or snapshot['files']:
        namespace = hashlib.sha256(machine.encode()).hexdigest()[:12]
        candidate = _state_path(root, Path('history') / namespace / snapshot['fingerprint'])
        if candidate.exists():
            expected = {row['path']: {'sha256': row['sha256'], 'size': row['size']} for row in snapshot['files']}
            if source is not None:
                expected['library.sqlite'] = {'sha256': snapshot['database_sha256'], 'size': snapshot['database_size']}
            _verify_archive(candidate, expected, snapshot['fingerprint'])
    report = {'command': 'onboard', 'machine': machine, 'root': str(root), 'database': str(portable),
              'action': action, 'apply': apply, 'searched_legacy_database': str(searched),
              'source_database': str(source) if source else None, 'included_evidence': snapshot['includes'],
              'history': {'coverage': 'incomplete', 'deferred_machines': sorted((set(metadata['deferred_machines']) | set(defer_machines)) - {machine}),
                          'note': 'No approval is inferred from audio placement; unavailable and unreconciled history remains explicit.'}}
    if not apply:
        return report
    with library_lock(root, purpose='onboard machine', allow_adoption=initializing or adopting or action == 'initialize'):
        # Metadata and source can change between preview and lock acquisition.
        metadata = _metadata(root)
        if source_snapshot(source, inputs)['fingerprint'] != snapshot['fingerprint']:
            raise ValueError('local history changed before onboarding; refresh the preview')
        if action == 'initialize':
            _initialize(root, machine)
        elif action == 'adopt':
            if source is None:
                raise ValueError('the original source database is required to resume adoption')
            destination = backup_dir or _state_path(root, Path('backups') / ('onboard-' + hashlib.sha256(machine.encode()).hexdigest()[:12]))
            adopt_database(source, portable, root=root, backup_dir=destination,
                           include=tuple(Path(path) for path in snapshot['includes']), apply=True)
        elif action == 'migrate':
            migrate_database(portable, root=root, backup_dir=backup_dir, apply=True)
        # Reusing an established portable database performs no SQL writes.
        identity = library_identity(root)
        metadata['library_id'] = identity
        captures = list(metadata['machines'].get(machine, {}).get('capture_ids', []))
        if source is not None or snapshot['files']:
            existing = next(((key, value) for key, value in metadata['captures'].items()
                             if value['machine'] == machine and value['source_fingerprint'] == snapshot['fingerprint']), None)
            if existing:
                capture_id, receipt = existing
                _verify_capture(root, receipt)
            else:
                capture_id, receipt = _publish_capture(root, machine, snapshot)
                metadata['captures'][capture_id] = receipt
            if capture_id not in captures:
                captures.append(capture_id)
            history_status = 'adopted' if action == 'adopt' else 'preserved_pending_reconciliation'
        else:
            history_status = metadata['machines'].get(machine, {}).get('history_status', 'no_local_history_found')
        metadata['machines'][machine] = {'history_status': history_status, 'capture_ids': captures,
                                         'host_hint': socket.gethostname()}
        metadata['deferred_machines'] = sorted((set(metadata['deferred_machines']) | set(defer_machines)) - {machine})
        atomic_json(state / 'onboarding.json', metadata)
        report['history'] = history_report(root)
        report['library_id'] = identity
        report['verified'] = True
        return report
