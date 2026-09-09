"""A folder is searchable evidence, never an imported listening decision."""
import csv
import json
from pathlib import Path

import pytest

from librarytools import curate, find, find_cli
from librarytools.inventory import LibraryDatabase, scan_library


def _source(path, data=b'audio'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_existing_curated_audio_is_searchable_but_search_crate_requires_review(tmp_path):
    pytest.importorskip('sampletools')
    from sampletools.config import get_spec
    from sampletools.export import build_crate_plan, ExportError
    root = tmp_path / 'SAMPLES'
    source = _source(root / 'CURATED/KICK/old.wav')
    database = LibraryDatabase(tmp_path / 'library.sqlite')
    scan_library(root, database)
    matches = find.search(find.load_index(database), find.Query(curated_only=True))
    assert len(matches) == 1 and root / matches[0].path == source
    playlist = tmp_path / 'listen.m3u8'
    find.write_m3u8(root, matches, playlist)
    assert str(source) in playlist.read_text()
    crate = tmp_path / 'kit.tsv'
    find.write_crate(matches, crate, 'found in CURATED')
    with pytest.raises(ExportError, match='review|approval'):
        build_crate_plan(get_spec('digitakt'), crate, root)
    metadata = json.loads(crate.with_suffix('.tsv.metadata.json').read_text())
    assert metadata['approval']['status'] == 'requires_review'


def test_recorded_promotion_and_favourite_allow_generated_search_crate(tmp_path):
    pytest.importorskip('sampletools')
    from sampletools.config import get_spec
    from sampletools.export import build_crate_plan
    root = tmp_path / 'SAMPLES'
    _source(root / 'PACKS/pack/kick.wav')
    database = LibraryDatabase(tmp_path / 'library.sqlite')
    scan_library(root, database)
    location = database.current_locations()[0]
    labels = tmp_path / 'labels.tsv'
    with labels.open('w', newline='') as out:
        writer = csv.DictWriter(out, delimiter='\t', fieldnames=curate.LABEL_FIELDS)
        writer.writeheader()
        writer.writerow({'sample_id': location.sample_id, 'current_path': location.path,
                         'suggested_role': 'KICK', 'decision': 'favourite', 'true_role': 'KICK',
                         'descriptor': 'short', 'tags': '', 'notes': 'heard'})
    promoted = curate.promote_favourites(root, database, labels, run_id='heard-one')[0]
    # A byte-identical legacy copy must not hide the explicitly promoted location.
    _source(root / 'CURATED/AAA/old-copy.wav')
    scan_library(root, database)
    matches = find.search(find.load_index(database), find.Query(curated_only=True))
    crate = tmp_path / 'kit.tsv'
    find.write_crate(matches, crate, 'heard selection')
    plan = build_crate_plan(get_spec('digitakt'), crate, root)
    assert [item.src for item in plan.items] == [promoted]
    metadata = json.loads(crate.with_suffix('.tsv.metadata.json').read_text())
    assert metadata['approval']['status'] == 'approved'
    assert metadata['approval']['rows'][0]['run_id'] == 'heard-one'


def test_promotion_for_another_path_does_not_approve_a_duplicate(tmp_path):
    root = tmp_path / 'SAMPLES'
    _source(root / 'CURATED/KICK/old.wav')
    database = LibraryDatabase(tmp_path / 'library.sqlite')
    scan_library(root, database)
    location = database.current_locations()[0]
    database.record_review(location.sample_id, 'heard', 'favourite', 'KICK', 'short', '')
    database.record_promotion(location.sample_id, Path('CURATED/KICK/different.wav'), location.path, 'other')
    matches = find.load_index(database)
    crate = tmp_path / 'kit.tsv'
    find.write_crate(matches, crate, '')
    metadata = json.loads(crate.with_suffix('.tsv.metadata.json').read_text())
    assert metadata['approval']['status'] == 'requires_review'


def test_find_cli_warns_about_unverified_curated_history(tmp_path, capsys):
    root = tmp_path / 'SAMPLES'
    _source(root / 'CURATED/KICK/old.wav')
    database = LibraryDatabase(tmp_path / 'library.sqlite')
    scan_library(root, database)
    assert find_cli.main(['--root', str(root), '--library-db', str(database.path),
                          '--curated-only', '--crate', str(tmp_path / 'kit.tsv')]) == 0
    assert 'requires review' in capsys.readouterr().out.lower()


def test_promotion_row_without_listening_decision_still_requires_review(tmp_path):
    root = tmp_path / 'SAMPLES'
    _source(root / 'CURATED/KICK/old.wav')
    database = LibraryDatabase(tmp_path / 'library.sqlite')
    scan_library(root, database)
    location = database.current_locations()[0]
    database.record_promotion(location.sample_id, location.path, Path('PACKS/original.wav'), 'old')
    assert find.load_index(database)[0].approval_status == 'requires_review'


def test_withdrawn_promotion_cannot_approve_an_existing_file(tmp_path):
    root = tmp_path / 'SAMPLES'
    _source(root / 'CURATED/KICK/old.wav')
    database = LibraryDatabase(tmp_path / 'library.sqlite')
    scan_library(root, database)
    location = database.current_locations()[0]
    database.record_review(location.sample_id, 'heard', 'favourite', 'KICK', 'short', '')
    database.record_promotion(location.sample_id, location.path, Path('PACKS/original.wav'), 'old')
    database.mark_promotion_withdrawn(location.sample_id, location.path)
    assert find.load_index(database)[0].approval_status == 'requires_review'


def test_failed_metadata_write_never_publishes_unapproved_search_crate(tmp_path, monkeypatch):
    from librarytools import artifacts
    crate = tmp_path / 'kit.tsv'
    match = find.Match('a' * 64, Path('CURATED/KICK/old.wav'), 'KICK', 'unknown', zone='CURATED')
    def fail(*args, **kwargs):
        raise OSError('disk failure')
    monkeypatch.setattr(artifacts, 'write_crate_metadata', fail)
    with pytest.raises(OSError, match='disk failure'):
        find.write_crate([match], crate, 'search')
    assert not crate.exists()


def test_legacy_standalone_crate_remains_compatible(tmp_path):
    pytest.importorskip('sampletools')
    from sampletools.config import get_spec
    from sampletools.export import build_crate_plan
    import hashlib
    root = tmp_path / 'SAMPLES'
    source = _source(root / 'CURATED/KICK/old.wav')
    crate = tmp_path / 'legacy.tsv'
    crate.write_text('sample_id\tsource_path\trole\tdescriptor\treason\n'
                     f'{hashlib.sha256(source.read_bytes()).hexdigest()}\tCURATED/KICK/old.wav\tKICK\tshort\theard\n')
    assert [item.src for item in build_crate_plan(get_spec('digitakt'), crate, root).items] == [source]
