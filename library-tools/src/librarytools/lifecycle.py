"""Read-only diagnostics and verified, portable state backup/restore."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import uuid
from contextlib import closing, nullcontext
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .schema import SCHEMA_VERSION, inspect_database, readonly_database
from .state import library_identity, state_directory


def _hash(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _write_json(path: Path, data):
    with path.open('x', encoding='utf-8') as out:
        json.dump(data, out, indent=2, sort_keys=True)
        out.write('\n')
        out.flush()
        os.fsync(out.fileno())


def backup_bundle(database: Path, destination: Path, *, root: Path | None = None,
                  include: tuple[Path, ...] = ()) -> dict:
    """Snapshot SQLite plus all durable state. No source audio is copied.

    Additional evidence directories (legacy labels/manifests/config) are opt-in
    and retained under imports/<name>, with their source path in the manifest.
    """
    from .locking import database_lock, library_lock
    database, destination = Path(database).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError(f'backup destination already exists: {destination}')
    if not database.is_file():
        raise ValueError(f'library database not found: {database}')
    lock = library_lock(root, purpose='backup', allow_recovery=True, allow_adoption=True) if root is not None else database_lock(database, 'backup')
    with lock:
        # Unlike immutable readers, SQLite backup also includes committed WAL data.
        destination.mkdir(parents=True)
        state = destination / 'state'
        state.mkdir()
        try:
            with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as source:
                with closing(sqlite3.connect(state / 'library.sqlite')) as target:
                    source.backup(target)
            inspect_database(state / 'library.sqlite')
            copied = []
            if root is not None:
                state_root = state_directory(root)
                copied.append({'source': str(state_root), 'destination': '.'})
                if state_root.is_dir():
                    _copy_evidence(state_root, state, database=database, excluded=destination)
            for source in include:
                source = Path(source).resolve()
                if not source.exists():
                    raise ValueError(f'additional evidence not found: {source}')
                target = state / 'imports' / source.name
                if target.exists():
                    raise ValueError(f'duplicate evidence destination: {source.name}')
                if source.is_dir():
                    _copy_evidence(source, target, database=database, excluded=destination)
                else:
                    _copy_file(source, target)
                copied.append({'source': str(source), 'destination': str(target.relative_to(state))})
            files = {p.relative_to(state).as_posix(): {'sha256': _hash(p), 'size': p.stat().st_size}
                     for p in sorted(state.rglob('*')) if p.is_file()}
            manifest = {'format_version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
                        'source_database': str(database), 'evidence': copied, 'files': files}
            _write_json(destination / 'manifest.json', manifest)
            _verify_bundle(destination)
            return {'destination': str(destination), 'files': len(files), 'verified': True}
        except BaseException:
            # Failed evidence is retained with no valid manifest rather than called a backup.
            raise


def _copy_file(source: Path, target: Path):
    from . import config
    if source.is_symlink():
        raise ValueError(f'evidence symlink must be reconciled explicitly: {source}')
    if source.suffix.lower() in config.SOURCE_EXTS:
        raise ValueError(f'audio is not part of a state backup: {source}')
    before = source.stat()
    with source.open('rb') as stream:
        sqlite_file = stream.read(16) == b'SQLite format 3\x00'
    with readonly_database(source) if sqlite_file else nullcontext():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        after = source.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns) or _hash(source) != _hash(target):
            raise ValueError(f'evidence changed during backup: {source}')


def _copy_evidence(source: Path, target: Path, *, database: Path, excluded: Path):
    def fail(error):
        raise error
    for directory, dirs, names in os.walk(source, onerror=fail, followlinks=False):
        base = Path(directory)
        dirs[:] = [d for d in dirs if d not in {'backups', 'cache', 'caches', 'tmp'}
                   and not (base / d).resolve().is_relative_to(excluded)]
        for name in dirs:
            if (base / name).is_symlink():
                raise ValueError(f'evidence directory is a symlink: {base / name}')
        for name in names:
            path = base / name
            if path.resolve() == database or name.endswith(('.writer.lock', '-wal', '-shm', '-journal')) or name == 'writer.lock':
                continue
            relative = path.relative_to(source)
            output = target / relative
            if output.exists():
                # The SQLite backup API already supplied the authoritative DB.
                if relative.as_posix() == 'library.sqlite':
                    continue
                raise ValueError(f'backup evidence collision: {relative}')
            _copy_file(path, output)


def _verify_bundle(bundle: Path) -> dict:
    manifest = json.loads((bundle / 'manifest.json').read_text(encoding='utf-8'))
    if (not isinstance(manifest, dict)
            or type(manifest.get('format_version')) is not int
            or manifest['format_version'] != 1
            or not isinstance(manifest.get('files'), dict)):
        raise ValueError('unsupported backup format')
    state = (bundle / 'state').resolve()
    for name, evidence in manifest['files'].items():
        if (not isinstance(evidence, dict)
                or type(evidence.get('size')) is not int or evidence['size'] < 0
                or not isinstance(evidence.get('sha256'), str)
                or len(evidence['sha256']) != 64
                or any(char not in '0123456789abcdef' for char in evidence['sha256'])):
            raise ValueError(f'invalid backup file metadata: {name}')
        relative = Path(name)
        path = state / relative
        if relative.is_absolute() or '..' in relative.parts or path.is_symlink() or not path.resolve().is_relative_to(state):
            raise ValueError(f'invalid backup path: {name}')
        if not path.is_file() or path.stat().st_size != evidence['size'] or _hash(path) != evidence['sha256']:
            raise ValueError(f'backup checksum mismatch: {name}')
    if 'library.sqlite' not in manifest['files']:
        raise ValueError('backup has no database')
    inspect_database(state / 'library.sqlite')
    return manifest


def restore_bundle(bundle: Path, destination: Path, *, apply: bool = True) -> dict:
    """Restore verified state into a new directory; never adopt or overwrite live state."""
    bundle, destination = Path(bundle).resolve(), Path(destination).resolve()
    manifest = _verify_bundle(bundle)
    if destination.exists():
        raise ValueError(f'restore destination already exists: {destination}')
    report = {'source': str(bundle), 'destination': str(destination), 'files': len(manifest['files']), 'apply': apply}
    if not apply:
        return report
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name('.restore-' + uuid.uuid4().hex)
    temporary.mkdir()
    try:
        for relative, evidence in manifest['files'].items():
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bundle / 'state' / relative, target)
            if _hash(target) != evidence['sha256']:
                raise ValueError(f'backup checksum changed during restoration: {relative}')
        inspect_database(temporary / 'library.sqlite')
        if destination.exists():
            raise ValueError('restore destination appeared during verification')
        temporary.rename(destination)
    except BaseException:
        shutil.rmtree(temporary)
        raise
    return {**report, 'verified': True}


def doctor(root: Path, database_path: Path | None = None) -> dict:
    """Describe available evidence without locks, writes, or migrations."""
    from . import config
    root = Path(root).resolve()
    state = state_directory(root)
    database = Path(database_path).resolve() if database_path is not None else state / 'library.sqlite'
    result = {'root': str(root), 'root_available': root.is_dir(), 'state_directory': str(state),
              'database': {'path': str(database), 'status': 'missing'}, 'issues': [],
              'runtime': {'python': sys.version.split()[0], 'platform': platform.platform(),
                          'sqlite': sqlite3.sqlite_version},
              'evidence': [], 'operations': [], 'retention': 'human decisions and recovery evidence are retained indefinitely'}
    packages = {}
    for package, distribution in (('library-tools', 'librarytools'), ('sample-tools', 'sampletools'), ('ableton-tools', 'abletontools')):
        try:
            packages[package] = version(distribution)
        except PackageNotFoundError:
            packages[package] = None
    result['runtime']['packages'] = packages
    for binary in ('ffmpeg', 'ffprobe'):
        executable = shutil.which(binary)
        result['runtime'][binary] = None
        if executable:
            try:
                completed = subprocess.run([executable, '-version'], capture_output=True, text=True, timeout=5, check=False)
                result['runtime'][binary] = completed.stdout.splitlines()[0] if completed.stdout else f'exit {completed.returncode}'
            except (OSError, subprocess.TimeoutExpired) as exc:
                result['runtime'][binary] = str(exc)
    if not root.is_dir():
        result['issues'].append('library root is unavailable')
        return result
    try:
        result['library_id'] = library_identity(root)
    except ValueError as exc:
        result['issues'].append(str(exc))
    adoption = state / 'adoption.json'
    if adoption.is_file():
        try:
            result['adoption'] = json.loads(adoption.read_text(encoding='utf-8'))
            if not isinstance(result['adoption'], dict):
                raise ValueError('invalid adoption record')
            if result['adoption'].get('format_version') != 1 or result['adoption'].get('status') != 'complete':
                result['issues'].append('library adoption execution is incomplete; repeat the original sample-library onboard or migrate command to finish publication')
        except (ValueError, OSError) as exc:
            result['issues'].append(f'cannot inspect adoption record: {exc}')
    try:
        from .onboarding import history_report, assert_captured_sources_current
        history = history_report(root)
        if history is not None:
            result['history'] = history
            result['issues'].append('historical coverage is incomplete or awaits reconciliation; this alone does not block portable library work')
            assert_captured_sources_current(root)
    except (ValueError, OSError) as exc:
        result['issues'].append(f'historical coverage: {exc}')
    legacy = getattr(config, 'LEGACY_MANIFEST_DIR', config.MANIFEST_DIR) / 'sample-library.sqlite'
    result['legacy_database'] = str(legacy) if legacy.is_file() else None
    if legacy.is_file() and legacy.resolve() != database.resolve():
        from .state import legacy_is_superseded
        result['legacy_superseded'] = legacy_is_superseded(root, legacy)
        if not result['legacy_superseded']:
            result['issues'].append('legacy state requires reconciliation; no databases were merged')
    if database.is_file():
        try:
            info = inspect_database(database)
            result['database'].update(info, status='current' if info['detected_version'] == SCHEMA_VERSION and info['declared_version'] == SCHEMA_VERSION else 'migration_required')
            with readonly_database(database) as conn:
                result['counts'] = {table: conn.execute(f'select count(*) from {table}').fetchone()[0]
                                    for table in ('assets', 'locations', 'reviews', 'promotions')}
                result['incomplete_scans'] = [dict(r) for r in conn.execute("select * from scans where status='incomplete'")]
                latest = conn.execute("select scan_id,completed_at from scans where status='complete' order by completed_at desc limit 1").fetchone()
                for scan in result['incomplete_scans']:
                    scan['superseded_by'] = latest['scan_id'] if latest is not None and latest['completed_at'] > scan['started_at'] else None
                locations = [r[0] for r in conn.execute('select path from locations where exists_now=1')]
                result['invalid_locations'] = [name for name in locations if Path(name).is_absolute() or '..' in Path(name).parts
                                               or not (root / name).resolve().is_relative_to(root)]
                result['missing_locations'] = [name for name in locations if name not in result['invalid_locations'] and not (root / name).is_file()]
                if info['detected_version'] == SCHEMA_VERSION:
                    result['promotion_discrepancies'] = [dict(row) for row in conn.execute("select sample_id,curated_path,source_path,run_id,status from promotions where status='missing'")]
                    identity = conn.execute('select library_id from library_identity where singleton=1').fetchone()
                    if identity is None:
                        result['issues'].append('database is not bound to a library identity')
                    elif identity[0] != result.get('library_id'):
                        result['issues'].append('database and library identity do not match')
                    result['features'] = {r[0]: r[1] for r in conn.execute("select case when audio_error<>'' then 'failed' when extractor_version='' then 'unversioned' when extractor_version<>'acoustic-v1' then 'stale' when provenance<>'measured' then 'imported' else 'measured' end as status,count(*) from asset_features group by status")}
            if any(scan['superseded_by'] is None for scan in result.get('incomplete_scans', [])):
                result['issues'].append('incomplete scans retained; rerun scan to publish a fresh complete inventory')
            if result.get('missing_locations'):
                result['issues'].append('indexed audio locations are currently missing')
            if result.get('invalid_locations'):
                result['issues'].append('indexed audio contains paths outside this library; reconcile before use')
            if result.get('promotion_discrepancies'):
                result['issues'].append('recorded promotion copies are missing or changed; approval history and discrepancies are retained')
        except (ValueError, OSError, sqlite3.DatabaseError) as exc:
            result['database'].update(status='error', error=str(exc))
            result['issues'].append(str(exc))
    else:
        result['issues'].append('library database is missing; preview sample-library onboard --machine NAME on this machine')
    try:
        from .operations import journals
        result['operations'] = [{'path': str(path), 'operation_id': data['operation_id'], 'status': data['status'], 'kind': data['kind']}
                                for path, data in journals(root)]
        if any(row['status'] != 'complete' for row in result['operations']):
            result['issues'].append('incomplete operations require sample-library recover review')
    except (ValueError, OSError) as exc:
        result['issues'].append(str(exc))
    if state.is_dir():
        for path in sorted(state.rglob('*')):
            if path.is_file() and not path.is_symlink():
                result['evidence'].append({'path': path.relative_to(state).as_posix(), 'bytes': path.stat().st_size})
    result['state_bytes'] = sum(row['bytes'] for row in result['evidence'])
    return result


def maintenance_preview(root: Path, database_path: Path | None = None) -> dict:
    """Measure rebuildable cache growth and temporary evidence; never delete."""
    root = Path(root).resolve()
    state = state_directory(root)
    candidates = []
    for name in ('cache', 'caches', 'tmp'):
        directory = state / name
        if directory.is_dir() and not directory.is_symlink():
            for path in sorted(directory.rglob('*')):
                if path.is_file() and not path.is_symlink():
                    candidates.append({'path': path.relative_to(state).as_posix(), 'bytes': path.stat().st_size})
    partial_copies = []
    curated = root / 'CURATED'
    if curated.is_dir() and not curated.is_symlink():
        def fail(error):
            raise error
        for directory, dirs, names in os.walk(curated, followlinks=False, onerror=fail):
            base = Path(directory)
            dirs[:] = [name for name in dirs if not (base / name).is_symlink()]
            for name in sorted(names):
                path = base / name
                if name.startswith('.') and '.eidetic-copy-' in name and name.endswith('.partial') and path.is_file() and not path.is_symlink():
                    partial_copies.append({'path': path.relative_to(root).as_posix(),
                                           'bytes': path.stat().st_size, 'status': 'requires_recovery_review'})
    database = Path(database_path) if database_path is not None else state / 'library.sqlite'
    return {'apply': False, 'candidates': candidates, 'partial_copies': sorted(partial_copies, key=lambda row: row['path']),
            'database_cache': _database_cache_usage(database),
            'retained': 'Audio, labels, manifests, histories, quarantine and recovery records are never removed.'}


def _database_cache_usage(database: Path) -> dict:
    """Inventory cache tables only, leaving decisions and provenance out of cleanup."""
    report = {'path': str(database), 'status': 'missing', 'tables': {}, 'warnings': []}
    if not database.is_file():
        return report
    try:
        info = inspect_database(database)
        tables = {}
        with readonly_database(database) as conn:
            available = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
            for table, policy in (('audio_embeddings', 'excerpt_policy'), ('prompt_embeddings', 'prompt_policy')):
                if table not in available:
                    continue
                groups = [dict(row) for row in conn.execute(
                    f'select model_id,model_revision,{policy},count(*) as rows,coalesce(sum(length(embedding)),0) as blob_bytes '
                    f'from {table} group by model_id,model_revision,{policy} order by model_id,model_revision,{policy}')]
                tables[table] = {'rows': sum(row['rows'] for row in groups),
                                 'blob_bytes': sum(row['blob_bytes'] for row in groups), 'versions': groups}
            tables['hash_cache'] = {'rows': conn.execute('select count(*) from hash_cache').fetchone()[0]}
            if info['detected_version'] == SCHEMA_VERSION:
                groups = [dict(row) for row in conn.execute(
                    "select extractor_version,provenance,case when audio_error<>'' then 'failed' "
                    "when extractor_version='' then 'unversioned' when extractor_version<>'acoustic-v1' then 'stale' "
                    "else 'current' end as status,count(*) as rows,coalesce(sum(length(cast(payload_json as blob))),0) as payload_bytes "
                    "from asset_features group by extractor_version,provenance,status order by extractor_version,provenance,status")]
            else:
                groups = [dict(row) for row in conn.execute(
                    "select '' as extractor_version,'legacy' as provenance,"
                    "case when audio_error<>'' then 'failed' else 'unversioned' end as status,"
                    "count(*) as rows,coalesce(sum(length(cast(payload_json as blob))),0) as payload_bytes "
                    "from asset_features group by status order by status")]
            tables['asset_features'] = {'rows': sum(row['rows'] for row in groups),
                                       'payload_bytes': sum(row['payload_bytes'] for row in groups),
                                       'current_extractor_version': 'acoustic-v1', 'versions': groups}
            report['database_bytes'] = database.stat().st_size
            report['free_page_bytes'] = conn.execute('pragma freelist_count').fetchone()[0] * conn.execute('pragma page_size').fetchone()[0]
        for status in ('unversioned', 'stale'):
            rows = sum(group['rows'] for group in groups
                       if (group['extractor_version'] == '' if status == 'unversioned'
                           else group['extractor_version'] not in ('', 'acoustic-v1')))
            if rows:
                report['warnings'].append(f'{rows} {status} feature records require remeasurement review; retained unchanged')
        report.update(status='available', schema_version=info['detected_version'], tables=tables)
    except (ValueError, OSError, sqlite3.DatabaseError) as exc:
        report.update(status='error', error=str(exc))
    return report


def adopt_database(source: Path, destination: Path, *, root: Path, backup_dir: Path | None = None,
                   include: tuple[Path, ...] = (), apply: bool = False) -> dict:
    """Adopt a migrated copy, retaining a retryable record until every file is verified."""
    from .inventory import LibraryDatabase
    from .locking import library_lock
    from .operations import atomic_json
    from .schema import migrate_database
    source, destination, root = Path(source).resolve(), Path(destination).resolve(), Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f'library root is unavailable: {root}')
    if destination != state_directory(root) / 'library.sqlite':
        raise ValueError('adoption destination must be ROOT/.eidetic/library.sqlite; use in-place migration for an explicit external database')
    info = inspect_database(source)
    state = state_directory(root)
    pending = state / 'adoption.json'
    requested = [str(Path(path).resolve()) for path in include]
    record = json.loads(pending.read_text(encoding='utf-8')) if pending.exists() else None
    if record is not None and record.get('status') == 'complete':
        raise ValueError('library adoption already completed; inspect state with doctor')
    if record is not None:
        if record.get('format_version') != 1 or record.get('source_database') != str(source) or record.get('destination') != str(destination) or record.get('includes') != requested:
            raise ValueError('different library adoption is pending; repeat its original command or reconcile the retained evidence')
        if record['source_sha256'] != _hash(source):
            raise ValueError('source database changed since adoption started; preserve and reconcile both versions')
        backup = Path(record['backup'])
        staging = Path(record['staging'])
    else:
        if destination.exists():
            raise ValueError('migration destination already exists; divergent databases must be reconciled, never merged automatically')
        backup = Path(backup_dir).resolve() if backup_dir else source.parent / 'backups' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        if backup.exists():
            raise ValueError(f'backup destination already exists: {backup}')
        staging = state / ('.adoption-' + uuid.uuid4().hex)
    # Decide all import destinations and collisions before any publication.
    names = [Path(path).name for path in requested]
    if len(set(names)) != len(names):
        raise ValueError('included evidence directories must have distinct names')
    for name, path in zip(names, requested):
        if not Path(path).exists():
            raise ValueError(f'additional evidence not found: {path}')
        if record is None and (state / 'imports' / name).exists():
            raise ValueError(f'imported evidence already exists: {name}; reconcile before adoption')
    report = {**info, 'source_database': str(source), 'destination': str(destination),
              'backup': str(backup), 'apply': apply, 'included_evidence': requested,
              'schema_version': SCHEMA_VERSION, 'resuming': record is not None}
    if not apply:
        return report
    with library_lock(root, purpose='adopt migrated library', allow_recovery=True, allow_adoption=True):
        if record is None:
            record = {'format_version': 1, 'status': 'pending', 'source_database': str(source),
                      'source_sha256': _hash(source), 'destination': str(destination),
                      'backup': str(backup), 'staging': str(staging), 'includes': requested,
                      'created_at': datetime.now(timezone.utc).isoformat()}
            atomic_json(pending, record)
        if not (backup / 'manifest.json').is_file():
            if backup.exists():
                raise ValueError(f'incomplete backup retained at {backup}; reconcile it before repeating adoption')
            backup_bundle(source, backup, root=root, include=include)
        manifest = _verify_bundle(backup)
        if not staging.exists():
            restore_bundle(backup, staging)
        working = staging / 'library.sqlite'
        if not destination.exists():
            if inspect_database(working)['detected_version'] != SCHEMA_VERSION:
                migrate_database(working, apply=True, backup_dir=staging / 'before-migration')
            # Stage and verify every human file before publishing the database.
            for name in names:
                source_evidence = staging / 'imports' / name
                final_evidence = state / 'imports' / name
                prefix = 'imports/' + name
                for relative, expected in manifest['files'].items():
                    if relative == prefix or relative.startswith(prefix + '/'):
                        candidate = (state if final_evidence.exists() else staging) / relative
                        if not candidate.is_file() or _hash(candidate) != expected['sha256']:
                            raise ValueError(f'imported evidence checksum mismatch: {relative}')
                if not final_evidence.exists():
                    final_evidence.parent.mkdir(parents=True, exist_ok=True)
                    source_evidence.rename(final_evidence)
            database = LibraryDatabase(working)
            record['library_id'] = database.bind_root(root)
            record['database_sha256'] = _hash(working)
            atomic_json(pending, record)
            inspect_database(source)  # Also reject new committed WAL evidence.
            if _hash(source) != record['source_sha256']:
                raise ValueError('source database changed while adopting; reconcile the retained versions before publication')
            if destination.exists():
                raise ValueError('adoption destination appeared; refusing to overwrite')
            working.rename(destination)
        if 'database_sha256' not in record or _hash(destination) != record['database_sha256']:
            raise ValueError('published adoption database differs from its recorded checksum; reconcile before continuing')
        # A crash after rename resumes here and verifies the already-published state.
        inspect_database(destination)
        if library_identity(root) != record.get('library_id'):
            raise ValueError('adopted library identity differs from its recorded identity')
        for relative, expected in manifest['files'].items():
            if relative.startswith('imports/'):
                candidate = state / relative
                if not candidate.is_file() or _hash(candidate) != expected['sha256']:
                    raise ValueError(f'adopted evidence checksum mismatch: {relative}')
        record['status'] = 'complete'
        record['completed_at'] = datetime.now(timezone.utc).isoformat()
        atomic_json(pending, record)
        return {**report, 'verified': True, 'library_id': record['library_id']}
