"""The optional scale benchmark must exercise the planner without a real library."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/benchmark_collection_planner.py'


def run_benchmark(tmp_path, *arguments):
    environment = dict(os.environ)
    environment.pop('PYTHONPATH', None)
    return subprocess.run([sys.executable, str(SCRIPT), *arguments], cwd=tmp_path,
                          env=environment, capture_output=True, text=True, timeout=30)


def test_small_benchmark_checks_history_shortages_and_offline_pins(tmp_path):
    result = run_benchmark(tmp_path, '--identities', '24', '--count', '30',
                           '--history', '6', '--pins', '3', '--repeats', '2')
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['config'] == {'identities': 24, 'count': 30, 'history': 6,
                                'pins': 3, 'repeats': 2, 'seed': 1729}
    assert report['summary']['selected'] == 18
    assert report['summary']['shortage'] == 12
    assert report['summary']['excluded_previous'] == 6
    assert report['summary']['known_repeats'] == 0
    assert report['checks']['offline_regeneration'] is True
    assert report['checks']['retained_pins'] == 3
    assert report['checks']['parent_lineage_preserved'] is True
    assert report['checks']['all_unreviewed'] is True
    assert report['checks']['parent_and_database_unchanged'] is True
    assert report['checks']['exact_alias_deduplicated'] is True
    assert report['checks']['same_seed_reproduced'] is True
    assert report['sizes_bytes']['plan_json'] > 0
    assert report['sizes_bytes']['review_markdown'] > 0
    assert set(report['median_seconds']) == {
        'create_plan', 'validate_plan', 'write_plan', 'read_plan',
        'regenerate_plan_offline', 'write_regenerated', 'read_regenerated'}
    assert all(value >= 0 for value in report['median_seconds'].values())
    assert report['fixture']['locations'] == 25
    assert report['fixture']['audio_files_created'] == 0
    assert report['environment']['python']
    assert report['environment']['platform']
    assert 'metadata' in report['scope'].lower()
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('arguments', [
    ('--identities', '0'), ('--count', '0'), ('--repeats', '11'),
    ('--identities', '10', '--history', '10'),
    ('--identities', '10', '--history', '3', '--count', '4', '--pins', '5'),
])
def test_invalid_benchmark_sizes_fail_before_work(tmp_path, arguments):
    result = run_benchmark(tmp_path, *arguments)
    assert result.returncode == 2
    assert 'error:' in result.stderr
    assert result.stdout == ''
    assert not list(tmp_path.iterdir())
