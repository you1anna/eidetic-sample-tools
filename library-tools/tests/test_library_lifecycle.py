import json
import sqlite3
from pathlib import Path

import pytest

from librarytools.inventory import LibraryDatabase, scan_library


def historic(tmp_path, version):
    path = tmp_path / 'legacy.sqlite'
    with sqlite3.connect(path) as conn:
        conn.executescript((Path(__file__).parent / f'fixtures/schemas/v{version}.sql').read_text())
        conn.execute("insert into assets values ('sample',4,'.wav','2025-01-01')")
        conn.execute("insert into reviews values ('sample','old-packet','favourite','KICK','warm','','2025-01-01')")
    return path


def test_malformed_adoption_record_does_not_crash_legacy_diagnostics(tmp_path, monkeypatch):
    from librarytools import config
    from librarytools.lifecycle import doctor
    from librarytools.state import legacy_is_superseded
    source = historic(tmp_path, 1)
    legacy = source.with_name('sample-library.sqlite')
    source.rename(legacy)
    monkeypatch.setattr(config, 'LEGACY_MANIFEST_DIR', tmp_path)
    root = tmp_path / 'samples'
    state = root / '.eidetic'
    state.mkdir(parents=True)
    record = state / 'adoption.json'
    record.write_text('[]')
    before = {path: path.read_bytes() for path in (record, legacy)}
    assert legacy_is_superseded(root, legacy) is False
    report = doctor(root)
    assert report['legacy_superseded'] is False
    assert any('invalid adoption record' in issue for issue in report['issues'])
    assert {path: path.read_bytes() for path in (record, legacy)} == before


@pytest.mark.parametrize('version', [1, 2, 3, 4])
def test_old_schema_requires_explicit_migration_and_preserves_evidence(tmp_path, version):
    from librarytools.schema import MigrationRequired, SCHEMA_VERSION, migrate_database
    path = historic(tmp_path, version)
    before = path.read_bytes()
    with pytest.raises(MigrationRequired):
        LibraryDatabase(path)
    assert path.read_bytes() == before
    preview = migrate_database(path)
    assert preview['apply'] is False
    assert path.read_bytes() == before
    report = migrate_database(path, apply=True, backup_dir=tmp_path / 'backup')
    assert report['schema_version'] == SCHEMA_VERSION
    with sqlite3.connect(path) as conn:
        assert conn.execute('select decision from reviews').fetchone()[0] == 'favourite'
    assert (tmp_path / 'backup' / 'manifest.json').is_file()
    LibraryDatabase(path)


def test_future_and_unknown_database_open_does_not_write(tmp_path):
    from librarytools.schema import SchemaError
    for version in (999, 4):
        path = tmp_path / f'{version}.sqlite'
        with sqlite3.connect(path) as conn:
            conn.execute('create table unexpected(data text)')
            conn.execute(f'pragma user_version={version}')
        before = path.read_bytes()
        with pytest.raises(SchemaError):
            LibraryDatabase(path)
        assert path.read_bytes() == before


def test_misleading_old_stamp_uses_validated_shape(tmp_path):
    from librarytools.schema import migrate_database
    path = historic(tmp_path, 2)
    with sqlite3.connect(path) as conn:
        conn.execute('pragma user_version=4')
    report = migrate_database(path)
    assert report['detected_version'] == 2


def test_incomplete_scan_does_not_publish_new_or_missing_locations(tmp_path):
    root = tmp_path / 'SAMPLES'
    root.mkdir()
    sound = root / 'sound.wav'
    sound.write_bytes(b'old')
    db = LibraryDatabase(tmp_path / 'library.sqlite')
    scan_library(root, db)
    before = db.current_locations()
    sound.write_bytes(b'new content')
    pending = db.begin_scan(root)
    db.record_file(root, sound, pending)
    assert db.current_locations() == before
    assert len(db.assets()) == 1


def test_missing_root_rejected_before_retiring_inventory(tmp_path):
    root = tmp_path / 'SAMPLES'
    root.mkdir()
    (root / 'sound.wav').write_bytes(b'sound')
    db = LibraryDatabase(tmp_path / 'library.sqlite')
    scan_library(root, db)
    before = db.current_locations()
    with pytest.raises(ValueError, match='root'):
        scan_library(root / 'missing', db)
    assert db.current_locations() == before


def test_library_uuid_survives_mount_relocation_and_rejects_other_library(tmp_path):
    root = tmp_path / 'SAMPLES'
    root.mkdir()
    (root / 'sound.wav').write_bytes(b'sound')
    db = LibraryDatabase(tmp_path / 'library.sqlite')
    scan_library(root, db)
    original_id = json.loads((root / '.eidetic/library.json').read_text())['library_id']
    moved = tmp_path / 'remounted'
    root.rename(moved)
    scan_library(moved, db)
    assert json.loads((moved / '.eidetic/library.json').read_text())['library_id'] == original_id
    other = tmp_path / 'other'
    other.mkdir()
    with pytest.raises(ValueError, match='library|identity'):
        scan_library(other, db)
    assert not (other / '.eidetic').exists()


def test_backup_restore_verifies_database_and_human_files(tmp_path):
    from librarytools.lifecycle import backup_bundle, restore_bundle
    root = tmp_path / 'SAMPLES'
    root.mkdir()
    db = LibraryDatabase(root / '.eidetic/library.sqlite')
    scan_library(root, db)
    labels = root / '.eidetic/packets/session/labels.tsv'
    labels.parent.mkdir(parents=True)
    labels.write_text('human evidence\n')
    bundle = tmp_path / 'backup'
    backup_bundle(db.path, bundle, root=root)
    restored = tmp_path / 'restored-state'
    restore_bundle(bundle, restored)
    assert (restored / 'packets/session/labels.tsv').read_text() == 'human evidence\n'
    assert (restored / 'library.sqlite').is_file()
    labels_backup = bundle / 'state/packets/session/labels.tsv'
    labels_backup.write_text('tampered')
    with pytest.raises(ValueError, match='hash|checksum'):
        restore_bundle(bundle, tmp_path / 'bad-restore')
    assert not (tmp_path / 'bad-restore').exists()


def test_doctor_missing_state_is_read_only(tmp_path):
    from librarytools.lifecycle import doctor
    root = tmp_path / 'SAMPLES'
    root.mkdir()
    report = doctor(root)
    assert report['database']['status'] == 'missing'
    assert list(root.iterdir()) == []


def test_retagging_preserves_human_tags_and_rolls_back_failure(tmp_path):
    db = LibraryDatabase(tmp_path / 'library.sqlite')
    with db._connect() as conn:
        conn.execute("insert into assets values ('a',1,'.wav','today')")
    db.record_tags('a', [('role','KICK')])
    db.record_tags('a', [('feel','favourite')], source='human')
    db.replace_generated_tags({'a': [('role','PERC')]})
    assert db.tags_for('a') == [('feel','favourite'), ('role','PERC')]
    with pytest.raises(sqlite3.IntegrityError):
        db.replace_generated_tags({'missing': [('role','SNARE')]})
    assert ('role','PERC') in db.tags_for('a')


def test_feature_versions_and_promotion_history(tmp_path):
    db = LibraryDatabase(tmp_path / 'library.sqlite')
    with db._connect() as conn:
        conn.execute("insert into assets values ('a',1,'.wav','today')")
    db.record_features('a', '{}', 'decode failure', extractor_version='acoustic-v1')
    assert not db.feature_ids(successful_only=True)
    assert db.feature_metadata()['a']['audio_error'] == 'decode failure'
    db.record_features('a', '{"rms":1}', extractor_version='acoustic-v2')
    assert not db.feature_ids(extractor_version='acoustic-v1')
    assert db.feature_ids(extractor_version='acoustic-v2', successful_only=True) == {'a'}
    db.record_promotion('a', Path('CURATED/a.wav'), Path('PACKS/a.wav'), 'run')
    db.mark_promotion_withdrawn('a', Path('CURATED/a.wav'))
    assert db.promotions(include_inactive=False) == []
    with db._connect() as conn:
        assert [r[0] for r in conn.execute('select status from promotion_events order by event_id')] == ['active','withdrawn']


def test_revised_reviews_and_picks_keep_original_human_evidence(tmp_path):
    db = LibraryDatabase(tmp_path / 'library.sqlite')
    with db._connect() as conn:
        conn.execute("insert into assets values ('a',1,'.wav','today')")
    db.record_review('a', 'packet', 'keep', 'KICK', 'short', 'first thought')
    db.record_review('a', 'packet', 'reject', 'PERC', '', 'changed my mind')
    db.record_pick('a', 'kit', 'kick', True)
    db.record_pick('a', 'kit', 'kick', False)
    with db._connect() as conn:
        assert [r[0] for r in conn.execute('select decision from review_events order by event_id')] == ['keep','reject']
        assert [r[0] for r in conn.execute('select kept from pick_events order by event_id')] == [1,0]


def test_failed_migration_rolls_back_every_schema_step(tmp_path, monkeypatch):
    from librarytools import schema
    path = historic(tmp_path, 1)
    original = path.read_bytes()
    execute = schema._execute_migration
    def failing(conn, version):
        execute(conn, version)
        if version == 3:
            raise RuntimeError('simulated interruption')
    monkeypatch.setattr(schema, '_execute_migration', failing)
    with pytest.raises(RuntimeError, match='interruption'):
        schema.migrate_database(path, apply=True, backup_dir=tmp_path / 'backup')
    assert path.read_bytes() == original


def test_interrupted_traversal_leaves_completed_inventory_unchanged(tmp_path, monkeypatch):
    from librarytools import inventory
    root = tmp_path / 'samples'
    root.mkdir()
    (root / 'a.wav').write_bytes(b'a')
    db = LibraryDatabase(tmp_path / 'library.sqlite')
    scan_library(root, db)
    before = db.current_locations()
    def broken_walk(*args, **kwargs):
        yield str(root), [], ['a.wav']
        kwargs['onerror'](PermissionError('unreadable subtree'))
    monkeypatch.setattr(inventory.os, 'walk', broken_walk)
    with pytest.raises(PermissionError):
        scan_library(root, db)
    assert db.current_locations() == before


def test_database_readonly_and_long_lived_future_guard(tmp_path):
    from librarytools.schema import SchemaError
    path = tmp_path / 'library.sqlite'
    db = LibraryDatabase(path)
    readonly = LibraryDatabase(path, readonly=True)
    with pytest.raises(sqlite3.OperationalError):
        readonly.record_pick('anything', 'kit', 'query')
    with sqlite3.connect(path) as conn:
        conn.execute('pragma user_version=999')
    with pytest.raises(SchemaError, match='schema'):
        db.record_pick('anything', 'kit', 'query')


def test_future_library_marker_is_rejected_before_lock_writes(tmp_path):
    from librarytools.locking import library_lock
    root = tmp_path / 'samples'
    state = root / '.eidetic'
    state.mkdir(parents=True)
    (state / 'library.json').write_text(json.dumps({'format_version': 999, 'library_id': 'not-used'}))
    with pytest.raises(ValueError, match='version'):
        with library_lock(root):
            pytest.fail('lock granted for future state')
    assert not (state / 'writer.lock').exists()


def test_competing_process_writer_is_rejected_with_owner_details(tmp_path):
    import subprocess
    import sys
    from librarytools.locking import LibraryBusyError, library_lock
    root = tmp_path / 'samples'
    root.mkdir()
    source = "from pathlib import Path; from librarytools.locking import library_lock; import sys; " \
             "lock=library_lock(Path(sys.argv[1]), purpose='test owner'); lock.__enter__(); print('locked',flush=True); sys.stdin.readline(); lock.__exit__(None,None,None)"
    child = subprocess.Popen([sys.executable, '-c', source, str(root)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == 'locked'
        with pytest.raises(LibraryBusyError, match='test owner'):
            with library_lock(root):
                pytest.fail('competing writer entered')
    finally:
        child.communicate('\n', timeout=5)
    with library_lock(root):
        pass


@pytest.mark.parametrize('mode', ['WAL', 'PERSIST', 'TRUNCATE'])
def test_doctor_never_creates_journal_sidecars(tmp_path, mode):
    from librarytools.lifecycle import doctor
    root = tmp_path / 'samples'
    root.mkdir()
    db = LibraryDatabase(root / '.eidetic/library.sqlite')
    scan_library(root, db)
    with sqlite3.connect(db.path) as conn:
        conn.execute(f'pragma journal_mode={mode}')
        conn.execute("insert into state_metadata values('test','test')")
    conn.close()
    before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
    assert doctor(root)['database']['status'] == 'current'
    assert {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()} == before


def test_unknown_constraint_is_not_a_recognised_historical_schema(tmp_path):
    from librarytools.schema import SchemaError, inspect_database
    path = tmp_path / 'changed.sqlite'
    sql = (Path(__file__).parent / 'fixtures/schemas/v1.sql').read_text().replace("check(status in ('incomplete','complete'))", '')
    with sqlite3.connect(path) as conn:
        conn.executescript(sql)
    with pytest.raises(SchemaError, match='structure'):
        inspect_database(path)


def test_explicit_worker_inherits_parent_lock_without_unlocking_it(tmp_path):
    import subprocess
    import sys
    from librarytools.locking import adopt_inherited_library_lock, inherited_lock_fd, library_lock
    root = tmp_path / 'samples'
    root.mkdir()
    db = LibraryDatabase(root / '.eidetic/library.sqlite')
    scan_library(root, db)
    script = ('import sys; from pathlib import Path; '
              'from librarytools.locking import adopt_inherited_library_lock; '
              'from librarytools.inventory import LibraryDatabase; '
              'ctx=adopt_inherited_library_lock(Path(sys.argv[1]),int(sys.argv[2])); '
              'ctx.__enter__(); db=LibraryDatabase(Path(sys.argv[1])/".eidetic/library.sqlite"); '
              'print(db.assets()); ctx.__exit__(None,None,None)')
    with library_lock(root):
        fd = inherited_lock_fd(root)
        child = subprocess.run([sys.executable, '-c', script, str(root), str(fd)], pass_fds=(fd,), capture_output=True, text=True)
        assert child.returncode == 0, child.stderr
        # A distinct process without the inherited description is still excluded.
        other = subprocess.run([sys.executable, '-c', 'from pathlib import Path; from librarytools.locking import library_lock; import sys; library_lock(Path(sys.argv[1])).__enter__()', str(root)], capture_output=True, text=True)
        assert other.returncode != 0
        assert 'another writer' in other.stderr
    assert inherited_lock_fd(root) is None


def test_bound_external_database_cannot_write_after_ssd_identity_swap(tmp_path):
    from librarytools.state import library_identity
    root = tmp_path / 'samples'
    root.mkdir()
    db = LibraryDatabase(tmp_path / 'library.sqlite')
    scan_library(root, db)
    original = (root / '.eidetic/library.json').read_text()
    (root / '.eidetic/library.json').unlink()
    library_identity(root, create=True)
    with pytest.raises(ValueError, match='identity'):
        db.record_pick('anything', 'kit', 'query')
    (root / '.eidetic/library.json').write_text(original)
    moved = tmp_path / 'new-mount'
    root.rename(moved)
    reopened = LibraryDatabase(db.path)
    with pytest.raises(ValueError, match='bound|root'):
        reopened.record_pick('anything', 'kit', 'query')
    reopened.bind_root(moved)
    assert reopened.assets() == []


@pytest.mark.parametrize('change', ['missing', 'changed'])
def test_scan_preserves_promotion_discrepancy_in_doctor_until_matching_copy_restored(tmp_path, change):
    from librarytools.lifecycle import doctor
    root = tmp_path / 'samples'
    curated = root / 'CURATED/KICK/kick.wav'
    curated.parent.mkdir(parents=True)
    source = root / 'kick.wav'
    source.write_bytes(b'approved audio')
    curated.write_bytes(source.read_bytes())
    db = LibraryDatabase(root / '.eidetic/library.sqlite')
    scan_library(root, db)
    sample_id = db.location(Path('kick.wav')).sample_id
    db.record_promotion(sample_id, curated.relative_to(root), Path('kick.wav'), 'original-approval')
    if change == 'missing':
        curated.unlink()
    else:
        curated.write_bytes(b'unapproved changed audio')
    scan_library(root, db)
    assert db.promotions()[0]['status'] == 'missing'
    report = doctor(root)
    assert report['promotion_discrepancies'][0]['sample_id'] == sample_id
    assert any('promotion' in issue for issue in report['issues'])
    curated.write_bytes(source.read_bytes())
    scan_library(root, db)
    assert db.promotions()[0]['status'] == 'active'
    assert doctor(root)['promotion_discrepancies'] == []


def test_writer_lock_symlink_never_truncates_target(tmp_path):
    from librarytools.locking import library_lock
    root = tmp_path / 'samples'
    state = root / '.eidetic'
    state.mkdir(parents=True)
    sound = root / 'precious.wav'
    sound.write_bytes(b'original audio')
    (state / 'writer.lock').symlink_to(sound)
    with pytest.raises(ValueError, match='symlink'):
        with library_lock(root):
            pytest.fail('symlink lock accepted')
    assert sound.read_bytes() == b'original audio'


def test_completed_rescan_supersedes_old_incomplete_scan_without_deleting_evidence(tmp_path):
    from librarytools.lifecycle import doctor
    root = tmp_path / 'samples'
    root.mkdir()
    db = LibraryDatabase(root / '.eidetic/library.sqlite')
    scan_library(root, db)
    unfinished = db.begin_scan(root)
    assert any('incomplete scan' in issue for issue in doctor(root)['issues'])
    completed = scan_library(root, db)
    report = doctor(root)
    assert not any('incomplete scan' in issue for issue in report['issues'])
    assert report['incomplete_scans'][0]['superseded_by'] == completed.scan_id
    assert db.scan_status(unfinished) == 'incomplete'
