"""Find a local Python 3.12 test environment and verify the current checkout.

This helper never installs packages, downloads models or reads a sample library.
Use --python or EIDETIC_PYTHON to choose an environment explicitly.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


REPO = Path(__file__).resolve().parents[1]
PACKAGES = ('library-tools', 'sample-tools', 'ableton-tools')
SOURCES = [str(REPO / package / 'src') for package in PACKAGES]
PROBE = '''
import importlib.util, json, platform, sys
sys.path[:0] = json.loads(sys.argv[1])
names = ('pytest', 'numpy', 'soundfile', 'flask')
packages = ('librarytools', 'sampletools', 'abletontools')
print(json.dumps({
    'version': platform.python_version(),
    'virtualenv': sys.prefix != sys.base_prefix,
    'dependencies': {name: importlib.util.find_spec(name) is not None for name in names},
    'sources': {name: importlib.util.find_spec(name).origin for name in packages},
}))
'''


def clean_environment():
    environment = dict(os.environ)
    environment.pop('PYTHONHOME', None)
    environment['PYTHONPATH'] = os.pathsep.join(SOURCES)
    environment['PYTHONNOUSERSITE'] = '1'
    return environment


def probe(python):
    if not python.strip():
        raise ValueError('interpreter must not be empty')
    # Do not resolve symlinks: doing so bypasses the virtualenv's pyvenv.cfg.
    python = str(Path(shutil.which(python) or python).expanduser().absolute())
    try:
        result = subprocess.run([python, '-I', '-c', PROBE, json.dumps(SOURCES)],
                                cwd=REPO, env=clean_environment(), text=True,
                                capture_output=True, timeout=10)
        if result.returncode:
            raise ValueError(result.stderr.strip() or 'interpreter probe failed')
        report = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        raise ValueError(f'{python}: {error}') from error
    if not report['virtualenv']:
        raise ValueError(f'{python}: use a virtual environment, not global Python')
    if not report['version'].startswith('3.12.'):
        raise ValueError(f'{python}: Python 3.12 is required for the pinned test environment')
    missing = [name for name, found in report['dependencies'].items() if not found]
    if missing:
        raise ValueError(f'{python}: missing test dependencies: {", ".join(missing)}')
    expected = {name: str(Path(path) / name / '__init__.py') for path, name in
                zip(SOURCES, ('librarytools', 'sampletools', 'abletontools'))}
    if report['sources'] != expected:
        raise ValueError(f'{python}: source imports do not point to this checkout')
    return dict(report, python=python, repository=str(REPO))


def discover(explicit=None):
    override = explicit if explicit is not None else os.environ.get('EIDETIC_PYTHON')
    if override is not None:
        return probe(override)  # Explicit failures must not select another environment.
    candidates = []
    if sys.prefix != sys.base_prefix:
        candidates.append(sys.executable)
    if os.environ.get('VIRTUAL_ENV'):
        candidates.append(str(Path(os.environ['VIRTUAL_ENV']) / 'bin/python'))
    candidates.extend(str(Path.home() / '.venvs' / name / 'bin/python') for name in
                      ('eidetic-sample-tools-dev', 'eidetic-ai', 'library-tools'))
    failures = []
    for candidate in dict.fromkeys(candidates):
        try:
            return probe(candidate)
        except ValueError as error:
            failures.append(str(error))
    raise ValueError('No ready test environment found. See docs/DEVELOPMENT.md.\n' + '\n'.join(failures))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', help='explicit virtualenv interpreter; never silently falls back')
    commands = parser.add_subparsers(dest='command', required=True)
    doctor = commands.add_parser('doctor', help='report interpreter, dependency availability and source imports')
    doctor.add_argument('--json', action='store_true')
    tests = commands.add_parser('test', help='run pytest against this checkout')
    tests.add_argument('pytest_args', nargs=argparse.REMAINDER, help='arguments after -- replace the default full suite')
    benchmark = commands.add_parser('benchmark', help='measure synthetic collection planning; no audio or AI')
    benchmark.add_argument('benchmark_args', nargs=argparse.REMAINDER, help='benchmark options after --')
    args = parser.parse_args(argv)
    try:
        report = discover(args.python)
        report['tools'] = {name: shutil.which(name) for name in ('ffmpeg', 'ffprobe')}
        missing = [name for name, path in report['tools'].items() if path is None]
        if missing:
            raise ValueError('Missing system tools: ' + ', '.join(missing))
    except ValueError as error:
        print(f'dev-check: {error}', file=sys.stderr)
        return 2
    if args.command == 'doctor':
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(f"Python {report['version']}: {report['python']}")
            print(f'Source imports: {REPO} (all three packages)')
            print('Available: pytest, numpy, soundfile, flask, ffmpeg, ffprobe')
        return 0
    arguments = args.pytest_args if args.command == 'test' else args.benchmark_args
    if arguments[:1] == ['--']:
        arguments = arguments[1:]
    if args.command == 'test':
        arguments = ['-m', 'pytest', *(arguments or [*PACKAGES, '-q', '-rs'])]
        print(f"Testing checkout with {report['python']}", flush=True)
    else:
        arguments = [str(REPO / 'scripts/benchmark_collection_planner.py'), *arguments]
        print(f"Benchmarking checkout with {report['python']}", file=sys.stderr, flush=True)
    try:
        return subprocess.run([report['python'], *arguments],
                              cwd=REPO, env=clean_environment()).returncode
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
