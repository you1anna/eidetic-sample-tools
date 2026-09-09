"""Preserve previous analysis evidence before publishing new latest reports."""
from __future__ import annotations

import hashlib
import shutil
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .operations import atomic_json


def _outputs(directory: Path) -> list[Path]:
    paths = list(directory.glob('*-latest.tsv'))
    paths.extend(directory / name for name in ('analysis-run.json',) if (directory / name).exists())
    for name in ('crates', 'reports'):
        parent = directory / name
        if parent.is_symlink():
            raise ValueError(f'analysis output directory is a symlink: {parent}')
        if parent.is_dir():
            paths.extend(p for p in parent.rglob('*') if p.is_file() or p.is_symlink())
    return sorted(paths)


def _hash(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


@contextmanager
def analysis_run(directory: Path, root: Path):
    if directory.is_symlink() or (directory / '.history').is_symlink():
        raise ValueError('analysis output/history must not be a symlink')
    run_id = uuid.uuid4().hex
    previous = _outputs(directory)
    archive = directory / '.history' / run_id
    checksums = {}
    for path in previous:
        if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError(f'analysis evidence path is unsafe: {path}')
        relative = path.relative_to(directory)
        target = archive / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        before = _hash(path)
        shutil.copy2(path, target)
        if _hash(path) != before or _hash(target) != before:
            raise ValueError(f'analysis evidence changed during archival: {path}')
        checksums[relative.as_posix()] = before
    if previous:
        atomic_json(archive / 'archive.json', {'format_version': 1, 'files': checksums})
    data = {'format_version': 1, 'run_id': run_id, 'root': str(root),
            'started_at': datetime.now(timezone.utc).isoformat(), 'tool_version': __version__,
            'status': 'incomplete', 'previous_evidence': str(archive) if previous else None}
    marker = directory / 'analysis-run.json'
    atomic_json(marker, data)
    try:
        yield data
    except BaseException as exc:
        data['error'] = str(exc)
        atomic_json(marker, data)
        raise
    else:
        data.update(status='complete' if data.get('exit_code', 0) == 0 else 'failed', completed_at=datetime.now(timezone.utc).isoformat(),
                    outputs={p.relative_to(directory).as_posix(): _hash(p)
                             for p in _outputs(directory) if p != marker})
        atomic_json(marker, data)
