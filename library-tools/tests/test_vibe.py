from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf


def make_session(tmp_path):
    from librarytools.vibe import prepare_session
    root = tmp_path / 'library'
    root.mkdir()
    rate = 48000
    t = np.arange(2 * rate) / rate
    anchor = root / 'groove.wav'
    vocal = root / 'voice.wav'
    sf.write(anchor, .3 * np.sin(2 * np.pi * 110 * t), rate)
    sf.write(vocal, .2 * np.sin(2 * np.pi * 440 * t[:rate]), rate)
    output = tmp_path / 'session'
    state = prepare_session(root, output, [anchor], [vocal], bpm=120)
    selection = {'anchor_id': state['anchors'][0]['id'], 'vocal_id': state['vocals'][0]['id'],
                 'recipe': {'bpm': 120, 'bars': 8, 'anchor_start_s': 0, 'anchor_end_s': 2,
                 'anchor_bars': 1, 'vocal_start_s': 0, 'vocal_end_s': .25,
                 'vocal_fit_beats': 0, 'offset_beats': 1, 'repeat_beats': 4,
                 'anchor_gain_db': -6, 'vocal_gain_db': -6}}
    return root, output, state, selection


def test_prepare_keeps_sources_unchanged_and_refuses_existing_or_in_library_output(tmp_path):
    from librarytools.vibe import prepare_session, VibeError
    root, output, state, _ = make_session(tmp_path)
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    assert state['anchors'][0]['duration_s'] == 2
    assert len(state['vocals'][0]['waveform']) > 0
    assert not (root / '.eidetic').exists()
    for destination in [output, root / 'preview']:
        with pytest.raises(VibeError):
            prepare_session(root, destination, [root / 'groove.wav'], [root / 'voice.wav'])
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}


def test_prepare_rejects_symlink_escape_and_nonfinite_tempo(tmp_path):
    from librarytools.vibe import prepare_session, VibeError
    root, _, _, _ = make_session(tmp_path)
    outside = tmp_path / 'outside.wav'
    outside.write_bytes((root / 'voice.wav').read_bytes())
    (root / 'escape.wav').symlink_to(outside)
    with pytest.raises(VibeError, match='root'):
        prepare_session(root, tmp_path / 'escape', [root / 'groove.wav'], [root / 'escape.wav'])
    with pytest.raises(VibeError, match='BPM'):
        prepare_session(root, tmp_path / 'nan', [root / 'groove.wav'], [root / 'voice.wav'], bpm=float('nan'))


def test_render_cache_is_verified_and_feedback_survives_reload(tmp_path):
    from librarytools.vibe import render_preview, save_feedback, session_state, VibeError
    root, output, _, selection = make_session(tmp_path)
    before = hashlib.sha256((root / 'groove.wav').read_bytes()).hexdigest()
    result = render_preview(output, selection)
    assert result['cache_hit'] is False
    assert result['duration_s'] == 16
    assert render_preview(output, selection)['cache_hit'] is True
    save_feedback(output, result['render_id'], 'works', 'Test judgment only')
    feedback = session_state(output)['feedback']
    assert feedback[-1]['selection'] == selection
    assert feedback[-1]['note'] == 'Test judgment only'
    assert not (root / 'CURATED').exists()
    assert hashlib.sha256((root / 'groove.wav').read_bytes()).hexdigest() == before
    (output / 'renders' / result['render_id'] / 'mix.wav').write_bytes(b'changed')
    with pytest.raises(VibeError, match='changed'):
        render_preview(output, selection)
    with pytest.raises(VibeError):
        save_feedback(output, result['render_id'], 'works', '')


def test_changed_source_unknown_selection_and_invalid_recipe_fail_closed(tmp_path):
    from librarytools.vibe import render_preview, VibeError
    root, output, _, selection = make_session(tmp_path)
    with pytest.raises(VibeError):
        render_preview(output, {**selection, 'anchor_id': '../voice.wav'})
    with pytest.raises(VibeError):
        render_preview(output, {**selection, 'recipe': {**selection['recipe'], 'bpm': float('nan')}})
    (root / 'voice.wav').write_bytes(b'changed')
    with pytest.raises(VibeError, match='changed'):
        render_preview(output, selection)
    assert not list((output / 'renders').glob('*/receipt.json'))


def test_api_requires_tokens_and_serves_only_verified_session_audio(tmp_path):
    from librarytools.vibe_server import create_vibe_app
    root, output, state, selection = make_session(tmp_path)
    app = create_vibe_app(output, write_token='test-token')
    client = app.test_client()
    assert client.post('/api/render', json=selection).status_code == 403
    headers = {'X-Vibe-Token': 'test-token'}
    assert client.post('/api/render', json=[], headers=headers).status_code == 400
    assert client.get('/source/../../etc/passwd').status_code == 404
    source_id = state['vocals'][0]['id']
    response = client.get(f'/source/{source_id}', headers={'Range': 'bytes=0-3'})
    assert response.status_code == 206
    assert response.data == b'RIFF'
    result = client.post('/api/render', json=selection, headers=headers)
    assert result.status_code == 200
    rendered = result.get_json()
    assert client.get(rendered['audio']['mix']).status_code == 200
    assert client.get(f"/audio/{rendered['render_id']}/receipt.json").status_code == 404
    body = {'render_id': rendered['render_id'], 'decision': 'works', 'note': 'listen later'}
    assert client.post('/api/feedback', json=body).status_code == 403
    assert client.post('/api/feedback', json=body, headers=headers).status_code == 200
    assert client.get('/api/state').get_json()['feedback'][-1]['note'] == 'listen later'
    (root / 'voice.wav').write_bytes(b'changed')
    assert client.get(f'/source/{source_id}').status_code == 409


def test_unknown_render_and_wrong_feedback_never_record_approval(tmp_path):
    from librarytools.vibe import save_feedback, session_state, VibeError
    _, output, _, _ = make_session(tmp_path)
    with pytest.raises(VibeError):
        save_feedback(output, 'a' * 64, 'works', '')
    with pytest.raises(VibeError):
        save_feedback(output, 'a' * 64, 'favourite', '')
    assert session_state(output)['feedback'] == []


def test_server_rejects_external_bind_and_cli_reports_bad_input(tmp_path, capsys):
    from librarytools.vibe_server import validate_bind_host
    from librarytools.vibe_cli import main
    from librarytools.vibe import VibeError
    with pytest.raises(VibeError, match='127.0.0.1'):
        validate_bind_host('0.0.0.0')
    assert main(['serve', '--session-dir', str(tmp_path / 'missing')]) == 2
    assert 'error' in capsys.readouterr().err.lower()


def test_server_rejects_rebound_host_and_non_ascii_token(tmp_path):
    from librarytools.vibe_server import create_vibe_app
    _, output, _, selection = make_session(tmp_path)
    client = create_vibe_app(output, write_token='test-token').test_client()
    assert client.get('/', headers={'Host': 'attacker.example'}).status_code == 400
    response = client.post('/api/render', json=selection, headers={'X-Vibe-Token': 'é'})
    assert response.status_code == 403
    assert client.get('/', headers={'Host': '127.0.0.1:8767'}).status_code == 200


def test_corrupt_session_returns_actionable_error_instead_of_server_failure(tmp_path):
    from librarytools.vibe import session_state, VibeError
    _, output, _, _ = make_session(tmp_path)
    path = output / 'session.json'
    state = json.loads(path.read_text())
    del state['sources'][state['anchors'][0]]['name']
    path.write_text(json.dumps(state))
    with pytest.raises(VibeError, match='source'):
        session_state(output)


def test_source_preview_attenuates_float_audio_instead_of_clipping(tmp_path):
    from librarytools.vibe import prepare_session, source_audio
    root = tmp_path / 'library'
    root.mkdir()
    source = root / 'hot.wav'
    samples = np.tile(np.array([0., .5, 1., 2.], dtype=np.float32), 12000)
    sf.write(source, samples, 48000, subtype='FLOAT')
    output = tmp_path / 'preview'
    state = prepare_session(root, output, [source], [source])
    decoded, _ = sf.read(source_audio(output, state['anchors'][0]['id']))
    assert .94 < np.max(decoded) <= .950001
    assert decoded[2, 0] == pytest.approx(decoded[3, 0] / 2, abs=1e-6)


@pytest.mark.parametrize('damage', ['huge_bpm', 'feedback_entry', 'receipt_outputs', 'receipt_processing'])
def test_damaged_evidence_is_reported_as_a_controlled_error(tmp_path, damage):
    from librarytools.vibe import render_preview, session_state, VibeError
    _, output, _, selection = make_session(tmp_path)
    if damage == 'huge_bpm':
        path = output / 'session.json'
        data = json.loads(path.read_text())
        data['bpm'] = 10 ** 400
    elif damage == 'feedback_entry':
        path = output / 'feedback.json'
        data = {'schema_version': 1, 'feedback': [None]}
    else:
        rendered = render_preview(output, selection)
        path = output / 'renders' / rendered['render_id'] / 'receipt.json'
        data = json.loads(path.read_text())
        data['outputs' if damage == 'receipt_outputs' else 'processing'] = []
    path.write_text(json.dumps(data))
    with pytest.raises(VibeError):
        if damage.startswith('receipt'):
            render_preview(output, selection)
        else:
            session_state(output)
