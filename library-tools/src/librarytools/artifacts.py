"""Version sidecars for durable public interchange files."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .inventory import sha256_file
from .operations import atomic_json


def write_crate_metadata(path: Path, *, packet_id: str | None = None,
                         approval: dict | None = None, content_sha256: str | None = None) -> Path:
    """Keep legacy TSV columns readable while explicitly versioning new crates."""
    output = path.with_suffix(path.suffix + '.metadata.json')
    data = {'format': 'eidetic-crate', 'version': 1,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'sha256': content_sha256 or sha256_file(path), 'packet_id': packet_id}
    if approval is not None:
        data['approval'] = approval
    atomic_json(output, data)
    return output


def packet_root(metadata: dict, current_root: Path | None = None) -> Path:
    """Resolve a portable packet using recorded identity, retaining its origin path."""
    from .state import library_identity
    if metadata.get('schema_version', 1) not in {1, 2, 3} or metadata.get('packet_format_version', 1) != 1:
        raise ValueError('unsupported packet version; use compatible tools')
    original = metadata.get('root')
    if not isinstance(original, str) or not original.strip():
        raise ValueError('invalid packet metadata: root must be a non-empty path')
    root = (current_root or Path(original)).resolve()
    identity = metadata.get('library_id')
    if identity:
        if library_identity(root) != identity:
            raise ValueError('packet library identity does not match attached root')
    elif root != Path(original).resolve():
        raise ValueError('legacy packet has no library identity; migrate its evidence before rebinding')
    if not root.is_dir():
        raise ValueError(f'sample root is unavailable: {root}')
    return root
