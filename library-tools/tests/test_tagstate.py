import json
import os
from pathlib import Path

import pytest

from librarytools import moves, tagstate
from librarytools.inventory import LibraryDatabase, scan_library


def test_snapshot_is_unpublished_on_flush_failure_and_retry_can_publish(tmp_path, monkeypatch):
    payload = b'schema_version=2\n'
    path = tmp_path / '.eidetic/configurations' / f'vocabulary-{tagstate.digest(payload)}.toml'

    def interrupted(descriptor):
        assert not path.exists()
        raise OSError('simulated disk failure before publication')

    with monkeypatch.context() as patch:
        patch.setattr(os, 'fsync', interrupted)
        with pytest.raises(OSError, match='before publication'):
            tagstate.preserve_vocabulary(tmp_path, payload)
    assert not path.exists()
    tagstate.preserve_vocabulary(tmp_path, payload)
    assert path.read_bytes() == payload


def test_snapshot_publication_never_overwrites_a_competing_digest_file(tmp_path, monkeypatch):
    payload = b'schema_version=2\n'
    path = tmp_path / '.eidetic/configurations' / f'vocabulary-{tagstate.digest(payload)}.toml'
    publish = moves._rename_exclusive

    def competing_file(source, target):
        target.write_bytes(b'other evidence')
        publish(source, target)

    monkeypatch.setattr(moves, '_rename_exclusive', competing_file)
    with pytest.raises((ValueError, FileExistsError)):
        tagstate.preserve_vocabulary(tmp_path, payload)
    assert path.read_bytes() == b'other evidence'


def test_reusing_matching_snapshot_keeps_its_bytes_and_mtime(tmp_path):
    payload = b'schema_version=2\n'
    tagstate.preserve_vocabulary(tmp_path, payload)
    path = tmp_path / '.eidetic/configurations' / f'vocabulary-{tagstate.digest(payload)}.toml'
    before = path.read_bytes(), path.stat().st_mtime_ns
    tagstate.preserve_vocabulary(tmp_path, payload)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


@pytest.mark.parametrize('existing', ['different-bytes', 'symlink', 'dangling-symlink', 'directory'])
def test_snapshot_publication_refuses_changed_or_indirect_evidence(tmp_path, existing):
    payload = b'schema_version=2\n'
    path = tmp_path / '.eidetic/configurations' / f'vocabulary-{tagstate.digest(payload)}.toml'
    path.parent.mkdir(parents=True)
    target = tmp_path / 'external.toml'
    if existing == 'different-bytes':
        path.write_bytes(b'other evidence')
    elif existing == 'directory':
        path.mkdir()
    else:
        if existing == 'symlink':
            target.write_bytes(payload)
        path.symlink_to(target)
    with pytest.raises(ValueError, match='snapshot'):
        tagstate.preserve_vocabulary(tmp_path, payload)
    if existing == 'different-bytes':
        assert path.read_bytes() == b'other evidence'
    elif existing == 'directory':
        assert path.is_dir()
    else:
        assert path.is_symlink()
        assert target.exists() is (existing == 'symlink')


@pytest.mark.parametrize('generation_module', ['refresh.py', 'tag_cli.py'])
def test_generation_changes_invalidate_tags_but_search_changes_do_not(tmp_path, monkeypatch, generation_module):
    root = tmp_path / 'samples'
    root.mkdir()
    (root / 'kick.wav').write_bytes(b'synthetic audio')
    database = LibraryDatabase(root / '.eidetic/library.sqlite')
    scan_library(root, database)
    sample_id = database.assets()[0]
    package = tmp_path / 'recipe'
    package.mkdir()
    for name in ('tagstate.py', 'refresh.py', 'tag_cli.py', 'find.py'):
        (package / name).write_text('def transform():\n    return "original"\n')
    monkeypatch.setattr(tagstate, '__file__', str(package / 'tagstate.py'))
    payload = b'schema_version=2\n'
    generated = {sample_id: [('role', 'KICKS')]}
    database.replace_generated_tags(generated, vocabulary_digest=tagstate.digest(payload),
                                    metadata=tagstate.publication_metadata(database, payload, 'custom', generated))
    assert tagstate.freshness(database, payload)['status'] == 'current'

    (package / 'find.py').write_text('def transform():\n    return "new search behavior"\n')
    assert tagstate.freshness(database, payload)['status'] == 'current'
    (package / generation_module).write_text('def transform():\n    return "new tag behavior"\n')
    assert tagstate.freshness(database, payload)['status'] == 'stale'


@pytest.mark.parametrize(('field', 'value'), [
    ('format_version', True),
    ('vocabulary_digest', {'invalid': 'digest'}),
    ('recipe_digest', []),
    ('inputs_digest', 'short'),
    ('output_digest', 'z' * 64),
    ('vocabulary_kind', 'unexpected'),
    ('feature_version', 2),
    ('librarytools_version', None),
    ('generated_at', 'not-a-timestamp'),
])
@pytest.mark.parametrize('explicit', [False, True])
def test_malformed_publication_blocks_vocabulary_selection_without_state_changes(tmp_path, field, value, explicit):
    root = tmp_path / 'samples'
    root.mkdir()
    database = LibraryDatabase(root / '.eidetic/library.sqlite')
    database.bind_root(root)
    payload = b'schema_version=2\n'
    tagstate.preserve_vocabulary(root, payload)
    evidence = tagstate.publication_metadata(database, payload, 'custom', {})
    record = json.loads(evidence[tagstate.STATE_KEY])
    record[field] = value
    database.replace_generated_tags({}, metadata={tagstate.STATE_KEY: json.dumps(record)})
    vocabulary = tmp_path / 'custom.toml'
    vocabulary.write_bytes(payload)
    before = database.path.read_bytes()

    with pytest.raises(ValueError, match='tag freshness record'):
        tagstate.select_vocabulary(root, database, vocabulary if explicit else None)

    assert database.path.read_bytes() == before


@pytest.mark.parametrize('missing', ['recipe_digest', 'vocabulary_kind', 'feature_version', 'generated_at'])
def test_incomplete_publication_record_is_not_treated_as_fresh_or_legacy(tmp_path, missing):
    database = LibraryDatabase(tmp_path / 'library.sqlite')
    payload = b'schema_version=2\n'
    record = json.loads(tagstate.publication_metadata(database, payload, 'default', {})[tagstate.STATE_KEY])
    del record[missing]
    database.replace_generated_tags({}, metadata={tagstate.STATE_KEY: json.dumps(record)})
    with pytest.raises(ValueError, match='tag freshness record'):
        tagstate.freshness(database, payload)
