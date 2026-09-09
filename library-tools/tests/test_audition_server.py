"""Transport boundaries for the source audition and curation handoff."""
from __future__ import annotations

import pytest

from test_vibe import make_session


@pytest.fixture
def audition(tmp_path):
    from librarytools.vibe_server import create_vibe_app
    root, output, state, _ = make_session(tmp_path)
    client = create_vibe_app(output, write_token='shortlist-test').test_client()
    return client, root, output, state['anchors'][0]['id']


def test_main_screen_is_source_audition_and_vocal_editor_is_separate(audition):
    client, _, _, _ = audition
    page = client.get('/')
    assert b'Choose samples.' in page.data
    assert b'Keep &amp; next' in page.data
    assert b'audition.js' in page.data
    assert b'Render audition' not in page.data
    assert b'Render audition' in client.get('/vocal-lab').data
    for asset in ('audition.js', 'audition.css'):
        response = client.get('/static/' + asset)
        assert response.status_code == 200
        assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert client.get('/static/session.json').status_code == 404


def test_shortlist_api_is_token_gated_and_never_promotes(audition):
    client, root, output, source_id = audition
    body = {'source_id': source_id, 'decision': 'keep'}
    headers = {'X-Vibe-Token': 'shortlist-test'}
    assert client.post('/api/shortlist', json=body).status_code == 403
    assert client.post('/api/shortlist', json={**body, 'decision': 'favourite'}, headers=headers).status_code == 400
    assert client.post('/api/shortlist', json={**body, 'unexpected': True}, headers=headers).status_code == 400
    assert client.post('/api/shortlist', json={**body, 'source_id': '../anything'}, headers=headers).status_code == 400
    assert client.post('/api/shortlist', json=body, headers=headers).status_code == 200
    assert client.get('/api/shortlist').json['decisions'][source_id] == 'keep'
    assert not (root / 'CURATED').exists()
    assert not (root / '.eidetic').exists()
    assert client.get('/api/state').json['feedback'] == []
    response = client.get('/api/shortlist/playlist')
    assert response.status_code == 200
    assert 'attachment' in response.headers['Content-Disposition']
    assert str(root / 'groove.wav') in response.text
    assert 'sources/' not in response.text
    assert client.post('/api/shortlist', json={**body, 'decision': 'unreviewed'}, headers=headers).status_code == 200
    assert client.get('/api/shortlist').json['counts']['keep'] == 0
    assert client.get('/api/shortlist/playlist').status_code == 409


def test_missing_index_cannot_turn_shortlist_into_export_approval(audition):
    client, root, output, source_id = audition
    status = client.get('/api/shortlist/status')
    assert status.status_code == 200
    assert status.json['available'] is False
    assert 'index' in status.json['reason'].lower()
    headers = {'X-Vibe-Token': 'shortlist-test'}
    assert client.post('/api/shortlist/packet', json={}).status_code == 403
    assert client.post('/api/shortlist/packet', json={'output': '/tmp/escape'}, headers=headers).status_code == 400
    assert client.post('/api/shortlist', json={'source_id': source_id, 'decision': 'keep'}, headers=headers).status_code == 200
    response = client.post('/api/shortlist/packet', json={}, headers=headers)
    assert response.status_code == 400
    assert not (output / 'curation-packets').exists()
    assert not (root / '.eidetic').exists()


def test_changed_original_blocks_playlist_and_audio_with_saved_choice_intact(audition):
    client, root, _, source_id = audition
    headers = {'X-Vibe-Token': 'shortlist-test'}
    client.post('/api/shortlist', json={'source_id': source_id, 'decision': 'keep'}, headers=headers)
    (root / 'groove.wav').write_bytes(b'changed')
    assert client.get('/api/shortlist/playlist').status_code == 409
    assert client.get('/source/' + source_id).status_code == 409
    assert client.get('/api/shortlist').json['decisions'][source_id] == 'keep'


@pytest.mark.parametrize('error_kind', ['index', 'identity'])
def test_changed_index_state_returns_json_reason(audition, monkeypatch, error_kind):
    import sqlite3
    import librarytools.vibe_server as server
    client, _, _, _ = audition
    error = sqlite3.DatabaseError('index damaged') if error_kind == 'index' else ValueError('library identity changed')
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(server, 'create_shortlist_packet', fail)
    response = client.post('/api/shortlist/packet', json={}, headers={'X-Vibe-Token': 'shortlist-test'})
    assert response.status_code == 400
    assert response.json == {'error': str(error)}


def test_source_chooser_is_independent_of_optional_vocal_feedback(audition):
    client, _, output, source_id = audition
    (output / 'feedback.json').write_text('broken optional vocal experiment')
    response = client.get('/api/sources')
    assert response.status_code == 200
    assert response.json['sources'][0] == {
        'id': source_id, 'name': 'groove.wav', 'duration_s': 2,
        'kind': 'Groove candidate',
    }
    assert len(response.json['sources']) == 2
    assert client.get('/api/shortlist').status_code == 200
    assert client.get('/source/' + source_id).status_code == 200
    # The experiment still reports its damaged evidence rather than discarding it.
    assert client.get('/api/state').status_code == 409


def test_prepared_chooser_does_not_load_the_audio_renderer(audition):
    import subprocess
    import sys
    _, _, output, _ = audition
    script = '''
from pathlib import Path
import sys
from librarytools.vibe_server import create_vibe_app
client = create_vibe_app(Path(sys.argv[1])).test_client()
assert client.get('/').status_code == 200
assert client.get('/api/sources').status_code == 200
assert client.get('/api/shortlist').status_code == 200
assert 'librarytools.vibe' not in sys.modules
assert 'librarytools.vibe_audio' not in sys.modules
assert 'numpy' not in sys.modules
assert 'soundfile' not in sys.modules
'''
    result = subprocess.run([sys.executable, '-c', script, str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
