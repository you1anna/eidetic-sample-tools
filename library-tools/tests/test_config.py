from __future__ import annotations

from librarytools import config


def test_buckets_are_the_four_expected():
    assert config.BUCKETS == ("LOOPS", "ONE-SHOTS", "PADS-DRONES", "OTHER")


def test_in_scope_is_the_messy_folders_only():
    assert config.IN_SCOPE == ("_PACKS", "DRUM-KITS", "00_INBOX")


def test_unconfigured_root_requires_explicit_selection(monkeypatch):
    import pytest
    monkeypatch.setattr(config, 'SAMPLES_ROOT', None)
    with pytest.raises(ValueError, match='--root.*SAMPLES_ROOT'):
        config.manifest_path('classify')


def test_manifest_path_has_prefix_and_tsv_suffix(tmp_path):
    p = config.manifest_path("classify", root=tmp_path)
    assert p.name.startswith("classify-")
    assert p.suffix == ".tsv"
    assert p.parent == tmp_path / '.eidetic' / 'runs'
