from __future__ import annotations

from pathlib import Path

from librarytools.classify import classify_path
from librarytools import classify as classify_mod


def test_loop_keyword_wins():
    b, r = classify_path(Path("_PACKS/Riemann/drum loop 132.wav"))
    assert b == "LOOPS"
    assert "loop" in r


def test_bpm_token_is_a_loop():
    b, _ = classify_path(Path("_PACKS/Pack/rumble_132bpm.wav"))
    assert b == "LOOPS"


def test_pad_keyword():
    b, _ = classify_path(Path("_PACKS/Pack/warm pad C.wav"))
    assert b == "PADS-DRONES"


def test_drone_keyword():
    b, _ = classify_path(Path("DRUM-KITS/Vendor/dark drone.wav"))
    assert b == "PADS-DRONES"


def test_oneshot_keyword():
    b, _ = classify_path(Path("DRUM-KITS/Vendor/kick hit 01.wav"))
    assert b == "ONE-SHOTS"


def test_loop_beats_pad_when_both_present():
    b, _ = classify_path(Path("_PACKS/Pack/pad loop.wav"))
    assert b == "LOOPS"


def test_short_duration_oneshot_when_no_keyword():
    b, r = classify_path(Path("_PACKS/Pack/zap.wav"), duration=0.4)
    assert b == "ONE-SHOTS"
    assert "duration" in r


def test_long_duration_loop_when_no_keyword():
    b, _ = classify_path(Path("_PACKS/Pack/zap.wav"), duration=4.0)
    assert b == "LOOPS"


def test_unmatched_no_duration_is_other():
    b, r = classify_path(Path("_PACKS/Pack/mystery.wav"))
    assert b == "OTHER"
    assert r == "unmatched"


def test_folder_keyword_counts():
    b, _ = classify_path(Path("_PACKS/Techno Loops/bd.wav"))
    assert b == "LOOPS"


def test_dest_rel_keeps_pack_and_subpath():
    rel = Path("_PACKS/Riemann Tribal/loops/bd 132.wav")
    dest = classify_mod.dest_rel(rel, "LOOPS")
    assert dest == Path("LOOPS/Riemann Tribal/loops/bd 132.wav")


def test_dest_rel_drum_kits_uses_vendor_as_pack():
    rel = Path("DRUM-KITS/Goldbaby/kick hit.wav")
    dest = classify_mod.dest_rel(rel, "ONE-SHOTS")
    assert dest == Path("ONE-SHOTS/Goldbaby/kick hit.wav")


def test_dest_rel_loose_file_uses_underscore_loose():
    rel = Path("00_INBOX/random loop.wav")
    dest = classify_mod.dest_rel(rel, "LOOPS")
    assert dest == Path("LOOPS/_loose/random loop.wav")


def test_build_plan_classifies_in_scope_audio(tmp_path: Path):
    root = tmp_path
    (root / "_PACKS" / "PackA").mkdir(parents=True)
    (root / "_PACKS" / "PackA" / "drum loop.wav").write_text("x")
    (root / "_PACKS" / "PackA" / "kick hit.wav").write_text("x")
    (root / "_PACKS" / "PackA" / "._sneaky.wav").write_text("x")  # AppleDouble: ignored
    (root / "_PACKS" / "PackA" / "notes.txt").write_text("x")      # non-audio: ignored
    (root / "KICKS").mkdir()                                       # out of scope
    (root / "KICKS" / "curated.wav").write_text("x")

    plan = classify_mod.build_plan(root=root, probe_durations=False)
    by_name = {m.src.name: m for m in plan}
    assert set(by_name) == {"drum loop.wav", "kick hit.wav"}
    assert by_name["drum loop.wav"].dest == root / "LOOPS" / "PackA" / "drum loop.wav"
    assert by_name["kick hit.wav"].dest == root / "ONE-SHOTS" / "PackA" / "kick hit.wav"
