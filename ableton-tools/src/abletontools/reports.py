"""Dated, immutable input observations accompanying the legacy TSV reports."""
from __future__ import annotations

import fcntl
import gzip
import hashlib
import json
import os
import tempfile
import uuid
import xml.etree.ElementTree as ET
import zlib
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, payload: bytes) -> None:
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.tmp', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class ReportRun:
    def __init__(self, roots: list[Path], kind: str):
        try:
            tool_version = version('abletontools')
        except PackageNotFoundError:
            tool_version = 'uninstalled'
        self.data = {
            'format': 'eidetic-ableton-report', 'version': 1, 'report_kind': kind,
            'run_id': str(uuid.uuid4()), 'generated_at': _now(), 'tool_version': tool_version,
            'complete': True, 'roots': [], 'inputs': [], 'errors': [],
            'exclusions': ['Backup directories', 'hidden files and directories'],
        }
        self.roots = roots

    def sets(self):
        """Parse exactly the input bytes hashed into the evidence, once per path."""
        visited = set()
        for requested in self.roots:
            root = requested.resolve()
            record = {'path': str(root), 'status': 'scanned'}
            self.data['roots'].append(record)
            if not root.is_dir():
                record['status'] = 'unavailable'
                self.data['complete'] = False
                self.data['errors'].append(f'root unavailable: {root}')
                continue
            def walk_error(error):
                record['status'] = 'partial'
                self.data['complete'] = False
                self.data['errors'].append(str(error))
            for directory, dirs, files in os.walk(root, onerror=walk_error, followlinks=False):
                dirs[:] = sorted(name for name in dirs if name != 'Backup' and not name.startswith('.'))
                for name in list(dirs):
                    if (Path(directory) / name).is_symlink():
                        walk_error(f'directory symlink not scanned: {Path(directory) / name}')
                        dirs.remove(name)
                for name in sorted(files):
                    if name.startswith('.') or not name.endswith('.als'):
                        continue
                    path = Path(directory) / name
                    if path in visited:
                        continue
                    visited.add(path)
                    entry = {'path': str(path), 'status': 'parsed'}
                    self.data['inputs'].append(entry)
                    try:
                        before = path.stat()
                        payload = path.read_bytes()
                        after = path.stat()
                        entry.update(size=len(payload), mtime_ns=before.st_mtime_ns,
                                     sha256=hashlib.sha256(payload).hexdigest())
                        if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                            raise OSError('Set changed while reading')
                        tree = ET.fromstring(gzip.decompress(payload))
                    except (OSError, EOFError, ET.ParseError, zlib.error) as exc:
                        entry['status'] = 'parse_error' if 'sha256' in entry else 'read_error'
                        entry['error'] = str(exc)
                        self.data['complete'] = False
                        self.data['errors'].append(f'{path}: {exc}')
                        continue
                    yield path, tree, entry

    def report_error(self, entry: dict, error: Exception) -> None:
        entry['status'] = 'report_error'
        entry['error'] = str(error)
        self.data['complete'] = False
        self.data['errors'].append(f"{entry['path']}: {error}")

    def publish(self, path: Path, rows: list[str]) -> None:
        """Preserve earlier evidence before atomically publishing each new artifact.

        The metadata's hash detects an interrupted TSV/metadata pair publication.
        Earlier pairs (including pre-versioning TSVs) remain in .history for recovery.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = ('\n'.join(rows) + '\n').encode('utf-8')
        metadata_path = path.with_suffix(path.suffix + '.metadata.json')
        self.data.update(report_sha256=hashlib.sha256(payload).hexdigest(),
                         report_file=path.name, rows=len(rows) - 1, completed_at=_now())
        lock_path = path.with_name('.' + path.name + '.writer.lock')
        with lock_path.open('a+') as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError(f'another writer is publishing {path}') from exc
            try:
                if path.exists() or metadata_path.exists():
                    history = path.parent / '.history' / path.stem / self.data['run_id']
                    history.mkdir(parents=True, exist_ok=False)
                    for previous in (path, metadata_path):
                        if previous.exists():
                            _atomic_write(history / previous.name, previous.read_bytes())
                _atomic_write(path, payload)
                _atomic_write(metadata_path, (json.dumps(self.data, indent=2, sort_keys=True) + '\n').encode('utf-8'))
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
