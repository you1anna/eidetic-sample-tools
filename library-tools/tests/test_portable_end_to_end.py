"""Rehearse an old installation's upgrade and SSD handoff using generated audio."""
import csv
import hashlib
import json
import shutil
import sqlite3
import wave
from pathlib import Path

import pytest

from librarytools.curate import LABEL_FIELDS, prepare_packet, promote_favourites, undo_promotions, write_consumer_views
from librarytools.inventory import LibraryDatabase, scan_library
from librarytools.library_cli import main
from librarytools.lifecycle import backup_bundle, restore_bundle


def test_old_installation_upgrade_handoff_export_undo_and_restore(tmp_path, monkeypatch):
    pytest.importorskip('sampletools')
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('FFmpeg required for actual export rehearsal')
    from sampletools import export
    from sampletools.config import get_spec
    root = tmp_path / 'first-mount'
    source = root / 'CATALOGUE' / 'KICKS' / 'kick-fixture.wav'
    source.parent.mkdir(parents=True)
    with wave.open(str(source), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(44100)
        audio.writeframes(b'\x01\x00' * 4410)
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    old = tmp_path / 'old-machine' / 'manifests'
    old.mkdir(parents=True)
    legacy = old / 'sample-library.sqlite'
    with sqlite3.connect(legacy) as conn:
        conn.executescript((Path(__file__).parent / 'fixtures/schemas/v1.sql').read_text())
        conn.execute('insert into assets values(?,?,?,?)', (original_hash, source.stat().st_size, '.wav', '2025-01-01'))
        conn.execute('insert into reviews values(?,?,?,?,?,?,?)', (original_hash, 'historic', 'keep', '', '', 'heard on old machine', '2025-01-01'))
    (old / 'historic-labels.tsv').write_text('preserved human evidence\n')
    old_bytes = legacy.read_bytes()
    destination = root / '.eidetic' / 'library.sqlite'
    command = ['migrate', '--root', str(root), '--library-db', str(legacy),
               '--destination', str(destination), '--include', str(old),
               '--backup-dir', str(tmp_path / 'upgrade-backup')]
    assert main(command) == 0
    assert not destination.exists()
    assert main([*command, '--apply']) == 0
    assert legacy.read_bytes() == old_bytes
    db = LibraryDatabase(destination)
    scan_library(root, db)
    packet = root / '.eidetic' / 'runs' / 'kit'
    assert prepare_packet(root, db, packet, quotas={'KICK': 1}) == 1
    labels = packet / 'labels.tsv'
    with labels.open() as handle:
        rows = list(csv.DictReader(handle, delimiter='\t'))
    rows[0].update(decision='favourite', true_role='KICK', descriptor='punch')
    with labels.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=LABEL_FIELDS, delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)
    promoted = promote_favourites(root, db, labels, run_id='kit')
    assert len(promoted) == 1
    # Handoff: both state and audio change mount path; no metadata rewriting.
    remounted = tmp_path / 'second-mount'
    root.rename(remounted)
    db = LibraryDatabase(remounted / '.eidetic' / 'library.sqlite')
    db.bind_root(remounted)
    views = write_consumer_views(db, remounted / '.eidetic/runs/kit/labels.tsv',
                                 remounted / '.eidetic/runs/crates', quotas={'KICK': 1}, name='kit')
    spec = get_spec('octatrack')
    plan = export.build_crate_plan(spec, views['all'], remounted)
    monkeypatch.setattr(export, 'EXPORT_ROOT', remounted / '_EXPORT')
    assert export.export_device(spec, plan=plan, dry_run=True) == (1, 0)
    assert export.export_device(spec, plan=plan) == (1, 0)
    assert export.export_device(spec, plan=plan) == (0, 1)
    backup = tmp_path / 'backup'
    backup_bundle(db.path, backup, root=remounted)
    assert undo_promotions(remounted, db, 'kit') == 1
    assert db.promotions()[0]['status'] == 'withdrawn'
    restored = tmp_path / 'restore-check'
    restore_bundle(backup, restored)
    with sqlite3.connect(restored / 'library.sqlite') as conn:
        assert conn.execute('select count(*) from reviews').fetchone()[0] == 2
        assert conn.execute('select status from promotions').fetchone()[0] == 'active'
    assert (restored / 'runs/kit/labels.tsv').is_file()
    assert (restored / 'imports/manifests/historic-labels.tsv').read_text() == 'preserved human evidence\n'
    assert hashlib.sha256((remounted / source.relative_to(root)).read_bytes()).hexdigest() == original_hash
