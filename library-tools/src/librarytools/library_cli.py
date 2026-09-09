"""Manage portable library state. Start with onboard for independent per-machine setup."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from . import config
from .inventory import LibraryDatabase, _iter_audio
from .lifecycle import backup_bundle, doctor, maintenance_preview, restore_bundle
from .locking import library_lock
from .schema import inspect_database, migrate_database
from .state import library_identity, state_directory


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=config.SAMPLES_ROOT, help='mounted sample library root')
    parser.add_argument('--library-db', type=Path, help='database override; local historical source for onboard')
    parser.add_argument('--json', action='store_true', help='print a structured JSON report')
    commands = parser.add_subparsers(dest='command', required=True)
    descriptions = {
        'doctor': 'Inspect state, runtime, recovery records and historical coverage without writes.',
        'onboard': 'Set up this machine and preserve its history; other machines can join later.',
        'init': 'Create an empty index; prefer onboard to account for per-machine history.',
        'migrate': 'Upgrade a validated schema with a backup, or adopt a copy at a new path.',
        'backup': 'Preserve the database and durable evidence in a verified bundle.',
        'restore': 'Restore a verified bundle to a separate new directory.',
        'recover': 'Review unfinished file operations and resume verified steps.',
        'maintenance': 'Report cache growth and temporary evidence without deleting anything.',
    }
    for name, description in descriptions.items():
        sub = commands.add_parser(name, help=description, description=description)
        # Accept the same location options before or after the subcommand.
        sub.add_argument('--root', type=Path, default=argparse.SUPPRESS, help='mounted sample library root')
        sub.add_argument('--library-db', type=Path, default=argparse.SUPPRESS,
                         help='local historical database to preserve' if name == 'onboard' else 'database path override')
        sub.add_argument('--json', action='store_true', default=argparse.SUPPRESS,
                         help='print a structured JSON report')
        if name not in ('doctor', 'maintenance'):
            sub.add_argument('--apply', action='store_true', help='perform the operation; omission previews without writes')
        if name in ('backup', 'restore'):
            sub.add_argument('--output', type=Path, required=True)
        if name == 'restore':
            sub.add_argument('--source', type=Path, required=True)
        if name in ('migrate', 'backup', 'onboard'):
            sub.add_argument('--include', type=Path, action='append', default=[],
                             help='legacy labels, manifests, or configuration to preserve')
        if name == 'migrate':
            sub.add_argument('--backup-dir', type=Path)
            sub.add_argument('--destination', type=Path,
                             help='adopt a copy at a new database path; never overwrite or merge')
        if name == 'onboard':
            sub.add_argument('--machine', required=True, help='name for this machine in historical coverage records')
            sub.add_argument('--defer-machine', action='append', default=[], help='unavailable machine to account for later')
            sub.add_argument('--backup-dir', type=Path)
        if name == 'recover':
            sub.add_argument('--operation-id')
    return parser


def _init(args):
    root = args.root.resolve()
    if not root.is_dir():
        raise ValueError(f'library root is unavailable: {root}')
    path = args.library_db or state_directory(root) / 'library.sqlite'
    if path.exists():
        raise ValueError('library database already exists; use doctor to inspect it or onboard to set up this machine')
    legacy = getattr(config, 'LEGACY_MANIFEST_DIR', config.MANIFEST_DIR) / 'sample-library.sqlite'
    if legacy.is_file() and args.library_db is None:
        raise ValueError(f'legacy state exists at {legacy}; preview sample-library onboard --machine NAME to preserve it')
    identity = library_identity(root)
    if identity is not None:
        raise ValueError('library identity exists without its database; restore or reconcile missing state')
    report = {'command': 'init', 'root': str(root), 'database': str(path), 'apply': args.apply,
              'unverified_audio_files': len(_iter_audio(root)),
              'approval_import': 'none; audio placement does not establish human approval'}
    if args.apply:
        with library_lock(root, purpose='initialise portable library'):
            database = LibraryDatabase(path)
            report['library_id'] = database.bind_root(root)
    return report


def _migrate(args):
    source = args.library_db or state_directory(args.root) / 'library.sqlite'
    if args.destination is None:
        # The in-place operation always retains a verified original backup.
        return migrate_database(source, root=args.root, backup_dir=args.backup_dir,
                                apply=args.apply, include=tuple(args.include))
    from .lifecycle import adopt_database
    return adopt_database(source, args.destination, root=args.root, backup_dir=args.backup_dir,
                          include=tuple(args.include), apply=args.apply)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command != 'restore':
            args.root = config.require_root(args.root)
        code = 0
        if args.command == 'doctor':
            report = doctor(args.root, args.library_db)
            code = 2 if report['database']['status'] in {'missing', 'error'} else (1 if report['issues'] or report['database']['status'] == 'migration_required' else 0)
        elif args.command == 'init':
            report = _init(args)
        elif args.command == 'onboard':
            from .onboarding import onboard
            report = onboard(args.root, args.machine, defer_machines=args.defer_machine,
                             legacy_db=args.library_db, include=args.include,
                             backup_dir=args.backup_dir, apply=args.apply)
        elif args.command == 'migrate':
            report = _migrate(args)
        elif args.command == 'backup':
            path = args.library_db or state_directory(args.root) / 'library.sqlite'
            info = inspect_database(path)
            if args.output.exists():
                raise ValueError(f'backup destination already exists: {args.output}')
            for evidence in args.include:
                if not evidence.exists():
                    raise ValueError(f'additional evidence not found: {evidence}')
            report = {'apply': args.apply, 'database': str(path), 'destination': str(args.output), **info}
            if args.apply:
                report.update(backup_bundle(path, args.output, root=args.root, include=tuple(args.include)))
        elif args.command == 'restore':
            report = restore_bundle(args.source, args.output, apply=args.apply)
        elif args.command == 'recover':
            from .operations import recover_operations
            path = args.library_db or state_directory(args.root) / 'library.sqlite'
            database = LibraryDatabase(path, readonly=not args.apply) if path.is_file() else None
            if database is not None:
                database.bind_root(args.root, create=args.apply)
            report = {'apply': args.apply, 'operations': recover_operations(args.root, database, apply=args.apply, operation_id=args.operation_id)}
        else:
            report = maintenance_preview(args.root, args.library_db)
            if report['database_cache']['status'] == 'error':
                code = 2
        print(json.dumps(report, indent=2, sort_keys=True) if args.json else _text_report(report))
        return code
    except (ValueError, OSError, sqlite3.DatabaseError) as exc:
        if args.json:
            print(json.dumps({'error': str(exc)}, sort_keys=True))
        else:
            print(str(exc), file=sys.stderr)
        return 2


def _text_report(report):
    return '\n'.join(f'{key}: {json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value}'
                     for key, value in report.items())


if __name__ == '__main__':
    raise SystemExit(main())
