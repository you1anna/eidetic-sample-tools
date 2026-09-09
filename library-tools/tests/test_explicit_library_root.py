"""Fresh CLI processes must never infer a machine-specific library."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('module,function,arguments,setting', [
    *[(f'librarytools.{name}', 'main', [], 'SAMPLES_ROOT') for name in
      ('review', 'sort', 'dedupe', 'intake', 'classify', 'analyze', 'find_cli', 'tag_cli', 'neardupe')],
    ('librarytools.library_cli', 'main', ['doctor'], 'SAMPLES_ROOT'),
    ('librarytools.curate_cli', 'main', ['check'], 'SAMPLES_ROOT'),
    ('librarytools.benchmark_cli', 'main', ['prepare', '--output-dir', 'out'], 'SAMPLES_ROOT'),
    ('librarytools.rolecleanup_cli', 'main', ['prepare', '--audit', 'audit', '--output-dir', 'out'], 'SAMPLES_ROOT'),
    ('sampletools.cli', 'main', ['digitakt', '--dry-run'], 'SAMPLES_ROOT'),
    ('abletontools.cli', 'index_main', ['--out', 'out'], 'ALS_ROOTS'),
    ('abletontools.cli', 'samples_main', ['--out', 'out'], 'ALS_ROOTS'),
])
def test_unconfigured_commands_fail_clearly_without_writes(tmp_path, module, function, arguments, setting):
    if module.startswith(('sampletools', 'abletontools')):
        pytest.importorskip(module.split('.')[0])
    environment = os.environ.copy()
    environment.pop('SAMPLES_ROOT', None)
    environment.pop('ALS_ROOTS', None)
    program = f'import sys; from {module} import {function}; raise SystemExit({function}(sys.argv[1:]))'
    result = subprocess.run([sys.executable, '-c', program, *arguments], cwd=tmp_path,
                            env=environment, text=True, capture_output=True, timeout=15)
    assert result.returncode == 2
    assert setting in result.stderr and '--root' in result.stderr
    assert 'Traceback' not in result.stderr
    assert list(tmp_path.iterdir()) == []


def test_review_explicit_root_overrides_environment(tmp_path):
    from librarytools.review import main
    root = tmp_path / 'selected'
    root.mkdir()
    assert main(['--root', str(root), '--no-probe', '--summary']) == 0
