import json
import sqlite3
from pathlib import Path

import pytest

from librarytools import config
from librarytools.inventory import LibraryDatabase
from librarytools.locking import library_lock
from librarytools.state import resolve_library_db


def _legacy(directory):
    directory.mkdir(parents=True)
    path = directory / 'sample-library.sqlite'
    with sqlite3.connect(path) as conn:
        conn.executescript((Path(__file__).parent / 'fixtures/schemas/v1.sql').read_text())
        conn.execute("insert into assets values('old',1,'.wav','yesterday')")
        conn.execute("insert into reviews values('old','old-session','keep','','','ear decision','yesterday')")
    return path


def _snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}


def test_independent_onboarding_previews_and_reuses_current_state(tmp_path, monkeypatch):
    from librarytools.onboarding import onboard
    monkeypatch.setattr(config, 'LEGACY_MANIFEST_DIR', tmp_path / 'no-old-state')
    root = tmp_path / 'samples'
    root.mkdir()
    before = _snapshot(root)
    report = onboard(root, 'air', defer_machines=('mini',))
    assert report['action'] == 'initialize'
    assert _snapshot(root) == before
    report = onboard(root, 'air', defer_machines=('mini',), apply=True)
    assert report['history']['coverage'] == 'incomplete'
    assert report['history']['deferred_machines'] == ['mini']
    database_before = (root / '.eidetic/library.sqlite').read_bytes()
    report = onboard(root, 'air', apply=True)
    assert report['action'] == 'reuse'
    assert (root / '.eidetic/library.sqlite').read_bytes() == database_before
    with library_lock(root):
        pass  # Incomplete historical coverage does not block normal writes.


def test_first_machine_can_adopt_its_local_history_without_other_machine(tmp_path, monkeypatch):
    from librarytools.onboarding import onboard
    root = tmp_path / 'samples'
    root.mkdir()
    legacy = _legacy(tmp_path / 'old/manifests')
    monkeypatch.setattr(config, 'LEGACY_MANIFEST_DIR', legacy.parent)
    labels = legacy.parent / 'labels.tsv'
    labels.write_text('old listening decision')
    original = legacy.read_bytes()
    report = onboard(root, 'mini', defer_machines=('air',), apply=True)
    assert report['action'] == 'adopt'
    assert legacy.read_bytes() == original
    with sqlite3.connect(root / '.eidetic/library.sqlite') as conn:
        assert conn.execute('select notes from reviews').fetchone()[0] == 'ear decision'
    assert resolve_library_db(root) == root / '.eidetic/library.sqlite'


def test_fresh_initialization_retries_after_interruption_without_competing_identity(tmp_path, monkeypatch):
    from librarytools.onboarding import onboard
    monkeypatch.setattr(config, 'LEGACY_MANIFEST_DIR', tmp_path / 'no-old-state')
    root = tmp_path / 'samples'
    root.mkdir()
    original = LibraryDatabase.bind_root
    def interrupted(*args, **kwargs):
        raise OSError('simulated disconnect')
    monkeypatch.setattr(LibraryDatabase, 'bind_root', interrupted)
    with pytest.raises(OSError, match='disconnect'):
        onboard(root, 'air', defer_machines=('mini',), apply=True)
    with pytest.raises(ValueError):
        with library_lock(root):
            pytest.fail('incomplete initialization admitted writer')
    monkeypatch.setattr(LibraryDatabase, 'bind_root', original)
    moved = tmp_path / 'new-mount'
    root.rename(moved)
    root = moved
    report = onboard(root, 'air', defer_machines=('mini',), apply=True)
    assert report['verified']
    with library_lock(root):
        pass


def test_changed_and_new_human_files_require_new_capture_even_when_database_unchanged(tmp_path, monkeypatch):
    from librarytools.onboarding import onboard
    monkeypatch.setattr(config, 'LEGACY_MANIFEST_DIR', tmp_path / 'no-old-state')
    root = tmp_path / 'samples'
    root.mkdir()
    onboard(root, 'air', apply=True)
    source = _legacy(tmp_path / 'mini/manifests')
    monkeypatch.setattr(config, 'LEGACY_MANIFEST_DIR', source.parent)
    labels = source.parent / 'labels.tsv'
    labels.write_text('first decision')
    before = (root / '.eidetic/library.sqlite').read_bytes()
    onboard(root, 'mini', apply=True)
    assert resolve_library_db(root).is_file()
    (source.parent / 'extra-labels.tsv').write_text('new offline decisions')
    with pytest.raises(ValueError):
        resolve_library_db(root)
    onboard(root, 'mini', apply=True)
    assert resolve_library_db(root).is_file()
    assert (root / '.eidetic/library.sqlite').read_bytes() == before
    assert len(json.loads((root / '.eidetic/onboarding.json').read_text())['captures']) == 2


def test_future_portable_state_and_future_local_schema_are_rejected_without_writes(tmp_path, monkeypatch):
    from librarytools.onboarding import onboard
    monkeypatch.setattr(config, 'LEGACY_MANIFEST_DIR', tmp_path / 'no-old-state')
    root = tmp_path / 'samples'
    root.mkdir()
    onboard(root, 'air', apply=True)
    db = root / '.eidetic/library.sqlite'
    with sqlite3.connect(db) as conn:
        conn.execute('pragma user_version=999')
    before = _snapshot(root)
    with pytest.raises(ValueError):
        onboard(root, 'mini', apply=True)
    assert _snapshot(root) == before


def test_tampered_archive_cannot_acknowledge_unpreserved_local_history(tmp_path, monkeypatch):
    from librarytools.onboarding import onboard
    monkeypatch.setattr(config, 'LEGACY_MANIFEST_DIR', tmp_path / 'no-old-state')
    root = tmp_path / 'samples'
    root.mkdir()
    onboard(root, 'air', apply=True)
    source = _legacy(tmp_path / 'mini/manifests')
    monkeypatch.setattr(config, 'LEGACY_MANIFEST_DIR', source.parent)
    (source.parent / 'labels.tsv').write_text('original')
    onboard(root, 'mini', apply=True)
    saved = next((root / '.eidetic/history').rglob('labels.tsv'))
    saved.write_text('damaged evidence')
    with pytest.raises(ValueError):
        resolve_library_db(root)


def _active_and_legacy(tmp_path, monkeypatch):
    from librarytools.onboarding import onboard
    monkeypatch.setattr(config, 'LEGACY_MANIFEST_DIR', tmp_path / 'no-old-state')
    root = tmp_path / 'samples'
    root.mkdir()
    onboard(root, 'air', apply=True)
    source = _legacy(tmp_path / 'mini/manifests')
    monkeypatch.setattr(config, 'LEGACY_MANIFEST_DIR', source.parent)
    (source.parent / 'labels.tsv').write_text('original')
    return root, source


def test_capture_survives_mount_change_and_receipt_publication_interruption(tmp_path, monkeypatch):
    from librarytools import onboarding
    root, source = _active_and_legacy(tmp_path, monkeypatch)
    original = onboarding.atomic_json
    def interrupted(path, value):
        if path.name == 'onboarding.json':
            raise OSError('interrupted receipt publication')
        return original(path, value)
    monkeypatch.setattr(onboarding, 'atomic_json', interrupted)
    with pytest.raises(OSError):
        onboarding.onboard(root, 'mini', apply=True)
    assert len(list((root / '.eidetic/history').rglob('labels.tsv'))) == 1
    monkeypatch.setattr(onboarding, 'atomic_json', original)
    moved = tmp_path / 'remounted'
    root.rename(moved)
    onboarding.onboard(moved, 'mini', apply=True)
    assert resolve_library_db(moved) == moved / '.eidetic/library.sqlite'
    assert len(list((moved / '.eidetic/history').rglob('labels.tsv'))) == 1
    onboarding.onboard(moved, 'mini', apply=True)
    assert len(list((moved / '.eidetic/history').rglob('labels.tsv'))) == 1


def test_same_absolute_legacy_path_on_two_machines_keeps_inputs_independent(tmp_path, monkeypatch):
    from librarytools.onboarding import onboard
    root, source = _active_and_legacy(tmp_path, monkeypatch)
    air = tmp_path / 'air-only'
    mini = tmp_path / 'mini-only'
    air.mkdir()
    (air / 'labels.tsv').write_text('Air decisions')
    original_source = source.read_bytes()
    onboard(root, 'air', legacy_db=source, include=(air,), apply=True)
    air.rename(tmp_path / 'air-offline')
    mini.mkdir()
    (mini / 'labels.tsv').write_text('Mini decisions')
    with sqlite3.connect(source) as conn:
        conn.execute("update reviews set notes='Mini revision'")
    onboard(root, 'mini', legacy_db=source, include=(mini,), apply=True)
    assert resolve_library_db(root).is_file()
    mini.rename(tmp_path / 'mini-offline')
    (tmp_path / 'air-offline').rename(air)
    source.write_bytes(original_source)
    assert resolve_library_db(root).is_file()
    onboard(root, 'air', legacy_db=source, include=(air,), apply=True)
    assert resolve_library_db(root).is_file()


def test_unrelated_empty_archive_cannot_be_acknowledged_as_captured_history(tmp_path, monkeypatch):
    import hashlib
    from librarytools.onboarding import onboard, source_snapshot
    root, source = _active_and_legacy(tmp_path, monkeypatch)
    snapshot = source_snapshot(source, (source.parent,))
    archive = root / '.eidetic/history' / hashlib.sha256(b'mini').hexdigest()[:12] / snapshot['fingerprint']
    archive.mkdir(parents=True)
    (archive / 'manifest.json').write_text(json.dumps({'format_version': 1, 'files': {}}))
    before = _snapshot(root)
    with pytest.raises(ValueError, match='expected source'):
        onboard(root, 'mini', apply=True)
    assert _snapshot(root) == before


def test_history_symlink_rejected_before_any_external_write(tmp_path, monkeypatch):
    from librarytools.onboarding import onboard
    root, source = _active_and_legacy(tmp_path, monkeypatch)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (root / '.eidetic/history').symlink_to(outside)
    with pytest.raises(ValueError, match='symlink'):
        onboard(root, 'mini', apply=True)
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize('filename,payload', [
    ('onboarding.json', []),
    ('adoption.json', []),
    ('adoption.json', {'format_version': 1, 'operation': 'onboard-initialize', 'machine': 'mini', 'status': 'pending'}),
])
def test_malformed_metadata_has_clear_error_without_writes(tmp_path, monkeypatch, filename, payload):
    from librarytools.onboarding import onboard
    monkeypatch.setattr(config, 'LEGACY_MANIFEST_DIR', tmp_path / 'no-old-state')
    root = tmp_path / 'samples'
    (root / '.eidetic').mkdir(parents=True)
    (root / '.eidetic' / filename).write_text(json.dumps(payload))
    before = _snapshot(root)
    with pytest.raises(ValueError):
        onboard(root, 'mini', apply=True)
    assert _snapshot(root) == before


def test_future_local_schema_rejected_without_changing_current_ssd(tmp_path, monkeypatch):
    from librarytools.onboarding import onboard
    root, source = _active_and_legacy(tmp_path, monkeypatch)
    with sqlite3.connect(source) as conn:
        conn.execute('pragma user_version=999')
    before = _snapshot(root)
    with pytest.raises(ValueError, match='newer schema'):
        onboard(root, 'mini', apply=True)
    assert _snapshot(root) == before


def test_labels_without_any_database_are_preserved_and_changes_detected(tmp_path, monkeypatch):
    from librarytools.onboarding import onboard
    old = tmp_path / 'old/manifests'
    old.mkdir(parents=True)
    (old / 'labels.tsv').write_text('very early listening evidence')
    monkeypatch.setattr(config, 'LEGACY_MANIFEST_DIR', old)
    root = tmp_path / 'samples'
    root.mkdir()
    onboard(root, 'air', apply=True)
    assert len(list((root / '.eidetic/history').rglob('labels.tsv'))) == 1
    assert resolve_library_db(root).is_file()
    (old / 'labels.tsv').write_text('new offline evidence')
    with pytest.raises(ValueError):
        resolve_library_db(root)
    onboard(root, 'air', apply=True)
    assert resolve_library_db(root).is_file()
    assert len(list((root / '.eidetic/history').rglob('labels.tsv'))) == 2


def test_source_journal_appearing_during_capture_never_publishes_receipt(tmp_path, monkeypatch):
    from librarytools import onboarding
    root, source = _active_and_legacy(tmp_path, monkeypatch)
    copy_file = onboarding._copy_file
    writer = None
    def copied_then_changed(path, target):
        nonlocal writer
        copy_file(path, target)
        if path == source:
            writer = sqlite3.connect(source)
            writer.execute('pragma journal_mode=WAL')
            writer.execute("update reviews set notes='concurrent new listening decision'")
            writer.commit()
    monkeypatch.setattr(onboarding, '_copy_file', copied_then_changed)
    original = (root / '.eidetic/library.sqlite').read_bytes()
    try:
        with pytest.raises(ValueError, match='journal|changed'):
            onboarding.onboard(root, 'mini', apply=True)
        assert json.loads((root / '.eidetic/onboarding.json').read_text())['captures'] == {}
        assert (root / '.eidetic/library.sqlite').read_bytes() == original
    finally:
        if writer is not None:
            writer.close()


def test_secondary_sqlite_with_arbitrary_suffix_rejects_pending_wal(tmp_path, monkeypatch):
    from librarytools.onboarding import onboard
    root, source = _active_and_legacy(tmp_path, monkeypatch)
    secondary = source.parent / 'older-cache.data'
    writer = sqlite3.connect(secondary)
    try:
        writer.execute('pragma journal_mode=WAL')
        writer.execute('create table old_notes(note text)')
        writer.execute("insert into old_notes values('human note in WAL')")
        writer.commit()
        before = _snapshot(root)
        with pytest.raises(ValueError, match='journal'):
            onboard(root, 'mini', apply=True)
        assert _snapshot(root) == before
    finally:
        writer.close()


def test_older_narrower_receipt_cannot_hide_changed_later_evidence_input(tmp_path, monkeypatch):
    from librarytools.onboarding import onboard
    root, source = _active_and_legacy(tmp_path, monkeypatch)
    first = tmp_path / 'first-review.tsv'
    later = tmp_path / 'later-review.tsv'
    first.write_text('first hearing')
    later.write_text('second hearing')
    onboard(root, 'mini', include=(first,), apply=True)
    onboard(root, 'mini', include=(later,), apply=True)
    later.write_text('a new offline decision')
    with pytest.raises(ValueError):
        resolve_library_db(root)
    onboard(root, 'mini', include=(later,), apply=True)
    assert resolve_library_db(root).is_file()


def test_other_machine_narrower_receipt_cannot_hide_accessible_changed_evidence(tmp_path, monkeypatch):
    from librarytools.onboarding import onboard
    root, source = _active_and_legacy(tmp_path, monkeypatch)
    extra = tmp_path / 'mini-extra.tsv'
    extra.write_text('Mini listening decision')
    onboard(root, 'air', apply=True)
    onboard(root, 'mini', include=(extra,), apply=True)
    extra.write_text('new offline Mini decision')
    before = _snapshot(root)
    with pytest.raises(ValueError):
        resolve_library_db(root)
    assert _snapshot(root) == before

    # A new capture includes accessible evidence from either label, without
    # requiring the caller to rediscover every previously included path.
    report = onboard(root, 'air')
    assert str(extra) in report['included_evidence']
    assert _snapshot(root) == before
    onboard(root, 'air', apply=True)
    assert resolve_library_db(root).is_file()
    count = len(json.loads((root / '.eidetic/onboarding.json').read_text())['captures'])
    onboard(root, 'air', apply=True)
    assert len(json.loads((root / '.eidetic/onboarding.json').read_text())['captures']) == count

    # Different old DB bytes at the same path do not cause a permanent conflict:
    # preserving the current complete snapshot restores ordinary operation.
    with sqlite3.connect(source) as conn:
        conn.execute("update reviews set notes='another machine revision'")
    with pytest.raises(ValueError):
        resolve_library_db(root)
    onboard(root, 'mini', apply=True)
    assert resolve_library_db(root).is_file()
