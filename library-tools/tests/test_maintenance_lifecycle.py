import sqlite3

import pytest

from librarytools.inventory import LibraryDatabase, scan_library
from librarytools.lifecycle import maintenance_preview


def _snapshot(root):
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in root.rglob('*') if path.is_file()}


@pytest.mark.parametrize('journal_mode', ['WAL', 'PERSIST', 'TRUNCATE'])
def test_maintenance_reports_versioned_cache_growth_without_changing_state(tmp_path, journal_mode):
    root = tmp_path / 'samples'
    root.mkdir()
    db = LibraryDatabase(root / '.eidetic/library.sqlite')
    scan_library(root, db)
    with db._connect() as conn:
        conn.executemany("insert into assets values(?,1,'.wav','today')", [('old',), ('new',), ('legacy',)])
        conn.executemany('insert into audio_embeddings values(?,?,?,?,?,?,?,?,?)', [
            ('old','clap','rev-old','first-10',2,'float16',b'aaaa','today','today'),
            ('new','clap','rev-new','first-10',2,'float16',b'bbbb','today','today'),
        ])
        conn.execute('insert into prompt_embeddings values(?,?,?,?,?,?,?,?,?)',
                     ('clap','rev-new','prompt-v1','kick',2,'float16',b'cccc','today','today'))
        conn.execute("insert into hash_cache values(1,2,3,4,'old')")
    db.record_features('old', '{}', extractor_version='acoustic-v0')
    db.record_features('new', '{}')
    db.record_features('legacy', '{}', extractor_version='', provenance='legacy')
    db.record_review('old','human-packet','keep','KICK','short','keep this forever')
    db.record_pick('old','human-kit','warm kick')
    with sqlite3.connect(db.path) as conn:
        conn.execute(f'pragma journal_mode={journal_mode}')
        conn.execute("insert into state_metadata values('test','test')")
    conn.close()
    before = _snapshot(root)

    report = maintenance_preview(root)

    assert _snapshot(root) == before
    assert report['apply'] is False
    assert report['database_cache']['status'] == 'available'
    tables = report['database_cache']['tables']
    assert set(tables) == {'audio_embeddings','prompt_embeddings','hash_cache','asset_features'}
    assert tables['audio_embeddings']['rows'] == 2
    assert tables['audio_embeddings']['blob_bytes'] == 8
    assert {row['model_revision'] for row in tables['audio_embeddings']['versions']} == {'rev-old','rev-new'}
    assert tables['prompt_embeddings']['versions'][0]['prompt_policy'] == 'prompt-v1'
    assert tables['hash_cache']['rows'] == 1
    assert {row['status'] for row in tables['asset_features']['versions']} == {'current','stale','unversioned'}
    assert len(report['database_cache']['warnings']) == 2
    assert not {'reviews','review_events','picks','pick_events','promotions','promotion_events'} & tables.keys()


def test_maintenance_flags_partial_curated_copies_without_recommending_audio_deletion(tmp_path):
    root = tmp_path / 'samples'
    curated = root / 'CURATED/KICK/pack'
    curated.mkdir(parents=True)
    partial = curated / '.kick.wav.eidetic-copy-interrupted.partial'
    partial.write_bytes(b'partial copy evidence')
    original = curated / 'kick.wav'
    original.write_bytes(b'approved original audio')
    human = root / '.eidetic/packets/session/labels.tsv'
    human.parent.mkdir(parents=True)
    human.write_text('human decision')
    before = _snapshot(root)

    report = maintenance_preview(root)

    assert _snapshot(root) == before
    assert report['database_cache']['status'] == 'missing'
    assert report['partial_copies'] == [{
        'path': partial.relative_to(root).as_posix(), 'bytes': len(partial.read_bytes()),
        'status': 'requires_recovery_review',
    }]
    assert report['candidates'] == []


def test_maintenance_reports_pending_journal_without_ignoring_or_changing_it(tmp_path):
    root = tmp_path / 'samples'
    root.mkdir()
    db = LibraryDatabase(root / '.eidetic/library.sqlite')
    scan_library(root, db)
    writer = sqlite3.connect(db.path)
    try:
        writer.execute('pragma journal_mode=WAL')
        writer.execute("insert into state_metadata values('still-writing','pending')")
        writer.commit()
        before = _snapshot(root)
        report = maintenance_preview(root)
        assert _snapshot(root) == before
        assert report['database_cache']['status'] == 'error'
        assert 'journal' in report['database_cache']['error']
        assert report['database_cache']['tables'] == {}
    finally:
        writer.close()
