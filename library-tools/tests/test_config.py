from __future__ import annotations

from librarytools import config


def test_buckets_are_the_four_expected():
    assert config.BUCKETS == ("LOOPS", "ONE-SHOTS", "PADS-DRONES", "OTHER")


def test_in_scope_is_the_messy_folders_only():
    assert config.IN_SCOPE == ("_PACKS", "DRUM-KITS", "00_INBOX")


def test_to_delete_root_under_samples_root():
    assert config.TO_DELETE_ROOT == config.SAMPLES_ROOT / "_TO-DELETE"


def test_manifest_path_has_prefix_and_tsv_suffix():
    p = config.manifest_path("classify")
    assert p.name.startswith("classify-")
    assert p.suffix == ".tsv"
    assert p.parent == config.MANIFEST_DIR
