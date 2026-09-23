"""Prepare and verify deterministic release manifests; bump independent versions.

This script changes repository metadata only when explicitly asked to prepare or
bump. It does not build, install, publish, access a library or fetch remote refs.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tomllib


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'library-tools/src'))
from librarytools.release_runtime import (  # noqa: E402
    MANIFEST_PATH, PACKAGE_LAYOUT, _checkout_packages, _differences, _included_file,
    _read_manifest, _version_tuple,
)


def _runtime_project_metadata(project: dict) -> dict:
    """Installation requirements and callable interfaces shipped in the wheel."""
    fields = ('requires-python', 'dependencies', 'optional-dependencies',
              'scripts', 'gui-scripts', 'entry-points')
    return {field: project[field] for field in fields if field in project}


def _git(checkout: Path, *arguments: str) -> bytes:
    result = subprocess.run(['git', '-C', str(checkout), *arguments], capture_output=True)
    if result.returncode:
        raise ValueError(result.stderr.decode(errors='replace').strip())
    return result.stdout


def _base_packages(checkout: Path, reference: str) -> dict:
    revision = _git(checkout, 'rev-parse', '--verify', f'{reference}^{{commit}}').decode().strip()
    # Read the tracked baseline directly; no checkout, extraction or network access.
    archive = _git(checkout, 'archive', '--format=tar', revision,
                   *(folder for folder, _, _ in PACKAGE_LAYOUT))
    packages = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:') as tree:
        members = {member.name: member for member in tree.getmembers() if member.isfile()}
        for folder, module, distribution in PACKAGE_LAYOUT:
            project_name = f'{folder}/pyproject.toml'
            if project_name not in members:
                continue
            project = tomllib.loads(tree.extractfile(members[project_name]).read().decode())['project']
            _version_tuple(project['version'])
            prefix = f'{folder}/src/{module}/'
            files = {name[len(prefix):]: hashlib.sha256(tree.extractfile(member).read()).hexdigest()
                     for name, member in members.items()
                     if name.startswith(prefix) and _included_file(name[len(prefix):], module)}
            packages[distribution] = {'version': project['version'], 'files': files,
                                      'runtime_metadata': _runtime_project_metadata(project)}
    return packages


def prepare(checkout: Path) -> None:
    manifest = {'manifest_version': 1, 'packages': _checkout_packages(checkout)}
    destination = checkout / MANIFEST_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(f'Prepared {destination}')


def check(checkout: Path, base: str | None = None) -> list[str]:
    manifest = _read_manifest(checkout / MANIFEST_PATH)
    actual = _checkout_packages(checkout)
    issues = []
    for distribution, package in actual.items():
        expected = manifest['packages'][distribution]
        if expected['version'] != package['version']:
            issues.append(f'{distribution}: manifest version differs from pyproject.toml')
        for kind, files in _differences(expected['files'], package['files']).items():
            if files:
                issues.append(f'{distribution}: {kind}: {", ".join(files)}')
    if base:
        for distribution, previous in _base_packages(checkout, base).items():
            current = actual[distribution]
            project_path = checkout / current['path'] / 'pyproject.toml'
            project = tomllib.loads(project_path.read_text(encoding='utf-8'))['project']
            metadata_changed = _runtime_project_metadata(project) != previous['runtime_metadata']
            old_version = _version_tuple(previous['version'])
            new_version = _version_tuple(current['version'])
            if new_version < old_version:
                issues.append(f'{distribution}: version decreased from {previous["version"]}')
            elif new_version == old_version:
                if current['files'] != previous['files']:
                    issues.append(f'{distribution}: runtime changed without a version increase from {previous["version"]}')
                if metadata_changed:
                    issues.append(f'{distribution}: runtime project metadata changed without a version increase from {previous["version"]}')
    return issues


def bump(checkout: Path, name: str, increment: str) -> None:
    packages = _checkout_packages(checkout)
    selected = next((row for row in PACKAGE_LAYOUT if name in row), None)
    if selected is None:
        raise ValueError(f'unknown package: {name}')
    folder, module, distribution = selected
    old = packages[distribution]['version']
    version = list(_version_tuple(old))
    if increment in {'major', 'minor', 'patch'}:
        index = {'major': 0, 'minor': 1, 'patch': 2}[increment]
        version[index] += 1
        version[index + 1:] = [0] * (2 - index)
        new = '.'.join(map(str, version))
    else:
        new = increment
    if _version_tuple(new) <= _version_tuple(old):
        raise ValueError(f'new version must be greater than {old}')
    edits = {}
    for package_folder, _, _ in PACKAGE_LAYOUT:
        path = checkout / package_folder / 'pyproject.toml'
        text = path.read_text(encoding='utf-8')
        if package_folder == folder:
            section = re.search(r'(?ms)^\[project\][^\n]*\n.*?(?=^\[|\Z)', text)
            replacement, count = re.subn(r'(?m)^(version\s*=\s*)([\'\"])[^\'\"]+\2',
                                         lambda match: f'{match[1]}{match[2]}{new}{match[2]}',
                                         section[0], count=1)
            if count != 1:
                raise ValueError(f'cannot update project version in {path}')
            text = text[:section.start()] + replacement + text[section.end():]
        pin = (rf'(?<![0-9A-Za-z_.-])({re.escape(distribution)}(?:\[[^\]]+\])?\s*==\s*)'
               rf'{re.escape(old)}(?![0-9A-Za-z.+-])')
        text = re.sub(pin, lambda match: match[1] + new, text)
        if text != path.read_text(encoding='utf-8'):
            edits[path] = text
    initializer = checkout / folder / 'src' / module / '__init__.py'
    original = initializer.read_text(encoding='utf-8')
    updated = re.sub(r'(?m)^(__version__\s*=\s*)([\'\"])[^\'\"]+\2',
                     lambda match: f'{match[1]}{match[2]}{new}{match[2]}', original)
    if updated != original:
        edits[initializer] = updated
    for path, text in edits.items():
        path.write_text(text, encoding='utf-8')
    print(f'{distribution}: {old} -> {new}; run prepare after all runtime edits')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'check', 'bump'):
        command = commands.add_parser(name)
        command.add_argument('--checkout', type=Path, default=REPO)
        if name == 'check':
            command.add_argument('--base', help='local Git ref to enforce per-package version increases')
        elif name == 'bump':
            command.add_argument('package', help='distribution, import name or package directory')
            command.add_argument('increment', help='major, minor, patch or explicit MAJOR.MINOR.PATCH')
    arguments = parser.parse_args(argv)
    checkout = arguments.checkout.expanduser().resolve()
    try:
        if arguments.command == 'prepare':
            prepare(checkout)
        elif arguments.command == 'bump':
            bump(checkout, arguments.package, arguments.increment)
        else:
            issues = check(checkout, arguments.base)
            if issues:
                print('\n'.join(issues), file=sys.stderr)
                return 1
            print('Release manifest and versions verified')
    except (OSError, ValueError, TypeError, KeyError, SyntaxError, tarfile.TarError) as error:
        print(f'Release check failed: {error}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
