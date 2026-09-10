"""Run the developer helper as a user would, including from outside the checkout."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / 'scripts/dev_check.py'


def run(*args, cwd, env=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                          env=env, text=True, capture_output=True, timeout=30)


def test_doctor_preserves_explicit_venv_and_uses_checkout_imports(tmp_path):
    shadow = tmp_path / 'shadow'
    shadow.mkdir()
    (shadow / 'librarytools.py').write_text('raise RuntimeError("wrong checkout")\n')
    env = dict(os.environ, PYTHONPATH=str(shadow), EIDETIC_PYTHON='/missing/python')
    result = run('--python', sys.executable, 'doctor', '--json', cwd=tmp_path, env=env)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['python'] == str(Path(sys.executable).absolute())
    assert report['virtualenv'] is True
    assert report['version'].startswith('3.12.')
    for package, folder in [('librarytools', 'library-tools'), ('sampletools', 'sample-tools'),
                            ('abletontools', 'ableton-tools')]:
        assert Path(report['sources'][package]) == REPO / folder / 'src' / package / '__init__.py'


def test_explicit_missing_interpreter_does_not_silently_fallback(tmp_path):
    result = run('--python', str(tmp_path / 'missing'), 'doctor', cwd=tmp_path)
    assert result.returncode == 2
    assert 'missing' in result.stderr


def test_environment_override_is_explicit_not_a_fallback_hint(tmp_path):
    env = dict(os.environ, EIDETIC_PYTHON=str(tmp_path / 'missing-override'))
    result = run('doctor', cwd=tmp_path, env=env)
    assert result.returncode == 2
    assert 'missing-override' in result.stderr


def test_global_interpreter_is_rejected(tmp_path):
    result = run('--python', sys._base_executable, 'doctor', cwd=tmp_path)
    assert result.returncode == 2
    assert 'virtual environment' in result.stderr


@pytest.mark.parametrize('value', ['', '   '])
def test_empty_explicit_interpreter_is_rejected_without_fallback(tmp_path, value):
    result = run('--python', value, 'doctor', cwd=tmp_path)
    assert result.returncode == 2
    assert 'empty' in result.stderr


def test_empty_environment_override_is_rejected_without_fallback(tmp_path):
    env = dict(os.environ, EIDETIC_PYTHON='')
    result = run('doctor', cwd=tmp_path, env=env)
    assert result.returncode == 2
    assert 'empty' in result.stderr


def test_test_command_runs_selected_test_against_checkout(tmp_path):
    test = tmp_path / 'test_source.py'
    expected = str(REPO / 'library-tools/src/librarytools/__init__.py')
    test.write_text('from pathlib import Path\nimport librarytools\n'
                    'def test_source():\n'
                    f'    assert str(Path(librarytools.__file__).resolve()) == {expected!r}\n')
    result = run('--python', sys.executable, 'test', '--', str(test), '-q', cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '1 passed' in result.stdout


def test_test_command_preserves_pytest_failure_exit(tmp_path):
    test = tmp_path / 'test_failure.py'
    test.write_text('def test_failure():\n    assert False, "intentional helper check"\n')
    result = run('--python', sys.executable, 'test', '--', str(test), '-q', cwd=tmp_path)
    assert result.returncode == 1
    assert 'intentional helper check' in result.stdout


def test_benchmark_command_reuses_environment_and_emits_json(tmp_path):
    result = run('--python', sys.executable, 'benchmark', '--', '--identities', '12',
                 '--count', '4', '--history', '3', '--pins', '2', '--repeats', '1', cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['summary']['selected'] == 4
    assert report['summary']['excluded_previous'] == 3
    assert report['checks']['retained_pins'] == 2
