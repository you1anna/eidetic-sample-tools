from __future__ import annotations

from pathlib import Path

import pytest

from librarytools import moves


def test_safe_move_moves_into_new_dir(tmp_path: Path):
    src = tmp_path / "a" / "x.wav"
    src.parent.mkdir(parents=True)
    src.write_text("data")
    dest = tmp_path / "b" / "c" / "x.wav"
    assert moves.safe_move(src, dest) == "moved"
    assert dest.read_text() == "data"
    assert not src.exists()


def test_safe_move_skips_when_dest_exists(tmp_path: Path):
    src = tmp_path / "x.wav"
    src.write_text("new")
    dest = tmp_path / "out" / "x.wav"
    dest.parent.mkdir()
    dest.write_text("original")
    assert moves.safe_move(src, dest) == "exists"
    assert dest.read_text() == "original"  # not clobbered
    assert src.exists()                     # source left in place


def test_safe_move_missing_source(tmp_path: Path):
    assert moves.safe_move(tmp_path / "nope.wav", tmp_path / "out.wav") == "missing"


def test_apply_plan_writes_undo_for_moved_only(tmp_path: Path):
    src = tmp_path / "s" / "x.wav"
    src.parent.mkdir()
    src.write_text("d")
    dest = tmp_path / "d" / "x.wav"
    undo = tmp_path / "undo.tsv"
    counts = moves.apply_plan([moves.Move(src, dest, "LOOPS")], undo)
    assert counts == {"moved": 1, "exists": 0, "missing": 0}
    assert undo.read_text().strip() == f"{dest}\t{src}"


def test_apply_plan_undo_contains_moved_lines_only(tmp_path: Path):
    # one entry will move, one will hit an existing dest (skip), one is missing src
    moved_src = tmp_path / "src" / "a.wav"
    moved_src.parent.mkdir(parents=True)
    moved_src.write_text("a")
    moved_dest = tmp_path / "out" / "a.wav"

    exists_src = tmp_path / "src" / "b.wav"
    exists_src.write_text("b")
    exists_dest = tmp_path / "out" / "b.wav"
    exists_dest.parent.mkdir(parents=True)
    exists_dest.write_text("already here")

    missing_src = tmp_path / "src" / "gone.wav"  # never created
    missing_dest = tmp_path / "out" / "gone.wav"

    undo = tmp_path / "undo.tsv"
    plan = [
        moves.Move(moved_src, moved_dest, "LOOPS"),
        moves.Move(exists_src, exists_dest, "LOOPS"),
        moves.Move(missing_src, missing_dest, "LOOPS"),
    ]
    counts = moves.apply_plan(plan, undo)

    assert counts == {"moved": 1, "exists": 1, "missing": 1}
    # undo must list ONLY the moved file, as dest<TAB>src
    undo_lines = undo.read_text().splitlines()
    assert undo_lines == [f"{moved_dest}\t{moved_src}"]
    # safety: the pre-existing dest was not clobbered, its src remains
    assert exists_dest.read_text() == "already here"
    assert exists_src.exists()


def test_safe_move_preserves_dangling_destination_symlink(tmp_path):
    src = tmp_path / 'source.wav'
    src.write_bytes(b'audio')
    destination = tmp_path / 'destination.wav'
    destination.symlink_to(tmp_path / 'missing-target')
    assert moves.safe_move(src, destination) == 'exists'
    assert destination.is_symlink() and src.read_bytes() == b'audio'


def test_move_directory_rejects_symlink_dependencies_before_mutation(tmp_path):
    import pytest
    root = tmp_path / 'SAMPLES'
    source = root / 'PACKS' / 'pack'
    source.mkdir(parents=True)
    (source / 'audio.wav').write_bytes(b'audio')
    (source / 'external.wav').symlink_to(tmp_path / 'outside.wav')
    destination = root / 'CATALOGUE' / 'pack'
    with pytest.raises(ValueError, match='symlink'):
        moves.apply_plan([moves.Move(source, destination, 'test')], tmp_path / 'undo.tsv', root=root)
    assert source.is_dir() and not destination.exists()


def test_destination_created_after_preflight_is_not_overwritten(tmp_path, monkeypatch):
    src = tmp_path / 'source.wav'
    src.write_bytes(b'new audio')
    destination = tmp_path / 'out' / 'destination.wav'
    mkdir = Path.mkdir
    def race_mkdir(path, *args, **kwargs):
        mkdir(path, *args, **kwargs)
        if path == destination.parent:
            destination.write_bytes(b'created by another process')
    monkeypatch.setattr(Path, 'mkdir', race_mkdir)
    assert moves.safe_move(src, destination) == 'exists'
    assert destination.read_bytes() == b'created by another process'
    assert src.read_bytes() == b'new audio'


@pytest.mark.parametrize('marker', [
    '{"format_version": 999, "library_id": "00000000-0000-0000-0000-000000000000"}',
    '{"format_version": 1}',
])
def test_portable_preview_rejects_unsupported_or_malformed_identity_without_writes(tmp_path, marker):
    root = tmp_path / 'SAMPLES'
    state = root / '.eidetic'
    state.mkdir(parents=True)
    identity = state / 'library.json'
    identity.write_text(marker)
    plan_path = state / 'runs' / 'preview.tsv'
    before = {path: path.read_bytes() for path in state.rglob('*') if path.is_file()}
    with pytest.raises(ValueError, match='identity'):
        moves.write_plan(plan_path, [])
    assert not plan_path.parent.exists()
    assert before == {path: path.read_bytes() for path in state.rglob('*') if path.is_file()}


def test_portable_preview_rejects_future_database_before_creating_plan(tmp_path):
    import sqlite3
    from librarytools.inventory import LibraryDatabase
    root = tmp_path / 'SAMPLES'
    root.mkdir()
    database = root / '.eidetic' / 'library.sqlite'
    LibraryDatabase(database)
    with sqlite3.connect(database) as conn:
        conn.execute('pragma user_version=999')
    before = database.read_bytes()
    output = root / '.eidetic' / 'runs' / 'preview.tsv'
    with pytest.raises(ValueError, match='newer|unsupported|version'):
        moves.write_plan(output, [])
    assert not output.parent.exists() and database.read_bytes() == before
