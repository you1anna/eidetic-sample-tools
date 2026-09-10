"""Exercise collection planning through the public command boundary."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest

from librarytools.collection_cli import main
from librarytools.inventory import LibraryDatabase, scan_library


@pytest.fixture
def library(tmp_path):
    root = tmp_path / 'samples'
    paths = []
    for number in range(10):
        path = root / 'PACKS' / 'tribal' / f'perc-{number}.wav'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f'cli source {number}'.encode())
        paths.append(path)
    database = LibraryDatabase(root / '.eidetic' / 'library.sqlite')
    database.bind_root(root)
    scan_library(root, database)
    ids = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    history = tmp_path / 'history.json'
    history.write_text(json.dumps({
        'schema': 'eidetic-delegated-library-v1',
        'items': [{'sample_id': sid, 'device': 'octatrack', 'output_sha256': 'f' * 64}
                  for sid in ids[:2]],
    }))
    return root, history, ids


def plan_args(library, output, *extra):
    root, history, _ = library
    return ['plan', 'perc', '--root', str(root), '--device', 'octatrack',
            '--count', '12', '--freshness', 'exclude', '--history', str(history),
            '--brief', 'hypnotic tribal', '--output-dir', str(output), *extra]


def test_plan_json_summary_and_saved_unreviewed_candidates(library, tmp_path, capsys):
    output = tmp_path / 'first'
    before = {p: p.read_bytes() for p in library[0].rglob('*') if p.is_file()}
    assert main(plan_args(library, output, '--json')) == 0
    message = json.loads(capsys.readouterr().out)
    assert message['summary']['selected'] == 8
    assert message['summary']['requested'] == 12
    assert message['summary']['shortage'] == 4
    assert message['summary']['known_repeats'] == 0
    assert message['history_coverage'] == 'provided_records_only'
    assert 'snapshot' not in message and 'selected' not in message
    assert Path(message['plan_path']) == output / 'plan.json'
    assert Path(message['review_path']) == output / 'REVIEW.md'
    saved = json.loads((output / 'plan.json').read_text())
    assert all(row['decision'] == 'unreviewed' for row in saved['selected'])
    assert set(row['sample_id'] for row in saved['selected']).isdisjoint(library[2][:2])
    assert before == {p: p.read_bytes() for p in library[0].rglob('*') if p.is_file()}


def test_human_output_explains_metadata_and_capacity_limits(library, tmp_path, capsys):
    assert main(plan_args(library, tmp_path / 'plan')) == 0
    out = capsys.readouterr().out.lower()
    for text in ('metadata', 'seeded', 'unreviewed', 'context only', 'capacity', 'not checked',
                 'shortage', 'repeats', 'pins', 'provided_records_only', 'review.md'):
        assert text in out


@pytest.mark.parametrize('input_is_directory', [False, True])
def test_regenerate_offline_retains_pins_and_parent(library, tmp_path, capsys, input_is_directory):
    first = tmp_path / 'first'
    assert main(plan_args(library, first, '--count', '4')) == 0
    capsys.readouterr()
    first_bytes = (first / 'plan.json').read_bytes()
    original = json.loads(first_bytes)
    pin = original['selected'][0]['sample_id']
    shutil.rmtree(library[0])
    library[1].unlink()
    source = first if input_is_directory else first / 'plan.json'
    second = tmp_path / 'second'
    assert main(['regenerate', '--from-plan', str(source), '--seed', '77', '--count', '6',
                 '--pin', pin, '--output-dir', str(second), '--json']) == 0
    summary = json.loads(capsys.readouterr().out)
    saved = json.loads((second / 'plan.json').read_text())
    assert summary['summary']['selected'] == 6
    assert summary['pins'] == 1
    assert saved['pins'] == [pin]
    assert saved['parent_plan_id'] == original['plan_id']
    assert saved['snapshot'] == original['snapshot']
    assert (first / 'plan.json').read_bytes() == first_bytes


@pytest.mark.parametrize('input_is_directory', [False, True])
def test_regenerate_cannot_write_inside_parent(library, tmp_path, capsys, input_is_directory):
    first = tmp_path / 'first'
    assert main(plan_args(library, first)) == 0
    capsys.readouterr()
    source = first if input_is_directory else first / 'plan.json'
    output = first / 'child'
    assert main(['regenerate', '--from-plan', str(source), '--seed', '1',
                 '--output-dir', str(output)]) == 2
    assert 'parent' in capsys.readouterr().err.lower()
    assert not output.exists()


def test_show_json_is_full_validated_plan_and_human_show_has_caveats(library, tmp_path, capsys):
    output = tmp_path / 'plan'
    assert main(plan_args(library, output)) == 0
    capsys.readouterr()
    assert main(['show', str(output), '--json']) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown == json.loads((output / 'plan.json').read_text())
    assert main(['show', str(output / 'plan.json')]) == 0
    assert 'unreviewed' in capsys.readouterr().out
    shown['selected'][0]['decision'] = 'favourite'
    (output / 'plan.json').write_text(json.dumps(shown))
    assert main(['show', str(output), '--json']) == 2
    failed = capsys.readouterr()
    assert failed.out == ''
    assert 'changed' in failed.err and 'Traceback' not in failed.err


def test_bad_history_does_not_create_output(library, tmp_path, capsys):
    library[1].write_text('{bad')
    output = tmp_path / 'missing' / 'plan'
    assert main(plan_args(library, output)) == 2
    failed = capsys.readouterr()
    assert 'history' in failed.err.lower() and 'Traceback' not in failed.err
    assert not output.parent.exists()


def test_existing_output_is_preserved(library, tmp_path, capsys):
    output = tmp_path / 'exists'
    output.mkdir()
    marker = output / 'mine.txt'
    marker.write_text('preserve')
    assert main(plan_args(library, output)) == 2
    assert 'exists' in capsys.readouterr().err
    assert list(output.iterdir()) == [marker]
    assert marker.read_text() == 'preserve'


@pytest.mark.parametrize('extra', [['--device', 'tr8s'], ['--freshness', 'allow'],
                                 ['--history', 'some.json'], ['--role', 'KICK']])
def test_regeneration_rejects_trajectory_changes_before_output(tmp_path, extra):
    output = tmp_path / 'never-created'
    with pytest.raises(SystemExit) as failure:
        main(['regenerate', '--from-plan', str(tmp_path / 'missing'), '--seed', '2',
              '--output-dir', str(output), *extra])
    assert failure.value.code == 2
    assert not output.exists()


@pytest.mark.parametrize('option', ['--device', '--count', '--freshness', '--root', '--output-dir'])
def test_plan_requires_explicit_controls(library, tmp_path, option):
    argv = plan_args(library, tmp_path / 'out')
    index = argv.index(option)
    del argv[index:index + 2]
    with pytest.raises(SystemExit) as failure:
        main(argv)
    assert failure.value.code == 2


@pytest.mark.parametrize('error', [OSError('cannot write destination'), sqlite3.Error('index unreadable')])
def test_operational_errors_are_actionable_without_traceback(library, tmp_path, capsys, monkeypatch, error):
    import librarytools.collection_cli as cli

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(cli, 'create_plan', fail)
    output = tmp_path / 'out'
    assert main(plan_args(library, output)) == 2
    captured = capsys.readouterr()
    assert str(error) in captured.err
    assert 'Traceback' not in captured.err
    assert not output.exists()


def test_module_entrypoint_exposes_same_command():
    result = subprocess.run([sys.executable, '-m', 'librarytools.collection_cli', '--help'],
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert 'sample-collection' in result.stdout
    assert 'regenerate' in result.stdout


def test_query_filters_and_repeated_evidence_are_recorded(library, tmp_path, capsys):
    output = tmp_path / 'filtered'
    assert main(plan_args(library, output, '--role', 'PERC', '--role', 'KICK',
                          '--origin', 'TRIBAL', '--origin', 'OTHER', '--any',
                          '--history', str(library[1]),
                          '--library-db', str(library[0] / '.eidetic' / 'library.sqlite'))) == 0
    capsys.readouterr()
    saved = json.loads((output / 'plan.json').read_text())
    assert saved['snapshot']['query'] == {
        'terms': ['perc'], 'groups': {'role': ['kick', 'perc'], 'origin': ['other', 'tribal']},
        'any': True, 'curated_only': False,
    }
    assert saved['policy']['seed'] == 0
    assert len(saved['history']['sources']) == 1


@pytest.mark.parametrize('corruption', ['malformed', 'bad-pin'])
def test_bad_regeneration_input_does_not_create_output(library, tmp_path, capsys, corruption):
    parent = tmp_path / 'first'
    assert main(plan_args(library, parent)) == 0
    capsys.readouterr()
    output = tmp_path / 'never' / 'second'
    args = ['regenerate', '--from-plan', str(parent), '--seed', '3', '--output-dir', str(output)]
    if corruption == 'malformed':
        (parent / 'plan.json').write_text('{bad')
    else:
        args += ['--pin', 'short-id']
    assert main(args) == 2
    assert 'Traceback' not in capsys.readouterr().err
    assert not output.parent.exists()


def test_paths_expand_home_without_writing_there(monkeypatch):
    import librarytools.collection_cli as cli

    parsed = cli._parser().parse_args([
        'plan', '--root', '~/samples', '--device', 'octatrack', '--count', '3',
        '--freshness', 'allow', '--history', '~/history.json', '--library-db', '~/db.sqlite',
        '--output-dir', '~/plan',
    ])
    assert parsed.root == Path.home() / 'samples'
    assert parsed.history == [Path.home() / 'history.json']
    assert parsed.library_db == Path.home() / 'db.sqlite'
    assert parsed.output_dir == Path.home() / 'plan'


def test_unresolvable_home_path_is_an_argument_error(monkeypatch, capsys):
    def fail_expand(self):
        raise RuntimeError('Could not determine home directory')

    monkeypatch.setattr(Path, 'expanduser', fail_expand)
    with pytest.raises(SystemExit) as failure:
        main(['show', '~missing/plan.json'])
    assert failure.value.code == 2
    assert 'Could not determine home directory' in capsys.readouterr().err
