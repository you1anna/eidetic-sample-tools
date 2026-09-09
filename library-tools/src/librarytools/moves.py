"""Filesystem mutations: move-only, never overwrite, always reversible."""

from __future__ import annotations

import ctypes
import errno
import os
import sys
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Move:
    src: Path
    dest: Path
    tag: str  # bucket name (classify) or reason (dedupe)


def _rename_exclusive(src: Path, dest: Path) -> None:
    """Use the platform's atomic no-replace rename; never fall back to overwrite."""
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == 'darwin':
        rename = libc.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(os.fsencode(src), os.fsencode(dest), 0x00000004)  # RENAME_EXCL
    elif sys.platform.startswith('linux') and hasattr(libc, 'renameat2'):
        rename = libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(-100, os.fsencode(src), -100, os.fsencode(dest), 1)  # RENAME_NOREPLACE
    else:
        raise OSError(errno.ENOTSUP, 'atomic no-replace moves require macOS or Linux', str(src))
    if result:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(dest))


def safe_move(src: Path, dest: Path) -> str:
    """Move within one filesystem. Cross-filesystem moves fail without deleting data."""
    from .operations import sync_directory
    if not src.exists():
        return 'missing'
    if dest.exists() or dest.is_symlink():
        return 'exists'
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        _rename_exclusive(src, dest)
    except FileExistsError:
        return 'exists'
    except FileNotFoundError:
        return 'missing'
    sync_directory(dest.parent)
    if src.parent != dest.parent:
        sync_directory(src.parent)
    return 'moved'


def write_plan(path: Path, plan: list[Move]) -> None:
    """Write the planned moves as a TSV: src<TAB>dest<TAB>tag."""
    from .locking import library_lock
    portable_root = next((parent.parent for parent in path.absolute().parents
                          if parent.name == '.eidetic'), None)
    lock = library_lock(portable_root, purpose='write move preview', allow_recovery=True) if portable_root is not None else nullcontext()
    with lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for m in plan:
                fh.write(f"{m.src}\t{m.dest}\t{m.tag}\n")
        from .operations import atomic_json, sidecars
        dependencies = [{"audio": str(item.src), "path": path, "action": "retained at source; review dependency before applying"}
                        for item in plan for path in sidecars(item.src)]
        if dependencies:
            atomic_json(path.with_suffix(path.suffix + ".dependencies.json"), {"schema_version": 1, "sidecars": dependencies})


def apply_plan(plan: list[Move], undo_path: Path, *, root: Path | None = None) -> dict[str, int]:
    """Execute one durable plan; identical retries verify bytes and rebuild its undo."""
    from . import operations
    from .locking import library_lock
    if root is None:
        parents = [str(path.absolute().parent) for item in plan for path in (item.src, item.dest)]
        root = Path(os.path.commonpath(parents)) if parents else undo_path.absolute().parent
    root = root.resolve()
    if not root.is_dir():
        raise operations.OperationError(f'library root is missing: {root}')
    undo_path = undo_path.absolute()
    undo_relative = undo_path.relative_to(root).as_posix() if undo_path.is_relative_to(root) else None
    key = undo_relative or str(undo_path)
    with library_lock(root, purpose='apply move plan', allow_recovery=True):
        signature = [{'source': item.src.absolute().relative_to(root).as_posix(),
                      'destination': item.dest.absolute().relative_to(root).as_posix(), 'tag': item.tag}
                     for item in plan]
        existing = operations.find_operation(root, 'moves', key)
        if existing:
            path, data = existing
            if data['plan'] != signature:
                raise operations.OperationError('undo path belongs to another plan; choose a fresh undo path')
        else:
            if undo_path.exists() or undo_path.is_symlink():
                raise operations.OperationError(f'undo path exists without this operation: {undo_path}')
            items = []
            for planned in signature:
                source = operations.contained(root, planned['source'])
                destination = operations.contained(root, planned['destination'])
                status = 'missing' if not source.exists() else 'exists' if destination.exists() or destination.is_symlink() else 'pending'
                items.append({**planned, 'action': 'move', 'status': status,
                              'fingerprint': operations.fingerprint(source) if status == 'pending' else None,
                              'sidecars_left_at_source': operations.sidecars(source)})
            path, data = operations.create_operation(root, 'moves', key, items,
                                                       plan=signature, undo_path=str(undo_path),
                                                       undo_relative=undo_relative)
        operations.resume_operation(root, path, data, write_legacy_undo=True)
        return {'moved': sum(item['status'] == 'complete' for item in data['items']),
                'exists': sum(item['status'] == 'exists' for item in data['items']),
                'missing': sum(item['status'] == 'missing' for item in data['items'])}
