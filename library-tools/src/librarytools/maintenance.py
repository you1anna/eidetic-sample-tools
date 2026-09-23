"""Read-only release/library readiness and the public refresh entry point."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import features, tagstate, tagging
from .inventory import LibraryDatabase, _iter_audio
from .schema import SCHEMA_VERSION, MigrationRequired, readonly_database
from .state import resolve_library_db


def runtime_report(checkout=None):
    from .release_runtime import runtime_report as inspect_runtime
    return inspect_runtime(checkout)


def action(identifier: str, reason: str, root: Path, database_path: Path | None = None, *, command='refresh') -> dict:
    argv = ['sample-library', command, '--root', str(root)]
    if database_path is not None:
        argv += ['--library-db', str(database_path)]
    return {'id': identifier, 'reason': reason, 'argv': argv}


def inventory_status(root: Path, database, check_files: bool) -> dict:
    result = {'checked': check_files, 'added': 0, 'changed': 0, 'missing': 0, 'total_files': None,
              'examples': {'added': [], 'changed': [], 'missing': []}}
    if not check_files:
        return result
    known = {loc.path.as_posix(): loc for loc in database.current_locations()}
    seen = set()
    for path in _iter_audio(root):
        relative = path.relative_to(root).as_posix()
        seen.add(relative)
        stat = path.stat()
        previous = known.get(relative)
        change = 'added' if previous is None else (
            'changed' if (stat.st_size, stat.st_mtime_ns) != (previous.size, previous.mtime_ns) else None)
        if change:
            result[change] += 1
            if len(result['examples'][change]) < 5:
                result['examples'][change].append(relative)
    missing = sorted(set(known) - seen)
    result['missing'] = len(missing)
    result['examples']['missing'] = missing[:5]
    result['total_files'] = len(seen)
    return result


def feature_status(database) -> dict:
    metadata = database.feature_metadata()
    active = {loc.sample_id for loc in database.current_locations()}
    counts = dict(current=0, missing=0, stale=0, failed=0)
    for sid in active:
        row = metadata.get(sid)
        key = 'missing' if row is None else ('failed' if row['audio_error'] else
                    'stale' if row['extractor_version'] != features.FEATURE_VERSION else 'current')
        counts[key] += 1
    return counts


def _execution_blockers(root: Path) -> None:
    from .operations import require_settled
    from .onboarding import _metadata
    from .state import library_identity
    require_settled(root)
    _metadata(root)  # Explicit database selection must still validate portable history.
    adoption = root / '.eidetic/adoption.json'
    if adoption.exists():
        record = json.loads(adoption.read_text())
        if (adoption.is_symlink() or not isinstance(record, dict) or record.get('format_version') != 1
                or record.get('status') != 'complete' or record.get('library_id') != library_identity(root)):
            raise ValueError('library adoption is incomplete; resume the original onboarding/adoption command')


def status(root: Path, database_path: Path | None = None, checkout: Path | None = None,
           check_files: bool = False, *, vocabulary: Path | None = None, retry_failed: bool = False) -> dict:
    root = Path(root).expanduser().resolve()
    runtime = runtime_report(checkout)
    report = {'contract_version': 1, 'status': runtime['status'], 'runtime': runtime,
              'actions': list(runtime.get('actions', [])), 'issues': list(runtime.get('issues', [])),
              'warnings': [], 'library': {'root': str(root), 'database': None}}
    library = report['library']
    try:
        path = resolve_library_db(root, database_path)
        library['database'] = str(path.resolve())
        if not path.is_file():
            raise ValueError('library database is missing; use sample-library onboard to preserve available history')
        # All component reads must describe one stable database observation.
        with readonly_database(path):
            database = LibraryDatabase(path, readonly=True)
            library['library_id'] = database.bind_root(root, create=False)
            _execution_blockers(root)
            library['schema_version'] = SCHEMA_VERSION
            locations = database.current_locations()
            library['counts'] = {'locations': len(locations), 'identities': len({loc.sample_id for loc in locations})}
            library['inventory'] = inventory_status(root, database, check_files)
            with database._connect() as conn:
                latest = conn.execute("select completed_at from scans where status='complete' order by completed_at desc limit 1").fetchone()
                incomplete = conn.execute("select count(*) from scans where status='incomplete' and started_at>?",
                                          (latest[0] if latest else '',)).fetchone()[0]
                discrepancies = conn.execute("select count(*) from promotions where status='missing'").fetchone()[0]
            inventory = library['inventory']
            if incomplete or latest is None or any(inventory[k] for k in ('added', 'changed', 'missing')):
                report['actions'].append(action('scan_inventory',
                    'inventory is incomplete or audio paths have been added, modified or removed', root, database_path))
            if discrepancies:
                report['warnings'].append(f'{discrepancies} recorded promoted copies are missing or changed; review promotion health before export')
            counts = library['features'] = feature_status(database)
            if counts['missing'] or counts['stale'] or (retry_failed and counts['failed']):
                report['actions'].append(action('measure_features',
                    f"measure {counts['missing']} missing and {counts['stale']} outdated identities"
                    + (f"; retry {counts['failed']} failures" if retry_failed else ''), root, database_path))
            if counts['failed']:
                report['warnings'].append(f"{counts['failed']} acoustic measurements failed; existing failures are retained. Retry explicitly with --retry-failed.")
            payload, kind = tagstate.select_vocabulary(root, database, vocabulary)
            tagging.load_vocabulary(payload=payload)
            library['tags'] = tagstate.freshness(database, payload)
            library['tags']['vocabulary_kind'] = kind
            if kind == 'custom':
                report['warnings'].append('using the preserved custom vocabulary; pass --vocabulary to change it')
            if library['tags']['status'] == 'stale':
                report['actions'].append(action('refresh_tags', '; '.join(library['tags']['reasons']), root, database_path))
            _embedding_status(database, report)
            if report['status'] != 'blocked':
                report['status'] = 'action_required' if report['actions'] else 'ready'
            _execution_blockers(root)
            database.bind_root(root, create=False)
    except MigrationRequired as exc:
        report['status'] = 'blocked'
        report['issues'].append(str(exc))
        report['actions'].append(action('migrate_schema', str(exc), root, database_path, command='migrate'))
    except (ValueError, OSError, sqlite3.Error) as exc:
        report['status'] = 'blocked'
        report['issues'].append(str(exc))
        report['actions'].append(action('reconcile_library', str(exc), root, database_path, command='doctor'))
    # Recovery commands must preserve the caller's selection and retry intent.
    # They are previews: applying still requires an explicit --apply.
    for item in report['actions']:
        if item['id'] in {'scan_inventory', 'measure_features', 'refresh_tags'}:
            if vocabulary is not None:
                item['argv'] += ['--vocabulary', str(Path(vocabulary).expanduser().resolve())]
            if retry_failed:
                item['argv'].append('--retry-failed')
            if checkout is not None:
                item['argv'] += ['--checkout', str(Path(checkout).expanduser().resolve())]
    return report


def _embedding_status(database, report):
    from .classification.models import MODEL_SPECS
    from .classification.workers import EXCERPT_POLICY
    specs = {(spec.model_id, spec.revision) for spec in MODEL_SPECS}
    with database._connect() as conn:
        rows = conn.execute('select model_id,model_revision,excerpt_policy,count(*) from audio_embeddings '
                            'group by model_id,model_revision,excerpt_policy').fetchall()
    total = sum(row[3] for row in rows)
    obsolete = sum(row[3] for row in rows if (row[0], row[1]) not in specs or row[2] != EXCERPT_POLICY)
    report['library']['embeddings'] = {'audio_rows': total, 'obsolete_audio_rows': obsolete,
                                       'excerpt_policy': EXCERPT_POLICY}
    if obsolete:
        report['warnings'].append(f'{obsolete} stored audio embeddings use an older model/policy; explicit AI work recomputes affected entries on demand')


def refresh(root: Path, database_path: Path | None = None, *, apply: bool = False,
            retry_failed: bool = False, vocabulary: Path | None = None,
            backup_dir: Path | None = None, checkout: Path | None = None) -> dict:
    from .refresh import run_refresh
    return run_refresh(root, database_path, apply=apply, retry_failed=retry_failed,
                       vocabulary=vocabulary, backup_dir=backup_dir, checkout=checkout)
