"""Dated report evidence must distinguish incomplete scans from clean ones."""
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from abletontools import cli

XML = b'<Ableton><LiveSet><Tracks/><Scenes/></LiveSet></Ableton>'


@pytest.mark.parametrize(('command', 'name'), [(cli.index_main, 'als-index.tsv'), (cli.samples_main, 'als-samples.tsv')])
def test_reports_record_exact_inputs_tool_version_and_output_hash(tmp_path, command, name):
    root = tmp_path / 'SETS'
    root.mkdir()
    source = root / 'set.als'
    payload = gzip.compress(XML)
    source.write_bytes(payload)
    out = tmp_path / 'reports'
    command(['--root', str(root), '--out', str(out)])
    metadata = json.loads((out / (name + '.metadata.json')).read_text())
    assert metadata['version'] == 1
    assert metadata['generated_at']
    assert metadata['tool_version']
    assert metadata['complete'] is True
    assert metadata['roots'][0] == {'path': str(root), 'status': 'scanned'}
    assert metadata['inputs'][0]['sha256'] == hashlib.sha256(payload).hexdigest()
    assert metadata['inputs'][0]['size'] == len(payload)
    assert metadata['inputs'][0]['mtime_ns'] == source.stat().st_mtime_ns
    assert metadata['report_sha256'] == hashlib.sha256((out / name).read_bytes()).hexdigest()
    assert source.read_bytes() == payload


def test_bad_set_and_unavailable_root_remain_in_evidence(tmp_path, monkeypatch):
    root = tmp_path / 'SETS'
    root.mkdir()
    (root / 'good.als').write_bytes(gzip.compress(XML))
    (root / 'bad.als').write_bytes(b'broken')
    absent = tmp_path / 'disconnected'
    monkeypatch.setenv('ALS_ROOTS', f'{root}:{absent}')
    out = tmp_path / 'reports'
    cli.index_main(['--out', str(out)])
    metadata = json.loads((out / 'als-index.tsv.metadata.json').read_text())
    assert metadata['complete'] is False
    assert metadata['roots'][1] == {'path': str(absent), 'status': 'unavailable'}
    failure = next(item for item in metadata['inputs'] if item['path'].endswith('bad.als'))
    assert failure['status'] == 'parse_error'
    assert failure['sha256'] == hashlib.sha256(b'broken').hexdigest()
    assert failure['error']


@pytest.mark.parametrize(('command', 'name'), [(cli.index_main, 'als-index.tsv'), (cli.samples_main, 'als-samples.tsv')])
def test_corrupt_deflate_stream_is_recorded_without_aborting_other_sets(tmp_path, command, name):
    root = tmp_path / 'SETS'
    root.mkdir()
    (root / 'good.als').write_bytes(gzip.compress(XML))
    payload = bytearray(gzip.compress(XML))
    payload[10:14] = b'\xff\xff\xff\xff'  # Valid gzip header, invalid deflate block.
    broken = root / 'broken.als'
    broken.write_bytes(payload)
    out = tmp_path / 'reports'

    assert command(['--root', str(root), '--out', str(out)]) == 0

    metadata = json.loads((out / (name + '.metadata.json')).read_text())
    assert metadata['complete'] is False
    observed = {Path(item['path']).name: item for item in metadata['inputs']}
    assert observed['good.als']['status'] == 'parsed'
    assert observed['broken.als']['status'] == 'parse_error'
    assert observed['broken.als']['sha256'] == hashlib.sha256(payload).hexdigest()
    assert observed['broken.als']['error']
    assert metadata['report_sha256'] == hashlib.sha256((out / name).read_bytes()).hexdigest()
    assert broken.read_bytes() == payload


def test_repeated_report_preserves_previous_report_and_metadata(tmp_path):
    root = tmp_path / 'SETS'
    root.mkdir()
    source = root / 'a.als'
    source.write_bytes(gzip.compress(XML))
    out = tmp_path / 'reports'
    cli.index_main(['--root', str(root), '--out', str(out)])
    previous = (out / 'als-index.tsv').read_bytes()
    previous_metadata = (out / 'als-index.tsv.metadata.json').read_bytes()
    source.unlink()
    cli.index_main(['--root', str(root), '--out', str(out)])
    archived = list((out / '.history').rglob('als-index.tsv'))
    assert len(archived) == 1
    assert archived[0].read_bytes() == previous
    assert archived[0].with_suffix('.tsv.metadata.json').read_bytes() == previous_metadata
    assert (out / 'als-index.tsv').read_bytes() != previous


def test_legacy_unversioned_report_is_archived_before_first_upgrade(tmp_path):
    root = tmp_path / 'SETS'
    root.mkdir()
    out = tmp_path / 'reports'
    out.mkdir()
    (out / 'als-index.tsv').write_bytes(b'legacy evidence\n')
    cli.index_main(['--root', str(root), '--out', str(out)])
    assert next((out / '.history').rglob('als-index.tsv')).read_bytes() == b'legacy evidence\n'


def test_interrupted_publication_preserves_history_and_exposes_hash_mismatch(tmp_path, monkeypatch):
    from abletontools import reports
    root = tmp_path / 'SETS'
    root.mkdir()
    source = root / 'a.als'
    source.write_bytes(gzip.compress(XML))
    out = tmp_path / 'reports'
    cli.index_main(['--root', str(root), '--out', str(out)])
    previous = (out / 'als-index.tsv').read_bytes()
    source.unlink()
    original_write = reports._atomic_write
    def disconnected(path, payload):
        if path.parent == out and path.name.endswith('.metadata.json'):
            raise OSError('disk disconnected')
        original_write(path, payload)
    monkeypatch.setattr(reports, '_atomic_write', disconnected)
    assert cli.index_main(['--root', str(root), '--out', str(out)]) == 2
    assert next((out / '.history').rglob('als-index.tsv')).read_bytes() == previous
    metadata = json.loads((out / 'als-index.tsv.metadata.json').read_text())
    assert metadata['report_sha256'] != hashlib.sha256((out / 'als-index.tsv').read_bytes()).hexdigest()


def test_directory_access_failure_is_recorded_as_incomplete(tmp_path, monkeypatch):
    from abletontools import reports
    root = tmp_path / 'SETS'
    root.mkdir()
    def failing_walk(path, onerror, **kwargs):
        onerror(PermissionError('unreadable project folder'))
        return iter(())
    monkeypatch.setattr(reports.os, 'walk', failing_walk)
    out = tmp_path / 'reports'
    cli.index_main(['--root', str(root), '--out', str(out)])
    metadata = json.loads((out / 'als-index.tsv.metadata.json').read_text())
    assert metadata['complete'] is False
    assert metadata['roots'][0]['status'] == 'partial'
    assert any('unreadable' in message for message in metadata['errors'])
