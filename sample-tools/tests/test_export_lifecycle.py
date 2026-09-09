"""Exports are derived evidence, never trusted only because a WAV exists."""
import csv
import hashlib
import json
import shutil
import wave
from dataclasses import replace
from pathlib import Path

import pytest

from sampletools import config, export as exports


def wav(path, value=1000):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(44100)
        fh.writeframes(value.to_bytes(2, 'little', signed=True) * 100)
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / 'SAMPLES'
    src = root / 'CURATED/KICK/a.wav'
    sample_id = wav(src)
    crate = tmp_path / 'kit.tsv'
    crate.write_text('sample_id\tsource_path\trole\tdescriptor\treason\n'
                     f'{sample_id}\tCURATED/KICK/a.wav\tKICK\tshort\tfavourite\n')
    spec = config.get_spec('octatrack')
    plan = exports.build_crate_plan(spec, crate, root)
    monkeypatch.setattr(exports, 'EXPORT_ROOT', root / '_EXPORT')
    monkeypatch.setattr(exports, 'SAMPLES_ROOT', root)
    output = root / '_EXPORT' / spec.export_dir / plan.items[0].out_rel
    return root, src, crate, spec, plan, output


def test_existing_unreceipted_export_requires_force(setup):
    _, _, _, spec, plan, output = setup
    output.parent.mkdir(parents=True)
    output.write_bytes(b'old export')
    with pytest.raises(exports.ExportError, match='--force'):
        exports.export_device(spec, plan=plan)
    assert output.read_bytes() == b'old export'


def test_receipt_proves_source_settings_and_output_before_reuse(setup):
    _, src, _, spec, plan, output = setup
    assert exports.export_device(spec, plan=plan) == (1, 0)
    receipt = json.loads(output.with_suffix('.wav.receipt.json').read_text())
    assert receipt['source_sha256'] == hashlib.sha256(src.read_bytes()).hexdigest()
    assert receipt['output_sha256'] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert receipt['settings']['rate'] == 44100
    assert receipt['tool_version']
    assert receipt['ffmpeg_version'].startswith('ffmpeg version')
    assert receipt['hardware_verification'] == 'unverified'
    assert exports.export_device(spec, plan=plan) == (0, 1)


@pytest.mark.parametrize('change', ['output', 'settings', 'legacy_source', 'tool'])
def test_changed_inputs_or_damaged_output_reject_reuse(setup, monkeypatch, change):
    _, src, _, spec, plan, output = setup
    # A legacy manifest has no approval identity, but its reuse is still content-addressed.
    if change == 'legacy_source':
        plan = exports.Plan(spec, [exports.Item(src, 'a.wav')], [])
        output = exports.EXPORT_ROOT / spec.export_dir / 'a.wav'
    exports.export_device(spec, plan=plan)
    if change == 'output':
        output.write_bytes(b'corruption')
    elif change == 'settings':
        spec = replace(spec, rate=48000)
    elif change == 'legacy_source':
        wav(src, 2000)
    else:
        receipt = output.with_suffix('.wav.receipt.json')
        data = json.loads(receipt.read_text())
        data['tool_version'] = 'ancient-version'
        receipt.write_text(json.dumps(data))
    with pytest.raises(exports.ExportError, match='--force'):
        exports.export_device(spec, plan=plan)
    assert exports.export_device(spec, plan=plan, force=True) == (1, 0)
    assert exports.export_device(spec, plan=plan) == (0, 1)


def test_changed_crate_source_after_plan_is_rejected_even_with_force(setup):
    _, src, _, spec, plan, output = setup
    wav(src, 2000)
    with pytest.raises(exports.ExportError, match='hash changed'):
        exports.export_device(spec, plan=plan, force=True)
    assert not output.exists()


def test_source_change_during_conversion_keeps_previous_output(setup, monkeypatch):
    _, src, _, spec, plan, output = setup
    exports.export_device(spec, plan=plan)
    before = output.read_bytes()
    original_convert = exports.convert_file
    def interrupted(source, target, spec):
        original_convert(source, target, spec)
        wav(source, 2000)
    monkeypatch.setattr(exports, 'convert_file', interrupted)
    with pytest.raises(exports.ExportError, match='changed'):
        exports.export_device(spec, plan=plan, force=True)
    assert output.read_bytes() == before


def test_failed_output_validation_keeps_previous_output(setup, monkeypatch):
    _, _, _, spec, plan, output = setup
    exports.export_device(spec, plan=plan)
    before = output.read_bytes()
    monkeypatch.setattr(exports, 'convert_file', lambda source, target, spec: target.write_bytes(b'bad'))
    with pytest.raises(exports.ExportError, match='format'):
        exports.export_device(spec, plan=plan, force=True)
    assert output.read_bytes() == before


def test_unknown_crate_sidecar_version_is_rejected_but_legacy_is_readable(setup):
    _, _, crate, spec, _, _ = setup
    assert len(exports.read_crate_tsv(crate)) == 1
    crate.with_suffix('.tsv.metadata.json').write_text(json.dumps({'format':'eidetic-crate', 'version': 999}))
    with pytest.raises(exports.ExportError, match='version'):
        exports.read_crate_tsv(crate)


def test_transfer_records_verified_copy_separately_from_hardware(setup, tmp_path):
    _, _, _, spec, plan, output = setup
    exports.export_device(spec, plan=plan)
    card = tmp_path / 'CARD'
    card.mkdir()
    assert exports.sync_to_card(spec, card, plan=plan) == 1
    destination = card / plan.items[0].out_rel
    assert destination.read_bytes() == output.read_bytes()
    receipts = list((plan.samples_root / '.eidetic' / 'transfers').glob('*.json'))
    assert len(receipts) == 1
    data = json.loads(receipts[0].read_text())
    assert data['status'] == 'complete'
    assert data['hardware_verification'] == 'unverified'
    assert data['items'][0]['status'] == 'verified'
    assert data['items'][0]['output_sha256'] == hashlib.sha256(output.read_bytes()).hexdigest()
    stamp = destination.stat().st_mtime_ns
    assert exports.sync_to_card(spec, card, plan=plan) == 1
    assert destination.stat().st_mtime_ns == stamp


def test_interrupted_transfer_preserves_destination_and_retries(setup, tmp_path, monkeypatch):
    _, _, _, spec, plan, output = setup
    exports.export_device(spec, plan=plan)
    card = tmp_path / 'CARD'
    destination = card / plan.items[0].out_rel
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b'previous')
    original_copy = shutil.copy2
    def fail_copy(source, target, **kwargs):
        Path(target).write_bytes(b'partial')
        raise OSError('card disconnected')
    monkeypatch.setattr(exports.shutil, 'copy2', fail_copy)
    with pytest.raises(OSError, match='disconnected'):
        exports.sync_to_card(spec, card, plan=plan)
    assert destination.read_bytes() == b'previous'
    record = next((plan.samples_root / '.eidetic' / 'transfers').glob('*.json'))
    data = json.loads(record.read_text())
    assert data['status'] == 'interrupted'
    monkeypatch.setattr(exports.shutil, 'copy2', original_copy)
    assert exports.sync_to_card(spec, card, plan=plan) == 1
    assert destination.read_bytes() == output.read_bytes()


def test_dry_run_reports_unverified_outputs_without_writing(setup, capsys):
    _, _, _, spec, plan, output = setup
    output.parent.mkdir(parents=True)
    output.write_bytes(b'old')
    exports.export_device(spec, plan=plan, dry_run=True)
    assert '--force' in capsys.readouterr().out
    assert output.read_bytes() == b'old'
    assert not output.with_suffix('.wav.receipt.json').exists()


def test_transfer_rejects_damaged_staged_receipt_before_card_write(setup, tmp_path):
    _, _, _, spec, plan, output = setup
    exports.export_device(spec, plan=plan)
    output.write_bytes(b'corrupted')
    card = tmp_path / 'CARD'
    card.mkdir()
    with pytest.raises(exports.ExportError, match='receipt|damaged'):
        exports.sync_to_card(spec, card, plan=plan)
    assert not list(card.rglob('*'))


@pytest.mark.parametrize('invalid', ['marker', 'database'])
def test_future_library_state_rejects_export_without_mutation(setup, invalid):
    import sqlite3
    _, _, _, spec, plan, output = setup
    state = plan.samples_root / '.eidetic'
    state.mkdir()
    if invalid == 'marker':
        marker = state / 'library.json'
        marker.write_text(json.dumps({'format_version': 99, 'library_id': 'future'}))
    else:
        with sqlite3.connect(state / 'library.sqlite') as connection:
            connection.execute('PRAGMA user_version=99')
    with pytest.raises(exports.ExportError, match='version|newer'):
        exports.export_device(spec, plan=plan)
    assert not output.exists()
    assert not (state / 'writer.lock').exists()


def test_another_library_writer_blocks_export_but_not_dry_run(setup):
    import fcntl
    _, _, _, spec, plan, output = setup
    state = plan.samples_root / '.eidetic'
    state.mkdir()
    lock = state / 'writer.lock'
    lock.write_text('other writer')
    with lock.open('a+') as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(exports.ExportError, match='writer|locked'):
            exports.export_device(spec, plan=plan)
        assert exports.export_device(spec, plan=plan, dry_run=True) == (1, 0)
        assert lock.read_text() == 'other writer'
    assert not output.exists()


def test_incomplete_library_operation_blocks_export_until_reconciled(setup):
    _, _, _, spec, plan, output = setup
    journal = plan.samples_root / '.eidetic/operations/pending.json'
    journal.parent.mkdir(parents=True)
    journal.write_text(json.dumps({'schema_version': 1, 'operation_id': 'pending', 'status': 'pending'}))
    with pytest.raises(exports.ExportError, match='recover'):
        exports.export_device(spec, plan=plan)
    assert not output.exists()
    assert exports.export_device(spec, plan=plan, dry_run=True) == (1, 0)


@pytest.mark.parametrize('record', [{'format_version': 1, 'status': 'pending'},
                                  {'format_version': 999, 'status': 'complete'}, []])
def test_unfinished_or_unknown_adoption_blocks_export_and_sync(setup, tmp_path, record):
    _, _, _, spec, plan, output = setup
    exports.export_device(spec, plan=plan)
    before = output.read_bytes()
    (plan.samples_root / '.eidetic/adoption.json').write_text(json.dumps(record))
    card = tmp_path / 'CARD'; card.mkdir()
    with pytest.raises(exports.ExportError, match='adoption'):
        exports.export_device(spec, plan=plan, force=True)
    with pytest.raises(exports.ExportError, match='adoption'):
        exports.sync_to_card(spec, card, plan=plan)
    assert output.read_bytes() == before
    assert not list(card.iterdir())
    assert exports.export_device(spec, plan=plan, dry_run=True) == (0, 1)


def test_lock_symlink_created_after_preflight_cannot_clobber_audio(setup, monkeypatch):
    _, src, _, spec, plan, output = setup
    state = plan.samples_root / '.eidetic'; state.mkdir()
    lock = state / 'writer.lock'
    original = Path.is_symlink
    audio_before = src.read_bytes()
    swapped = False
    def race(path):
        nonlocal swapped
        result = original(path)
        if path == lock and not swapped:
            swapped = True
            lock.symlink_to(src)
        return result
    monkeypatch.setattr(Path, 'is_symlink', race)
    with pytest.raises(exports.ExportError, match='lock|symlink'):
        exports.export_device(spec, plan=plan)
    assert src.read_bytes() == audio_before
    assert not output.exists()


def test_crate_sidecar_hash_detects_interrupted_pair_without_breaking_legacy_metadata(setup):
    _, _, crate, _, _, _ = setup
    sidecar = crate.with_suffix('.tsv.metadata.json')
    metadata = {'format': 'eidetic-crate', 'version': 1}
    sidecar.write_text(json.dumps(metadata))
    assert len(exports.read_crate_tsv(crate)) == 1
    metadata['sha256'] = hashlib.sha256(crate.read_bytes()).hexdigest()
    sidecar.write_text(json.dumps(metadata))
    assert len(exports.read_crate_tsv(crate)) == 1
    crate.write_text(crate.read_text().replace('\tshort\t', '\tchanged\t'))
    with pytest.raises(exports.ExportError, match='hash|checksum'):
        exports.read_crate_tsv(crate)


@pytest.mark.parametrize('problem', ['future', 'non-object', 'boolean-version', 'missing-machines', 'wrong-library', 'invalid-deferred', 'symlink'])
def test_invalid_onboarding_metadata_blocks_export_and_transfer_before_writes(setup, tmp_path, problem):
    root, _, _, spec, plan, output = setup
    identity = '00000000-0000-0000-0000-000000000001'
    state = root / '.eidetic'
    state.mkdir()
    (state / 'library.json').write_text(json.dumps({'format_version': 1, 'library_id': identity}))
    exports.export_device(spec, plan=plan)
    metadata = {'format_version': 1, 'library_id': identity, 'coverage': 'incomplete',
                'machines': {}, 'captures': {}, 'deferred_machines': ['Mac mini']}
    if problem == 'future':
        metadata['format_version'] = 999
    elif problem == 'non-object':
        metadata = []
    elif problem == 'boolean-version':
        metadata['format_version'] = True
    elif problem == 'missing-machines':
        metadata.pop('machines')
    elif problem == 'wrong-library':
        metadata['library_id'] = '00000000-0000-0000-0000-000000000002'
    elif problem == 'invalid-deferred':
        metadata['deferred_machines'] = 'Mac mini'
    onboarding = state / 'onboarding.json'
    if problem == 'symlink':
        external = tmp_path / 'external-onboarding.json'
        external.write_text(json.dumps(metadata))
        onboarding.symlink_to(external)
    else:
        onboarding.write_text(json.dumps(metadata))
    before = {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}
    card = tmp_path / 'CARD'
    card.mkdir()
    with pytest.raises(exports.ExportError, match='onboarding'):
        exports.export_device(spec, plan=plan, force=True)
    with pytest.raises(exports.ExportError, match='onboarding'):
        exports.sync_to_card(spec, card, plan=plan)
    assert before == {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}
    assert not list(card.iterdir())


def test_pending_other_machine_history_allows_export_and_transfer(setup, tmp_path):
    root, _, _, spec, plan, output = setup
    identity = '00000000-0000-0000-0000-000000000001'
    state = root / '.eidetic'
    state.mkdir()
    (state / 'library.json').write_text(json.dumps({'format_version': 1, 'library_id': identity}))
    metadata = {'format_version': 1, 'library_id': identity, 'coverage': 'incomplete',
                'machines': {'MacBook': {'history_status': 'no_local_history_found', 'capture_ids': []}},
                'captures': {}, 'deferred_machines': ['Mac mini']}
    onboarding = state / 'onboarding.json'
    onboarding.write_text(json.dumps(metadata))
    original = onboarding.read_bytes()
    assert exports.export_device(spec, plan=plan) == (1, 0)
    card = tmp_path / 'CARD'
    card.mkdir()
    assert exports.sync_to_card(spec, card, plan=plan) == 1
    assert output.is_file() and onboarding.read_bytes() == original
