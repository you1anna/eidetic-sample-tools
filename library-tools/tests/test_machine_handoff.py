"""Independent installation must not need simultaneous access to both machines."""
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from librarytools import config, find_cli
from librarytools.inventory import LibraryDatabase, scan_library
from librarytools.library_cli import main
from librarytools.lifecycle import backup_bundle, restore_bundle
from librarytools.state import library_identity, resolve_library_db


def invoke(arguments):
    # An absent CLI command is an observable nonzero exit, as in a real shell.
    try:
        return main(arguments)
    except SystemExit as error:
        return error.code


def test_machine_can_start_before_old_machine_returns_then_preserve_both_histories(tmp_path, monkeypatch, capsys):
    root = tmp_path / 'macbook-mount'
    source = root / 'CATALOGUE' / 'kick.wav'
    source.parent.mkdir(parents=True)
    source.write_bytes(b'stable sample fixture')
    local = tmp_path / 'air-checkout' / 'manifests'
    monkeypatch.setattr(config, 'LEGACY_MANIFEST_DIR', local)
    setup = ['onboard', '--root', str(root), '--machine', 'macbook', '--defer-machine', 'mac-mini']
    assert invoke(setup) == 0
    assert not (root / '.eidetic').exists()
    assert invoke([*setup, '--apply']) == 0
    identity = library_identity(root)
    db = LibraryDatabase(root / '.eidetic/library.sqlite')
    scan_library(root, db)
    sample_id = hashlib.sha256(source.read_bytes()).hexdigest()
    db.record_review(sample_id, 'air-session', 'favourite', 'KICK', 'punch', 'heard on MacBook')
    assert find_cli.main(['--root', str(root)]) == 0

    # Months later: attach the same SSD under another mount path, upgrade the
    # returning machine, and preserve its divergent early-version records.
    destination = tmp_path / 'mini-mount'
    root.rename(destination)
    legacy_dir = tmp_path / 'mini-checkout' / 'manifests'
    legacy_dir.mkdir(parents=True)
    legacy = legacy_dir / 'sample-library.sqlite'
    with sqlite3.connect(legacy) as conn:
        conn.executescript((Path(__file__).parent / 'fixtures/schemas/v1.sql').read_text())
        conn.execute('insert into assets values(?,?,?,?)', (sample_id, 21, '.wav', '2025-01-01'))
        conn.execute('insert into reviews values(?,?,?,?,?,?,?)', (sample_id, 'mini-old', 'keep', '', '', 'heard on Mac mini', '2025-01-01'))
    labels = legacy_dir / 'old-labels.tsv'
    labels.write_text('original offline listening decisions\n')
    original_legacy = legacy.read_bytes()
    portable = destination / '.eidetic/library.sqlite'
    original_portable = portable.read_bytes()
    monkeypatch.setattr(config, 'LEGACY_MANIFEST_DIR', legacy_dir)
    setup = ['onboard', '--root', str(destination), '--machine', 'mac-mini', '--library-db', str(legacy), '--include', str(legacy_dir)]
    assert invoke(setup) == 0
    assert portable.read_bytes() == original_portable
    assert invoke([*setup, '--apply']) == 0
    assert portable.read_bytes() == original_portable
    assert legacy.read_bytes() == original_legacy
    assert library_identity(destination) == identity
    assert resolve_library_db(destination) == portable
    assert find_cli.main(['--root', str(destination)]) == 0
    assert invoke([*setup, '--apply']) == 0
    saved_labels = list((destination / '.eidetic').rglob('old-labels.tsv'))
    assert len(saved_labels) == 1
    assert saved_labels[0].read_bytes() == labels.read_bytes()
    with sqlite3.connect(portable) as conn:
        assert conn.execute('select notes from reviews').fetchall() == [('heard on MacBook',)]

    # Offline labels can change without modifying the old database. The next
    # command must detect that evidence has not yet been preserved.
    labels.write_text('later offline listening decision\n')
    with pytest.raises(ValueError):
        resolve_library_db(destination)
    assert invoke([*setup, '--apply']) == 0
    assert resolve_library_db(destination) == portable
    assert {path.read_text() for path in (destination / '.eidetic').rglob('old-labels.tsv')} == {
        'original offline listening decisions\n', 'later offline listening decision\n'}
    assert portable.read_bytes() == original_portable

    backup = tmp_path / 'state-backup'
    backup_bundle(portable, backup, root=destination)
    restored = tmp_path / 'restored-state'
    restore_bundle(backup, restored)
    assert {path.read_text() for path in restored.rglob('old-labels.tsv')} == {
        'original offline listening decisions\n', 'later offline listening decision\n'}
    capsys.readouterr()
    assert main(['doctor', '--root', str(destination), '--json']) == 1
    report = json.loads(capsys.readouterr().out)
    assert report['database']['status'] == 'current'
    assert report['counts']['reviews'] == 1
    assert report['issues']
