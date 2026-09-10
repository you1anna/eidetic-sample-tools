"""Exercise built wheels in a fresh environment, using generated audio only.

Run with all three wheels installed and FFmpeg/FFprobe on PATH. This deliberately
rejects editable source installs: packaging and bundled resources are the boundary
being checked. All library state and exports are created in a temporary directory.
"""
from __future__ import annotations

import contextlib
import argparse
import hashlib
from importlib import import_module, metadata
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import wave


def invoke(function, arguments, expected=0):
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        result = function(arguments)
    if result != expected:
        raise AssertionError(f'{arguments}: expected exit {expected}, got {result}\n{output.getvalue()}')


def collection_command(*arguments):
    """Run the installed console script, rather than importing its Python main."""
    executable = Path(sys.executable).parent / 'sample-collection'
    result = subprocess.run([str(executable), *map(str, arguments), '--json'],
                            capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(f'sample-collection {arguments}: exit {result.returncode}\n{result.stderr}')
    return json.loads(result.stdout)


def check_collection(root: Path, scratch: Path, source: Path):
    """Check alias identity and explicit export history through the installed CLI."""
    before = (root / '.eidetic/library.sqlite').read_bytes()
    source_id = hashlib.sha256(source.read_bytes()).hexdigest()
    first = collection_command('plan', '--root', root, '--device', 'octatrack',
                               '--count', 3, '--freshness', 'allow', '--output-dir', scratch / 'collection-all')
    plan = collection_command('show', first['plan_path'])
    assert first['summary']['selected'] == 2 and first['summary']['shortage'] == 1
    assert len({row['sample_id'] for row in plan['selected']}) == 2
    original = next(row for row in plan['snapshot']['candidates'] if row['sample_id'] == source_id)
    assert {alias['path'] for alias in original['aliases']} == {'CATALOGUE/kick.wav', 'CURATED/KICK/kick.wav'}
    assert all(row['decision'] == 'unreviewed' for row in plan['selected'])
    receipts = list((root / '_EXPORT').rglob('*.wav.receipt.json'))
    assert len(receipts) == 1
    fresh = collection_command('plan', '--root', root, '--device', 'octatrack', '--count', 2,
                               '--freshness', 'exclude', '--history', receipts[0],
                               '--output-dir', scratch / 'collection-fresh')
    plan = collection_command('show', fresh['plan_path'])
    assert fresh['summary']['selected'] == 1 and fresh['summary']['shortage'] == 1
    assert fresh['summary']['excluded_previous'] == 1 and fresh['summary']['known_repeats'] == 0
    assert plan['history']['sample_ids'] == [source_id]
    assert plan['history']['coverage'] == 'provided_records_only'
    assert plan['selected'][0]['sample_id'] != source_id
    assert plan['selected'][0]['decision'] == 'unreviewed'
    assert (root / '.eidetic/library.sqlite').read_bytes() == before
    parent_files = {Path(fresh[key]): Path(fresh[key]).read_bytes() for key in ('plan_path', 'review_path')}
    return plan, parent_files, receipts[0]


def check_collection_offline(parent: dict, parent_files: dict, old_receipt: Path,
                             old_root: Path, remounted: Path, scratch: Path):
    """Saved population/history and a retained pin survive losing original paths."""
    assert not old_root.exists() and not old_receipt.exists()
    before = (remounted / '.eidetic/library.sqlite').read_bytes()
    plan_path = next(path for path in parent_files if path.name == 'plan.json')
    pin = parent['selected'][0]['sample_id']
    revised = collection_command('regenerate', '--from-plan', plan_path, '--seed', 99,
                                 '--pin', pin, '--output-dir', scratch / 'collection-next')
    plan = collection_command('show', revised['plan_path'])
    assert plan['parent_plan_id'] == parent['plan_id'] and plan['pins'] == [pin]
    assert plan['snapshot'] == parent['snapshot'] and plan['history'] == parent['history']
    assert plan['selected'][0]['sample_id'] == pin and plan['selected'][0]['decision'] == 'unreviewed'
    assert all(path.read_bytes() == original for path, original in parent_files.items())
    assert (remounted / '.eidetic/library.sqlite').read_bytes() == before


def check_audition(root: Path, scratch: Path, source: Path):
    """Exercise installed chooser assets and the exact-source curation handoff."""
    from librarytools.vibe_cli import main as audition_main
    from librarytools.vibe_server import create_vibe_app
    from librarytools.curate import read_labels, validate_labels

    session = scratch / 'audition'
    invoke(audition_main, ['prepare', '--root', str(root), '--anchor', str(source),
                          '--vocal', str(source), '--output-dir', str(session)])
    client = create_vibe_app(session, write_token='wheel-test').test_client()
    assert b'Sample audition' in client.get('/').data
    for asset in ('audition.js', 'audition.css', 'vibe.js', 'vibe.css', 'tokens.css'):
        assert client.get(f'/static/{asset}').status_code == 200
    sources = client.get('/api/sources').get_json()['sources']
    assert len(sources) == 1  # The same original in both groups is one choice.
    sample_id = hashlib.sha256(source.read_bytes()).hexdigest()
    assert sources[0]['id'] == sample_id
    choice = {'source_id': sample_id, 'decision': 'keep'}
    assert client.post('/api/shortlist', json=choice).status_code == 403
    assert client.post('/api/shortlist', json=choice,
                       headers={'X-Vibe-Token': 'wheel-test'}).status_code == 200
    playlist = client.get('/api/shortlist/playlist')
    assert playlist.status_code == 200
    assert playlist.text.splitlines()[1:] == [str(source.resolve())]
    packet = scratch / 'audition-packet'
    invoke(audition_main, ['packet', '--session-dir', str(session), '--output-dir', str(packet)])
    rows = read_labels(packet / 'labels.tsv')
    validate_labels(rows)
    assert len(rows) == 1 and rows[0].sample_id == sample_id
    assert rows[0].decision == 'keep' and not rows[0].true_role and not rows[0].descriptor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core-only', action='store_true', help='verify the base install without optional browser review')
    args = parser.parse_args()
    installed = Path(sysconfig.get_path('purelib')).resolve()
    for name in ('librarytools', 'sampletools', 'abletontools'):
        package = import_module(name)
        if not Path(package.__file__).resolve().is_relative_to(installed):
            raise AssertionError(f'{name} must be installed from a wheel, not an editable checkout')
        distribution = metadata.distribution(name)
        if hasattr(package, '__version__'):
            assert package.__version__ == distribution.version
        commands = [entry for entry in distribution.entry_points if entry.group == 'console_scripts']
        assert commands, f'{name} did not install its commands'
        if name == 'librarytools':
            assert any(entry.name == 'sample-collection' for entry in commands), 'librarytools wheel omitted sample-collection'
        for entry in commands:
            subprocess.run([str(Path(sys.executable).parent / entry.name), '--help'],
                           check=True, stdout=subprocess.DEVNULL)
    assert shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg and FFprobe are required'

    from librarytools import find_cli, profiles, tag_cli, tagging
    from librarytools.inventory import LibraryDatabase
    from librarytools.library_cli import main as library_main
    from librarytools.lifecycle import backup_bundle, restore_bundle
    from sampletools.cli import main as export_main
    from sampletools.config import manifest_path

    resources = Path(profiles.__file__).parent / 'resources'
    assert profiles.resolve_profile('eidetic-studio', profile_root=resources / 'profiles').devices
    assert tagging.load_vocabulary(resources / 'vocabulary.toml')
    assert manifest_path('octatrack').is_file()

    with tempfile.TemporaryDirectory(prefix='eidetic-wheel-check-') as directory:
        scratch = Path(directory).resolve()
        root = scratch / 'first-mount'
        source = root / 'CATALOGUE/kick.wav'
        source.parent.mkdir(parents=True)
        with wave.open(str(source), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(44100)
            audio.writeframes(b'\x01\x00' * 4410)
        curated = root / 'CURATED/KICK/kick.wav'
        curated.parent.mkdir(parents=True)
        curated.write_bytes(source.read_bytes())
        with wave.open(str(root / 'CATALOGUE/clap.wav'), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(44100)
            audio.writeframes(b'\x02\x00' * 4410)
        setup = ['onboard', '--root', str(root), '--machine', 'first', '--defer-machine', 'second']
        invoke(library_main, setup)
        assert not (root / '.eidetic').exists()
        invoke(library_main, [*setup, '--apply'])
        invoke(tag_cli.main, ['--root', str(root), '--rescan', '--skip-features', '--apply'])
        if not args.core_only:
            check_audition(root, scratch, source)

        unverified = scratch / 'unverified.tsv'
        invoke(find_cli.main, ['--root', str(root), '--curated-only', '--crate', str(unverified)])
        invoke(export_main, ['octatrack', '--root', str(root), '--profile', 'eidetic-studio',
                             '--crate', str(unverified), '--dry-run'], expected=2)
        assert not (root / '_EXPORT').exists()

        # Seed explicit synthetic decisions for the already-copied test fixture.
        sample_id = hashlib.sha256(source.read_bytes()).hexdigest()
        database = LibraryDatabase(root / '.eidetic/library.sqlite')
        database.record_review(sample_id, 'wheel-check', 'favourite', 'KICK', 'punch', 'synthetic fixture')
        database.record_promotion(sample_id, Path('CURATED/KICK/kick.wav'), Path('CATALOGUE/kick.wav'), 'wheel-check')
        crate = scratch / 'approved.tsv'
        invoke(find_cli.main, ['--root', str(root), '--curated-only', '--crate', str(crate)])
        export = ['octatrack', '--profile', 'eidetic-studio', '--crate', str(crate)]
        invoke(export_main, [*export, '--root', str(root), '--dry-run'])
        invoke(export_main, [*export, '--root', str(root)])
        assert len(list((root / '_EXPORT').rglob('*.wav'))) == 1
        collection, parent_files, receipt = check_collection(root, scratch, source)

        remounted = scratch / 'second-mount'
        root.rename(remounted)
        check_collection_offline(collection, parent_files, receipt, root, remounted, scratch)
        before = (remounted / '.eidetic/library.sqlite').read_bytes()
        evidence = scratch / 'older-listening-files'
        evidence.mkdir()
        (evidence / 'labels.tsv').write_text('older offline decisions\n', encoding='utf-8')
        setup = ['onboard', '--root', str(remounted), '--machine', 'second', '--include', str(evidence), '--apply']
        invoke(library_main, setup)
        invoke(library_main, setup)
        assert (remounted / '.eidetic/library.sqlite').read_bytes() == before
        assert len(list((remounted / '.eidetic/history').rglob('labels.tsv'))) == 1
        staged = next((remounted / '_EXPORT').rglob('*.wav'))
        output_before = staged.read_bytes(), staged.stat().st_mtime_ns
        invoke(export_main, [*export, '--root', str(remounted)])
        assert (staged.read_bytes(), staged.stat().st_mtime_ns) == output_before
        invoke(library_main, ['doctor', '--root', str(remounted), '--json'], expected=1)
        backup_bundle(remounted / '.eidetic/library.sqlite', scratch / 'backup', root=remounted)
        restore_bundle(scratch / 'backup', scratch / 'restored')
        assert next((scratch / 'restored').rglob('labels.tsv')).read_bytes() == (evidence / 'labels.tsv').read_bytes()
    checks = 'commands, resources, onboarding, approval, export, collection planning, offline regeneration, handoff and restore'
    if not args.core_only:
        checks += ', audition'
    print(f'Installed-package checks passed: {checks}.')


if __name__ == '__main__':
    main()
