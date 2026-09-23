import json
from pathlib import Path
import wave

import pytest

from librarytools.inventory import LibraryDatabase, scan_library


def audio(path, value=100):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as out:
        out.setparams((1, 2, 44100, 0, 'NONE', 'not compressed'))
        out.writeframes(int(value).to_bytes(2, 'little', signed=True) * 4410)
    return path


def snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


@pytest.fixture
def library(tmp_path, monkeypatch):
    from librarytools import maintenance
    # Installed-release validation has its own real-artifact tests. Keep these
    # tests independent of an unfinished development checkout's release manifest.
    monkeypatch.setattr(maintenance, 'runtime_report', lambda checkout=None: {
        'contract_version': 1, 'status': 'ready', 'packages': {}, 'issues': [], 'actions': []})
    root = tmp_path / 'samples'
    audio(root / 'PACKS/One/kick.wav')
    database = LibraryDatabase(root / '.eidetic/library.sqlite')
    scan_library(root, database)
    for loc in database.current_locations():
        database.record_features(loc.sample_id, json.dumps({'tail_ms': 50, 'attack_ms': 2}))
    return root, database


def test_preview_reports_unstamped_tags_without_writing_any_evidence(library):
    from librarytools.maintenance import refresh
    root, database = library
    before = snapshot(root)
    report = refresh(root)
    assert report['contract_version'] == 1
    assert report['status'] == 'action_required'
    assert report['apply'] is False
    assert {a['id'] for a in report['actions']} == {'refresh_tags'}
    assert snapshot(root) == before


def test_tag_refresh_preserves_human_decisions_and_repeat_is_noop(library, monkeypatch):
    from librarytools import inventory, maintenance
    root, database = library
    loc = database.current_locations()[0]
    database.record_tags(loc.sample_id, [('style', 'my-choice')], source='human')
    database.record_review(loc.sample_id, 'packet', 'favourite', 'KICK', 'warm', 'keep')
    database.record_pick(loc.sample_id, 'kit', 'warm')
    source = (root / loc.path).read_bytes()
    # An unchanged inventory/tag refresh must not read source audio for hashing.
    monkeypatch.setattr(inventory, 'sha256_file', lambda p: pytest.fail('unnecessary audio hash'))
    report = maintenance.refresh(root, apply=True)
    assert report['status'] == 'ready'
    assert report['executed'] == ['refresh_tags']
    assert Path(report['backup']['destination'], 'manifest.json').is_file()
    assert ('style', 'my-choice') in database.tags_for(loc.sample_id)
    assert database.favourite_descriptions()[(loc.sample_id, 'KICK')] == 'warm'
    assert database.pick_counts()[loc.sample_id] == 1
    assert (root / loc.path).read_bytes() == source
    before = snapshot(root)
    assert maintenance.refresh(root, apply=True)['executed'] == []
    assert snapshot(root) == before


def test_added_audio_is_discovered_and_only_new_identity_is_measured(library, monkeypatch):
    from librarytools import maintenance, features
    root, database = library
    maintenance.refresh(root, apply=True)
    old = database.feature_metadata()
    new = audio(root / 'PACKS/Two/snare.wav', 200)
    assert maintenance.status(root)['library']['inventory']['checked'] is False
    preview = maintenance.refresh(root)
    assert preview['library']['inventory']['added'] == 1
    assert 'scan_inventory' in {a['id'] for a in preview['actions']}
    calls = []
    extract = features.audiofeatures.extract
    def measured(path, **kwargs):
        calls.append(path)
        return extract(path, **kwargs)
    monkeypatch.setattr(features.audiofeatures, 'extract', measured)
    report = maintenance.refresh(root, apply=True)
    assert report['status'] == 'ready'
    assert calls == [new]
    assert report['features_result']['extracted'] == 1
    for sid, evidence in old.items():
        assert database.feature_metadata()[sid] == evidence
    assert len(database.current_locations()) == 2


def test_changed_and_removed_files_are_reported_before_inventory_publication(library):
    from librarytools import maintenance
    root, database = library
    maintenance.refresh(root, apply=True)
    old = database.current_locations()[0]
    audio(root / old.path, 201)
    before = database.path.read_bytes()
    report = maintenance.refresh(root)
    assert report['library']['inventory']['changed'] == 1
    assert database.path.read_bytes() == before
    (root / old.path).unlink()
    report = maintenance.refresh(root)
    assert report['library']['inventory']['missing'] == 1
    assert database.current_locations()[0].sample_id == old.sample_id


def test_role_recipe_change_requires_tags_but_no_scan_or_audio_measurement(library, monkeypatch):
    from librarytools import maintenance, tagstate
    root, _ = library
    maintenance.refresh(root, apply=True)
    monkeypatch.setattr(tagstate, 'recipe_digest', lambda payload: 'changed-role-rules')
    report = maintenance.status(root)
    assert {a['id'] for a in report['actions']} == {'refresh_tags'}


def test_feature_version_change_requires_only_obsolete_measurements(library):
    from librarytools import maintenance
    root, database = library
    maintenance.refresh(root, apply=True)
    loc = database.current_locations()[0]
    database.record_features(loc.sample_id, '{}', extractor_version='acoustic-obsolete')
    report = maintenance.status(root)
    assert report['library']['features']['stale'] == 1
    assert 'measure_features' in {a['id'] for a in report['actions']}
    assert 'scan_inventory' not in {a['id'] for a in report['actions']}


def test_prior_failed_measurement_is_visible_without_endless_retry(library, monkeypatch):
    from librarytools import maintenance, features
    root, database = library
    loc = database.current_locations()[0]
    database.record_features(loc.sample_id, '{}', 'decode failure')
    maintenance.refresh(root, apply=True)
    monkeypatch.setattr(features.audiofeatures, 'extract', lambda *a, **kw: pytest.fail('implicit retry'))
    report = maintenance.status(root)
    assert report['status'] == 'ready'
    assert report['library']['features']['failed'] == 1
    assert report['warnings']
    assert maintenance.refresh(root)['actions'] == []
    assert 'measure_features' in {a['id'] for a in maintenance.refresh(root, retry_failed=True)['actions']}


def test_explicit_database_cannot_scan_one_pack_as_whole_library(library):
    from librarytools import maintenance
    root, database = library
    before = snapshot(root)
    report = maintenance.refresh(root / 'PACKS/One', database_path=database.path, apply=True)
    assert report['status'] == 'blocked'
    assert snapshot(root) == before


def test_runtime_drift_requires_install_before_apply(library, monkeypatch):
    from librarytools import maintenance
    root, _ = library
    monkeypatch.setattr(maintenance, 'runtime_report', lambda checkout=None: {
        'contract_version': 1, 'status': 'action_required', 'packages': {}, 'issues': ['installed code differs'],
        'actions': [{'id': 'install_release', 'reason': 'installed code differs', 'argv': []}]})
    before = snapshot(root)
    report = maintenance.refresh(root, apply=True)
    assert report['status'] == 'action_required'
    assert 'install_release' in {a['id'] for a in report['actions']}
    assert snapshot(root) == before


def test_custom_vocabulary_is_retained_through_later_refresh(library, tmp_path):
    from librarytools import maintenance
    root, database = library
    vocabulary = tmp_path / 'custom.toml'
    vocabulary.write_text('schema_version = 1\n[[tag]]\nname="personal"\ngroup="style"\nname_matches=["kick"]\n')
    assert maintenance.refresh(root, vocabulary=vocabulary, apply=True)['status'] == 'ready'
    vocabulary.unlink()
    assert maintenance.status(root)['status'] == 'ready'
    loc = database.current_locations()[0]
    assert ('style', 'personal') in database.tags_for(loc.sample_id)


def test_supported_sample_tag_records_same_freshness_contract(library, tmp_path, capsys):
    from librarytools import maintenance, tag_cli
    root, _ = library
    assert tag_cli.main(['--root', str(root), '--skip-features', '--apply',
                         '--proposal', str(tmp_path / 'proposal.txt')]) == 0
    capsys.readouterr()
    assert maintenance.status(root)['status'] == 'ready'


def test_cli_status_refresh_and_repeat_report_stable_exit_codes(library, capsys):
    from librarytools.library_cli import main
    root, _ = library
    assert main(['status', '--root', str(root), '--check-files', '--json']) == 1
    report = json.loads(capsys.readouterr().out)
    assert report['contract_version'] == 1 and report['status'] == 'action_required'
    assert main(['refresh', '--root', str(root), '--apply', '--json']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'ready'
    assert main(['refresh', '--root', str(root), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['actions'] == []


def test_output_tampering_is_not_treated_as_fresh_generated_tags(library):
    from librarytools import maintenance
    root, database = library
    maintenance.refresh(root, apply=True)
    database.clear_tags()
    report = maintenance.status(root)
    assert {a['id'] for a in report['actions']} == {'refresh_tags'}


def test_interrupted_feature_refresh_resumes_and_preserves_first_backup(library, monkeypatch):
    from librarytools import maintenance, features
    root, database = library
    maintenance.refresh(root, apply=True)
    audio(root / 'PACKS/Two/snare.wav', 200)
    old_ids = set(database.assets())
    extract = features.audiofeatures.extract
    def interrupted(*args, **kwargs):
        raise OSError('simulated interrupted decoder')
    monkeypatch.setattr(features.audiofeatures, 'extract', interrupted)
    with pytest.raises(OSError, match='interrupted'):
        maintenance.refresh(root, apply=True)
    backups = set((root / '.eidetic/backups').glob('*/manifest.json'))
    assert len(backups) == 2
    assert old_ids <= set(database.assets())
    monkeypatch.setattr(features.audiofeatures, 'extract', extract)
    result = maintenance.refresh(root, apply=True)
    assert result['status'] == 'ready'
    assert 'scan_inventory' not in result['executed']
    assert backups <= set((root / '.eidetic/backups').glob('*/manifest.json'))


def test_new_extractor_version_is_used_by_tags_and_feature_consumers(library, monkeypatch):
    from librarytools import maintenance, features
    from librarytools.featurecache import FeatureRecord
    root, database = library
    maintenance.refresh(root, apply=True)
    loc = database.current_locations()[0]
    monkeypatch.setattr(features, 'FEATURE_VERSION', 'acoustic-next')
    monkeypatch.setattr(features.audiofeatures, 'extract', lambda *a, **kw:
                        FeatureRecord(loc.path, loc.size, 1.0, tail_ms=50))
    result = maintenance.refresh(root, apply=True)
    assert result['status'] == 'ready'
    assert result['features_result']['extracted'] == 1
    assert json.loads(database.features()[loc.sample_id])['tail_ms'] == 50
    assert ('character', 'short') in database.tags_for(loc.sample_id)


def test_failed_old_extractor_needs_explicit_retry_even_when_other_work_runs(library, monkeypatch):
    from librarytools import maintenance, features
    root, database = library
    loc = database.current_locations()[0]
    database.record_features(loc.sample_id, '{}', 'bad audio', extractor_version='acoustic-old')
    original = features.audiofeatures.extract
    calls = []
    def extract(path, **kw):
        calls.append(path)
        return original(path, **kw)
    monkeypatch.setattr(features.audiofeatures, 'extract', extract)
    new = audio(root / 'PACKS/Two/snare.wav', 200)
    result = maintenance.refresh(root, apply=True)
    assert result['status'] == 'ready' and result['library']['features']['failed'] == 1
    assert result['warnings'] and calls == [new]
    assert database.feature_metadata()[loc.sample_id]['extractor_version'] == 'acoustic-old'
    retry = maintenance.refresh(root, retry_failed=True)
    assert all('--retry-failed' in a['argv'] for a in retry['actions'])
    maintenance.refresh(root, retry_failed=True, apply=True)
    assert calls == [new, root / loc.path]


def test_suggested_custom_vocabulary_command_replays_the_requested_change(library, tmp_path, capsys):
    from librarytools import maintenance
    from librarytools.library_cli import main
    root, database = library
    maintenance.refresh(root, apply=True)
    vocabulary = tmp_path / 'personal.toml'
    vocabulary.write_text('schema_version=2\n[[tag]]\nname="mine"\ngroup="style"\nname_matches=["kick"]\n')
    report = maintenance.status(root, vocabulary=vocabulary)
    command = next(a['argv'] for a in report['actions'] if a['id'] == 'refresh_tags')
    assert '--vocabulary' in command
    assert main(command[1:] + ['--apply', '--json']) == 0
    capsys.readouterr()
    assert ('style', 'mine') in database.tags_for(database.current_locations()[0].sample_id)


@pytest.mark.parametrize('use_tag_command', [False, True])
def test_recovered_origin_survives_move_to_generic_folder(library, use_tag_command, tmp_path, capsys):
    from librarytools import maintenance, tag_cli
    root, database = library
    loc = database.current_locations()[0]
    packed = root / 'PACKS/House/kick.wav'
    packed.parent.mkdir(parents=True)
    (root / loc.path).rename(packed)
    maintenance.refresh(root, apply=True)
    stored = database.origins()[loc.sample_id]
    assert stored[0] == 'house'
    destination = root / 'CATALOGUE/KICKS/kick.wav'
    destination.parent.mkdir(parents=True)
    packed.rename(destination)
    if use_tag_command:
        assert tag_cli.main(['--root', str(root), '--rescan', '--skip-features', '--apply',
                             '--proposal', str(tmp_path / 'proposal')]) == 0
        capsys.readouterr()
    else:
        assert maintenance.refresh(root, apply=True)['status'] == 'ready'
    assert database.origins()[loc.sample_id] == stored
    assert ('style', 'house') in database.tags_for(loc.sample_id)


def test_concurrent_database_update_cannot_publish_false_ready(library, monkeypatch):
    from librarytools import maintenance, tagstate
    root, database = library
    maintenance.refresh(root, apply=True)
    original = tagstate.output_digest
    def write_between_reads(db):
        database.record_features(database.current_locations()[0].sample_id, '{"tail_ms":1000}')
        return original(db)
    monkeypatch.setattr(tagstate, 'output_digest', write_between_reads)
    report = maintenance.status(root)
    assert report['status'] == 'blocked'
    assert any('changed during inspection' in issue for issue in report['issues'])


def test_explicit_database_cannot_bypass_invalid_onboarding(library):
    from librarytools import maintenance
    root, database = library
    (root / '.eidetic/onboarding.json').write_text(json.dumps({
        'format_version': 1, 'library_id': 'another-library', 'machines': {},
        'captures': {}, 'deferred_machines': [], 'coverage': 'incomplete'}))
    before = snapshot(root)
    assert maintenance.refresh(root, database.path, apply=True)['status'] == 'blocked'
    assert snapshot(root) == before
