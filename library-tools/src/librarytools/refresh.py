"""Apply a reviewed derived-data refresh using existing lifecycle primitives."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from . import features, maintenance, origin, tagging, tagstate
from .inventory import LibraryDatabase, scan_library
from .lifecycle import backup_bundle
from .locking import library_lock
from .operations import atomic_json


def regenerate_tags(root: Path, database, payload: bytes, kind: str) -> int:
    rules = tagging.load_vocabulary(payload=payload)
    locations = database.current_locations()
    resolved = origin.resolve_and_store(database, locations)
    payloads = database.features()
    generated = {}
    for loc in locations:
        if loc.sample_id in generated:
            continue
        found = resolved.get(loc.sample_id)
        sample = tagging.build_sample(loc.sample_id, loc.path, found.origin if found else '',
                                      json.loads(payloads.get(loc.sample_id, '{}')))
        generated[loc.sample_id] = tagging.tags_for(sample, rules)
    tagstate.preserve_vocabulary(root, payload)
    evidence = tagstate.publication_metadata(database, payload, kind, generated)
    database.replace_generated_tags(generated, vocabulary_digest=tagstate.digest(payload), metadata=evidence)
    return sum(len(tags) for tags in generated.values())


def run_refresh(root: Path, database_path: Path | None = None, *, apply=False, retry_failed=False,
                vocabulary=None, backup_dir=None, checkout=None) -> dict:
    root = Path(root).expanduser().resolve()
    def preview():
        return maintenance.status(root, database_path, checkout, True,
                                  vocabulary=vocabulary, retry_failed=retry_failed)
    report = {**preview(), 'apply': bool(apply), 'executed': []}
    if (not apply or report['status'] == 'blocked' or not report['actions']
            or any(a['id'] == 'install_release' for a in report['actions'])):
        return report
    with library_lock(root, purpose='refresh library derived data'):
        report = {**preview(), 'apply': True, 'executed': []}
        if (report['status'] == 'blocked' or not report['actions']
                or any(a['id'] == 'install_release' for a in report['actions'])):
            return report
        database = LibraryDatabase(Path(report['library']['database']))
        database.bind_root(root, create=False)
        payload, kind = tagstate.select_vocabulary(root, database, vocabulary)
        run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
        destination = Path(backup_dir) if backup_dir is not None else root / '.eidetic/backups' / ('refresh-' + run_id)
        backup = backup_bundle(database.path, destination, root=root)
        executed = []
        feature_result = None
        if any(a['id'] == 'scan_inventory' for a in report['actions']):
            scan_library(root, database)
            executed.append('scan_inventory')
        counts = maintenance.feature_status(database)
        if counts['missing'] or counts['stale'] or (retry_failed and counts['failed']):
            locations = database.current_locations()
            feature_result = asdict(features.sync_features(root, database,
                [(loc.sample_id, loc.path, loc.size, loc.mtime_ns) for loc in locations], retry_failed=retry_failed))
            executed.append('measure_features')
        written = regenerate_tags(root, database, payload, kind)
        executed.append('refresh_tags')
        # Failures just attempted remain warnings, not an endless retry request.
        after = maintenance.status(root, database_path, checkout, True, vocabulary=vocabulary)
        result = {**after, 'apply': True, 'executed': executed, 'backup': backup,
                  'features_result': feature_result, 'tags_written': written, 'run_id': run_id}
        receipt = root / '.eidetic/runs' / ('refresh-' + run_id + '.json')
        result['receipt'] = str(receipt)
        atomic_json(receipt, result)
        return result
