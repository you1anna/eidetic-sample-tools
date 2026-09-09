"""Portable library identity and non-mutating state path resolution."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

STATE_FORMAT_VERSION = 1


def state_directory(root: Path) -> Path:
    root = Path(root).resolve()
    state = root / '.eidetic'
    if state.is_symlink():
        raise ValueError('library state directory must not be a symlink')
    return state


def resolve_library_db(root: Path, explicit: Path | None = None, *, legacy_path: Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser()
    from . import config
    portable = state_directory(root) / 'library.sqlite'
    if portable.is_file():
        from .onboarding import assert_captured_sources_current
        assert_captured_sources_current(root)
    legacy = legacy_path if legacy_path is not None else getattr(config, 'LEGACY_MANIFEST_DIR', config.MANIFEST_DIR) / 'sample-library.sqlite'
    if Path(legacy).is_file() and Path(legacy).resolve() != portable.resolve():
        if legacy_is_superseded(root, Path(legacy)) and portable.is_file():
            return portable
        raise ValueError(f'legacy library state exists at {legacy}; run sample-library onboard '
                         '--machine NAME --library-db PATH to preview preserving it before using portable state')
    return portable


def legacy_is_superseded(root: Path, legacy: Path) -> bool:
    """Recognise unchanged history preserved by a verified capture or adoption."""
    from .onboarding import captured_source_matches
    if captured_source_matches(root, legacy):
        return True
    record = state_directory(root) / 'adoption.json'
    if not record.is_file():
        return False
    try:
        data = json.loads(record.read_text(encoding='utf-8'))
        if (not isinstance(data, dict) or data.get('format_version') != 1 or data.get('status') != 'complete'
                or data.get('source_database') != str(legacy.resolve())
                or data.get('library_id') != library_identity(root)):
            return False
        from .schema import readonly_database
        with readonly_database(legacy):
            with legacy.open('rb') as stream:
                return hashlib.file_digest(stream, 'sha256').hexdigest() == data.get('source_sha256')
    except (ValueError, OSError):
        return False


def library_identity(root: Path, create: bool = False) -> str | None:
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f'library root is unavailable: {root}')
    marker = state_directory(root) / 'library.json'
    if marker.is_symlink():
        raise ValueError('library identity must not be a symlink')
    if marker.is_file():
        try:
            data = json.loads(marker.read_text(encoding='utf-8'))
            if data['format_version'] != STATE_FORMAT_VERSION:
                raise ValueError('unsupported library identity format version')
            identity = str(uuid.UUID(data['library_id']))
            return identity
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError('invalid library identity marker; preserve it and investigate') from exc
    if not create:
        return None
    from .locking import library_lock
    with library_lock(root, purpose='initialise library identity'):
        if marker.exists():
            return library_identity(root)
        identity = str(uuid.uuid4())
        payload = {'format_version': STATE_FORMAT_VERSION, 'library_id': identity,
                   'created_at': datetime.now(timezone.utc).isoformat()}
        temporary = marker.with_name('.library-' + uuid.uuid4().hex + '.tmp')
        try:
            with temporary.open('x', encoding='utf-8') as out:
                json.dump(payload, out, indent=2)
                out.write('\n')
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, marker)
        finally:
            temporary.unlink(missing_ok=True)
        return identity
