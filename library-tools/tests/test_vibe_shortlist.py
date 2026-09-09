from __future__ import annotations

import hashlib
import csv
import json
from pathlib import Path
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from librarytools import curate
from librarytools.inventory import LibraryDatabase, scan_library
from librarytools.locking import _file_lock, LibraryBusyError
from librarytools.vibe import VibeError
from librarytools import vibe_shortlist as shortlist


def session_fixture(tmp_path):
    root = tmp_path / 'library'
    root.mkdir()
    session = tmp_path / 'session'
    session.mkdir()
    sources = {}
    for name, payload in [('groove.wav', b'groove'), ('voice.wav', b'voice')]:
        (root / name).write_bytes(payload)
        sample_id = hashlib.sha256(payload).hexdigest()
        sources[sample_id] = {'id': sample_id, 'name': name, 'path': name,
            'preview_hash': '0' * 64, 'duration_s': 2, 'suggested_bars': 1,
            'waveform': [0.1]}
    ids = list(sources)
    (session / 'session.json').write_text(json.dumps({'schema_version': 1,
        'root': str(root), 'bpm': 120, 'bars': 8, 'sources': sources,
        'anchors': [ids[0]], 'vocals': [ids[1]]}))
    return root, session, ids


def test_shortlist_decisions_persist_reset_and_ignore_pair_feedback(tmp_path):
    root, session, ids = session_fixture(tmp_path)
    (session / 'feedback.json').write_text('{"schema_version": 1, "feedback": [{"decision": "works"}]}')
    original = {p.name: p.read_bytes() for p in root.iterdir()}
    assert shortlist.shortlist_state(session)['counts'] == {'total': 2, 'keep': 0, 'skip': 0, 'unreviewed': 2}
    shortlist.save_shortlist_decision(session, ids[0], 'keep')
    result = shortlist.save_shortlist_decision(session, ids[1], 'skip')
    assert result['decisions'] == {ids[0]: 'keep', ids[1]: 'skip'}
    assert shortlist.shortlist_state(session) == result
    assert shortlist.save_shortlist_decision(session, ids[0], 'unreviewed')['counts']['keep'] == 0
    assert {p.name: p.read_bytes() for p in root.iterdir()} == original


@pytest.mark.parametrize('source_id,decision', [('f' * 64, 'keep'), ('../x', 'keep'), (None, 'skip'), ('known', 'favourite'), ('known', None)])
def test_shortlist_rejects_unknown_sources_and_decisions(tmp_path, source_id, decision):
    _, session, ids = session_fixture(tmp_path)
    with pytest.raises(VibeError):
        shortlist.save_shortlist_decision(session, ids[0] if source_id == 'known' else source_id, decision)
    assert not (session / 'shortlist.json').exists()


def test_keep_and_playlist_recheck_original_bytes(tmp_path):
    root, session, ids = session_fixture(tmp_path)
    shortlist.save_shortlist_decision(session, ids[0], 'keep')
    assert shortlist.shortlist_playlist(session) == f'#EXTM3U\n{root / "groove.wav"}\n'
    (root / 'groove.wav').write_bytes(b'changed')
    with pytest.raises(VibeError, match='changed'):
        shortlist.shortlist_playlist(session)
    with pytest.raises(VibeError, match='changed'):
        shortlist.save_shortlist_decision(session, ids[0], 'keep')
    shortlist.save_shortlist_decision(session, ids[0], 'skip')


def test_shortlist_writers_share_session_lock(tmp_path):
    _, session, ids = session_fixture(tmp_path)
    with _file_lock(session / 'writer.lock', purpose='test existing writer'):
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(shortlist.save_shortlist_decision, session, ids[0], 'keep')
            with pytest.raises(LibraryBusyError):
                result.result()


def test_corrupt_shortlist_is_not_silently_replaced(tmp_path):
    _, session, ids = session_fixture(tmp_path)
    path = session / 'shortlist.json'
    path.write_text('{"schema_version": 1, "decisions": {"unknown": "keep"}}')
    before = path.read_bytes()
    with pytest.raises(VibeError):
        shortlist.save_shortlist_decision(session, ids[0], 'keep')
    assert path.read_bytes() == before


def test_empty_shortlist_playlist_and_packet_fail_without_creating_state(tmp_path):
    root, session, _ = session_fixture(tmp_path)
    for operation in [lambda: shortlist.shortlist_playlist(session),
                      lambda: shortlist.create_shortlist_packet(session, tmp_path / 'packet')]:
        with pytest.raises(VibeError, match='Keep'):
            operation()
    assert not (root / '.eidetic').exists()
    assert not (tmp_path / 'packet').exists()


def test_missing_index_status_is_read_only_and_packet_errors_clearly(tmp_path):
    root, session, ids = session_fixture(tmp_path)
    shortlist.save_shortlist_decision(session, ids[0], 'keep')
    status = shortlist.handoff_status(session, tmp_path / 'missing.sqlite')
    assert status['available'] is False
    assert 'index' in status['reason'].lower()
    with pytest.raises(VibeError, match='index'):
        shortlist.create_shortlist_packet(session, tmp_path / 'packet', tmp_path / 'missing.sqlite')
    assert not (root / '.eidetic').exists()
    assert not (tmp_path / 'missing.sqlite').exists()


def test_exact_shortlist_becomes_canonical_keep_packet_in_source_order(tmp_path):
    root, session, ids = session_fixture(tmp_path)
    (root / 'unselected-kick.wav').write_bytes(b'other')
    db_path = tmp_path / 'library.sqlite'
    db = LibraryDatabase(db_path)
    scan = scan_library(root, db)
    for sample_id in reversed(ids):
        shortlist.save_shortlist_decision(session, sample_id, 'keep')
    packet = session / 'curation-packets' / 'one'
    assert shortlist.handoff_status(session, db_path)['available'] is True
    assert shortlist.create_shortlist_packet(session, packet, db_path) == 2
    rows = curate.read_labels(packet / 'labels.tsv')
    curate.validate_labels(rows)
    assert [row.sample_id for row in rows] == ids
    assert [row.current_path for row in rows] == [Path('groove.wav'), Path('voice.wav')]
    assert all(row.decision == 'keep' and not row.true_role and not row.descriptor for row in rows)
    metadata = json.loads((packet / 'packet-meta.json').read_text())
    assert metadata['schema_version'] == 2
    assert metadata['scan_id'] == scan.scan_id
    assert (packet / 'audition.m3u8').read_text().splitlines()[1:] == [str(root / 'groove.wav'), str(root / 'voice.wav')]
    assert not (root / 'CURATED').exists()


def test_shortlist_requires_explicit_favourite_before_promotion_and_crate(tmp_path):
    root, session, ids = session_fixture(tmp_path)
    originals = {path: path.read_bytes() for path in root.glob('*.wav')}
    db_path = tmp_path / 'library.sqlite'
    db = LibraryDatabase(db_path)
    scan_library(root, db)
    for sample_id in ids:
        shortlist.save_shortlist_decision(session, sample_id, 'keep')
    packet = tmp_path / 'packet'
    assert shortlist.create_shortlist_packet(session, packet, db_path) == 2
    labels = packet / 'labels.tsv'
    initial = curate.read_labels(labels)
    curate.validate_labels(initial)
    assert all(row.decision == 'keep' and not row.true_role and not row.descriptor for row in initial)

    # This explicit label edit represents human approval in this synthetic test.
    with labels.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle, delimiter='\t'))
    approved_id = ids[1]
    rows[1].update(decision='favourite', true_role='VOCAL-LOOP', descriptor='short-phrase')
    with labels.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=curate.LABEL_FIELDS, delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)
    updated = curate.read_labels(labels)
    assert updated[0] == initial[0]
    curate.validate_labels(updated)

    promoted = curate.promote_favourites(root, db, labels, run_id='shortlist-test')
    assert len(promoted) == 1
    assert promoted[0].parent == root / 'CURATED' / 'VOCAL-LOOP'
    assert promoted[0].read_bytes() == originals[root / 'voice.wav']
    assert [item['sample_id'] for item in db.promotions()] == [approved_id]
    assert list((root / 'CURATED').rglob('*.wav')) == promoted

    views = curate.write_consumer_views(db, labels, tmp_path / 'views',
        quotas={'VOCAL-LOOP': 1}, name='shortlist-test')
    with views['all'].open(encoding='utf-8', newline='') as handle:
        crate = list(csv.DictReader(handle, delimiter='\t'))
    assert len(crate) == 1
    assert crate[0]['sample_id'] == approved_id
    assert root / crate[0]['source_path'] == promoted[0]
    assert crate[0]['role'] == 'VOCAL-LOOP'
    assert crate[0]['descriptor'] == 'short-phrase'
    assert ids[0] not in views['all'].read_text()
    assert originals == {path: path.read_bytes() for path in originals}


@pytest.mark.parametrize('damage', ['bytes', 'missing', 'unindexed', 'outside', 'duplicate', 'newline', 'wrong_hash', 'symlink'])
def test_explicit_packet_rejects_invalid_evidence_before_writing(tmp_path, damage):
    root, _, ids = session_fixture(tmp_path)
    db = LibraryDatabase(tmp_path / 'library.sqlite')
    scan_library(root, db)
    candidates = [(ids[0], Path('groove.wav'))]
    if damage == 'bytes':
        (root / 'groove.wav').write_bytes(b'changed')
    elif damage == 'missing':
        (root / 'groove.wav').unlink()
    elif damage == 'unindexed':
        (root / 'new.wav').write_bytes(b'groove')
        candidates = [(ids[0], Path('new.wav'))]
    elif damage == 'outside':
        candidates = [(ids[0], Path('../groove.wav'))]
    elif damage == 'duplicate':
        candidates *= 2
    elif damage == 'wrong_hash':
        candidates = [(ids[1], Path('groove.wav'))]
    elif damage == 'symlink':
        (root / 'groove.wav').unlink()
        other = tmp_path / 'outside.wav'
        other.write_bytes(b'groove')
        (root / 'groove.wav').symlink_to(other)
    elif damage == 'newline':
        path = root / 'bad\nname.wav'
        path.write_bytes(b'groove')
        scan_library(root, db)
        candidates = [(ids[0], path.relative_to(root))]
    out = tmp_path / 'packet'
    with pytest.raises(curate.CurationError):
        curate.prepare_packet(root, db, out, explicit_candidates=candidates)
    assert not out.exists()


def test_playlist_rejects_newlines_in_original_paths(tmp_path):
    root, session, ids = session_fixture(tmp_path)
    renamed = root / 'groove\nfile.wav'
    (root / 'groove.wav').rename(renamed)
    manifest = session / 'session.json'
    state = json.loads(manifest.read_text())
    state['sources'][ids[0]]['path'] = renamed.name
    manifest.write_text(json.dumps(state))
    shortlist.save_shortlist_decision(session, ids[0], 'keep')
    with pytest.raises(VibeError, match='newline'):
        shortlist.shortlist_playlist(session)


def test_handoff_status_does_not_modify_index_or_lock(tmp_path):
    root, session, _ = session_fixture(tmp_path)
    db_path = tmp_path / 'library.sqlite'
    scan_library(root, LibraryDatabase(db_path))
    observed = [db_path, root / '.eidetic' / 'library.json', root / '.eidetic' / 'writer.lock']
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in observed}
    assert shortlist.handoff_status(session, db_path)['available'] is True
    assert before == {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in observed}


def test_explicit_empty_packet_does_not_fall_back_to_quotas(tmp_path):
    root, _, _ = session_fixture(tmp_path)
    db = LibraryDatabase(tmp_path / 'library.sqlite')
    scan_library(root, db)
    out = tmp_path / 'packet'
    with pytest.raises(curate.CurationError, match='empty'):
        curate.prepare_packet(root, db, out, explicit_candidates=[])
    assert not out.exists()


def test_incomplete_index_and_wrong_library_are_unavailable(tmp_path):
    root, session, ids = session_fixture(tmp_path)
    db_path = tmp_path / 'library.sqlite'
    db = LibraryDatabase(db_path)
    db.bind_root(root)
    assert shortlist.handoff_status(session, db_path)['available'] is False
    scan_library(root, db)
    other = tmp_path / 'other'
    other.mkdir()
    other_db_path = tmp_path / 'other.sqlite'
    scan_library(other, LibraryDatabase(other_db_path))
    assert shortlist.handoff_status(session, other_db_path)['available'] is False


def test_shortlist_packet_rejects_library_or_reserved_output(tmp_path):
    root, session, ids = session_fixture(tmp_path)
    shortlist.save_shortlist_decision(session, ids[0], 'keep')
    for output in [root / 'packet', session, session / 'sources' / 'packet', session / 'renders' / 'packet']:
        with pytest.raises(VibeError, match='output'):
            shortlist.create_shortlist_packet(session, output)


def test_cli_packet_sqlite_failure_is_controlled(tmp_path, monkeypatch, capsys):
    from librarytools.vibe_cli import main
    def failed(*args, **kwargs):
        raise sqlite3.DatabaseError('damaged index')
    monkeypatch.setattr(shortlist, 'create_shortlist_packet', failed)
    assert main(['packet', '--session-dir', str(tmp_path), '--output-dir', str(tmp_path / 'packet')]) == 2
    assert 'damaged index' in capsys.readouterr().err


def test_cli_playlist_prints_original_paths(tmp_path, capsys):
    from librarytools.vibe_cli import main
    root, session, ids = session_fixture(tmp_path)
    shortlist.save_shortlist_decision(session, ids[1], 'keep')
    assert main(['playlist', '--session-dir', str(session)]) == 0
    assert capsys.readouterr().out == f'#EXTM3U\n{root / "voice.wav"}\n'
