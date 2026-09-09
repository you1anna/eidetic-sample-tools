"""Independent, hash-verified audition sessions; never curation approval."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from datetime import datetime, timezone

import numpy as np
import soundfile as sf

from . import vibe_audio
from .locking import _file_lock
from .vibe_session import (
    VibeError, load_session, source_audio,
    hash_file as _hash, read_json as _json, write_json as _atomic_json,
    contained_path as _contained, validate_identifier as _identifier,
    finite_number as _finite_number, verify_source as _verify_source,
)


_PARTS = ('anchor', 'vocal', 'mix')


def prepare_session(root: Path, output_dir: Path, anchors: list[Path], vocals: list[Path],
                    bpm: float = 140) -> dict:
    """Create browser previews and evidence from an explicit, unranked shortlist."""
    root = Path(root).resolve()
    output_dir = Path(output_dir).absolute()
    if not root.is_dir():
        raise VibeError('Source root is unavailable')
    if output_dir.resolve().is_relative_to(root):
        raise VibeError('Audition output must be outside the source root')
    if output_dir.exists() or output_dir.is_symlink():
        raise VibeError('Audition output already exists; choose a new directory')
    if not _finite_number(bpm) or not 60 <= bpm <= 180:
        raise VibeError('BPM must be a finite number from 60 to 180')
    if not (1 <= len(anchors) <= 12 and 1 <= len(vocals) <= 12):
        raise VibeError('Supply between 1 and 12 candidates for each role')
    state = {'schema_version': 1, 'root': str(root), 'bpm': float(bpm), 'bars': 8,
             'sources': {}, 'anchors': [], 'vocals': []}
    for role, paths in (('anchors', anchors), ('vocals', vocals)):
        for raw in paths:
            path = _contained(root, raw if raw.is_absolute() else root / raw)
            if not path.is_file():
                raise VibeError(f'Audio source is missing: {path.name}')
            source_id = _hash(path)
            try:
                info = vibe_audio.probe_source(path)
            except vibe_audio.AudioError as exc:
                raise VibeError(str(exc)) from exc
            if not 0 < info['duration_s'] <= 120:
                raise VibeError('Pilot sources must be between 0 and 120 seconds')
            state['sources'][source_id] = {'id': source_id, 'name': path.name,
                'path': path.relative_to(root).as_posix(), **info}
            if source_id not in state[role]:
                state[role].append(source_id)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the destination without replacing an existing directory, even in a race.
    output_dir.mkdir()
    try:
        (output_dir / 'sources').mkdir()
        (output_dir / 'renders').mkdir()
        for source_id, item in state['sources'].items():
            source = _verify_source(state, source_id)
            audio = vibe_audio.decode_source(source)
            if not len(audio) or not np.isfinite(audio).all():
                raise VibeError('Source decoded to empty or nonfinite audio')
            peak = float(np.max(np.abs(audio)))
            item['preview_gain'] = min(1.0, .95 / peak) if peak else 1.0
            audio = audio.astype(np.float64) * item['preview_gain']
            target = output_dir / 'sources' / f'{source_id}.wav'
            sf.write(target, audio, 48000, subtype='PCM_24')
            item['preview_hash'] = _hash(target)
            envelope = np.max(np.abs(audio), axis=1)
            item['waveform'] = [float(np.max(chunk)) for chunk in np.array_split(envelope, min(512, len(envelope)))]
            # This estimates bar count assuming the requested tempo, not a detected beat grid.
            item['suggested_bars'] = min((1, 2, 4, 8), key=lambda bars: abs(item['duration_s'] - bars * 240 / bpm))
            _verify_source(state, source_id)
        _atomic_json(output_dir / 'feedback.json', {'schema_version': 1, 'feedback': []})
        _atomic_json(output_dir / 'session.json', state)  # Publish only complete preparation.
    except Exception:
        shutil.rmtree(output_dir)  # This invocation exclusively created this new directory.
        raise
    return session_state(output_dir)


def session_state(session_dir: Path) -> dict:
    state = load_session(session_dir)
    feedback_path = _contained(session_dir, session_dir / 'feedback.json')
    feedback = _feedback(feedback_path)
    def public_item(source_id):
        item = state['sources'][source_id]
        return {key: item[key] for key in ('id', 'name', 'duration_s', 'waveform', 'suggested_bars')}
    return {'bpm': state['bpm'], 'bars': 8, 'anchors': [public_item(i) for i in state['anchors']],
            'vocals': [public_item(i) for i in state['vocals']], 'feedback': feedback}


def _feedback(path: Path) -> list[dict]:
    evidence = _json(path)
    feedback = evidence.get('feedback')
    if evidence.get('schema_version') != 1 or not isinstance(feedback, list):
        raise VibeError('Invalid audition feedback')
    for entry in feedback:
        if (not isinstance(entry, dict) or not isinstance(entry.get('note'), str)
                or entry.get('decision') not in ('works', 'does_not_work', 'unsure')
                or not isinstance(entry.get('selection'), dict)
                or not isinstance(entry['selection'].get('recipe'), dict)):
            raise VibeError('Invalid saved listening decision')
        _identifier(entry.get('render_id'))
        _identifier(entry['selection'].get('anchor_id'))
        _identifier(entry['selection'].get('vocal_id'))
    return feedback


def _selection(state: dict, selection: dict) -> tuple[dict, Path, Path]:
    if not isinstance(selection, dict) or set(selection) != {'anchor_id', 'vocal_id', 'recipe'}:
        raise VibeError('Select one anchor, one vocal and an edit recipe')
    anchor_id, vocal_id = _identifier(selection['anchor_id']), _identifier(selection['vocal_id'])
    if anchor_id not in state['anchors'] or vocal_id not in state['vocals']:
        raise VibeError('Candidate is not registered for the selected role')
    anchor = _verify_source(state, anchor_id)
    vocal = _verify_source(state, vocal_id)
    try:
        recipe = vibe_audio.validate_recipe(selection['recipe'], state['sources'][anchor_id]['duration_s'],
                                            state['sources'][vocal_id]['duration_s'])
    except (vibe_audio.AudioError, TypeError, KeyError) as exc:
        raise VibeError(f'Invalid edit recipe: {exc}') from exc
    return {'anchor_id': anchor_id, 'vocal_id': vocal_id, 'recipe': recipe}, anchor, vocal


def _receipt(session_dir: Path, render_id: str) -> dict:
    render_id = _identifier(render_id)
    directory = _contained(session_dir, session_dir / 'renders' / render_id)
    receipt = _json(_contained(directory, directory / 'receipt.json'))
    if receipt.get('render_id') != render_id or receipt.get('schema_version') != 1:
        raise VibeError('Invalid render receipt')
    identity = receipt.get('identity')
    if not isinstance(identity, dict) or _digest(identity) != render_id:
        raise VibeError('Render recipe evidence changed')
    if receipt.get('selection') != identity.get('selection'):
        raise VibeError('Render selection evidence changed')
    outputs = receipt.get('outputs', {})
    processing = receipt.get('processing')
    if (not isinstance(outputs, dict) or not isinstance(processing, dict)
            or not _finite_number(processing.get('duration_s')) or processing['duration_s'] <= 0):
        raise VibeError('Invalid render output evidence')
    for part in _PARTS:
        path = _contained(directory, directory / f'{part}.wav')
        if not path.is_file() or _hash(path) != outputs.get(part):
            raise VibeError('Rendered audio is missing or changed; choose a new session to rebuild')
    return receipt


def _digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _result(receipt: dict, cache_hit: bool) -> dict:
    render_id = receipt['render_id']
    return {'render_id': render_id, 'selection': receipt['selection'], 'cache_hit': cache_hit,
            'duration_s': receipt['processing']['duration_s'],
            'audio': {part: f'/audio/{render_id}/{part}' for part in _PARTS}}


def render_preview(session_dir: Path, selection: dict) -> dict:
    session_dir = Path(session_dir).resolve()
    load_session(session_dir)
    with _file_lock(session_dir / 'writer.lock', 'audition render'):
        state = load_session(session_dir)
        selected, anchor, vocal = _selection(state, selection)
        identity = {'renderer_policy': 'groove-audition-v1', 'ffmpeg_version': vibe_audio.ffmpeg_version(),
                    'selection': selected}
        render_id = _digest(identity)
        parent = _contained(session_dir, session_dir / 'renders')
        target = _contained(session_dir, parent / render_id)
        if target.exists():
            return _result(_receipt(session_dir, render_id), True)
        with tempfile.TemporaryDirectory(prefix='.render-', dir=parent) as temporary:
            work = Path(temporary)
            try:
                processing = vibe_audio.render_audio(anchor, vocal, selected['recipe'], work)
            except vibe_audio.AudioError as exc:
                raise VibeError(str(exc)) from exc
            _verify_source(state, selected['anchor_id'])
            _verify_source(state, selected['vocal_id'])
            receipt = {'schema_version': 1, 'render_id': render_id, 'identity': identity,
                       'selection': selected, 'processing': processing,
                       'outputs': {part: _hash(work / f'{part}.wav') for part in _PARTS}}
            _atomic_json(work / 'receipt.json', receipt)
            work.rename(target)
        return _result(receipt, False)


def rendered_audio(session_dir: Path, render_id: str, part: str) -> Path:
    if part not in _PARTS:
        raise VibeError('Unknown audio layer')
    _receipt(session_dir, render_id)
    return _contained(session_dir, session_dir / 'renders' / render_id / f'{part}.wav')


def save_feedback(session_dir: Path, render_id: str, decision: str, note: str = '') -> dict:
    if decision not in ('works', 'does_not_work', 'unsure'):
        raise VibeError('Choose works, does_not_work or unsure; feedback does not approve curation')
    if not isinstance(note, str) or len(note) > 2000:
        raise VibeError('Feedback note must contain at most 2000 characters')
    load_session(session_dir)
    with _file_lock(session_dir / 'writer.lock', 'audition feedback'):
        receipt = _receipt(session_dir, render_id)
        _selection(load_session(session_dir), receipt['selection'])
        feedback_path = _contained(session_dir, session_dir / 'feedback.json')
        feedback = _feedback(feedback_path)
        feedback.append({'render_id': render_id, 'decision': decision, 'note': note,
                                    'selection': receipt['selection'],
                                    'recorded_at': datetime.now(timezone.utc).isoformat()})
        _atomic_json(feedback_path, {'schema_version': 1, 'feedback': feedback})
        return {'feedback': feedback}
