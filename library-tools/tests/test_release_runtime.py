"""Release checks use synthetic packages, never the developer's installed release."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

import pytest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / 'scripts/release.py'
RUNTIME = REPO / 'library-tools/src/librarytools/release_runtime.py'
PACKAGES = (
    ('library-tools', 'librarytools', 'librarytools', '0.3.0'),
    ('sample-tools', 'sampletools', 'sampletools', '0.2.0'),
    ('ableton-tools', 'abletontools', 'abletontools', '0.2.0'),
    ('live-tools', 'eideticlive', 'eidetic-live-tools', '0.2.0'),
)


def tree_hashes(path):
    return {file.relative_to(path).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
            for file in sorted(path.rglob('*'))
            if file.is_file() and '__pycache__' not in file.parts
            and file.suffix not in {'.pyc', '.pyo'}
            and not (path.name == 'librarytools'
                     and file.relative_to(path).as_posix() == 'resources/release.json')}


@pytest.fixture
def release(tmp_path):
    checkout = tmp_path / 'checkout'
    installed = tmp_path / 'installed'
    installed.mkdir()
    manifest = {'manifest_version': 1, 'packages': {}}
    for folder, module, distribution, version in PACKAGES:
        source = checkout / folder / 'src' / module
        source.mkdir(parents=True)
        # Optional packages must be inspectable without executing their initializer.
        initializer = f'__version__ = "{version}"\n'
        if module != 'librarytools':
            initializer += 'raise RuntimeError("optional package imported")\n'
        (source / '__init__.py').write_text(initializer)
        (source / 'worker.py').write_text('VALUE = "released"\n')
        (source / 'resources').mkdir()
        (source / 'resources/policy.txt').write_text('release policy\n')
        if module == 'librarytools' and RUNTIME.exists():
            shutil.copyfile(RUNTIME, source / 'release_runtime.py')
        project = f'[project]\nname = "{distribution}"\nversion = "{version}"\n'
        if module == 'librarytools':
            project += '[project.optional-dependencies]\nlive = ["eidetic-live-tools==0.2.0"]\n'
        (checkout / folder / 'pyproject.toml').write_text(project)
        manifest['packages'][distribution] = {
            'module': module, 'path': folder, 'version': version, 'files': tree_hashes(source),
        }
        shutil.copytree(source, installed / module)
        dist_info = installed / f'{distribution.replace("-", "_")}-{version}.dist-info'
        dist_info.mkdir()
        (dist_info / 'METADATA').write_text(f'Metadata-Version: 2.1\nName: {distribution}\nVersion: {version}\n')
    for root in (checkout / 'library-tools/src', installed):
        (root / 'librarytools/resources/release.json').write_text(json.dumps(manifest))
    return checkout, installed


def inspect(release, checkout=False, sources=False):
    selected, installed = release
    paths = ([str(selected / folder / 'src') for folder, *_ in PACKAGES]
             if sources else [str(installed)])
    # Metadata remains available when checkout modules shadow the installed wheel.
    if sources:
        paths.append(str(installed))
    code = ('import json\nfrom pathlib import Path\n'
            'from librarytools.release_runtime import runtime_report\n'
            f'print(json.dumps(runtime_report(checkout={"Path(" + repr(str(selected)) + ")" if checkout else "None"})))\n')
    result = subprocess.run([sys.executable, '-S', '-c', code], cwd=installed.parent,
                            env=dict(os.environ, PYTHONPATH=os.pathsep.join(paths)),
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def release_command(checkout, *args):
    return subprocess.run([sys.executable, str(SCRIPT), *args, '--checkout', str(checkout)],
                          cwd=checkout, capture_output=True, text=True, timeout=30)


def git(checkout, *args):
    result = subprocess.run(['git', '-C', str(checkout), *args], capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def commit_fixture(checkout):
    git(checkout, 'init', '-q')
    git(checkout, 'add', '.')
    git(checkout, '-c', 'user.email=test@example.invalid', '-c', 'user.name=Test',
        'commit', '-qm', 'Fixture release')
    return git(checkout, 'rev-parse', 'HEAD')


def test_verified_bytes_are_ready_and_keep_independent_versions(release):
    report = inspect(release, checkout=True)
    assert report['contract_version'] == 1
    assert report['status'] == 'ready'
    assert report['issues'] == report['actions'] == []
    packages = report['packages']
    assert packages['librarytools']['loaded_version'] == '0.3.0'
    assert packages['sampletools']['loaded_version'] == '0.2.0'
    assert all(package['status'] == 'verified' for package in packages.values())
    assert all(package['checkout_matches'] for package in packages.values())


@pytest.mark.parametrize('change', ['modified', 'missing', 'unexpected'])
def test_modified_installed_bytes_require_install_even_with_unchanged_metadata(release, change):
    _, installed = release
    target = installed / 'librarytools/worker.py'
    if change == 'modified':
        target.write_text('VALUE = "tampered"\n')
    elif change == 'missing':
        target.unlink()
    else:
        (installed / 'librarytools/extra.py').write_text('EXTRA = True\n')
    report = inspect(release)
    assert report['status'] == 'action_required'
    package = report['packages']['librarytools']
    assert package['installed_version'] == package['expected_version'] == '0.3.0'
    field = {'modified': 'changed_files', 'missing': 'missing_files',
             'unexpected': 'unexpected_files'}[change]
    assert package[field] == ['extra.py' if change == 'unexpected' else 'worker.py']
    assert report['actions'][0]['id'] == 'install_release'
    assert report['actions'][0]['argv'][:3] == [sys.executable, '-m', 'pip']


@pytest.mark.parametrize('checkout', [False, True])
def test_install_repair_preserves_dependencies_and_requires_followup_checks(release, checkout):
    selected, installed = release
    (installed / 'librarytools/worker.py').write_text('VALUE = "tampered"\n')
    action = inspect(release, checkout=checkout)['actions'][0]
    target = str(selected / 'library-tools') if checkout else 'librarytools==0.3.0'
    assert action['argv'] == [sys.executable, '-m', 'pip', 'install', '--upgrade',
                              '--force-reinstall', '--no-deps', target]
    assert sys.executable in action['reason']
    assert '-m pip check' in action['reason']
    assert 'status' in action['reason']


def test_optional_packages_missing_are_informational(release):
    _, installed = release
    for _, module, distribution, version in PACKAGES[1:]:
        shutil.rmtree(installed / module)
        shutil.rmtree(installed / f'{distribution.replace("-", "_")}-{version}.dist-info')
    report = inspect(release, checkout=True)
    assert report['status'] == 'ready'
    assert report['actions'] == []
    assert report['packages']['sampletools']['status'] == 'missing_optional'
    assert report['packages']['eidetic-live-tools']['status'] == 'missing_optional'


def test_missing_required_package_identity_blocks_readiness(release):
    _, installed = release
    (installed / 'librarytools/__init__.py').unlink()
    report = inspect(release)
    assert report['status'] == 'blocked'
    assert report['packages']['librarytools']['required'] is True
    assert report['packages']['librarytools']['status'] == 'unverified'


def test_wrong_installed_metadata_requires_install_even_when_bytes_match(release):
    _, installed = release
    (installed / 'librarytools-0.3.0.dist-info/METADATA').write_text(
        'Metadata-Version: 2.1\nName: librarytools\nVersion: 0.2.0\n')
    report = inspect(release)
    assert report['status'] == 'action_required'
    assert report['packages']['librarytools']['changed_files'] == []
    assert report['packages']['librarytools']['installed_version'] == '0.2.0'


def test_installed_optional_package_with_missing_source_requires_repair(release):
    _, installed = release
    shutil.rmtree(installed / 'sampletools')
    report = inspect(release)
    assert report['status'] == 'action_required'
    assert report['packages']['sampletools']['status'] == 'drift'
    assert 'sampletools==0.2.0' in report['actions'][0]['argv']


def test_same_version_checkout_edits_are_detected(release):
    checkout, _ = release
    (checkout / 'library-tools/src/librarytools/worker.py').write_text('VALUE = "new checkout"\n')
    report = inspect(release, checkout=True)
    assert report['status'] == 'action_required'
    assert report['packages']['librarytools']['checkout_matches'] is False
    assert report['packages']['librarytools']['checkout_version'] == '0.3.0'
    assert str(checkout / 'library-tools') in report['actions'][0]['argv']


def test_checkout_documentation_and_bytecode_do_not_require_install(release):
    checkout, installed = release
    (checkout / 'README.md').write_text('New documentation\n')
    for source in (checkout / 'library-tools/src/librarytools', installed / 'librarytools'):
        (source / '__pycache__').mkdir()
        (source / '__pycache__/worker.cpython-312.pyc').write_bytes(b'generated')
    assert inspect(release, checkout=True)['status'] == 'ready'


def test_checkout_source_identity_is_separate_from_old_installed_metadata(release):
    _, installed = release
    (installed / 'librarytools-0.3.0.dist-info/METADATA').write_text(
        'Metadata-Version: 2.1\nName: librarytools\nVersion: 0.2.0\n')
    report = inspect(release, sources=True)
    assert report['status'] == 'ready'
    package = report['packages']['librarytools']
    assert package['installed_version'] == '0.2.0'
    assert package['loaded_version'] == '0.3.0'


@pytest.mark.parametrize('manifest', [None, '{bad json', '{"manifest_version": 999}',
                                      '{"manifest_version": 1, "packages": {}}'])
def test_missing_or_invalid_release_manifest_blocks_readiness(release, manifest):
    _, installed = release
    target = installed / 'librarytools/resources/release.json'
    if manifest is None:
        target.unlink()
    else:
        target.write_text(manifest)
    report = inspect(release)
    assert report['status'] == 'blocked'
    assert report['issues']
    assert report['actions'][0]['id'] == 'install_release'


def test_selected_invalid_checkout_blocks_readiness(release):
    checkout, _ = release
    (checkout / 'sample-tools/pyproject.toml').unlink()
    report = inspect(release, checkout=True)
    assert report['status'] == 'blocked'
    assert any('checkout' in issue.lower() for issue in report['issues'])


def test_malformed_project_identity_produces_blocked_report(release):
    checkout, _ = release
    (checkout / 'library-tools/pyproject.toml').write_text('project = 1\n')
    report = inspect(release, checkout=True)
    assert report['status'] == 'blocked'
    assert report['issues']


def test_prepare_and_check_cover_resources_and_ignore_documentation(release):
    checkout, _ = release
    result = release_command(checkout, 'prepare')
    assert result.returncode == 0, result.stderr
    manifest_path = checkout / 'library-tools/src/librarytools/resources/release.json'
    first = manifest_path.read_bytes()
    assert release_command(checkout, 'prepare').returncode == 0
    assert manifest_path.read_bytes() == first
    (checkout / 'README.md').write_text('Documentation only\n')
    assert release_command(checkout, 'check').returncode == 0
    (checkout / 'sample-tools/src/sampletools/resources/policy.txt').write_text('changed\n')
    result = release_command(checkout, 'check')
    assert result.returncode == 1
    assert 'sampletools' in result.stderr and 'policy.txt' in result.stderr


def test_only_the_bundled_manifest_itself_is_excluded_from_hashes(release):
    checkout, _ = release
    resource = checkout / 'sample-tools/src/sampletools/resources/release.json'
    resource.write_text('{"export_policy": 1}\n')
    assert release_command(checkout, 'prepare').returncode == 0
    resource.write_text('{"export_policy": 2}\n')
    result = release_command(checkout, 'check')
    assert result.returncode == 1
    assert 'sampletools' in result.stderr and 'release.json' in result.stderr


def test_check_rejects_same_version_runtime_change_even_after_preparation(release):
    checkout, _ = release
    base = commit_fixture(checkout)
    (checkout / 'library-tools/src/librarytools/worker.py').write_text('VALUE = "unreleased"\n')
    assert release_command(checkout, 'prepare').returncode == 0
    result = release_command(checkout, 'check', '--base', base)
    assert result.returncode == 1
    assert 'librarytools' in result.stderr and 'version' in result.stderr.lower()
    assert release_command(checkout, 'bump', 'librarytools', 'patch').returncode == 0
    assert release_command(checkout, 'prepare').returncode == 0
    assert release_command(checkout, 'check', '--base', base).returncode == 0


@pytest.mark.parametrize(('old', 'new'), [
    ('dependencies = ["numpy>=2.0"]\n', 'dependencies = ["numpy>=2.1"]\n'),
    ('requires-python = ">=3.12"\n', 'requires-python = ">=3.13"\n'),
    ('[project.optional-dependencies]\nlive = ["eidetic-live-tools==0.2.0"]\n',
     '[project.optional-dependencies]\nlive = ["eidetic-live-tools==0.3.0"]\n'),
    ('[project.scripts]\nsample-export = "sampletools.cli:main"\n',
     '[project.scripts]\nsample-export = "sampletools.cli:new_main"\n'),
    ('[project.gui-scripts]\nsample-browser = "sampletools.ui:main"\n',
     '[project.gui-scripts]\nsample-browser = "sampletools.ui:new_main"\n'),
    ('[project.entry-points."sampletools.plugins"]\nexport = "sampletools.export:build"\n',
     '[project.entry-points."sampletools.plugins"]\nexport = "sampletools.export:new_build"\n'),
], ids=['dependencies', 'python-requirement', 'optional-dependencies', 'scripts',
        'gui-scripts', 'entry-points'])
def test_changed_runtime_project_metadata_requires_its_package_version_bump(release, old, new):
    checkout, _ = release
    project = checkout / 'sample-tools/pyproject.toml'
    original = project.read_text()
    project.write_text(original + old)
    base = commit_fixture(checkout)
    project.write_text(original + new)
    result = release_command(checkout, 'check', '--base', base)
    assert result.returncode == 1
    assert 'sampletools' in result.stderr and 'metadata' in result.stderr and 'version' in result.stderr
    assert release_command(checkout, 'bump', 'sampletools', 'patch').returncode == 0
    assert release_command(checkout, 'prepare').returncode == 0
    result = release_command(checkout, 'check', '--base', base)
    assert result.returncode == 0, result.stderr


def test_descriptive_build_and_test_metadata_need_no_runtime_version_bump(release):
    checkout, _ = release
    project = checkout / 'sample-tools/pyproject.toml'
    original = project.read_text()
    base = commit_fixture(checkout)
    project.write_text(original + 'description = "Updated package description"\n'
                       '[build-system]\nrequires = ["setuptools>=80"]\n'
                       'build-backend = "setuptools.build_meta"\n'
                       '[tool.pytest.ini_options]\naddopts = "-ra"\n')
    result = release_command(checkout, 'check', '--base', base)
    assert result.returncode == 0, result.stderr


def test_doc_only_change_needs_no_version_increment(release):
    checkout, _ = release
    base = commit_fixture(checkout)
    (checkout / 'README.md').write_text('New instructions\n')
    assert release_command(checkout, 'prepare').returncode == 0
    result = release_command(checkout, 'check', '--base', base)
    assert result.returncode == 0, result.stderr


def test_bump_preserves_independent_versions_and_updates_internal_pins(release):
    checkout, _ = release
    initializer = checkout / 'live-tools/src/eideticlive/__init__.py'
    initializer.write_text('__version__ = "0.2.0"\n')
    result = release_command(checkout, 'bump', 'eidetic-live-tools', 'minor')
    assert result.returncode == 0, result.stderr
    import tomllib
    live = tomllib.loads((checkout / 'live-tools/pyproject.toml').read_text())
    library = tomllib.loads((checkout / 'library-tools/pyproject.toml').read_text())
    sample = tomllib.loads((checkout / 'sample-tools/pyproject.toml').read_text())
    assert live['project']['version'] == '0.3.0'
    assert library['project']['version'] == '0.3.0'
    assert sample['project']['version'] == '0.2.0'
    assert library['project']['optional-dependencies']['live'] == ['eidetic-live-tools==0.3.0']
    assert runpy.run_path(str(initializer))['__version__'] == '0.3.0'


def test_bump_does_not_rewrite_similarly_named_external_dependencies(release):
    checkout, _ = release
    project = checkout / 'library-tools/pyproject.toml'
    project.write_text(project.read_text().replace(
        'live = ["eidetic-live-tools==0.2.0"]',
        'live = ["eidetic-live-tools==0.2.0", "other-eidetic-live-tools==0.2.0"]'))
    result = release_command(checkout, 'bump', 'eidetic-live-tools', 'patch')
    assert result.returncode == 0, result.stderr
    import tomllib
    dependencies = tomllib.loads(project.read_text())['project']['optional-dependencies']['live']
    assert dependencies == ['eidetic-live-tools==0.2.1', 'other-eidetic-live-tools==0.2.0']


def test_prepare_refuses_mismatched_declared_and_project_versions(release):
    checkout, _ = release
    (checkout / 'library-tools/src/librarytools/__init__.py').write_text('__version__ = "0.2.0"\n')
    result = release_command(checkout, 'prepare')
    assert result.returncode == 2
    assert 'version' in result.stderr


@pytest.mark.parametrize('version', ['0.2.0', '0.3.0', 'banana', '00.4.0'])
def test_invalid_version_bump_leaves_repository_unchanged(release, version):
    checkout, _ = release
    before = {path: path.read_bytes() for path in checkout.rglob('*') if path.is_file()}
    result = release_command(checkout, 'bump', 'librarytools', version)
    assert result.returncode == 2
    assert all(path.read_bytes() == content for path, content in before.items())
