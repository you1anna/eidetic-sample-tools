import json
from pathlib import Path
import pytest

from librarytools import find_cli, tag_cli
from librarytools.inventory import LibraryDatabase, scan_library


@pytest.fixture(autouse=True)
def isolated_defaults(tmp_path, monkeypatch):
    from librarytools import config
    monkeypatch.setattr(config, 'MANIFEST_DIR', tmp_path / 'legacy')
    monkeypatch.setattr(config, 'LEGACY_MANIFEST_DIR', tmp_path / 'legacy')


def test_search_uses_attached_root_database_without_modifying_state(tmp_path):
    root = tmp_path / 'samples'
    root.mkdir()
    (root / 'kick.wav').write_bytes(b'kick')
    path = root / '.eidetic' / 'library.sqlite'
    db = LibraryDatabase(path)
    scan_library(root, db)
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert find_cli.main(['--root', str(root)]) == 0
    assert {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()} == before


def test_tag_refuses_to_start_competing_state_on_uninitialised_drive(tmp_path, capsys):
    root = tmp_path / 'samples'
    root.mkdir()
    (root / 'a.wav').write_bytes(b'a')
    assert tag_cli.main(['--root', str(root), '--rescan', '--skip-features']) == 2
    assert 'init' in capsys.readouterr().err
    assert not (root / '.eidetic').exists()


def test_retag_preserves_human_tags_and_swaps_generated_tags(tmp_path):
    root = tmp_path / 'samples'
    root.mkdir()
    (root / 'kick.wav').write_bytes(b'kick')
    path = root / '.eidetic' / 'library.sqlite'
    db = LibraryDatabase(path)
    scan_library(root, db)
    sample_id = db.assets()[0]
    db.record_tags(sample_id, [('character', 'personal')], source='human')
    db.record_tags(sample_id, [('style', 'obsolete')])
    assert tag_cli.main(['--root', str(root), '--skip-features', '--apply']) == 0
    assert ('character', 'personal') in db.tags_for(sample_id)
    assert ('style', 'obsolete') not in db.tags_for(sample_id)


def test_retag_records_the_vocabulary_actually_used_if_file_changes(tmp_path, monkeypatch):
    import hashlib
    root = tmp_path / 'samples'
    root.mkdir()
    (root / 'kick.wav').write_bytes(b'kick')
    db = LibraryDatabase(root / '.eidetic/library.sqlite')
    scan_library(root, db)
    vocabulary = tmp_path / 'vocabulary.toml'
    original = b'schema_version=1\n[[tag]]\nname="old-rule"\ngroup="style"\nname_matches=["kick"]\n'
    vocabulary.write_bytes(original)
    resolver = tag_cli._resolve_origins
    def edit_during_work(*args):
        vocabulary.write_bytes(original.replace(b'old-rule', b'new-rule'))
        return resolver(*args)
    monkeypatch.setattr(tag_cli, '_resolve_origins', edit_during_work)
    assert tag_cli.main(['--root', str(root), '--skip-features', '--apply', '--vocabulary', str(vocabulary)]) == 0
    assert ('style', 'old-rule') in db.tags_for(db.assets()[0])
    snapshot = root / '.eidetic/configurations' / f'vocabulary-{hashlib.sha256(original).hexdigest()}.toml'
    assert snapshot.read_bytes() == original
