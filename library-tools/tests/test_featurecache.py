from __future__ import annotations

import sqlite3
from pathlib import Path

from librarytools.featurecache import FeatureCache, FeatureRecord


def _record(path: Path, size: int = 123, mtime: float = 4.5) -> FeatureRecord:
    return FeatureRecord(
        path=path,
        size=size,
        mtime=mtime,
        duration_s=1.25,
        peak=0.9,
        rms=0.3,
        crest=3.0,
        attack_ms=4.0,
        tail_ms=180.0,
        head_silence_ms=0.0,
        tail_silence_ms=20.0,
        centroid_hz=160.0,
        flatness=0.1,
        sub_ratio=0.7,
        low_ratio=0.8,
        mid_ratio=0.15,
        high_ratio=0.05,
        onset_density=2.0,
        zcr=0.02,
    )


def test_feature_cache_returns_hit_only_for_matching_size_and_mtime(tmp_path: Path):
    cache = FeatureCache(tmp_path / "features.sqlite")
    path = Path("PACKS/Vendor/Kicks/Kick.wav")

    cache.upsert(_record(path))

    hit = cache.get_or_none(path, size=123, mtime=4.5)
    assert hit is not None
    assert hit.path == path
    assert hit.sub_ratio == 0.7
    assert cache.get_or_none(path, size=124, mtime=4.5) is None
    assert cache.get_or_none(path, size=123, mtime=9.0) is None


def test_feature_cache_error_rows_are_persisted_but_retried(tmp_path: Path):
    db_path = tmp_path / "features.sqlite"
    cache = FeatureCache(db_path)
    path = Path("PACKS/Vendor/Broken.wav")

    cache.upsert(
        FeatureRecord(
            path=path,
            size=8,
            mtime=1.0,
            error="decode failed",
        )
    )

    assert cache.get_or_none(path, size=8, mtime=1.0) is None
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("select error from features where path = ?", (path.as_posix(),)).fetchone()
    assert row == ("decode failed",)
