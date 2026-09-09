"""Lifecycle failures must preserve bytes and enough evidence to resume."""
import csv
import json
from pathlib import Path

import pytest

from librarytools import curate, moves
from librarytools.inventory import LibraryDatabase, scan_library


def _packet(tmp_path):
    root = tmp_path / 'SAMPLES'
    source = root / 'PACKS' / 'pack' / 'kick.wav'
    source.parent.mkdir(parents=True)
    source.write_bytes(b'approved audio')
    db = LibraryDatabase(tmp_path / 'library.sqlite')
    scan_library(root, db)
    packet = tmp_path / 'packet'
    curate.prepare_packet(root, db, packet, quotas={'KICK': 1})
    labels = packet / 'labels.tsv'
    rows = list(csv.DictReader(labels.open(), delimiter='\t'))
    rows[0].update(decision='favourite', true_role='KICK', descriptor='deep', tags='tone:dark')
    with labels.open('w') as fh:
        writer = csv.DictWriter(fh, fieldnames=curate.LABEL_FIELDS, delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)
    return root, source, db, labels


def test_prepare_never_clobbers_completed_listening_packet(tmp_path):
    root, _, db, labels = _packet(tmp_path)
    before = labels.read_bytes()
    with pytest.raises(curate.CurationError, match='exists|empty'):
        curate.prepare_packet(root, db, labels.parent, quotas={'KICK': 1})
    assert labels.read_bytes() == before


def test_packet_identity_survives_rename(tmp_path):
    root, _, db, labels = _packet(tmp_path)
    packet_id = json.loads((labels.parent / 'packet-meta.json').read_text())['packet_id']
    renamed = labels.parent.with_name('renamed')
    labels.parent.rename(renamed)
    curate.promote_favourites(root, db, renamed / labels.name, run_id='one')
    with db._connect() as conn:
        assert conn.execute('select packet_id from reviews').fetchone()[0] == packet_id


def test_promotion_recovers_after_copy_before_database_record(tmp_path, monkeypatch):
    root, source, db, labels = _packet(tmp_path)
    original = db.record_promotion
    def fail_record(*args, **kwargs):
        raise OSError('database temporarily unavailable')
    monkeypatch.setattr(db, 'record_promotion', fail_record)
    with pytest.raises(OSError, match='temporarily unavailable'):
        curate.promote_favourites(root, db, labels, run_id='one')
    assert source.read_bytes() == b'approved audio'
    assert len(list((root / 'CURATED').rglob('*.wav'))) == 1
    monkeypatch.setattr(db, 'record_promotion', original)
    paths = curate.promote_favourites(root, db, labels, run_id='one')
    assert len(paths) == 1 and paths[0].read_bytes() == source.read_bytes()
    assert len(db.promotions()) == 1
    assert curate.promote_favourites(root, db, labels, run_id='one') == paths


def test_undo_recovers_after_move_before_database_record(tmp_path, monkeypatch):
    root, _, db, labels = _packet(tmp_path)
    paths = curate.promote_favourites(root, db, labels, run_id='one')
    original = db.mark_missing
    monkeypatch.setattr(db, 'mark_missing', lambda *a: (_ for _ in ()).throw(OSError('crash')))
    with pytest.raises(OSError, match='crash'):
        curate.undo_promotions(root, db, 'one')
    assert not paths[0].exists()
    monkeypatch.setattr(db, 'mark_missing', original)
    assert curate.undo_promotions(root, db, 'one') == 1
    assert curate.undo_promotions(root, db, 'one') == 1
    assert db.promotions()[0]['status'] == 'withdrawn'
    with pytest.raises(curate.CurationError, match='not been promoted|active'):
        curate.write_consumer_views(db, labels, tmp_path / 'views', quotas={'KICK': 1})


def test_changed_promoted_copy_is_never_quarantined(tmp_path):
    root, _, db, labels = _packet(tmp_path)
    paths = curate.promote_favourites(root, db, labels, run_id='one')
    paths[0].write_bytes(b'changed by user')
    with pytest.raises(curate.CurationError, match='changed'):
        curate.undo_promotions(root, db, 'one')
    assert paths[0].read_bytes() == b'changed by user'


def test_move_retry_restores_undo_after_crash(tmp_path, monkeypatch):
    root = tmp_path / 'SAMPLES'
    root.mkdir()
    source = root / 'one.wav'
    source.write_bytes(b'audio')
    destination = root / 'CATALOGUE' / 'one.wav'
    plan = [moves.Move(source, destination, 'test')]
    undo = tmp_path / 'undo.tsv'
    original = moves.safe_move
    def crash_after_move(src, dest):
        original(src, dest)
        raise OSError('power failure')
    monkeypatch.setattr(moves, 'safe_move', crash_after_move)
    with pytest.raises(OSError, match='power failure'):
        moves.apply_plan(plan, undo, root=root)
    monkeypatch.setattr(moves, 'safe_move', original)
    assert moves.apply_plan(plan, undo, root=root)['moved'] == 1
    assert undo.read_text().splitlines() == [f'{destination}\t{source}']
    assert destination.read_bytes() == b'audio'


def test_existing_undo_is_preserved_for_new_plan(tmp_path):
    root = tmp_path / 'SAMPLES'
    root.mkdir()
    undo = tmp_path / 'undo.tsv'
    undo.write_text('historical\tmove\n')
    source = root / 'one.wav'
    source.write_bytes(b'audio')
    with pytest.raises((ValueError, OSError), match='undo|exists'):
        moves.apply_plan([moves.Move(source, root / 'out.wav', 'test')], undo, root=root)
    assert undo.read_text() == 'historical\tmove\n'
    assert source.exists()


def test_recovery_preview_reads_evidence_without_mutating(tmp_path, monkeypatch):
    from librarytools import operations
    root, _, db, labels = _packet(tmp_path)
    original = db.record_promotion
    monkeypatch.setattr(db, 'record_promotion', lambda *a, **kw: (_ for _ in ()).throw(OSError('crash')))
    with pytest.raises(OSError, match='crash'):
        curate.promote_favourites(root, db, labels, run_id='one')
    files = {p: p.read_bytes() for p in (root / '.eidetic').rglob('*') if p.is_file()}
    reports = operations.recover_operations(root)
    assert reports[0]['items'] == ['published']
    assert reports[0]['recoverable'] is True
    assert files == {p: p.read_bytes() for p in (root / '.eidetic').rglob('*') if p.is_file()}
    monkeypatch.setattr(db, 'record_promotion', original)
    assert operations.recover_operations(root, db, apply=True)[0]['status'] == 'complete'
    assert len(db.promotions()) == 1


def test_sidecars_are_reported_and_preserved(tmp_path):
    root = tmp_path / 'SAMPLES'
    root.mkdir()
    source = root / 'one.wav'
    source.write_bytes(b'audio')
    sidecar = root / 'one.wav.asd'
    sidecar.write_bytes(b'Ableton analysis')
    manifest = tmp_path / 'plan.tsv'
    moves.write_plan(manifest, [moves.Move(source, root / 'out.wav', 'test')])
    report = json.loads(manifest.with_suffix('.tsv.dependencies.json').read_text())
    assert report['sidecars'][0]['path'] == str(sidecar)
    moves.apply_plan([moves.Move(source, root / 'out.wav', 'test')], tmp_path / 'undo.tsv', root=root)
    assert sidecar.read_bytes() == b'Ableton analysis'


def test_future_packet_versions_reject_before_copying(tmp_path):
    root, _, db, labels = _packet(tmp_path)
    path = labels.parent / 'packet-meta.json'
    meta = json.loads(path.read_text())
    meta['packet_format_version'] = 999
    path.write_text(json.dumps(meta))
    with pytest.raises(curate.CurationError, match='unsupported packet version'):
        curate.promote_favourites(root, db, labels, run_id='one')
    assert not (root / 'CURATED').exists()


def test_consumer_crates_have_versioned_receipts(tmp_path):
    root, _, db, labels = _packet(tmp_path)
    curate.promote_favourites(root, db, labels, run_id='one')
    paths = curate.write_consumer_views(db, labels, tmp_path / 'views', quotas={'KICK': 1})
    meta = json.loads(paths['all'].with_suffix('.tsv.metadata.json').read_text())
    assert meta['format'] == 'eidetic-crate' and meta['version'] == 1


def test_finished_move_cannot_reuse_undo_path_for_different_plan(tmp_path):
    root = tmp_path / 'SAMPLES'
    root.mkdir()
    source = root / 'one.wav'
    source.write_bytes(b'audio')
    undo = tmp_path / 'undo.tsv'
    moves.apply_plan([moves.Move(source, root / 'out.wav', 'test')], undo, root=root)
    before = undo.read_bytes()
    source2 = root / 'two.wav'
    source2.write_bytes(b'more audio')
    with pytest.raises(ValueError, match='another plan'):
        moves.apply_plan([moves.Move(source2, root / 'out2.wav', 'test')], undo, root=root)
    assert source2.exists() and undo.read_bytes() == before


def test_repeating_old_promotion_never_recreates_withdrawn_copy(tmp_path):
    root, _, db, labels = _packet(tmp_path)
    destination = curate.promote_favourites(root, db, labels, run_id='one')[0]
    curate.undo_promotions(root, db, 'one')
    with pytest.raises(curate.CurationError, match='completed|withdrawn|missing'):
        curate.promote_favourites(root, db, labels, run_id='one')
    assert not destination.exists()
    assert db.promotions()[0]['status'] == 'withdrawn'


def test_repromote_after_withdrawal_retains_both_run_histories(tmp_path):
    root, _, db, labels = _packet(tmp_path)
    destination = curate.promote_favourites(root, db, labels, run_id='one')[0]
    curate.undo_promotions(root, db, 'one')
    assert curate.promote_favourites(root, db, labels, run_id='two') == [destination]
    with db._connect() as conn:
        history = conn.execute('select run_id,status from promotion_events order by rowid').fetchall()
    assert [tuple(row) for row in history] == [('one', 'active'), ('one', 'withdrawn'), ('two', 'active')]


def test_packet_root_rebind_checks_library_identity(tmp_path):
    from librarytools.artifacts import packet_root
    root, _, db, labels = _packet(tmp_path)
    metadata = json.loads((labels.parent / 'packet-meta.json').read_text())
    moved = root.with_name('RECONNECTED')
    root.rename(moved)
    assert packet_root(metadata, moved) == moved.resolve()
    wrong = tmp_path / 'OTHER'
    wrong.mkdir()
    with pytest.raises(ValueError, match='identity'):
        packet_root(metadata, wrong)


def test_legacy_packet_root_is_not_guessed_from_another_library(tmp_path):
    from librarytools.artifacts import packet_root
    old = tmp_path / 'OLD'
    new = tmp_path / 'NEW'
    new.mkdir()
    with pytest.raises(ValueError, match='legacy|identity'):
        packet_root({'root': str(old), 'schema_version': 2}, new)


def test_failed_copy_leaves_no_partial_destination_and_can_resume(tmp_path, monkeypatch):
    from librarytools import operations
    root, source, db, labels = _packet(tmp_path)
    original = operations.shutil.copyfileobj
    def fail_after_bytes(src, dst, **kwargs):
        dst.write(src.read(3))
        raise OSError('storage temporarily unavailable')
    monkeypatch.setattr(operations.shutil, 'copyfileobj', fail_after_bytes)
    with pytest.raises(OSError, match='storage temporarily unavailable'):
        curate.promote_favourites(root, db, labels, run_id='one')
    assert list((root / 'CURATED').rglob('*.wav')) == []
    monkeypatch.setattr(operations.shutil, 'copyfileobj', original)
    paths = curate.promote_favourites(root, db, labels, run_id='one')
    assert paths[0].read_bytes() == source.read_bytes()


def test_user_edited_undo_is_preserved_on_retry(tmp_path):
    root = tmp_path / 'SAMPLES'
    root.mkdir()
    source = root / 'one.wav'
    source.write_bytes(b'audio')
    plan = [moves.Move(source, root / 'out.wav', 'test')]
    undo = tmp_path / 'undo.tsv'
    moves.apply_plan(plan, undo, root=root)
    undo.write_text('human-added recovery notes\n')
    with pytest.raises(ValueError, match='undo.*changed|undo.*differs'):
        moves.apply_plan(plan, undo, root=root)
    assert undo.read_text() == 'human-added recovery notes\n'


def test_operation_directory_symlink_cannot_redirect_journals(tmp_path):
    from librarytools import operations
    root = tmp_path / 'SAMPLES'
    (root / '.eidetic').mkdir(parents=True)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (root / '.eidetic' / 'operations').symlink_to(outside)
    with pytest.raises(ValueError, match='symlink'):
        operations.journals(root)
    assert list(outside.iterdir()) == []


def test_promotion_journal_uses_one_immutable_label_snapshot(tmp_path, monkeypatch):
    import hashlib
    from librarytools import operations
    root, _, db, labels = _packet(tmp_path)
    original = labels.read_bytes()
    reader = Path.read_bytes
    def read_then_user_edits(path):
        result = reader(path)
        if path == labels:
            path.write_bytes(result.replace(b'\tfavourite\t', b'\treject\t'))
        return result
    monkeypatch.setattr(Path, 'read_bytes', read_then_user_edits)
    curate.promote_favourites(root, db, labels, run_id='one')
    _, journal = operations.journals(root)[0]
    assert journal['labels_tsv'].encode() == original
    assert journal['labels_sha256'] == hashlib.sha256(original).hexdigest()
    assert journal['items'][0]['review']['decision'] == 'favourite'


def test_move_recovery_after_handoff_never_writes_other_mac_undo_path(tmp_path, monkeypatch):
    from librarytools import operations
    root = tmp_path / 'SAMPLES'
    root.mkdir()
    source = root / 'one.wav'
    source.write_bytes(b'audio')
    undo = tmp_path / 'old-mac' / 'undo.tsv'
    original = moves.safe_move
    def crash_after_move(src, dest):
        original(src, dest)
        raise OSError('crash')
    monkeypatch.setattr(moves, 'safe_move', crash_after_move)
    with pytest.raises(OSError, match='crash'):
        moves.apply_plan([moves.Move(source, root / 'out.wav', 'test')], undo, root=root)
    undo.parent.mkdir()
    undo.write_text('unrelated evidence at an old path\n')
    new_root = root.with_name('RECONNECTED')
    root.rename(new_root)
    monkeypatch.setattr(moves, 'safe_move', original)
    reports = operations.recover_operations(new_root, apply=True)
    assert reports[0]['status'] == 'complete'
    assert Path(reports[0]['undo']).read_text() == 'out.wav\tone.wav\n'
    assert undo.read_text() == 'unrelated evidence at an old path\n'


def test_classifier_rejects_future_packet_before_measurement(tmp_path):
    from librarytools.packet_classifier import classify_packet, PacketClassifierError
    root, _, db, labels = _packet(tmp_path)
    metadata_path = labels.parent / 'packet-meta.json'
    metadata = json.loads(metadata_path.read_text())
    metadata['schema_version'] = 99
    metadata_path.write_text(json.dumps(metadata))
    with pytest.raises(PacketClassifierError, match='unsupported packet'):
        classify_packet(root, db, labels, labels.parent / 'benchmark.tsv')


def test_classifier_subprocess_uses_parent_library_lock_without_releasing_it(tmp_path):
    import numpy as np
    import subprocess
    import sys
    from librarytools.classification.cache import EmbeddingCache, EmbeddingKey
    from librarytools.classification.models import ModelSpec
    from librarytools.classification.workers import EmbeddingWorker, SampleRef, EXCERPT_POLICY
    from librarytools.locking import library_lock
    root, source, db, labels = _packet(tmp_path)
    sample_id = curate.read_labels(labels)[0].sample_id
    cache = EmbeddingCache(db.path)
    spec = ModelSpec('fixture-model', 'pinned-revision', 3)
    cache.put(EmbeddingKey(sample_id, spec.model_id, spec.revision, EXCERPT_POLICY), np.array([1., 0., 0.]))
    with library_lock(root):
        report = EmbeddingWorker().run(spec, [SampleRef(sample_id, source)], cache)
        assert report.cache_hits == 1 and report.embedded == 0
        result = subprocess.run([sys.executable, '-c',
                                 'from pathlib import Path; from librarytools.locking import library_lock; '
                                 'lock=library_lock(Path(__import__("sys").argv[1])); lock.__enter__()',
                                 str(root)], capture_output=True, text=True)
        assert result.returncode != 0 and 'another writer' in result.stderr
