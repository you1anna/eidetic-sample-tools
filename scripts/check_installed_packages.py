"""Exercise built wheels in a fresh environment, using generated audio only.

Run with all three wheels installed and FFmpeg/FFprobe on PATH. This deliberately
rejects editable source installs: packaging and bundled resources are the boundary
being checked. All library state and exports are created in a temporary directory.
"""
from __future__ import annotations

import contextlib
import hashlib
from importlib import import_module, metadata
import io
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


def main():
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
        scratch = Path(directory)
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
        setup = ['onboard', '--root', str(root), '--machine', 'first', '--defer-machine', 'second']
        invoke(library_main, setup)
        assert not (root / '.eidetic').exists()
        invoke(library_main, [*setup, '--apply'])
        invoke(tag_cli.main, ['--root', str(root), '--rescan', '--skip-features', '--apply'])

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

        remounted = scratch / 'second-mount'
        root.rename(remounted)
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
    print('Installed-package checks passed: commands, resources, onboarding, approval, export, handoff and restore.')


if __name__ == '__main__':
    main()
