"""Collection-to-audition handoff with lazy, verified working WAVs."""
from __future__ import annotations

import csv
from pathlib import Path
import tempfile

from .locking import _file_lock
from .vibe_session import (VibeError, contained_path, hash_file, load_session,
                           verify_source, write_json, validate_identifier)

BATCH_SIZE = 12


def prepare_collection(root: Path, output_dir: Path, *, plan: Path | None = None,
                       curated: Path | None = None) -> dict:
    from .state import library_identity
    root, output_dir = Path(root).resolve(), Path(output_dir).absolute()
    if not root.is_dir():
        raise VibeError('Source root is unavailable')
    library_id = library_identity(root)
    if not library_id:
        raise VibeError('Onboard the library before preparing a collection audition')
    if (plan is None) == (curated is None):
        raise VibeError('Supply exactly one collection plan or ableton-curated.tsv')
    if output_dir.resolve().is_relative_to(root) or root.is_relative_to(output_dir.resolve()):
        raise VibeError('Audition output must be outside the source library')
    if output_dir.exists() or output_dir.is_symlink():
        raise VibeError('Audition output already exists; serve it to resume or choose a new directory')
    if plan is not None:
        from .collection_plan import read_plan
        evidence = read_plan(Path(plan) / 'plan.json' if Path(plan).is_dir() else Path(plan))
        if evidence['snapshot']['library_id'] != library_id:
            raise VibeError('Collection plan belongs to another library')
        candidates = {row['sample_id']: row for row in evidence['snapshot']['candidates']}
        rows = [candidates[row['sample_id']] | {'history_status': row['history_status']}
                for row in evidence['selected']]
        plan_id = evidence['plan_id']
        origin = 'collection-plan'
    else:
        with Path(curated).open(encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle, delimiter='\t')
            if not {'sample_id', 'path', 'role', 'descriptor', 'tags'} <= set(reader.fieldnames or []):
                raise VibeError('Expected an ableton-curated.tsv with sample_id, path, role, descriptor and tags')
            rows = list(reader)
        plan_id, origin = hash_file(Path(curated)), 'ableton-curated'
    if not rows:
        raise VibeError('No candidates in supplied selection')
    state = {'schema_version': 2, 'root': str(root), 'library_id': library_id,
             'plan_id': plan_id, 'origin': origin, 'candidate_ids': [], 'sources': {},
             'batch_size': BATCH_SIZE, 'batch_index': 0}
    for row in rows:
        sid = validate_identifier(row['sample_id'])
        if sid in state['sources']:
            raise VibeError('Duplicate sample identity in selection')
        raw = Path(row['path'])
        if raw.is_absolute() or '..' in raw.parts:
            raise VibeError('Selection paths must be relative to the library')
        path = contained_path(root, root / raw)
        if not path.is_file():
            raise VibeError(f'Source is missing: {raw}')
        state['candidate_ids'].append(sid)
        state['sources'][sid] = {'id': sid, 'sample_id': sid, 'path': raw.as_posix(),
            'name': path.name, 'role': row.get('role') or 'Unknown',
            'history_status': row.get('history_status', 'unknown'),
            'timing_status': 'Unknown beat grid; correct Warp manually in Live before rhythmic comparison.'}
    # Full content checks happen lazily on each audition batch, never inferred from pins/labels.
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir()
    write_json(output_dir / 'session.json', state)
    return state


def _prepare_one(session_dir: Path, state: dict, sid: str) -> None:
    import numpy as np
    import soundfile as sf
    from . import vibe_audio
    source = verify_source(state, sid)
    item = state['sources'][sid]
    target = contained_path(session_dir, session_dir / 'sources' / f'{sid}.wav')
    if item.get('preview_hash'):
        if not target.is_file() or hash_file(target) != item['preview_hash']:
            raise VibeError('Working WAV is missing or changed; prepare a new session')
        return
    info = vibe_audio.probe_source(source)
    audio = vibe_audio.decode_source(source)
    peak = float(np.max(np.abs(audio)))
    gain = min(1.0, .95 / peak) if peak else 1.0
    audio = audio.astype(np.float64) * gain
    target.parent.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix='.wav', delete=False) as handle:
        temporary = Path(handle.name)
    try:
        sf.write(temporary, audio, 48000, subtype='PCM_24')
        verify_source(state, sid)
        digest = hash_file(temporary)
        temporary.replace(target)
        envelope = np.max(np.abs(audio), axis=1)
        item.update(info, preview_hash=digest, preview_gain=gain,
                    waveform=[float(np.max(chunk)) for chunk in np.array_split(envelope, min(512, len(envelope)))])
    finally:
        temporary.unlink(missing_ok=True)


def batch_state(session_dir: Path, batch_index: int | None = None) -> dict:
    """Prepare only the active twelve; preserve choices across batches and restarts."""
    session_dir = Path(session_dir).resolve()
    with _file_lock(session_dir / 'writer.lock', purpose='prepare audition batch'):
        state = load_session(session_dir)
        index = state['batch_index'] if batch_index is None else batch_index
        count = (len(state['candidate_ids']) + BATCH_SIZE - 1) // BATCH_SIZE
        if type(index) is not int or not 0 <= index < count:
            raise VibeError('Batch index is outside the collection')
        sources = []
        for sid in state['candidate_ids'][index * BATCH_SIZE:(index + 1) * BATCH_SIZE]:
            item = state['sources'][sid]
            error = None
            try:
                _prepare_one(session_dir, state, sid)
            except (ValueError, OSError) as exc:
                error = str(exc)
            sources.append({'id': sid, 'sample_id': sid, 'name': item['name'],
                'kind': f"{item['role']} candidate", 'duration_s': item.get('duration_s', 0),
                'waveform': [round(p, 3) for p in item.get('waveform', [])],
                'history_status': item['history_status'], 'timing_status': item['timing_status'],
                'error': error})
        state['batch_index'] = index
        write_json(session_dir / 'session.json', state)
    return {'schema_version': 2, 'sources': sources, 'batch_index': index,
            'batch_count': count, 'total': len(state['candidate_ids']),
            'library_id': state['library_id'], 'plan_id': state['plan_id']}


def rebind_root(session_dir: Path, root: Path) -> dict:
    """Explicitly relocate an unchanged portable library; retain all listening IDs."""
    from .state import library_identity
    session_dir, root = Path(session_dir).resolve(), Path(root).resolve()
    with _file_lock(session_dir / 'writer.lock', purpose='rebind audition library root'):
        state = load_session(session_dir)
        if state['schema_version'] != 2:
            raise VibeError('Library relocation requires a v2 collection session')
        if not root.is_dir() or library_identity(root) != state['library_id']:
            raise VibeError('New root must contain the same portable library identity')
        if session_dir.is_relative_to(root):
            raise VibeError('Working audio must remain outside the source library')
        state['root'] = str(root)
        write_json(session_dir / 'session.json', state)
    return {'root': str(root), 'library_id': state['library_id'],
            'message': 'Root rebound; original and working hashes are checked on audition and curation use.'}
