import sqlite3
from pathlib import Path

from librarytools import features
from librarytools.featurecache import FEATURE_COLUMNS, FeatureCache, FeatureRecord
from librarytools.inventory import LibraryDatabase, scan_library


def test_legacy_same_basename_collision_is_not_assigned(tmp_path):
    cache = FeatureCache(tmp_path / 'old.sqlite')
    cache.upsert(FeatureRecord(Path('one/hit.wav'), 4, 1.0, peak=0.1))
    cache.upsert(FeatureRecord(Path('two/hit.wav'), 4, 1.0, peak=0.9))
    index = features.LegacyFeatureIndex(cache.path)
    assert index.get(4, 1_000_000_000, 'hit.wav') is None


def test_legacy_unknown_shape_is_reported_without_modification(tmp_path):
    path = tmp_path / 'old.sqlite'
    with sqlite3.connect(path) as conn:
        conn.execute('create table features(path text, size int, mtime real, error text)')
        conn.execute("insert into features values('a.wav',4,1.0,'')")
    before = path.read_bytes()
    index = features.LegacyFeatureIndex(path)
    assert index.get(4, 1_000_000_000, 'a.wav') is None
    assert index.warnings
    assert path.read_bytes() == before


def _library(tmp_path):
    root = tmp_path / 'samples'
    root.mkdir()
    (root / 'a.wav').write_bytes(b'audio')
    db = LibraryDatabase(tmp_path / 'library.sqlite')
    scan_library(root, db)
    location = db.current_locations()[0]
    return root, db, location, [(location.sample_id, location.path, location.size, location.mtime_ns)]


def test_failed_measurement_can_be_retried_without_recomputing_success(tmp_path, monkeypatch):
    root, db, loc, rows = _library(tmp_path)
    calls = []
    def extract(path, **kwargs):
        calls.append(path)
        return FeatureRecord(loc.path, loc.size, 1.0, peak=0.5)
    db.record_features(loc.sample_id, '{}', 'decoder missing')
    monkeypatch.setattr(features.audiofeatures, 'extract', extract)
    assert features.sync_features(root, db, rows).skipped == 1
    assert features.sync_features(root, db, rows, retry_failed=True).extracted == 1
    assert features.sync_features(root, db, rows, retry_failed=True).skipped == 1
    assert len(calls) == 1


def test_changed_extractor_version_recomputes_existing_features(tmp_path, monkeypatch):
    root, db, loc, rows = _library(tmp_path)
    db.record_features(loc.sample_id, '{"peak": 0.1}', extractor_version='obsolete-v0')
    monkeypatch.setattr(features.audiofeatures, 'extract', lambda *a, **kw: FeatureRecord(loc.path, loc.size, 1.0, peak=0.8))
    result = features.sync_features(root, db, rows)
    assert result.extracted == 1
    assert db.feature_metadata()[loc.sample_id]['extractor_version'] == features.FEATURE_VERSION


def test_legacy_import_has_explicit_provenance(tmp_path):
    root, db, loc, rows = _library(tmp_path)
    cache = FeatureCache(tmp_path / 'old.sqlite')
    cache.upsert(FeatureRecord(loc.path, loc.size, loc.mtime_ns / 1e9, peak=0.5))
    assert features.sync_features(root, db, rows, legacy_cache=cache.path).migrated == 1
    assert db.feature_metadata()[loc.sample_id]['provenance'] == 'legacy-stat-match'


def test_resume_refuses_changed_bytes_before_recording_measurement(tmp_path, monkeypatch):
    import pytest
    root, db, loc, rows = _library(tmp_path)
    (root / loc.path).write_bytes(b'changed')
    monkeypatch.setattr(features.audiofeatures, 'extract', lambda *a, **kw: FeatureRecord(loc.path, loc.size, 1.0))
    with pytest.raises(ValueError, match='changed'):
        features.sync_features(root, db, rows)
    assert not db.feature_ids()
