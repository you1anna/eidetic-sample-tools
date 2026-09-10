"""Collection history is recorded export evidence, never approval or device presence."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from librarytools.collection_history import load_history, validate_history_snapshot

LIBRARY = 'library-test'
SOURCE_A = 'a' * 64
SOURCE_B = 'b' * 64
OUTPUT = 'f' * 64


def receipt(*, device='octatrack', sample_id=SOURCE_A, library_id=LIBRARY):
    return {
        'format': 'eidetic-export', 'version': 1,
        'source_sha256': sample_id, 'output_sha256': OUTPUT,
        'settings': {'device': device}, 'library_id': library_id,
        'software_validation': 'passed', 'source_path': '/never/read/source.wav',
        'hardware_verification': 'unverified',
    }


def historical(items=None, **extra):
    return {
        'schema': 'eidetic-delegated-library-v1',
        'authority': '/never/read/labels.tsv', 'samples_root': '/never/read/library',
        'items': items if items is not None else [
            {'sample_id': SOURCE_A, 'device': 'octatrack', 'output_sha256': OUTPUT},
            {'sample_id': SOURCE_B, 'device': 'digitakt', 'output_sha256': OUTPUT},
        ], **extra,
    }


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def load(paths, **kwargs):
    return load_history(paths, library_id=LIBRARY, device=kwargs.pop('device', 'octatrack'), **kwargs)


def test_no_inputs_are_unknown_not_complete_history():
    assert load([]) == {
        'version': 1, 'library_id': LIBRARY, 'device': 'octatrack',
        'coverage': 'unknown', 'sample_ids': [], 'sources': [],
    }


@pytest.mark.parametrize('device', ['octatrack', 'digitakt', 'tr8s'])
def test_receipt_records_original_identity_and_filters_device(tmp_path, device):
    path = write_json(tmp_path / 'old.wav.receipt.json', receipt(device=device))
    result = load([path], device=device)
    assert result['sample_ids'] == [SOURCE_A]
    assert OUTPUT not in result['sample_ids']
    assert result['coverage'] == 'provided_records_only'
    assert result['sources'] == [{
        'name': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'format': 'eidetic-export', 'library_id': LIBRARY, 'scope': 'library',
        'records_total': 1, 'records_for_device': 1,
    }]
    other = 'digitakt' if device != 'digitakt' else 'octatrack'
    filtered = load([path], device=other)
    assert filtered['sample_ids'] == []
    assert filtered['sources'][0]['records_for_device'] == 0
    assert filtered['coverage'] == 'provided_records_only'


@pytest.mark.parametrize('library_id', [None, ''])
def test_legacy_receipt_explicitly_reference_only(tmp_path, library_id):
    result = load([write_json(tmp_path / 'old.json', receipt(library_id=library_id))])
    assert result['sources'][0]['library_id'] is None
    assert result['sources'][0]['scope'] == 'reference'


def test_historical_filters_and_deduplicates_without_following_legacy_paths(tmp_path):
    value = historical()
    value['items'].append(dict(value['items'][0]))
    result = load([write_json(tmp_path / 'selection.json', value)])
    assert result['sample_ids'] == [SOURCE_A]
    assert result['sources'][0]['records_total'] == 3
    assert result['sources'][0]['records_for_device'] == 2
    assert result['sources'][0]['scope'] == 'reference'
    assert '/never/read' not in json.dumps(result)
    assert 'approval' not in json.dumps(result)
    assert 'presence' not in json.dumps(result)


def test_directory_only_reads_receipts_and_repeated_inputs_are_idempotent(tmp_path, monkeypatch):
    folder = tmp_path / 'exports'
    receipt_a = write_json(folder / 'nested' / 'one.wav.receipt.json', receipt())
    write_json(folder / 'two.wav.receipt.json', receipt(sample_id=SOURCE_B))
    (folder / 'audio.wav').write_bytes(b'not opened as audio')
    (folder / 'unrelated.json').write_text('invalid json ignored')
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    once = load([folder])
    repeated = load([receipt_a, folder, folder])
    assert repeated == once
    assert once['sample_ids'] == [SOURCE_A, SOURCE_B]
    assert len(once['sources']) == 2
    assert once['sources'] == sorted(once['sources'], key=lambda row: (row['sha256'], row['name']))
    after = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert after == before


@pytest.mark.parametrize('value, match', [
    (receipt(library_id='another-library'), 'library'),
    (receipt(library_id=123), 'library_id'),
    (receipt(device='other-device'), 'device'),
    ({**receipt(), 'version': True}, 'version'),
    ({**receipt(), 'version': 2}, 'version'),
    ({**receipt(), 'source_sha256': 'broken'}, 'source_sha256'),
    ({**receipt(), 'output_sha256': None}, 'output_sha256'),
    ({**receipt(), 'software_validation': 'failed'}, 'software_validation'),
    ({**receipt(), 'settings': {}}, 'device'),
    (historical([]), 'items'),
    (historical([{'sample_id': SOURCE_A, 'device': 'digitakt'}]), 'output_sha256'),
    (historical([{'sample_id': SOURCE_A, 'device': 'other', 'output_sha256': OUTPUT}]), 'device'),
    (historical(library_id='another-library'), 'library'),
    ({'format': 'something-else'}, 'recognized'),
    ([], 'object'),
])
def test_invalid_history_rejected_even_when_record_is_for_another_device(tmp_path, value, match):
    with pytest.raises(ValueError, match=match):
        load([write_json(tmp_path / 'bad.json', value)])


@pytest.mark.parametrize('contents', [
    '{', '{"format":"ignored","format":"eidetic-export"}',
    '{"value":NaN}', '{"value":Infinity}', '{"value":1e999}',
])
def test_malformed_json_duplicate_keys_and_nonfinite_values_rejected(tmp_path, contents):
    path = tmp_path / 'bad.json'
    path.write_text(contents)
    with pytest.raises(ValueError, match='Invalid history JSON'):
        load([path])


def test_empty_missing_and_symlink_evidence_rejected(tmp_path):
    with pytest.raises(ValueError, match='exist|read'):
        load([tmp_path / 'missing.json'])
    empty = tmp_path / 'empty'
    empty.mkdir()
    with pytest.raises(ValueError, match='receipt'):
        load([empty])
    real = write_json(tmp_path / 'real.json', receipt())
    linked = tmp_path / 'linked.json'
    linked.symlink_to(real)
    with pytest.raises(ValueError, match='symlink'):
        load([linked])
    (empty / 'linked.wav.receipt.json').symlink_to(real)
    with pytest.raises(ValueError, match='symlink'):
        load([empty])


def test_symlink_directory_not_silently_skipped(tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    outside = tmp_path / 'outside'
    write_json(outside / 'old.wav.receipt.json', receipt())
    (root / 'linked').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        load([root])


def test_oversized_input_rejected_without_reading_it_all(tmp_path):
    path = tmp_path / 'large.json'
    with path.open('wb') as stream:
        stream.truncate(32 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match='32 MiB'):
        load([path])


def test_snapshot_roundtrip_after_evidence_removed(tmp_path):
    path = write_json(tmp_path / 'receipt.json', receipt())
    result = load([path])
    path.unlink()
    validated = validate_history_snapshot(result, library_id=LIBRARY, device='octatrack')
    assert validated == result
    assert validated is not result
    validated['sources'][0]['name'] = 'changed.json'
    assert result['sources'][0]['name'] == 'receipt.json'


@pytest.mark.parametrize('change, match', [
    (lambda v: v.update(version=True), 'version'),
    (lambda v: v.update(library_id='wrong'), 'library'),
    (lambda v: v.update(device='digitakt'), 'device'),
    (lambda v: v.update(coverage='complete'), 'coverage'),
    (lambda v: v.update(coverage='unknown'), 'unknown'),
    (lambda v: v.update(sample_ids=[SOURCE_A, SOURCE_A]), 'sorted|unique'),
    (lambda v: v.update(sample_ids=[SOURCE_B, SOURCE_A]), 'sorted|unique'),
    (lambda v: v['sources'][0].update(name='/private/path/receipt.json'), 'name'),
    (lambda v: v['sources'][0].update(name='..'), 'name'),
    (lambda v: v['sources'][0].update(sha256='bad'), 'sha256'),
    (lambda v: v['sources'][0].update(scope='reference'), 'scope'),
    (lambda v: v['sources'][0].update(records_total=True), 'records_total'),
    (lambda v: v['sources'][0].update(records_for_device=2), 'records_for_device'),
    (lambda v: v.update(sample_ids=[]), 'sample_ids'),
    (lambda v: v['sources'].append(copy.deepcopy(v['sources'][0])), 'sorted|unique'),
    (lambda v: v.update(approval=True), 'fields'),
])
def test_invalid_saved_snapshots_rejected(tmp_path, change, match):
    snapshot = load([write_json(tmp_path / 'receipt.json', receipt())])
    change(snapshot)
    with pytest.raises(ValueError, match=match):
        validate_history_snapshot(snapshot, library_id=LIBRARY, device='octatrack')


@pytest.mark.parametrize('library_id,device', [('', 'octatrack'), (None, 'octatrack'), (LIBRARY, 'OT')])
def test_invalid_request_identity_rejected(library_id, device):
    with pytest.raises(ValueError):
        load_history([], library_id=library_id, device=device)


def test_directory_does_not_open_audio_database_or_legacy_paths(tmp_path, monkeypatch):
    import librarytools.collection_history as history

    folder = tmp_path / 'exports'
    evidence = write_json(folder / 'one.wav.receipt.json', receipt())
    (folder / 'one.wav').write_bytes(b'pretend audio')
    (folder / 'library.sqlite').write_bytes(b'pretend database')
    real_open = os.open
    opened = []

    def tracked_open(path, flags, *args, **kwargs):
        opened.append((Path(path), flags))
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(history.os, 'open', tracked_open)
    assert load([folder])['sample_ids'] == [SOURCE_A]
    assert [path for path, _ in opened] == [evidence]
    assert all(not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC) for _, flags in opened)
