"""Local, advisory single-writer locks shared by both machines' tools.

The SSD is attached to one machine at a time. flock releases on process death;
the persistent file is deliberately never unlinked (which would split locks).
"""
from __future__ import annotations

import fcntl
import json
import os
import socket
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class LibraryBusyError(ValueError):
    """Another process currently holds the library writer lock."""


_held: dict[tuple[int, int, str], int] = {}
_descriptors: dict[tuple[int, int, str], int] = {}


@contextmanager
def _file_lock(path: Path, purpose: str):
    if path.is_symlink():
        raise ValueError(f'writer lock must not be a symlink: {path}')
    path = path.resolve()
    key = (os.getpid(), threading.get_ident(), str(path))
    if key in _held:
        _held[key] += 1
        try:
            yield
        finally:
            _held[key] -= 1
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'r+', encoding='utf-8') as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.seek(0)
            raise LibraryBusyError(f'library has another writer: {handle.read() or path}') from exc
        _held[key] = 1
        _descriptors[key] = handle.fileno()
        try:
            handle.seek(0)
            handle.truncate()
            json.dump({'pid': os.getpid(), 'host': socket.gethostname(), 'purpose': purpose,
                       'started_at': datetime.now(timezone.utc).isoformat()}, handle)
            handle.flush()
            os.fsync(handle.fileno())
            yield
        finally:
            _held.pop(key, None)
            _descriptors.pop(key, None)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def library_lock(root: Path, purpose: str = 'library mutation', *, allow_recovery: bool = False,
                 allow_adoption: bool = False):
    """Lock supported state, blocking unfinished execution rather than history.

    Recovery and adoption bypasses are reserved for their own resume paths;
    deferred historical coverage alone never blocks a mutation.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f'library root is unavailable: {root}')
    if (root / '.eidetic').is_symlink():
        raise ValueError('library state directory must not be a symlink')
    path = root / '.eidetic/writer.lock'
    nested = (os.getpid(), threading.get_ident(), str(path.resolve())) in _held
    if not nested:
        from .state import library_identity
        from .schema import inspect_database
        library_identity(root)  # Validate without creating the identity.
        database = root / '.eidetic/library.sqlite'
        if database.exists():
            inspect_database(database)
        onboarding = root / '.eidetic/onboarding.json'
        if onboarding.exists():
            record = json.loads(onboarding.read_text(encoding='utf-8'))
            if not isinstance(record, dict) or record.get('format_version') != 1:
                raise ValueError('unsupported onboarding metadata version')
        adoption = root / '.eidetic/adoption.json'
        if adoption.exists():
            record = json.loads(adoption.read_text(encoding='utf-8'))
            if not isinstance(record, dict) or record.get('format_version') != 1:
                raise ValueError('unsupported library adoption record version')
            if record.get('status') != 'complete' and not allow_adoption:
                raise ValueError('library adoption execution is incomplete; repeat the original sample-library onboard or migrate command to finish publication')
    with _file_lock(path, purpose):
        if not nested and not allow_recovery:
            from .operations import require_settled
            require_settled(root)
        yield


def database_lock(path: Path, purpose: str = 'database mutation'):
    path = Path(path)
    return _file_lock(path.with_name(path.name + '.writer.lock'), purpose)


def inherited_lock_fd(root: Path) -> int | None:
    """Expose an already-held description only for an explicit subprocess pass_fds."""
    path = (Path(root).resolve() / '.eidetic/writer.lock').resolve()
    return _descriptors.get((os.getpid(), threading.get_ident(), str(path)))


@contextmanager
def adopt_inherited_library_lock(root: Path, fd: int):
    """Let a directly spawned worker participate in its parent's one mutation.

    Never unlock the inherited open description: flock ownership is shared with
    the parent. Independent processes still fail the usual nonblocking lock.
    """
    from .state import library_identity
    from .schema import inspect_database
    root = Path(root).resolve()
    library_identity(root)
    database = root / '.eidetic/library.sqlite'
    if database.exists():
        inspect_database(database)
    path = (root / '.eidetic/writer.lock').resolve()
    expected, actual = path.stat(), os.fstat(fd)
    if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
        raise ValueError('inherited lock descriptor does not belong to this library')
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise LibraryBusyError('inherited descriptor does not own the library writer lock') from exc
    key = (os.getpid(), threading.get_ident(), str(path))
    if key in _held:
        raise ValueError('worker already owns a library lock')
    duplicate = os.dup(fd)
    _held[key] = 1
    _descriptors[key] = duplicate
    try:
        yield
    finally:
        _held.pop(key, None)
        _descriptors.pop(key, None)
        os.close(duplicate)
