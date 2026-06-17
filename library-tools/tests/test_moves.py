from __future__ import annotations

from pathlib import Path

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
