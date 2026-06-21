from __future__ import annotations

from pathlib import Path

from librarytools import intake


def test_normalize_strips_scene_and_format_tags():
    raw = "Dark.Magic.Samples.Underground.Techno.MULTiFORMAT-DECiBEL"
    assert intake.normalize_pack_name(raw) == "dark-magic-underground-techno"


def test_normalize_spaces_to_hyphens_lowercase():
    assert intake.normalize_pack_name("Filterheadz Hardgroove Techno") == "filterheadz-hardgroove-techno"


def test_normalize_collapses_repeats_and_trims():
    assert intake.normalize_pack_name("__Foo..Bar--Baz__") == "foo-bar-baz"


def test_normalize_drops_release_id_wrapper_token():
    # release IDs like dcb-5289 / trailing numeric IDs are noise
    assert intake.normalize_pack_name("SomePack-dcb-5289") == "somepack"


def _mk(root: Path, rel: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("audio")
    return p


def test_stray_pack_folder_is_planned_to_PACKS(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    _mk(root, "Dark.Magic.Samples.Underground.Techno.MULTiFORMAT-DECiBEL/dcb/Kick 01.wav")

    plan = intake.build_plan(root=root)

    assert len(plan) == 1
    move = plan[0]
    assert move.src == root / "Dark.Magic.Samples.Underground.Techno.MULTiFORMAT-DECiBEL"
    assert move.dest == root / "PACKS" / "dark-magic-underground-techno"
    assert move.tag.startswith("pack|")


def test_known_top_level_dirs_are_not_strays(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    _mk(root, "KICKS/already.wav")        # role folder (legacy top-level)
    _mk(root, "CURATED/KICKS/a.wav")      # curated zone
    _mk(root, "PACKS/existing/b.wav")     # packs zone
    _mk(root, "_QUARANTINE/c.wav")        # staging

    assert intake.build_plan(root=root) == []


def test_loose_audio_file_at_top_is_not_a_pack(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    _mk(root, "00_INBOX/loose.wav")       # loose file, left for curation

    assert intake.build_plan(root=root) == []


def test_slug_collision_gets_suffix(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    (root / "PACKS" / "filterheadz-hardgroove-techno").mkdir(parents=True)
    _mk(root, "Filterheadz Hardgroove Techno/a.wav")

    plan = intake.build_plan(root=root)

    assert plan[0].dest == root / "PACKS" / "filterheadz-hardgroove-techno-2"


def test_apply_moves_pack_and_records_manifest(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    _mk(root, "Filterheadz Hardgroove Techno/a.wav")

    rc = intake.main(["--apply", "--root", str(root)])

    assert rc == 0
    dest = root / "PACKS" / "filterheadz-hardgroove-techno"
    assert (dest / "a.wav").is_file()                       # pack moved whole
    assert not (root / "Filterheadz Hardgroove Techno").exists()
    manifest = (root / "PACKS" / "_manifest.tsv").read_text()
    assert "filterheadz-hardgroove-techno\tFilterheadz Hardgroove Techno\t" in manifest


def test_dry_run_moves_nothing(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    _mk(root, "Some Pack/a.wav")

    rc = intake.main(["--root", str(root)])   # no --apply

    assert rc == 0
    assert (root / "Some Pack" / "a.wav").is_file()         # untouched
    assert not (root / "PACKS").exists()
