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
