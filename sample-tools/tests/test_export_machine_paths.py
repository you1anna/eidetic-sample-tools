"""Each invocation must use the selected machine's attached library and output."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import uuid
import wave
from pathlib import Path

import pytest

from sampletools import cli, config, export, receipts


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / 'ATTACHED'
    source = root / 'CURATED' / 'KICK' / 'kick.wav'
    source.parent.mkdir(parents=True)
    with wave.open(str(source), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(44100)
        out.writeframes(b'\0\0' * 441)
    identity = str(uuid.uuid4())
    state = root / '.eidetic'
    state.mkdir()
    (state / 'library.json').write_text(json.dumps({'format_version': 1, 'library_id': identity}))
    crate = tmp_path / 'kit.tsv'
    with crate.open('w', newline='') as out:
        writer = csv.DictWriter(out, delimiter='\t', fieldnames=('sample_id', 'source_path', 'role', 'descriptor', 'reason'))
        writer.writeheader()
        writer.writerow({'sample_id': hashlib.sha256(source.read_bytes()).hexdigest(),
                         'source_path': 'CURATED/KICK/kick.wav', 'role': 'KICK',
                         'descriptor': 'short', 'reason': 'favourite'})
    stale = tmp_path / 'OLD-MAC'
    for module in (cli, export):
        monkeypatch.setattr(module, 'SAMPLES_ROOT', stale)
        monkeypatch.setattr(module, 'EXPORT_ROOT', stale / 'custom-export')
    monkeypatch.setattr(receipts, 'runtime', lambda: {'tool_version': 'test', 'ffmpeg_version': 'fixture'})
    monkeypatch.setattr(export, 'convert_file', lambda src, dest, spec: shutil.copyfile(src, dest))
    return root, crate, identity, stale


@pytest.mark.parametrize('preview', ['--list', '--dry-run'])
def test_explicit_machine_root_previews_correct_destination_without_writes(library, preview, capsys):
    root, crate, _, stale = library
    before = {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}
    assert cli.main(['octatrack', '--root', str(root), '--crate', str(crate), preview]) == 0
    assert str(root / '_EXPORT' / 'OCTATRACK') in capsys.readouterr().out
    assert before == {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}
    assert not stale.exists()


def test_machine_root_controls_sources_export_receipts_locks_and_transfer_journal(library, tmp_path):
    root, crate, identity, stale = library
    card = tmp_path / 'CARD'
    card.mkdir()
    assert cli.main(['octatrack', '--root', str(root), '--crate', str(crate), '--sync', str(card)]) == 0
    staged = next((root / '_EXPORT').rglob('*.wav'))
    receipt = json.loads(receipts.receipt_path(staged).read_text())
    assert receipt['library_id'] == identity
    assert receipt['source_path'] == 'CURATED/KICK/kick.wav'
    assert (root / '.eidetic' / 'writer.lock').is_file()
    transfer = json.loads(next((root / '.eidetic' / 'transfers').glob('*.json')).read_text())
    assert transfer['status'] == 'complete'
    assert transfer['items'][0]['source'].startswith('OCTATRACK/')
    assert len(list(card.rglob('*.wav'))) == 1
    assert not stale.exists()


def test_explicit_export_override_keeps_evidence_on_selected_library(library, tmp_path):
    root, crate, _, stale = library
    output = tmp_path / 'STAGING'
    assert cli.main(['octatrack', '--root', str(root), '--export-root', str(output), '--crate', str(crate)]) == 0
    assert len(list(output.rglob('*.wav'))) == 1
    assert not (root / '_EXPORT').exists()
    assert (root / '.eidetic' / 'writer.lock').is_file()
    assert not stale.exists()


@pytest.mark.parametrize('manifest_location', ['portable', 'checkout', 'packaged'])
def test_manifest_plan_uses_selected_root_before_checkout_and_packaged_fallbacks(tmp_path, monkeypatch, manifest_location):
    root = tmp_path / 'ATTACHED'
    source = root / 'CURATED' / 'kick.wav'
    source.parent.mkdir(parents=True)
    source.write_bytes(b'audio')
    (source.parent / 'wrong.wav').write_bytes(b'wrong selection')
    old = tmp_path / 'OLD-MAC'
    old_manifest = old / '.eidetic/manifests/octatrack.txt'
    old_manifest.parent.mkdir(parents=True)
    old_manifest.write_text('CURATED/wrong.wav\n')
    monkeypatch.setattr(config, 'SAMPLES_ROOT', old)
    package = tmp_path / 'checkout/sample-tools/src/sampletools'
    monkeypatch.setattr(config, '__file__', str(package / 'config.py'))
    manifests = {
        'portable': root / '.eidetic/manifests',
        'checkout': package.parents[1] / 'manifests',
        'packaged': package / 'resources/manifests',
    }
    selected = manifests[manifest_location] / 'octatrack.txt'
    selected.parent.mkdir(parents=True)
    selected.write_text('CURATED/kick.wav\n')
    before = {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    plan = export.build_plan(config.get_spec('octatrack'), samples_root=root, export_root=root / '_EXPORT')
    assert [item.src for item in plan.items] == [source]
    assert plan.samples_root == root and plan.export_root == root / '_EXPORT'
    assert {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()} == before


def test_manifest_plan_without_root_override_uses_configured_portable_manifest(tmp_path, monkeypatch):
    root = tmp_path / 'CONFIGURED'
    root.mkdir()
    source = root / 'kick.wav'
    source.write_bytes(b'audio')
    manifest = root / '.eidetic/manifests/octatrack.txt'
    manifest.parent.mkdir(parents=True)
    manifest.write_text('kick.wav\n')
    monkeypatch.setattr(config, 'SAMPLES_ROOT', root)
    monkeypatch.setattr(export, 'SAMPLES_ROOT', root)

    assert config.manifest_path('octatrack') == manifest
    assert [item.src for item in export.build_plan(config.get_spec('octatrack')).items] == [source]


def test_no_root_override_preserves_machine_environment_export_setting(library, tmp_path, monkeypatch):
    root, crate, _, _ = library
    configured = tmp_path / 'CONFIGURED-EXPORT'
    monkeypatch.setattr(cli, 'SAMPLES_ROOT', root)
    monkeypatch.setattr(cli, 'EXPORT_ROOT', configured)
    assert cli.main(['octatrack', '--crate', str(crate)]) == 0
    assert len(list(configured.rglob('*.wav'))) == 1
    assert not (root / '_EXPORT').exists()


def test_custom_export_root_sync_and_force_reuse_selected_plan(library, tmp_path):
    root, crate, identity, stale = library
    output = tmp_path / 'EXTERNAL-STAGE'
    card = tmp_path / 'CARD'
    card.mkdir()
    args = ['octatrack', '--root', str(root), '--export-root', str(output), '--crate', str(crate)]
    assert cli.main(args) == 0
    staged = next(output.rglob('*.wav'))
    staged.write_bytes(b'damaged')
    assert cli.main(args) == 2
    assert staged.read_bytes() == b'damaged'
    assert cli.main(args + ['--force', '--sync', str(card)]) == 0
    assert staged.read_bytes() != b'damaged'
    receipt = json.loads(receipts.receipt_path(staged).read_text())
    assert receipt['library_id'] == identity
    transfer = json.loads(next((root / '.eidetic' / 'transfers').glob('*.json')).read_text())
    assert transfer['items'][0]['source'].startswith('OCTATRACK/')
    assert len(list(card.rglob('*.wav'))) == 1
    assert not stale.exists()
