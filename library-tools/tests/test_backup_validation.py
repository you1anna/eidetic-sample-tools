"""Damaged backup metadata must fail before restoration writes anything."""
import json

import pytest

from librarytools.library_cli import main


@pytest.mark.parametrize('manifest', [
    None, [], 'backup',
    {'format_version': True, 'files': {}},
    {'format_version': 1, 'files': []},
    *({'format_version': 1, 'files': {'library.sqlite': evidence}} for evidence in (
        None, [], {}, {'size': 4},
        {'size': True, 'sha256': 'a' * 64},
        {'size': -1, 'sha256': 'a' * 64},
        {'size': '4', 'sha256': 'a' * 64},
        {'size': 4, 'sha256': None},
        {'size': 4, 'sha256': 'not-a-hash'},
    )),
])
@pytest.mark.parametrize('apply', [False, True])
def test_restore_reports_malformed_manifest_without_writes(tmp_path, capsys, manifest, apply):
    bundle = tmp_path / 'backup'
    state = bundle / 'state'
    state.mkdir(parents=True)
    (state / 'library.sqlite').write_bytes(b'test')
    metadata = bundle / 'manifest.json'
    metadata.write_text(json.dumps(manifest))
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in bundle.rglob('*') if p.is_file()}
    destination = tmp_path / 'new-parent' / 'restored'
    args = ['restore', '--source', str(bundle), '--output', str(destination), '--json']

    assert main(args + (['--apply'] if apply else [])) == 2
    assert 'backup' in json.loads(capsys.readouterr().out)['error']
    assert not destination.parent.exists()
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in bundle.rglob('*') if p.is_file()} == before
