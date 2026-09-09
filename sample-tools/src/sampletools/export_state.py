"""Portable writer protocol, shared with library-tools without a dependency on it."""
from __future__ import annotations

import fcntl
import json
import os
import socket
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from .receipts import now


class StateError(ValueError):
    pass


def check_state(root: Path) -> str | None:
    if not root.is_dir():
        raise StateError(f'library root unavailable: {root}')
    state = root / '.eidetic'
    if state.is_symlink():
        raise StateError(f'library state must not be a symlink: {state}')
    identity = None
    marker = state / 'library.json'
    if marker.exists():
        try:
            data = json.loads(marker.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or type(data.get('format_version')) is not int or data['format_version'] != 1:
                raise StateError('unsupported portable library format version')
            identity = str(uuid.UUID(data['library_id']))
        except (ValueError, KeyError, TypeError) as exc:
            raise StateError(f'invalid or unsupported portable library version: {marker}') from exc
    database = state / 'library.sqlite'
    if database.exists():
        try:
            with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as conn:
                schema_version = conn.execute('PRAGMA user_version').fetchone()[0]
                if schema_version > 5:
                    raise StateError(f'library database version {schema_version} is newer than this exporter supports')
                bound = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='library_identity'").fetchone()
                if bound:
                    row = conn.execute('SELECT library_id FROM library_identity WHERE singleton=1').fetchone()
                    if row and row[0] != identity:
                        raise StateError('portable library identity does not match database')
        except sqlite3.Error as exc:
            raise StateError(f'cannot inspect library database: {database}') from exc
    onboarding = state / 'onboarding.json'
    if onboarding.exists() or onboarding.is_symlink():
        try:
            if onboarding.is_symlink():
                raise ValueError('onboarding record symlink')
            record = json.loads(onboarding.read_text(encoding='utf-8'))
            if not isinstance(record, dict) or type(record.get('format_version')) is not int or record['format_version'] != 1:
                raise ValueError('unsupported onboarding format')
            if identity is None or record.get('library_id') != identity:
                raise ValueError('onboarding library identity mismatch')
            if (record.get('coverage') != 'incomplete'
                    or not isinstance(record.get('machines'), dict)
                    or not isinstance(record.get('captures'), dict)
                    or not isinstance(record.get('deferred_machines'), list)
                    or not all(isinstance(machine, str) for machine in record['deferred_machines'])):
                raise ValueError('invalid onboarding metadata shape')
            # Deferred machines and preserved history are usable while their
            # historical approvals await reconciliation on the owning machine.
        except (ValueError, OSError) as exc:
            raise StateError(f'invalid or unsupported library onboarding record: {onboarding}') from exc
    adoption = state / 'adoption.json'
    if adoption.exists() or adoption.is_symlink():
        try:
            if adoption.is_symlink():
                raise ValueError('adoption record symlink')
            record = json.loads(adoption.read_text(encoding='utf-8'))
            if not isinstance(record, dict) or type(record.get('format_version')) is not int or record['format_version'] != 1:
                raise ValueError('unsupported adoption format')
        except (ValueError, OSError) as exc:
            raise StateError(f'invalid or unsupported library adoption record: {adoption}') from exc
        if record.get('status') != 'complete':
            raise StateError('incomplete library adoption; repeat the recorded sample-library migrate command before export')
    operations = state / 'operations'
    if operations.is_symlink():
        raise StateError(f'operation journal directory must not be a symlink: {operations}')
    for journal in sorted(operations.glob('*.json')):
        try:
            if journal.is_symlink():
                raise ValueError('journal symlink')
            data = json.loads(journal.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or type(data.get('schema_version')) is not int or data['schema_version'] != 1:
                raise ValueError('unsupported journal version')
        except (ValueError, OSError) as exc:
            raise StateError(f'cannot validate operation journal: {journal}; run sample-library recover') from exc
        if data.get('status') != 'complete':
            raise StateError(f'incomplete operation {journal.name}; run sample-library recover before export')
    return identity


@contextmanager
def library_writer(root: Path, purpose: str):
    """Never unlink lock files: flock owns the inode, including across crashes."""
    check_state(root)
    state = root / '.eidetic'
    state.mkdir(exist_ok=True)
    lock = state / 'writer.lock'
    if lock.is_symlink():
        raise StateError(f'writer lock must not be a symlink: {lock}')
    try:
        descriptor = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
        raise StateError(f'cannot open writer lock without following symlinks: {lock}') from exc
    with os.fdopen(descriptor, 'a+', encoding='utf-8') as fh:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise StateError(f'library has another active writer: {lock}') from exc
        try:
            # Recheck after locking in case an earlier writer just migrated it.
            identity = check_state(root)
            fh.seek(0)
            fh.truncate()
            json.dump({'pid': os.getpid(), 'host': socket.gethostname(), 'purpose': purpose,
                       'started_at': now()}, fh)
            fh.flush()
            os.fsync(fh.fileno())
            yield identity
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
