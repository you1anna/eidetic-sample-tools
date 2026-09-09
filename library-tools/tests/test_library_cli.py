import json


def test_init_and_doctor_are_preview_first(tmp_path, capsys):
    from librarytools.library_cli import main
    root = tmp_path / 'samples'
    root.mkdir()
    (root / 'kick.wav').write_bytes(b'kick')
    assert main(['init', '--root', str(root), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['unverified_audio_files'] == 1
    assert not (root / '.eidetic').exists()
    assert main(['--root', str(root), 'doctor', '--json']) == 2
    assert json.loads(capsys.readouterr().out)['database']['status'] == 'missing'
    assert not (root / '.eidetic').exists()
    assert main(['init', '--root', str(root), '--apply', '--json']) == 0
    capsys.readouterr()
    assert (root / '.eidetic/library.sqlite').is_file()
    assert main(['doctor', '--root', str(root), '--json']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['counts']['reviews'] == 0
    assert report['counts']['assets'] == 0


def test_doctor_current_state_has_no_file_effects(tmp_path, capsys):
    from librarytools.library_cli import main
    root = tmp_path / 'samples'
    root.mkdir()
    main(['init', '--root', str(root), '--apply'])
    capsys.readouterr()
    def snapshot():
        return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
    before = snapshot()
    assert main(['doctor', '--root', str(root), '--json']) == 0
    assert snapshot() == before


def test_adopt_legacy_copy_preserves_original_and_imports_human_evidence(tmp_path, capsys):
    import sqlite3
    from pathlib import Path
    from librarytools.library_cli import main
    root = tmp_path / 'samples'
    root.mkdir()
    legacy = tmp_path / 'old.sqlite'
    with sqlite3.connect(legacy) as conn:
        conn.executescript((Path(__file__).parent / 'fixtures/schemas/v1.sql').read_text())
    original = legacy.read_bytes()
    packet = tmp_path / 'session'
    packet.mkdir()
    (packet / 'labels.tsv').write_text('unmodified human decision')
    destination = root / '.eidetic/library.sqlite'
    args = ['migrate', '--root', str(root), '--library-db', str(legacy), '--destination', str(destination),
            '--include', str(packet), '--backup-dir', str(tmp_path / 'backup'), '--json']
    assert main(args) == 0
    assert not (root / '.eidetic').exists()
    capsys.readouterr()
    assert main([*args, '--apply']) == 0
    assert legacy.read_bytes() == original
    assert destination.is_file()
    assert (root / '.eidetic/imports/session/labels.tsv').read_text() == 'unmodified human decision'
    with sqlite3.connect(destination) as conn:
        assert conn.execute('pragma user_version').fetchone()[0] == 5
    from librarytools.state import resolve_library_db
    assert resolve_library_db(root, legacy_path=legacy) == destination
    with sqlite3.connect(legacy) as conn:
        conn.execute("insert into assets values('changed',1,'.wav','today')")
    import pytest
    with pytest.raises(ValueError, match='legacy'):
        resolve_library_db(root, legacy_path=legacy)


def test_restore_preview_does_not_create_destination(tmp_path, capsys):
    from librarytools.library_cli import main
    root = tmp_path / 'samples'
    root.mkdir()
    assert main(['init', '--root', str(root), '--apply']) == 0
    backup = tmp_path / 'backup'
    assert main(['backup', '--root', str(root), '--output', str(backup), '--apply']) == 0
    destination = tmp_path / 'restored'
    assert main(['restore', '--source', str(backup), '--output', str(destination)]) == 0
    assert not destination.exists()


def test_interrupted_adoption_blocks_other_writers_and_resumes(tmp_path, monkeypatch):
    import sqlite3
    from pathlib import Path
    import pytest
    from librarytools.lifecycle import adopt_database, doctor
    from librarytools.locking import library_lock
    root = tmp_path / 'samples'
    root.mkdir()
    source = tmp_path / 'old.sqlite'
    with sqlite3.connect(source) as conn:
        conn.executescript((Path(__file__).parent / 'fixtures/schemas/v1.sql').read_text())
    packet = tmp_path / 'packet'
    packet.mkdir()
    (packet / 'labels.tsv').write_text('keep human evidence')
    destination = root / '.eidetic/library.sqlite'
    rename = Path.rename
    def interrupt_publication(path, target):
        if Path(target) == destination:
            raise OSError('simulated disconnect before publication')
        return rename(path, target)
    monkeypatch.setattr(Path, 'rename', interrupt_publication)
    arguments = dict(root=root, backup_dir=tmp_path / 'backup', include=(packet,), apply=True)
    with pytest.raises(OSError, match='disconnect'):
        adopt_database(source, destination, **arguments)
    assert not destination.exists()
    assert doctor(root)['adoption']['status'] == 'pending'
    with pytest.raises(ValueError, match='adoption'):
        with library_lock(root):
            pytest.fail('writer entered an incomplete adoption')
    with pytest.raises(ValueError, match='adoption'):
        with library_lock(root, allow_recovery=True):
            pytest.fail('unrelated operation recovery entered an incomplete adoption')
    monkeypatch.setattr(Path, 'rename', rename)
    result = adopt_database(source, destination, **arguments)
    assert result['resuming'] and result['verified']
    assert (root / '.eidetic/imports/packet/labels.tsv').read_text() == 'keep human evidence'
    assert doctor(root)['adoption']['status'] == 'complete'


def test_adoption_resumes_after_database_published_before_completion_record(tmp_path, monkeypatch):
    import sqlite3
    from pathlib import Path
    import pytest
    from librarytools import operations
    from librarytools.lifecycle import adopt_database
    root = tmp_path / 'samples'
    root.mkdir()
    source = tmp_path / 'old.sqlite'
    with sqlite3.connect(source) as conn:
        conn.executescript((Path(__file__).parent / 'fixtures/schemas/v1.sql').read_text())
    atomic = operations.atomic_json
    def interrupted(path, data):
        if path.name == 'adoption.json' and data.get('status') == 'complete':
            raise OSError('simulated disconnect after publication')
        return atomic(path, data)
    monkeypatch.setattr(operations, 'atomic_json', interrupted)
    destination = root / '.eidetic/library.sqlite'
    arguments = dict(root=root, backup_dir=tmp_path / 'backup', apply=True)
    with pytest.raises(OSError, match='disconnect'):
        adopt_database(source, destination, **arguments)
    assert destination.is_file()
    monkeypatch.setattr(operations, 'atomic_json', atomic)
    assert adopt_database(source, destination, **arguments)['verified']
