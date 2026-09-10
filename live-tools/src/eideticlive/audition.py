"""Explicit saved-Set attachment and audition on two owned Session tracks.

No library database dependency, automatic tempo edits, Warp guesses or save calls.
Receipts are written before each mutation. An uncertain operation is never retried.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
from pathlib import Path
import tempfile
import threading
import uuid

from . import LiveClient, LiveError


def _hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _write(path, value):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.live-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


class LiveAudition:
    def __init__(self, session_dir: Path, client=None):
        self.directory = Path(session_dir).resolve()
        self.client = client or LiveClient()
        self.lock = threading.RLock()
        self.path = self.directory / 'live-attachment.json'
        self.pending = {}

    def _read(self):
        if self.path.is_symlink():
            raise LiveError('Live attachment evidence must not be a symlink')
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError) as exc:
            raise LiveError('Attach this audition to the saved Set first') from exc

    def _snapshot(self):
        snapshot = self.client.inspect()
        if not snapshot.get('complete'):
            raise LiveError('Live inspection is incomplete; no audition change was made')
        return snapshot

    def _attached(self):
        state = self._read()
        identity = self.client.runtime()
        if identity != state['identity']:
            raise LiveError('Live Set or bridge instance changed. Preview attachment to reuse the managed tracks; no automatic reconnect.')
        if state.get('status') != 'attached':
            raise LiveError('Previous operation needs reconciliation. Read its recovery report then preview attachment to recover explicitly.')
        for item in state['tracks'].values():
            if self.client.get(f"id {item['id']}", 'name') != item['name']:
                raise LiveError('Managed audition track changed or is missing; preview attachment to reconcile')
        snapshot = {'identity': identity, 'transport': {
            'playing': self.client.get('live_set', 'is_playing'),
            'tempo': self.client.get('live_set', 'tempo')}}
        return state, snapshot

    def _preview(self, operation):
        preview_id = uuid.uuid4().hex
        self.pending = {preview_id: operation}
        return {'preview_id': preview_id, **operation}

    def preview_attachment(self, saved_set: str):
        with self.lock, self.client.exclusive():
            snapshot = self._snapshot()
            path = Path(saved_set).expanduser().resolve()
            identity = snapshot['identity']
            if (path.suffix.lower() != '.als' or not path.is_file()
                    or not identity.get('set_path') or Path(identity['set_path']).resolve() != path):
                raise LiveError('Choose the currently open, saved .als Set; Save As in Live first if needed')
            if snapshot['transport']['playing']:
                raise LiveError('Stop Live before previewing attachment')
            self._no_recording()
            previous = self._read() if self.path.exists() else None
            suffix = uuid.uuid4().hex[:8]
            names = {role: f'Eidetic {role.title()} {suffix}' for role in ('reference', 'candidate')}
            recovered, loaded = {}, {}
            if previous:
                if Path(previous['identity']['set_path']).resolve() != path:
                    raise LiveError('This session belongs to a different saved Set; use a new audition session')
                names = previous.get('track_names') or previous.get('operation', {}).get('track_names') or {
                    role: item['name'] for role, item in previous['tracks'].items()}
                if set(names) != {'reference', 'candidate'}:
                    raise LiveError('Recovery evidence lacks both managed track names')
                for role, name in names.items():
                    matches = [t for t in snapshot['tracks'] if t['name'] == name]
                    if len(matches) > 1:
                        raise LiveError('Managed track name is ambiguous; resolve duplicates manually')
                    if matches:
                        recovered[role] = {'id': matches[0]['id'], 'name': name}
                        temporary = {'tracks': recovered}
                        current = self._current_clip(temporary, role)
                        if current:
                            possible = [previous.get('loaded', {}).get(role), previous.get('operation')]
                            known = next((x for x in possible if x and x.get('path')
                                and Path(x['path']).resolve() == Path(current['file_path']).resolve()
                                and (x.get('role', role) == role)
                                and _hash(x['path']) == x.get('sha256')), None)
                            if not known:
                                raise LiveError('Recovery found an unrecognised managed clip; inspect and move it manually first')
                            loaded[role] = {key: known[key] for key in ('sample_id', 'path', 'sha256')}
                            loaded[role]['clip_id'] = current['id']
            checkpoint_dir = self.directory / 'live-checkpoints'
            checkpoint_dir.mkdir(exist_ok=True)
            checkpoint = checkpoint_dir / (uuid.uuid4().hex + '.als')
            digest = _hash(path)
            shutil.copyfile(path, checkpoint)
            if _hash(path) != digest or _hash(checkpoint) != digest:
                raise LiveError('Saved Set changed while retaining its checkpoint; preview again')
            return self._preview({'kind': 'attach', 'identity': identity,
                'checkpoint': {'path': str(checkpoint), 'original_path': str(path), 'sha256': digest},
                'before_tracks': [str(t['id']) for t in snapshot['tracks']],
                'track_names': names, 'recovered_tracks': recovered, 'recovered_loaded': loaded,
                'tempo': snapshot['transport']['tempo'],
                'message': f'Reuse {len(recovered)} verified managed tracks and create {2-len(recovered)} missing tracks. Retain checkpoint; tempo stays unchanged. Save manually after checking.'})

    def reconcile(self):
        """Read-only recovery report; explicit attachment preview performs recovery."""
        with self.lock, self.client.exclusive():
            evidence = self._read()
            return {'schema_version': 1, 'saved_status': evidence['status'],
                    'identity_now': self.client.runtime(), 'evidence': evidence,
                    'next_step': 'Inspect the Set and this receipt. Stop Live, then Preview attachment and Confirm to reuse only recognised tracks and verified clips. Nothing is retried automatically.'}

    def confirm(self, preview_id: str):
        with self.lock, self.client.exclusive():
            operation = self.pending.pop(preview_id, None)
            if operation is None:
                raise LiveError('Preview expired or already used; inspect the Set before preparing a fresh preview')
            if operation['kind'] == 'attach':
                return self._attach(operation)
            return self._load(operation)

    def _attach(self, operation):
        snapshot = self._snapshot()
        if (snapshot['identity'] != operation['identity'] or snapshot['transport']['playing']
                or [str(t['id']) for t in snapshot['tracks']] != operation['before_tracks']
                or _hash(operation['checkpoint']['path']) != operation['checkpoint']['sha256']
                or _hash(operation['checkpoint']['original_path']) != operation['checkpoint']['sha256']):
            raise LiveError('Attachment preview is stale; inspect and preview again')
        self._guard({'identity': snapshot['identity'], 'tracks': operation['recovered_tracks']}, stopped=True)
        state = {'schema_version': 1, 'identity': snapshot['identity'], 'checkpoint': operation['checkpoint'],
                 'status': 'mutation_started', 'tracks': operation['recovered_tracks'], 'loaded': operation['recovered_loaded'], 'operation': operation,
                 'track_names': operation['track_names']}
        _write(self.path, state)
        try:
            prior = set(operation['before_tracks'])
            for role, name in operation['track_names'].items():
                if role in state['tracks']:
                    continue
                self._guard(state, stopped=True)
                self.client.call('live_set', 'create_audio_track', [-1])
                after = self._snapshot()
                if after['identity'] != state['identity']:
                    raise LiveError('Set changed while creating audition tracks')
                added = [t for t in after['tracks'] if str(t['id']) not in prior]
                if len(added) != 1:
                    raise LiveError('Cannot identify the created track; inspect Live before continuing')
                track = added[0]
                path = f"id {track['id']}"
                self._guard(state, stopped=True)
                if self.client.get(path, 'id') != track['id']:
                    raise LiveError('Created track identity changed')
                self.client.set(path, 'name', name)
                if self.client.get(path, 'name') != name:
                    raise LiveError('Track name readback did not match')
                state['tracks'][role] = {'id': track['id'], 'name': name}
                prior.add(str(track['id']))
                _write(self.path, state)
            state['status'] = 'attached'
            _write(self.path, state)
        except Exception:
            state['status'] = 'uncertain'
            _write(self.path, state)
            raise
        return self.status()

    def _slot(self, state, role):
        if role not in ('reference', 'candidate'):
            raise LiveError('Choose reference or candidate track')
        track_id = state['tracks'][role]['id']
        description = self.client.describe(f'id {track_id}')
        if str(description['id']) != str(track_id):
            raise LiveError('Managed track identity no longer resolves')
        path = description['path']
        if self.client.get(path, 'id') != description['id']:
            raise LiveError('Track order changed while resolving its slot')
        return path + ' clip_slots 0'

    def _current_clip(self, state, role):
        slot = self._slot(state, role)
        if not self.client.get(slot, 'has_clip'):
            return None
        return {'id': self.client.get(slot + ' clip', 'id'),
                'file_path': self.client.get(slot + ' clip', 'file_path')}

    def preview_load(self, *, role: str, sample_id: str, path: str, sha256: str):
        with self.lock, self.client.exclusive():
            state, snapshot = self._attached()
            if snapshot['transport']['playing']:
                raise LiveError('Stop Live before previewing an audio load')
            self._no_recording()
            audio = Path(path).resolve()
            if (not audio.is_relative_to(self.directory / 'sources') or audio.suffix != '.wav'
                    or not audio.is_file() or _hash(audio) != sha256):
                raise LiveError('Only a verified working WAV in this audition may be loaded')
            current = self._current_clip(state, role)
            known = state['loaded'].get(role)
            if current and (not known or str(current['id']) != str(known['clip_id'])
                            or Path(current['file_path']).resolve() != Path(known['path']).resolve()):
                raise LiveError('Managed slot contains an unrecognised clip; move it manually before loading')
            return self._preview({'kind': 'load', 'identity': snapshot['identity'], 'role': role,
                'sample_id': sample_id, 'path': str(audio), 'sha256': sha256, 'before_clip': current,
                'message': f'Replace only the managed {role} slot with {audio.name}. Grid and Warp require manual checking in Live.'})

    def _load(self, operation):
        state, snapshot = self._attached()
        role = operation['role']
        if (snapshot['identity'] != operation['identity']
                or self._current_clip(state, role) != operation['before_clip']
                or _hash(operation['path']) != operation['sha256']):
            raise LiveError('Audio load preview is stale; inspect and preview again')
        self._guard(state, stopped=True)
        slot = self._slot(state, role)
        state.update(status='mutation_started', operation=operation)
        _write(self.path, state)
        try:
            if operation['before_clip']:
                self._guard(state, stopped=True)
                slot = self._slot(state, role)
                if self._current_clip(state, role) != operation['before_clip']:
                    raise LiveError('Managed clip changed before deletion')
                self.client.call(slot, 'delete_clip', [])
                if self.client.get(slot, 'has_clip'):
                    raise LiveError('Clip deletion did not read back; inspect Live')
            self._guard(state, stopped=True)
            slot = self._slot(state, role)
            if self.client.get(slot, 'has_clip'):
                raise LiveError('Managed slot is no longer empty')
            if _hash(operation['path']) != operation['sha256']:
                raise LiveError('Working audio changed before loading')
            self.client.call(slot, 'create_audio_clip', [operation['path']])
            current = self._current_clip(state, role)
            if not current or Path(current['file_path']).resolve() != Path(operation['path']).resolve():
                raise LiveError('Loaded clip path did not read back; inspect Live')
            if _hash(operation['path']) != operation['sha256']:
                raise LiveError('Working audio changed during loading')
            state['loaded'][role] = {key: operation[key] for key in ('sample_id', 'path', 'sha256')}
            state['loaded'][role]['clip_id'] = current['id']
            state['status'] = 'attached'
            _write(self.path, state)
        except Exception:
            state['status'] = 'uncertain'
            _write(self.path, state)
            raise
        return self.status()

    def _no_recording(self):
        if self.client.get('live_set', 'record_mode') or self.client.get('live_set', 'session_record'):
            raise LiveError('Disable Arrangement and Session recording before audition playback or structural changes')

    def _guard(self, state, *, stopped=False, no_recording=False):
        if self.client.runtime() != state['identity']:
            raise LiveError('Set identity changed before write')
        for item in state['tracks'].values():
            if self.client.get(f"id {item['id']}", 'name') != item['name']:
                raise LiveError('Managed track identity or name changed before write')
        if stopped and self.client.get('live_set', 'is_playing'):
            raise LiveError('Stop Live before structural audition changes')
        if stopped or no_recording:
            self._no_recording()

    def _verified_clip(self, state, role):
        loaded = state['loaded'].get(role)
        current = self._current_clip(state, role)
        if (not loaded or not current or str(current['id']) != str(loaded['clip_id'])
                or Path(current['file_path']).resolve() != Path(loaded['path']).resolve()
                or _hash(loaded['path']) != loaded['sha256']):
            raise LiveError(f'Load and confirm the {role} sample first; its clip or working WAV may have changed')
        return self._slot(state, role) + ' clip'

    def control(self, action: str, *, with_reference=False, gain=None, loop=None, warping=None, warp_mode=None):
        with self.lock, self.client.exclusive():
            state, _ = self._attached()
            if action not in ('play', 'stop', 'gain', 'loop', 'warp', 'warp_mode'):
                raise LiveError('Unknown Live audition control')
            if type(with_reference) is not bool:
                raise LiveError('Reference playback must be true or false')
            roles = ['candidate'] + (['reference'] if with_reference else [])
            clips = {role: self._verified_clip(state, role) for role in roles} if action != 'stop' else {}
            if action == 'gain' and (isinstance(gain, bool) or not isinstance(gain, (int, float))
                                     or not math.isfinite(gain) or not 0 <= gain <= 1):
                raise LiveError('Live clip gain must be between 0 and 1')
            if action == 'loop':
                if type(loop) is not bool:
                    raise LiveError('Loop must be true or false')
                if loop and any(not self.client.get(path, 'warping') for path in clips.values()):
                    raise LiveError('Live cannot loop unwarped audio. Set and verify Warp manually in Live first')
            if action == 'warp' and type(warping) is not bool:
                raise LiveError('Warp must be true or false')
            if action == 'warp_mode':
                if type(warp_mode) is not int:
                    raise LiveError('Choose an available Warp mode')
                for path in clips.values():
                    available = self.client.get(path, 'available_warp_modes')
                    if not isinstance(available, list):
                        available = [available]
                    if warp_mode not in available or not self.client.get(path, 'warping'):
                        raise LiveError('Warp mode is unavailable or Warp is not yet enabled; enable Warp and refresh first')
            if action == 'play':
                self._guard(state, no_recording=True)
            state.update(status='mutation_started', operation={'kind': 'control', 'action': action})
            _write(self.path, state)
            try:
                if action == 'stop':
                    for item in state['tracks'].values():
                        self._guard(state)
                        self.client.call(f"id {item['id']}", 'stop_all_clips', [])
                elif action == 'play':
                    if not with_reference:
                        self._guard(state, no_recording=True)
                        self.client.call(f"id {state['tracks']['reference']['id']}", 'stop_all_clips', [])
                    for role in roles:
                        path = self._verified_clip(state, role)
                        self._guard(state, no_recording=True)
                        self.client.call(path, 'fire', [])
                else:
                    prop, value = {'gain': ('gain', gain), 'loop': ('looping', int(bool(loop))),
                                   'warp': ('warping', int(bool(warping))), 'warp_mode': ('warp_mode', warp_mode)}[action]
                    for role in roles:
                        self._guard(state)
                        path = self._verified_clip(state, role)
                        self.client.set(path, prop, value)
                        actual = self.client.get(path, prop)
                        if prop == 'warping':
                            # Live defers Warp changes. Re-read only; never resend the mutation.
                            for _ in range(4):
                                if bool(actual) == bool(value):
                                    break
                                actual = self.client.get(path, prop)
                        if not math.isclose(float(actual), float(value), abs_tol=1e-6):
                            raise LiveError('Live control readback did not match')
                state['status'] = 'attached'
                _write(self.path, state)
            except Exception:
                state['status'] = 'uncertain'
                _write(self.path, state)
                raise
            return self.status()

    def status(self):
        with self.lock, self.client.exclusive():
            if not self.path.exists():
                snapshot = self._snapshot()
                return {'connected': True, 'attached': False, 'identity': snapshot['identity'],
                        'tempo': snapshot['transport']['tempo']}
            state, snapshot = self._attached()
            loaded = {}
            for role, item in state['loaded'].items():
                path = self._verified_clip(state, role)
                loaded[role] = {**item, **{prop: self.client.get(path, prop)
                    for prop in ('warping', 'warp_mode', 'loop_start', 'loop_end', 'looping', 'gain', 'gain_display_string', 'is_playing', 'available_warp_modes')}}
            return {'connected': True, 'attached': True, 'identity': state['identity'],
                    'tempo': snapshot['transport']['tempo'], 'tracks': state['tracks'], 'loaded': loaded,
                    'timing': 'Beat grid is unverified. Correct Warp and loop boundaries manually in Live; Set tempo is never changed.',
                    'persistence': 'Save the Set manually in Live. Keep and Skip remain separate listening decisions.'}
