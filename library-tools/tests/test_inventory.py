from pathlib import Path

from librarytools.inventory import LibraryDatabase, scan_library


def _audio(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_scan_assigns_same_sample_id_to_exact_copies(tmp_path):
    root = tmp_path / "SAMPLES"
    first = _audio(root / "PACKS" / "pack-a" / "kick.wav", b"same-audio")
    second = _audio(root / "CATALOGUE" / "KICKS" / "kick-copy.wav", b"same-audio")
    db = LibraryDatabase(tmp_path / "library.sqlite")

    result = scan_library(root, db)
    locations = {row.path: row for row in db.current_locations()}

    assert result.completed is True
    assert result.file_count == 2
    assert locations[first.relative_to(root)].sample_id == locations[second.relative_to(root)].sample_id
    assert len(db.assets()) == 1


def test_sample_identity_survives_move_and_old_location_becomes_missing(tmp_path):
    root = tmp_path / "SAMPLES"
    old = _audio(root / "CURATED" / "KICK" / "a.wav", b"kick")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    first = scan_library(root, db)
    sample_id = db.current_locations()[0].sample_id

    new = root / "CATALOGUE" / "KICK" / "a.wav"
    new.parent.mkdir(parents=True)
    old.rename(new)
    second = scan_library(root, db)

    current = db.current_locations()
    assert len(current) == 1
    assert current[0].path == new.relative_to(root)
    assert current[0].sample_id == sample_id
    assert db.scan_status(first.scan_id) == "complete"
    assert db.scan_status(second.scan_id) == "complete"
    assert db.location(old.relative_to(root)).exists is False


def test_changed_content_receives_new_identity(tmp_path):
    root = tmp_path / "SAMPLES"
    path = _audio(root / "CATALOGUE" / "KICK" / "a.wav", b"kick-one")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    scan_library(root, db)
    first_id = db.current_locations()[0].sample_id

    path.write_bytes(b"kick-two-is-different")
    scan_library(root, db)

    assert db.current_locations()[0].sample_id != first_id


def test_incomplete_scan_is_not_current(tmp_path):
    db = LibraryDatabase(tmp_path / "library.sqlite")
    scan_id = db.begin_scan(tmp_path / "SAMPLES")

    assert db.scan_status(scan_id) == "incomplete"
    assert db.latest_complete_scan() is None


def test_non_audio_and_staging_exports_are_not_indexed(tmp_path):
    root = tmp_path / "SAMPLES"
    _audio(root / "PACKS" / "pack" / "a.wav", b"a")
    _audio(root / "_EXPORT" / "DIGITAKT" / "derived.wav", b"derived")
    _audio(root / "PACKS" / "pack" / "notes.txt", b"notes")
    db = LibraryDatabase(tmp_path / "library.sqlite")

    result = scan_library(root, db)

    assert result.file_count == 1
    assert db.current_locations()[0].path == Path("PACKS/pack/a.wav")
