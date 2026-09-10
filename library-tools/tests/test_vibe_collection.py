"""V2 handoff verifies lazy batches and durable decisions without granting approval."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from librarytools.state import library_identity
from librarytools.vibe_collection import prepare_collection, batch_state
from librarytools.vibe_session import load_session, source_audio, VibeError
from librarytools.vibe_shortlist import save_shortlist_decision, shortlist_state


@pytest.fixture
def collection(tmp_path, monkeypatch):
    from librarytools import vibe_audio
    root = tmp_path / 'library'
    root.mkdir()
    library_identity(root, create=True)
    rows = []
    for index in range(14):
        path = root / f'percussion-{index}.wav'
        path.write_bytes(f'sample {index}'.encode())
        rows.append({'sample_id': hashlib.sha256(path.read_bytes()).hexdigest(),
                     'path': path.name, 'role': 'PERC', 'descriptor': 'test', 'tags': ''})
    tsv = tmp_path / 'ableton-curated.tsv'
    with tsv.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0], delimiter='\t')
        writer.writeheader(); writer.writerows(rows)
    decoded = []
    monkeypatch.setattr(vibe_audio, 'probe_source', lambda path: {'duration_s': .01, 'sample_rate': 48000, 'channels': 2, 'frames': 480})
    def decode(path):
        decoded.append(path.name)
        return np.ones((480, 2), dtype=np.float32) * .1
    monkeypatch.setattr(vibe_audio, 'decode_source', decode)
    output = tmp_path / 'project' / 'audition'
    return root, tsv, output, rows, decoded


def test_v2_batches_resume_and_keep_skip_are_sample_id_keyed(collection):
    root, tsv, output, rows, decoded = collection
    before = {p.name: p.read_bytes() for p in root.glob('*.wav')}
    state = prepare_collection(root, output, curated=tsv)
    assert state['schema_version'] == 2 and not decoded
    assert not (output / 'sources').exists()
    first = batch_state(output)
    assert len(first['sources']) == len(decoded) == 12
    assert first['total'] == 14 and first['batch_count'] == 2
    assert all(not item['error'] for item in first['sources'])
    save_shortlist_decision(output, rows[0]['sample_id'], 'keep')
    save_shortlist_decision(output, rows[1]['sample_id'], 'skip')
    second = batch_state(output, 1)
    assert len(second['sources']) == 2 and len(decoded) == 14
    assert batch_state(output)['batch_index'] == 1
    assert len(decoded) == 14  # Restart uses hash-verified WAVs, without decoding again.
    choices = shortlist_state(output)
    assert choices['counts'] == {'total': 14, 'keep': 1, 'skip': 1, 'unreviewed': 12}
    assert choices['decisions'][rows[0]['sample_id']] == 'keep'
    assert set(choices['decisions'].values()) <= {'unreviewed', 'keep', 'skip'}
    assert {p.name: p.read_bytes() for p in root.glob('*.wav')} == before
    assert not (root / 'CURATED').exists()


def test_changed_source_or_working_audio_is_visible_and_decisions_survive(collection):
    root, tsv, output, rows, _ = collection
    prepare_collection(root, output, curated=tsv)
    batch_state(output)
    first, second = (row['sample_id'] for row in rows[:2])
    save_shortlist_decision(output, first, 'keep')
    (root / rows[0]['path']).write_bytes(b'changed original')
    (output / 'sources' / f'{second}.wav').write_bytes(b'changed working copy')
    batch = batch_state(output)
    assert 'changed' in batch['sources'][0]['error']
    assert 'changed' in batch['sources'][1]['error']
    assert shortlist_state(output)['decisions'][first] == 'keep'
    for sid in (first, second):
        with pytest.raises(VibeError, match='changed'):
            source_audio(output, sid)


def test_collection_plan_validation_and_library_binding(collection):
    from librarytools.collection_plan import create_plan
    from librarytools.inventory import LibraryDatabase, scan_library
    from librarytools.find import Query
    root, _, output, _, _ = collection
    database = LibraryDatabase(root / '.eidetic' / 'library.sqlite')
    database.bind_root(root)
    scan_library(root, database)
    plan = create_plan(root, device='octatrack', count=14, freshness='allow', query=Query(), brief='Percussion', seed=7)
    path = output.parent.parent / 'plan.json'
    path.write_text(json.dumps(plan))
    state = prepare_collection(root, output, plan=path)
    assert state['plan_id'] == plan['plan_id']
    assert state['candidate_ids'] == [item['sample_id'] for item in plan['selected']]
    assert shortlist_state(output)['counts']['unreviewed'] == 14
    plan['selected'][0]['decision'] = 'favourite'
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError):
        prepare_collection(root, output.with_name('invalid'), plan=path)


def test_batch_route_is_token_gated_and_legacy_lab_is_explicit(collection):
    from librarytools.vibe_server import create_vibe_app
    root, tsv, output, _, _ = collection
    prepare_collection(root, output, curated=tsv)
    client = create_vibe_app(output, write_token='test').test_client()
    assert client.get('/api/sources').json['batch_index'] == 0
    assert client.post('/api/batch', json={'batch_index': 1}).status_code == 403
    headers = {'X-Vibe-Token': 'test'}
    assert client.post('/api/batch', json={'batch_index': 2}, headers=headers).status_code == 400
    assert client.post('/api/batch', json={'batch_index': 1}, headers=headers).json['batch_index'] == 1
    assert client.get('/vocal-lab').status_code == 409
    assert load_session(output)['batch_index'] == 1


def test_rebind_same_library_mount_preserves_choices_and_verifies_identity(collection):
    from librarytools.vibe_collection import rebind_root
    root, tsv, output, rows, _ = collection
    prepare_collection(root, output, curated=tsv)
    save_shortlist_decision(output, rows[0]['sample_id'], 'keep')
    moved = root.with_name('new-mount')
    root.rename(moved)
    rebind_root(output, moved)
    assert shortlist_state(output)['counts']['keep'] == 1
    assert batch_state(output)['sources'][0]['error'] is None
    other = moved.with_name('other-library'); other.mkdir()
    library_identity(other, create=True)
    with pytest.raises(VibeError, match='same portable'):
        rebind_root(output, other)


def test_browser_mode_and_batch_navigation_harness():
    import shutil
    import subprocess
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the shipped browser script regression harness')
    package = Path(__file__).resolve().parents[1]
    script = package / 'src/librarytools/resources/audition.js'
    html = script.with_suffix('.html')
    result = subprocess.run([node, str(Path(__file__).with_name('test_audition_browser.js')), str(script), str(html)],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
