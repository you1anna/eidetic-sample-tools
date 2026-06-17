from __future__ import annotations

from pathlib import Path

from librarytools import dedupe, config


def test_pick_canonical_prefers_shallowest():
    paths = [
        Path("a/b/c/x.wav"),
        Path("a/x.wav"),
        Path("a/b/x.wav"),
    ]
    assert dedupe.pick_canonical(paths) == Path("a/x.wav")


def test_pick_canonical_tiebreak_shortest_string():
    paths = [Path("aa/longer.wav"), Path("b/x.wav")]
    assert dedupe.pick_canonical(paths) == Path("b/x.wav")


def test_find_candidates_groups_same_size_and_name(tmp_path: Path):
    a = tmp_path / "p1" / "kick.wav"
    b = tmp_path / "p2" / "kick.wav"
    c = tmp_path / "p3" / "other.wav"
    for p in (a, b, c):
        p.parent.mkdir(parents=True)
    a.write_text("same")
    b.write_text("same")           # same size + name as a
    c.write_text("different len")  # unique
    groups = dedupe.find_candidates(tmp_path)
    assert list(groups) == [(len("same"), "kick.wav")]
    assert set(groups[(len("same"), "kick.wav")]) == {a, b}


def test_build_plan_moves_confirmed_dupes_to_to_delete(tmp_path: Path):
    a = tmp_path / "p1" / "kick.wav"
    b = tmp_path / "p2" / "kick.wav"
    for p in (a, b):
        p.parent.mkdir(parents=True)
    a.write_text("identical")
    b.write_text("identical")
    plan = dedupe.build_plan(root=tmp_path)
    assert len(plan) == 1                       # one of the two kept, one moved
    moved = plan[0]
    assert moved.dest.parts[-4:-1] == ("_TO-DELETE", "dupes", moved.src.parent.name)


def test_build_plan_ignores_false_positive_same_name_diff_bytes(tmp_path: Path):
    a = tmp_path / "p1" / "kick.wav"
    b = tmp_path / "p2" / "kick.wav"
    for p in (a, b):
        p.parent.mkdir(parents=True)
    a.write_text("AAAA")
    b.write_text("BBBB")  # same size + name, different bytes -> NOT a dupe
    assert dedupe.build_plan(root=tmp_path) == []
