"""Save unreviewed candidate plans without changing indexed metadata or audio."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from .collection_plan import create_plan, read_plan, regenerate_plan, write_plan
from .find import Query


def _path(value: str) -> Path:
    try:
        return Path(value).expanduser()
    except (RuntimeError, ValueError) as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='sample-collection',
        description='Plan unreviewed candidates using metadata and seeded ordering; never changes audio.',
    )
    commands = parser.add_subparsers(dest='command', required=True)
    plan = commands.add_parser('plan', help='capture an indexed population and propose candidates')
    plan.add_argument('terms', nargs='*', help='metadata terms or filename fragments')
    plan.add_argument('--root', type=_path, required=True, help='indexed library root')
    plan.add_argument('--device', choices=('octatrack', 'digitakt', 'tr8s'), required=True)
    plan.add_argument('--count', type=int, required=True, help='requested candidate count')
    plan.add_argument('--freshness', choices=('exclude', 'prefer-new', 'allow'), required=True,
                      help='how to treat identities in supplied export history')
    plan.add_argument('--brief', default='', help='recorded context only; does not rank candidates')
    plan.add_argument('--seed', type=int, default=0, help='reproducible ordering seed (default: 0)')
    plan.add_argument('--role', action='append', default=[], help='metadata role filter; repeatable')
    plan.add_argument('--origin', action='append', default=[], help='metadata origin filter; repeatable')
    plan.add_argument('--any', dest='any_', action='store_true', help='match any search term')
    plan.add_argument('--history', action='append', type=_path, default=[],
                      help='export JSON or receipt directory; repeatable')
    plan.add_argument('--library-db', type=_path, help='explicit library index path')
    plan.add_argument('--output-dir', type=_path, required=True, help='new directory for plan and review')
    plan.add_argument('--json', action='store_true', help='print a compact summary and output paths')

    regenerate = commands.add_parser('regenerate', help='revise a saved plan, retaining its population and history')
    regenerate.add_argument('--from-plan', type=_path, required=True, help='saved plan.json or its directory')
    regenerate.add_argument('--seed', type=int, required=True, help='new reproducible ordering seed')
    regenerate.add_argument('--count', type=int, help='replacement candidate count')
    regenerate.add_argument('--pin', action='append', default=[],
                            help='retain a selected sample by its full SHA-256 identity; repeatable')
    regenerate.add_argument('--output-dir', type=_path, required=True, help='new directory outside the parent plan')
    regenerate.add_argument('--json', action='store_true', help='print a compact summary and output paths')

    show = commands.add_parser('show', help='validate and inspect a saved plan')
    show.add_argument('plan_path', type=_path, help='saved plan.json or its directory')
    show.add_argument('--json', action='store_true', help='print the entire validated plan')
    return parser


def _plan_path(path: Path) -> Path:
    return (path / 'plan.json' if path.is_dir() else path).absolute()


def _summary(plan: dict, plan_path: Path) -> dict:
    return {
        'plan_id': plan['plan_id'], 'collection_id': plan['collection_id'],
        'device': plan['policy']['device'], 'freshness': plan['policy']['freshness'],
        'seed': plan['policy']['seed'], 'summary': plan['summary'],
        'pins': len(plan['pins']), 'history_coverage': plan['history']['coverage'],
        'selection_method': plan['policy']['method'], 'decisions': 'unreviewed',
        'brief_interpretation': plan['policy']['brief_interpretation'],
        'device_capacity': 'not_checked',
        'plan_path': str(plan_path), 'review_path': str(plan_path.parent / 'REVIEW.md'),
    }


def _print_summary(plan: dict, plan_path: Path, *, as_json: bool) -> None:
    info = _summary(plan, plan_path)
    if as_json:
        print(json.dumps(info, indent=2, sort_keys=True, allow_nan=False))
        return
    counts = info['summary']
    print(f"Candidates: {counts['selected']} / {counts['requested']} requested; "
          f"shortage: {counts['shortage']}; known repeats: {counts['known_repeats']}; pins: {info['pins']}.")
    print(f"Device: {info['device']}; freshness: {info['freshness']}; "
          f"history coverage: {info['history_coverage']}.")
    print('Selection: metadata filters and seeded ordering; all candidates are unreviewed.')
    print('Brief: recorded context only; device capacity: not checked.')
    print(f"Plan: {info['plan_path']}")
    print(f"Review: {info['review_path']}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == 'plan':
            groups = {name: tuple(value.lower() for value in values)
                      for name, values in [('role', args.role), ('origin', args.origin)] if values}
            query = Query(terms=tuple(term.lower() for term in args.terms), groups=groups, any_=args.any_)
            plan = create_plan(args.root, device=args.device, count=args.count,
                               freshness=args.freshness, query=query, brief=args.brief, seed=args.seed,
                               history_paths=args.history, library_db=args.library_db)
            path = write_plan(plan, args.output_dir)
            _print_summary(plan, path, as_json=args.json)
        elif args.command == 'regenerate':
            parent = read_plan(args.from_plan)
            parent_dir = _plan_path(args.from_plan).parent
            plan = regenerate_plan(parent, seed=args.seed, count=args.count, pins=args.pin)
            path = write_plan(plan, args.output_dir, parent_dir=parent_dir)
            _print_summary(plan, path, as_json=args.json)
        else:
            plan = read_plan(args.plan_path)
            if args.json:
                print(json.dumps(plan, indent=2, sort_keys=True, allow_nan=False))
            else:
                _print_summary(plan, _plan_path(args.plan_path), as_json=False)
        return 0
    except (ValueError, OSError, sqlite3.Error) as error:
        print(f'sample-collection: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
