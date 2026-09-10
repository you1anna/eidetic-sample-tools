"""Shared verified session storage for source audition and the optional vocal lab.

This module reads prepared evidence using only the standard library. It never
loads an audio engine, interprets musical preferences, or approves exports.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile


class VibeError(ValueError):
    """An audition cannot safely be prepared, rendered or recorded."""


_ID = re.compile(r'[a-f0-9]{64}')


def hash_file(path: Path) -> str:
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError('object required')
        return value
    except (OSError, ValueError) as exc:
        raise VibeError(f'Cannot read audition evidence: {path.name}: {exc}') from exc


def write_json(path: Path, value: dict) -> None:
    descriptor, name = tempfile.mkstemp(prefix='.write-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, indent=2, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def contained_path(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise VibeError('Audio path escapes its registered root')
    return resolved


def validate_identifier(value: object) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise VibeError('Invalid audition identifier')
    return value


def load_session(session_dir: Path) -> dict:
    path = contained_path(session_dir, session_dir / 'session.json')
    state = read_json(path)
    if state.get('schema_version') == 2:
        return _validate_v2(state, session_dir)
    if state.get('schema_version') != 1:
        raise VibeError('Unsupported audition session version')
    if not isinstance(state.get('sources'), dict) or not isinstance(state.get('root'), str):
        raise VibeError('Invalid audition session')
    if not finite_number(state.get('bpm')) or not 60 <= state['bpm'] <= 180 or state.get('bars') != 8:
        raise VibeError('Invalid audition tempo or scene length')
    for source_id, item in state['sources'].items():
        validate_identifier(source_id)
        if (not isinstance(item, dict) or item.get('id') != source_id
                or not all(isinstance(item.get(key), str) for key in ('name', 'path', 'preview_hash'))
                or not finite_number(item.get('duration_s')) or not 0 < item['duration_s'] <= 120
                or item.get('suggested_bars') not in (1, 2, 4, 8)
                or not isinstance(item.get('waveform'), list) or not 1 <= len(item['waveform']) <= 512
                or not all(finite_number(peak) and peak >= 0 for peak in item['waveform'])):
            raise VibeError('Invalid source evidence in audition session; prepare a new session')
        validate_identifier(item['preview_hash'])
    for role in ('anchors', 'vocals'):
        ids = state.get(role)
        if not isinstance(ids, list) or not 1 <= len(ids) <= 12:
            raise VibeError(f'Invalid {role} in audition session')
        for item in ids:
            validate_identifier(item)
            if item not in state['sources']:
                raise VibeError('Audition source is missing from session')
    return state


def finite_number(value) -> bool:
    try:
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    except OverflowError:
        return False


def verify_source(state: dict, source_id: str) -> Path:
    validate_identifier(source_id)
    source = state['sources'].get(source_id)
    if not isinstance(source, dict) or not isinstance(source.get('path'), str):
        raise VibeError('Source is not registered in this audition')
    root = Path(state['root'])
    if state.get('schema_version') == 2:
        from .state import library_identity
        if library_identity(root) != state['library_id']:
            raise VibeError('Library identity changed or its drive is unavailable')
    path = contained_path(root, root / source['path'])
    if not path.is_file():
        raise VibeError('Source is missing; connect its drive before auditioning')
    if hash_file(path) != source_id:
        raise VibeError('Source bytes changed since preparation; prepare a new session')
    return path


def source_audio(session_dir: Path, source_id: str) -> Path:
    state = load_session(session_dir)
    verify_source(state, source_id)
    path = contained_path(session_dir, session_dir / 'sources' / f'{source_id}.wav')
    if not path.is_file() or hash_file(path) != state['sources'][source_id].get('preview_hash'):
        raise VibeError('Prepared source preview is missing or changed')
    return path


def source_ids(state: dict) -> list[str]:
    """Distinct candidates in their explicitly supplied listening order."""
    if state['schema_version'] == 2:
        return list(state['candidate_ids'])
    return list(dict.fromkeys(state['anchors'] + state['vocals']))


def source_state(session_dir: Path) -> dict:
    """Only the source fields the chooser displays; no vocal-lab history."""
    state = load_session(Path(session_dir))
    if state['schema_version'] == 2:
        from .vibe_collection import batch_state
        return batch_state(Path(session_dir))
    anchors = set(state['anchors'])
    sources = []
    for source_id in source_ids(state):
        item = state['sources'][source_id]
        sources.append({key: item[key] for key in ('id', 'name', 'duration_s')} | {
            'kind': 'Groove candidate' if source_id in anchors else 'Vocal candidate',
            # Three decimals is finer than the audition waveform strip can draw.
            'waveform': [round(peak, 3) for peak in item['waveform']],
        })
    return {'sources': sources}


def _validate_v2(state: dict, session_dir: Path) -> dict:
    import uuid
    try:
        uuid.UUID(state['library_id'])
        validate_identifier(state['plan_id'])
        root = Path(state['root']).resolve()
        if Path(session_dir).resolve().is_relative_to(root):
            raise VibeError('Working audio must be outside the source library')
        ids, sources = state['candidate_ids'], state['sources']
        if (not isinstance(ids, list) or not ids or len(ids) != len(set(ids))
                or not isinstance(sources, dict) or set(ids) != set(sources)
                or state['batch_size'] != 12 or type(state['batch_index']) is not int
                or not 0 <= state['batch_index'] < (len(ids) + 11) // 12):
            raise VibeError('Invalid collection audition structure')
        for sid in ids:
            validate_identifier(sid)
            item = sources[sid]
            if item['id'] != sid or item['sample_id'] != sid:
                raise VibeError('Invalid sample identity in session')
            if not all(isinstance(item[key], str) for key in ('path', 'name', 'role', 'history_status', 'timing_status')):
                raise VibeError('Invalid collection source evidence')
            raw = Path(item['path'])
            if raw.is_absolute() or '..' in raw.parts:
                raise VibeError('Invalid collection source path')
            if 'preview_hash' in item:
                validate_identifier(item['preview_hash'])
                if (not finite_number(item['duration_s']) or not 0 < item['duration_s'] <= 120
                        or not isinstance(item['waveform'], list) or not 1 <= len(item['waveform']) <= 512
                        or not all(finite_number(p) and p >= 0 for p in item['waveform'])):
                    raise VibeError('Invalid working audio evidence')
    except (KeyError, TypeError, AttributeError) as exc:
        raise VibeError('Invalid collection audition session') from exc
    return state
