"""Portable dependency evidence for atomically published generated tags."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, features, tagging

STATE_KEY = 'tag_refresh_v1'
# Shipped 0.2 vocabulary, retained so an unstamped default is upgraded rather
# than mistaken for a personal vocabulary. Unknown legacy rules are preserved.
LEGACY_DEFAULTS = {'13676f8a401604f7f88c78f2071c785867c702b9095769abd5efd0de649c376e'}


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _rows_digest(rows) -> str:
    result = hashlib.sha256()
    for row in rows:
        result.update(json.dumps(list(row), separators=(',', ':'), ensure_ascii=False).encode())
        result.update(b'\n')
    return result.hexdigest()


def metadata(database) -> dict[str, str]:
    with database._connect() as conn:
        return dict(conn.execute('select key,value from state_metadata'))


def _valid_digest(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def recorded_state(database) -> dict:
    raw = metadata(database).get(STATE_KEY)
    if raw is None:
        return {}
    try:
        state = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError('invalid tag freshness record; preserve and reconcile it') from exc
    if (not isinstance(state, dict) or type(state.get('format_version')) is not int
            or state['format_version'] != 1):
        raise ValueError('unsupported tag freshness record; preserve and reconcile it')
    for name in ('recipe_digest', 'inputs_digest', 'output_digest', 'vocabulary_digest'):
        if not _valid_digest(state.get(name)):
            raise ValueError(f'invalid tag freshness record: {name} must be a SHA-256 digest')
    if state.get('vocabulary_kind') not in ('default', 'custom'):
        raise ValueError('invalid tag freshness record: vocabulary_kind must be default or custom')
    for name in ('feature_version', 'librarytools_version', 'generated_at'):
        if not isinstance(state.get(name), str) or not state[name].strip():
            raise ValueError(f'invalid tag freshness record: {name} must be a nonempty string')
    try:
        generated_at = datetime.fromisoformat(state['generated_at'])
        if generated_at.tzinfo is None:
            raise ValueError('timezone is missing')
    except ValueError as exc:
        raise ValueError('invalid tag freshness record: generated_at must be an ISO timestamp with timezone') from exc
    return state


def select_vocabulary(root: Path, database, explicit: Path | None = None) -> tuple[bytes, str]:
    default = tagging.DEFAULT_VOCABULARY.read_bytes()
    state = recorded_state(database)
    if explicit is not None:
        payload = Path(explicit).read_bytes()
        return payload, 'default' if payload == default else 'custom'
    previous = state.get('vocabulary_digest') or metadata(database).get('vocabulary_digest', '')
    if previous != '' and not _valid_digest(previous):
        raise ValueError('invalid recorded vocabulary digest')
    if state.get('vocabulary_kind') == 'default' or not previous or previous in LEGACY_DEFAULTS or previous == digest(default):
        return default, 'default'
    snapshot = root / '.eidetic/configurations' / f'vocabulary-{previous}.toml'
    if not snapshot.is_file() or snapshot.is_symlink() or digest(snapshot.read_bytes()) != previous:
        raise ValueError('recorded custom vocabulary is unavailable; supply its verified file with --vocabulary')
    return snapshot.read_bytes(), 'custom'


def recipe_digest(payload: bytes) -> str:
    package = Path(__file__).parent
    names = ('review.py', 'tagging.py', 'origin.py', 'lexical.py', 'config.py', 'tagstate.py',
             'refresh.py', 'tag_cli.py')
    rows = [(name, digest((package / name).read_bytes())) for name in names if (package / name).is_file()]
    rows += [('vocabulary', digest(payload)), ('features', features.FEATURE_VERSION)]
    return _rows_digest(rows)


def inputs_digest(database) -> str:
    """Only inputs to tagging: an unrelated release, review or scan ID is not one."""
    rows = []
    active = '(select distinct sample_id from locations where exists_now=1)'
    with database._connect() as conn:
        rows.extend(('location', *row) for row in conn.execute(
            'select path,sample_id,zone,size,mtime_ns from locations where exists_now=1 order by path'))
        rows.extend(('origin', *row) for row in conn.execute(
            f'select o.sample_id,o.origin from origins o join {active} a using(sample_id) order by o.sample_id'))
        rows.extend(('feature', *row) for row in conn.execute(
            f'select f.sample_id,f.extractor_version,f.audio_error,f.payload_json '
            f'from asset_features f join {active} a using(sample_id) order by f.sample_id'))
    return _rows_digest(rows)


def output_digest(database) -> str:
    with database._connect() as conn:
        return _rows_digest(conn.execute("select sample_id,tag_group,tag from tags where source='generated' "
                                         'order by sample_id,tag_group,tag'))


def publication_metadata(database, payload: bytes, kind: str, generated: dict) -> dict[str, str]:
    rows = sorted({(sid, group, tag) for sid, tags in generated.items() for group, tag in tags})
    record = {'format_version': 1, 'recipe_digest': recipe_digest(payload),
              'inputs_digest': inputs_digest(database), 'output_digest': _rows_digest(rows),
              'vocabulary_digest': digest(payload), 'vocabulary_kind': kind,
              'feature_version': features.FEATURE_VERSION, 'librarytools_version': __version__,
              'generated_at': datetime.now(timezone.utc).isoformat()}
    return {STATE_KEY: json.dumps(record, sort_keys=True)}


def freshness(database, payload: bytes) -> dict:
    state = recorded_state(database)
    reasons = []
    if not state:
        reasons.append('generated tags have no dependency record')
    else:
        if state.get('recipe_digest') != recipe_digest(payload):
            reasons.append('role, origin, tag rules or vocabulary changed')
        if state.get('inputs_digest') != inputs_digest(database):
            reasons.append('indexed locations, origins or measurements changed')
        if state.get('output_digest') != output_digest(database):
            reasons.append('generated tag contents differ from the published record')
    return {'status': 'stale' if reasons else 'current', 'reasons': reasons,
            'vocabulary_digest': digest(payload), 'recorded_release': state.get('librarytools_version')}


def preserve_vocabulary(root: Path, payload: bytes) -> None:
    """Publish a complete, durable snapshot without replacing any existing evidence.

    A crash before publication can leave only a hidden staging file; the final
    digest name is created by the same atomic no-replace rename used for audio.
    """
    from .moves import _rename_exclusive
    from .operations import sync_directory
    from .state import state_directory

    path = state_directory(root) / 'configurations' / f'vocabulary-{digest(payload)}.toml'
    if path.parent.is_symlink():
        raise ValueError(f'configuration snapshot directory must not be a symlink: {path.parent}')
    path.parent.mkdir(parents=True, exist_ok=True)

    def verify_existing():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != payload:
            raise ValueError(f'configuration snapshot has changed: {path}')

    if path.exists() or path.is_symlink():
        verify_existing()
        return
    fd, name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.partial', dir=path.parent)
    staging = Path(name)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        try:
            _rename_exclusive(staging, path)
        except FileExistsError:
            verify_existing()
        sync_directory(path.parent)
    finally:
        staging.unlink(missing_ok=True)
