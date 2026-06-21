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
