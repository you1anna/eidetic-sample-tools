"""Controlled fake Live verifies attachment safety, no automatic retry or tempo edits.

This exercises protocol orchestration, not audio quality or hardware qualification.
"""
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path

import pytest

from eideticlive import LiveError
from eideticlive.audition import LiveAudition


class FakeLive:
    def __init__(self, saved_set):
        self.identity = dict(build_id='test', instance_id='instance', set_id='set', set_path=str(saved_set), set_name='Test')
        self.tracks = []
        self.clips = {}
        self.writes = []
        self.fail = None
        self.disconnected = False
        self.record_mode = False
        self.session_record = False

    def exclusive(self):
        return nullcontext()

    def runtime(self):
        if self.disconnected: raise LiveError('disconnected')
        return dict(self.identity)

    def inspect(self):
        if self.disconnected:
            raise LiveError('disconnected')
        return {'schema_version': 1, 'complete': True, 'identity': dict(self.identity),
                'transport': {'playing': False, 'tempo': 127}, 'tracks': [dict(t) for t in self.tracks]}

    def describe(self, path):
        tid = int(path.split()[1])
        return {'id': tid, 'path': f'live_set tracks {next(i for i,t in enumerate(self.tracks) if t["id"] == tid)}'}

    def _track(self, path):
        if path.startswith('id '):
            return next(t for t in self.tracks if t['id'] == int(path.split()[1]))
        return self.tracks[int(path.split()[2])]

    def get(self, path, prop):
        if path == 'live_set':
            return {'is_playing': False, 'tempo': 127, 'record_mode': self.record_mode, 'session_record': self.session_record}[prop]
        track = self._track(path)
        clip = self.clips.get(track['id'])
        if path.endswith(' clip'):
            return clip[prop]
        if prop == 'has_clip': return bool(clip)
        return track[prop]

    def set(self, path, prop, value):
        self.writes.append(('set', path, prop, value))
        target = self.clips[self._track(path)['id']] if path.endswith(' clip') else self._track(path)
        target[prop] = value

    def call(self, path, method, args):
        self.writes.append(('call', path, method, args))
        if method == self.fail:
            self.fail = None
            raise LiveError('mutation acknowledgement lost')
        if method == 'create_audio_track':
            self.tracks.append({'id': 100 + len(self.tracks), 'name': 'Audio'})
            return
        track = self._track(path)
        if method == 'create_audio_clip':
            self.clips[track['id']] = {'id': 1000 + len(self.writes), 'file_path': args[0], 'gain': .5,
                 'gain_display_string': '0 dB', 'warping': False, 'warp_mode': 0,
                 'loop_start': 0, 'loop_end': 1, 'looping': False, 'is_playing': False, 'available_warp_modes': [0, 1, 4]}
        elif method == 'delete_clip': self.clips.pop(track['id'])
        elif method in ('fire', 'stop', 'stop_all_clips') and track['id'] in self.clips:
            self.clips[track['id']]['is_playing'] = method == 'fire'


@pytest.fixture
def audition(tmp_path):
    saved = tmp_path / 'Test.als'; saved.write_bytes(b'saved checkpoint')
    session = tmp_path / 'audition'; session.mkdir()
    (session / 'sources').mkdir()
    audio = session / 'sources' / 'working.wav'; audio.write_bytes(b'working WAV')
    live = FakeLive(saved)
    return LiveAudition(session, live), live, saved, audio


def attach(audition):
    controller, live, saved, audio = audition
    preview = controller.preview_attachment(str(saved))
    assert not live.writes
    assert Path(preview['checkpoint']['path']).read_bytes() == saved.read_bytes()
    controller.confirm(preview['preview_id'])
    return controller, live, saved, audio


def load(controller, audio, role='candidate'):
    digest = hashlib.sha256(audio.read_bytes()).hexdigest()
    preview = controller.preview_load(role=role, sample_id=digest, path=str(audio), sha256=digest)
    return controller.confirm(preview['preview_id'])


def test_live_attachment_load_controls_and_reconnect_are_explicit(audition):
    controller, live, saved, audio = attach(audition)
    assert len(live.tracks) == 2
    result = load(controller, audio)
    assert result['tempo'] == 127 and result['loaded']['candidate']['warping'] is False
    with pytest.raises(LiveError, match='Warp'):
        controller.control('loop', loop=True)
    controller.control('warp', warping=True)
    controller.control('warp_mode', warp_mode=4)
    controller.control('loop', loop=True)
    controller.control('gain', gain=.4)
    controller.control('play')
    controller.control('stop')
    assert not any(write[2] in ('tempo', 'stop_playing', 'save') for write in live.writes)
    assert LiveAudition(controller.directory, live).status()['attached']
    before = list(live.writes)
    live.identity['instance_id'] = 'restarted'
    with pytest.raises(LiveError, match='changed'):
        controller.control('play')
    assert live.writes == before


def test_stale_checkpoint_and_arbitrary_audio_are_rejected(audition):
    controller, live, saved, audio = audition
    preview = controller.preview_attachment(str(saved))
    saved.write_bytes(b'saved again')
    with pytest.raises(LiveError, match='stale'):
        controller.confirm(preview['preview_id'])
    assert not live.writes
    attach(audition)
    with pytest.raises(LiveError, match='working WAV'):
        controller.preview_load(role='candidate', sample_id='x', path=str(saved), sha256=hashlib.sha256(saved.read_bytes()).hexdigest())


def test_lost_mutation_ack_blocks_retry_and_preserves_uncertain_receipt(audition):
    controller, live, _, audio = attach(audition)
    live.fail = 'create_audio_clip'
    with pytest.raises(LiveError, match='acknowledgement'):
        load(controller, audio)
    before = list(live.writes)
    assert json.loads(controller.path.read_text())['status'] == 'uncertain'
    with pytest.raises(LiveError, match='reconciliation'):
        load(controller, audio)
    assert before == live.writes


def test_recovery_is_explicit_reuses_tracks_and_does_not_retry_failed_load(audition):
    controller, live, saved, audio = attach(audition)
    live.fail = 'create_audio_clip'
    with pytest.raises(LiveError):
        load(controller, audio)
    before = list(live.writes)
    assert controller.reconcile()['saved_status'] == 'uncertain'
    preview = controller.preview_attachment(str(saved))
    assert len(preview['recovered_tracks']) == 2
    assert live.writes == before
    controller.confirm(preview['preview_id'])
    assert live.writes == before and controller.status()['attached']
    load(controller, audio)
    live.identity['instance_id'] = 'reloaded'
    preview = controller.preview_attachment(str(saved))
    controller.confirm(preview['preview_id'])
    assert len(live.tracks) == 2
    assert controller.status()['loaded']['candidate']['sample_id']


@pytest.mark.parametrize('recording', ['record_mode', 'session_record'])
@pytest.mark.parametrize('phase', ['preview', 'confirm'])
def test_recording_blocks_attachment_before_mutation_journal(audition, recording, phase):
    controller, live, saved, _ = audition
    if phase == 'confirm':
        preview = controller.preview_attachment(str(saved))
    setattr(live, recording, True)
    with pytest.raises(LiveError, match='recording'):
        if phase == 'preview':
            controller.preview_attachment(str(saved))
        else:
            controller.confirm(preview['preview_id'])
    assert not live.writes
    assert not controller.path.exists()


@pytest.mark.parametrize('recording', ['record_mode', 'session_record'])
def test_recording_blocks_play_before_journal_and_stop_remains_available(audition, recording):
    controller, live, _, audio = attach(audition)
    load(controller, audio)
    previous = controller.path.read_bytes()
    writes = list(live.writes)
    setattr(live, recording, True)
    with pytest.raises(LiveError, match='recording'):
        controller.control('play')
    assert live.writes == writes
    assert controller.path.read_bytes() == previous
    controller.control('stop')
    assert all(write[2] == 'stop_all_clips' for write in live.writes[len(writes):])
    assert getattr(live, recording) is True


@pytest.mark.parametrize('recording', ['record_mode', 'session_record'])
def test_recording_is_rechecked_between_audition_fires(audition, recording, monkeypatch):
    controller, live, _, audio = attach(audition)
    load(controller, audio)
    load(controller, audio, role='reference')
    original_call = live.call
    def start_recording_after_first_fire(path, method, args):
        original_call(path, method, args)
        if method == 'fire':
            setattr(live, recording, True)
    monkeypatch.setattr(live, 'call', start_recording_after_first_fire)
    with pytest.raises(LiveError, match='recording'):
        controller.control('play', with_reference=True)
    assert len([write for write in live.writes if write[2] == 'fire']) == 1
    assert json.loads(controller.path.read_text())['status'] == 'uncertain'


@pytest.mark.parametrize('recording', ['record_mode', 'session_record'])
def test_recording_blocks_structural_load_before_journal(audition, recording):
    controller, live, _, audio = attach(audition)
    digest = hashlib.sha256(audio.read_bytes()).hexdigest()
    preview = controller.preview_load(role='candidate', sample_id=digest, path=str(audio), sha256=digest)
    previous = controller.path.read_bytes()
    writes = list(live.writes)
    setattr(live, recording, True)
    with pytest.raises(LiveError, match='recording'):
        controller.confirm(preview['preview_id'])
    assert live.writes == writes
    assert controller.path.read_bytes() == previous
