"""Benchmark metadata planning on a temporary synthetic index, with no audio files.

Run from any directory using a Python environment with library-tools dependencies.
This deliberately imports the checkout. It does not measure AI, audio analysis,
musical quality, device export or cold-disk throughput. JSON results go to stdout;
the fixture and real fsynced plan artifacts are removed when the run finishes.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
from time import perf_counter


REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / 'library-tools/src'))

from librarytools.collection_plan import (  # noqa: E402
    create_plan, read_plan, regenerate_plan, validate_plan, write_plan,
)
from librarytools.find import Query  # noqa: E402
from librarytools.inventory import LibraryDatabase  # noqa: E402


def bounded_integer(minimum, maximum):
    def parse(value):
        try:
            number = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError('expected an integer') from exc
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(f'expected {minimum} through {maximum}')
        return number
    return parse


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(f'benchmark correctness check failed: {message}')


def fixture(scratch, identities, history_count):
    """Bulk-load the real schema; synthetic paths intentionally have no files."""
    root = scratch / 'synthetic-library'
    root.mkdir()
    database = LibraryDatabase(root / '.eidetic/library.sqlite')
    library_id = database.bind_root(root)
    ids = [hashlib.sha256(f'synthetic-original-{index}'.encode()).hexdigest()
           for index in range(identities)]
    scan_id, timestamp = 'synthetic-complete-scan', '2026-01-01T00:00:00+00:00'
    with database._connect() as connection:
        connection.execute('insert into scans(scan_id,root,started_at,completed_at,status,file_count) '
                           'values(?,?,?,?,?,?)',
                           (scan_id, str(root), timestamp, timestamp, 'complete', identities + 1))
        connection.executemany('insert into assets(sample_id,size,extension,first_seen_at) values(?,?,?,?)',
                               ((sid, 88200, '.wav', timestamp) for sid in ids))
        connection.executemany('insert into locations(path,sample_id,zone,source_name,size,mtime_ns,scan_id,exists_now) '
                               'values(?,?,?,?,?,?,?,?)',
            ((f'PACKS/pack-{index % 24:02}/perc-tribal-{index:06}.wav', sid,
              'PACKS', f'pack-{index % 24:02}', 88200, 1, scan_id, 1)
             for index, sid in enumerate(ids)))
        connection.execute('insert into locations(path,sample_id,zone,source_name,size,mtime_ns,scan_id,exists_now) '
                           'values(?,?,?,?,?,?,?,?)',
                           ('CURATED/PERC/renamed-alias.wav', ids[0], 'CURATED',
                            'CURATED', 88200, 1, scan_id, 1))
        connection.executemany('insert into tags(sample_id,tag_group,tag) values(?,?,?)',
                               ((sid, 'character', 'tribal') for sid in ids))
    history = scratch / 'synthetic-history.json'
    history.write_text(json.dumps({'schema': 'eidetic-delegated-library-v1',
        'library_id': library_id, 'items': [
            {'device': 'octatrack', 'sample_id': sid,
             'output_sha256': hashlib.sha256(f'converted-{sid}'.encode()).hexdigest()}
            for sid in ids[:history_count]]}), encoding='utf-8')
    return root, database.path, ids, history


def git_value(*arguments):
    try:
        return subprocess.check_output(['git', '-C', str(REPOSITORY), *arguments],
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def benchmark(args):
    timings = defaultdict(list)

    def timed(stage, function, *arguments, **keywords):
        started = perf_counter()
        value = function(*arguments, **keywords)
        timings[stage].append(perf_counter() - started)
        return value

    with tempfile.TemporaryDirectory(prefix='eidetic-planner-benchmark-') as temporary:
        scratch = Path(temporary).resolve()  # Resolve macOS /var before strict path checks.
        started = perf_counter()
        root, database, ids, history = fixture(scratch, args.identities, args.history)
        setup_seconds = perf_counter() - started
        original_database = digest(database)
        prior = set(ids[:args.history])
        expected_selected = min(args.count, args.identities - args.history)
        options = dict(device='octatrack', count=args.count, freshness='exclude',
                       query=Query(), brief='Synthetic metadata performance fixture',
                       seed=1729, history_paths=[history])
        parents = []
        for iteration in range(args.repeats):
            plan = timed('create_plan', create_plan, root, **options)
            chosen = [row['sample_id'] for row in plan['selected']]
            require(len(chosen) == len(set(chosen)) == expected_selected, 'distinct selected count')
            require(set(chosen).isdisjoint(prior), 'original identities excluded across aliases')
            require(plan['summary']['excluded_previous'] == args.history, 'history exclusion count')
            require(plan['summary']['shortage'] == args.count - expected_selected, 'explicit shortage')
            require(len(plan['snapshot']['candidates']) == args.identities, 'alias deduplication')
            alias = next(row for row in plan['snapshot']['candidates'] if row['sample_id'] == ids[0])
            require(len(alias['aliases']) == 2, 'alias preserved in snapshot')
            if parents:
                require(plan['plan_id'] == parents[0][0]['plan_id'], 'same input and seed reproduce plan')
            timed('validate_plan', validate_plan, plan)
            output = scratch / f'parent-{iteration}'
            path = timed('write_plan', write_plan, plan, output)
            loaded = timed('read_plan', read_plan, path)
            require(loaded == plan, 'plan read round trip')
            originals = {name: digest(output / name) for name in ('plan.json', 'REVIEW.md')}
            parents.append((loaded, output, originals))

        # Even a small requested set exercises the shortage boundary once.
        shortage = create_plan(root, **dict(options, count=args.identities + 1))
        require(shortage['summary']['shortage'] == args.history + 1, 'shortage never refills with repeats')
        # With one timing repeat, still check a separately captured identical plan.
        if args.repeats == 1:
            require(create_plan(root, **options)['plan_id'] == parents[0][0]['plan_id'],
                    'same input and seed reproduce plan')
        require(digest(database) == original_database, 'planning changed database')
        offline_root = scratch / 'unavailable-library'
        root.rename(offline_root)
        history.rename(scratch / 'unavailable-history.json')
        require(not root.exists() and not history.exists(), 'fixture is offline')
        for iteration, (parent, output, originals) in enumerate(parents):
            pins = [row['sample_id'] for row in parent['selected'][:args.pins]]
            revised = timed('regenerate_plan_offline', regenerate_plan, parent,
                            seed=1730, pins=pins)
            require(revised['parent_plan_id'] == parent['plan_id'], 'child links to its parent')
            require(revised['pins'] == sorted(pins), 'pins retained')
            require(set(pins) <= {row['sample_id'] for row in revised['selected']}, 'pins selected')
            require(all(row['decision'] == 'unreviewed' for row in revised['selected']), 'no approval')
            require(revised['snapshot'] == parent['snapshot'] and revised['history'] == parent['history'],
                    'offline population and history preserved')
            inherited = regenerate_plan(revised, seed=1731)
            require(inherited['parent_plan_id'] == revised['plan_id'], 'next revision preserves lineage')
            require(inherited['pins'] == sorted(pins) and
                    set(pins) <= {row['sample_id'] for row in inherited['selected']}, 'inherited pins retained')
            require(all(row['decision'] == 'unreviewed' for row in inherited['selected']), 'pins never approve')
            child_path = timed('write_regenerated', write_plan, revised,
                               scratch / f'child-{iteration}', parent_dir=output)
            require(timed('read_regenerated', read_plan, child_path) == revised, 'child read round trip')
            require(all(digest(output / name) == value for name, value in originals.items()),
                    'parent artifacts changed')
        require(digest(offline_root / '.eidetic/library.sqlite') == original_database,
                'offline regeneration changed database')
        parent, output, _ = parents[0]
        sizes = {'database': (offline_root / '.eidetic/library.sqlite').stat().st_size,
                 'plan_json': (output / 'plan.json').stat().st_size,
                 'review_markdown': (output / 'REVIEW.md').stat().st_size}
        report = {
            'scope': 'Synthetic metadata planning only; no AI, audio, musical-quality or device-export measurement.',
            'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                            'revision': git_value('rev-parse', 'HEAD'),
                            'checkout_dirty': bool(git_value('status', '--porcelain'))},
            'config': dict(vars(args), seed=1729),
            'fixture': {'locations': args.identities + 1, 'audio_files_created': 0,
                        'setup_seconds': round(setup_seconds, 6)},
            'summary': parent['summary'], 'sizes_bytes': sizes,
            'median_seconds': {stage: round(statistics.median(values), 6)
                               for stage, values in timings.items()},
            'checks': {'offline_regeneration': True, 'retained_pins': args.pins,
                       'parent_lineage_preserved': True,
                       'all_unreviewed': True, 'parent_and_database_unchanged': True,
                       'exact_alias_deduplicated': True, 'same_seed_reproduced': True,
                       'shortage_does_not_refill': True},
            'timing_notes': 'Stages include their own validation; writes include JSON, Markdown and fsync. '
                            'Sequential runs may use warm OS caches. Fixture setup and extra correctness '
                            'checks are outside stage medians. Temporary artifacts are removed.',
        }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--identities', type=bounded_integer(2, 50000), default=22000)
    parser.add_argument('--count', type=bounded_integer(1, 100000), default=1000)
    parser.add_argument('--history', type=bounded_integer(1, 49999), default=240)
    parser.add_argument('--pins', type=bounded_integer(0, 50000), default=10)
    parser.add_argument('--repeats', type=bounded_integer(1, 10), default=3)
    args = parser.parse_args()
    if args.history >= args.identities:
        parser.error('--history must leave at least one identity eligible')
    if args.pins > min(args.count, args.identities - args.history):
        parser.error('--pins cannot exceed the number selected after history exclusion')
    print(json.dumps(benchmark(args), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
