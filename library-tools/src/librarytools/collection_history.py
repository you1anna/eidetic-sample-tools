"""Read explicit export records without claiming approval or current device presence.

Only receipt JSON and delegated-library manifests are read. Source/output paths in
those records are deliberately ignored; history is an identity-based planning hint.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import stat
from pathlib import Path
from typing import Sequence

_DEVICES = frozenset({'octatrack', 'digitakt', 'tr8s'})
_FORMATS = frozenset({'eidetic-export', 'eidetic-delegated-library-v1'})
_MAX_JSON_BYTES = 32 * 1024 * 1024
_SHA256 = re.compile(r'[0-9a-fA-F]{64}\Z')
_SNAPSHOT_FIELDS = {'version', 'library_id', 'device', 'coverage', 'sample_ids', 'sources'}
_SOURCE_FIELDS = {'name', 'sha256', 'format', 'library_id', 'scope',
                  'records_total', 'records_for_device'}


def _request_identity(library_id: str, device: str) -> None:
    if not isinstance(library_id, str) or not library_id.strip():
        raise ValueError('Provide a non-empty library_id for collection history.')
    _device(device)


def _device(value: object) -> str:
    if not isinstance(value, str) or value not in _DEVICES:
        raise ValueError('device must be octatrack, digitakt or tr8s.')
    return value


def _hash(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f'{field} must be a 64-character SHA-256 hex digest.')
    return value.lower()


def _record_library(value: object, library_id: str) -> str | None:
    if value is None or value == '':
        return None
    if not isinstance(value, str):
        raise ValueError('library_id must be a string or null in history evidence.')
    if value != library_id:
        raise ValueError('History library_id belongs to another library; supply matching evidence.')
    return value


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key {key!r}')
        result[key] = value
    return result


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f'non-finite JSON number {value}')
    return parsed


def _reject_constant(value: str) -> None:
    raise ValueError(f'non-finite JSON number {value}')


def _reject_symlink(path: Path) -> None:
    # Inspect ancestors too: opening a regular file through a linked directory
    # would otherwise follow evidence outside the explicitly chosen tree.
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError(f'History evidence contains a symlink: {component.name}; use a real path.')


def _evidence_files(paths: Sequence[Path]) -> list[Path]:
    found: set[Path] = set()
    for supplied in paths:
        path = Path(os.path.abspath(supplied))
        _reject_symlink(path)
        if path.is_dir():
            directory_receipts: list[Path] = []

            def walk_error(error: OSError) -> None:
                raise ValueError(f'Cannot read history directory {path.name}: {error.strerror}.') from error

            for current, dirs, names in os.walk(path, followlinks=False, onerror=walk_error):
                base = Path(current)
                for name in dirs:
                    if (base / name).is_symlink():
                        raise ValueError(f'History directory contains a symlink: {name}; use a real directory.')
                for name in names:
                    if name.endswith('.wav.receipt.json'):
                        candidate = base / name
                        _reject_symlink(candidate)
                        directory_receipts.append(candidate)
            if not directory_receipts:
                raise ValueError(f'No *.wav.receipt.json files found in history directory {path.name}.')
            found.update(directory_receipts)
        elif path.is_file():
            if path.suffix.lower() != '.json':
                raise ValueError(f'History input {path.name} must be a JSON file or receipt directory.')
            found.add(path)
        else:
            raise ValueError(f'History input does not exist or is not readable: {path.name}.')
    return sorted(found)


def _read_json(path: Path) -> tuple[dict, str]:
    try:
        # O_NOFOLLOW also closes the final-component symlink race after traversal.
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError('History JSON must be a regular file.')
            if info.st_size > _MAX_JSON_BYTES:
                raise ValueError('History JSON exceeds the 32 MiB limit; split the evidence into smaller files.')
            raw = stream.read(_MAX_JSON_BYTES + 1)
        if len(raw) > _MAX_JSON_BYTES:
            raise ValueError('History JSON exceeds the 32 MiB limit; split the evidence into smaller files.')
    except OSError as error:
        raise ValueError(f'Cannot read history JSON {path.name}: {error.strerror}.') from error
    try:
        value = json.loads(raw, object_pairs_hook=_no_duplicate_keys,
                           parse_constant=_reject_constant, parse_float=_finite_float)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValueError(f'Invalid history JSON {path.name}: {error}.') from error
    if not isinstance(value, dict):
        raise ValueError(f'History JSON {path.name} must contain an object.')
    return value, hashlib.sha256(raw).hexdigest()


def _parse_evidence(value: dict, *, library_id: str, device: str) -> tuple[str, str | None, list[str], int]:
    record_library = _record_library(value.get('library_id'), library_id)
    matches: list[str] = []
    if value.get('format') == 'eidetic-export':
        if type(value.get('version')) is not int or value['version'] != 1:
            raise ValueError('Unsupported eidetic-export version; expected integer version 1.')
        sample_id = _hash(value.get('source_sha256'), 'source_sha256')
        _hash(value.get('output_sha256'), 'output_sha256')
        settings = value.get('settings')
        record_device = _device(settings.get('device') if isinstance(settings, dict) else None)
        if value.get('software_validation') != 'passed':
            raise ValueError('Export receipt software_validation must be passed.')
        if record_device == device:
            matches.append(sample_id)
        return 'eidetic-export', record_library, matches, 1
    if value.get('schema') == 'eidetic-delegated-library-v1':
        items = value.get('items')
        if not isinstance(items, list) or not items:
            raise ValueError('Delegated-library history items must be a non-empty array.')
        for number, item in enumerate(items, 1):
            if not isinstance(item, dict):
                raise ValueError(f'History items record {number} must be an object.')
            sample_id = _hash(item.get('sample_id'), f'items[{number}].sample_id')
            _hash(item.get('output_sha256'), f'items[{number}].output_sha256')
            record_device = _device(item.get('device'))
            if record_device == device:
                matches.append(sample_id)
        return 'eidetic-delegated-library-v1', record_library, matches, len(items)
    raise ValueError('History JSON is not a recognized eidetic-export receipt or eidetic-delegated-library-v1 manifest.')


def load_history(paths: Sequence[Path], *, library_id: str, device: str) -> dict:
    """Load explicitly supplied evidence, deduplicated by original content hash.

    Directories contribute only recursive ``*.wav.receipt.json`` files. Coverage
    is limited to those supplied records even when every file parses correctly.
    """
    _request_identity(library_id, device)
    sample_ids: set[str] = set()
    sources: dict[tuple[str, str], dict] = {}
    for path in _evidence_files(paths):
        value, digest = _read_json(path)
        try:
            source_format, record_library, matches, total = _parse_evidence(
                value, library_id=library_id, device=device,
            )
        except ValueError as error:
            raise ValueError(f'Invalid history evidence {path.name}: {error}') from error
        sample_ids.update(matches)
        sources[(digest, path.name)] = {
            'name': path.name, 'sha256': digest, 'format': source_format,
            'library_id': record_library, 'scope': 'library' if record_library else 'reference',
            'records_total': total, 'records_for_device': len(matches),
        }
    return {
        'version': 1, 'library_id': library_id, 'device': device,
        'coverage': 'provided_records_only' if sources else 'unknown',
        'sample_ids': sorted(sample_ids), 'sources': [sources[key] for key in sorted(sources)],
    }


def validate_history_snapshot(value: object, *, library_id: str, device: str) -> dict:
    """Validate a saved plan's portable snapshot without reopening its evidence.

    This validates structure and identity, not the authenticity of a saved plan.
    Unknown fields are rejected to keep private paths and approval claims out of
    this intentionally narrow history format.
    """
    _request_identity(library_id, device)
    if not isinstance(value, dict) or set(value) != _SNAPSHOT_FIELDS:
        raise ValueError('History snapshot fields must match the version 1 schema.')
    if type(value['version']) is not int or value['version'] != 1:
        raise ValueError('History snapshot version must be integer 1.')
    if value['library_id'] != library_id:
        raise ValueError('History snapshot library_id does not match this library.')
    if value['device'] != device:
        raise ValueError('History snapshot device does not match this collection.')
    if value['coverage'] not in ('unknown', 'provided_records_only'):
        raise ValueError('History snapshot coverage must be unknown or provided_records_only.')
    ids = value['sample_ids']
    if not isinstance(ids, list):
        raise ValueError('History snapshot sample_ids must be a sorted unique list.')
    normal_ids = [_hash(sample_id, 'sample_ids') for sample_id in ids]
    if ids != sorted(set(normal_ids)):
        raise ValueError('History snapshot sample_ids must be sorted, unique lowercase SHA-256 values.')
    sources = value['sources']
    if not isinstance(sources, list):
        raise ValueError('History snapshot sources must be a list.')
    source_keys: list[tuple[str, str]] = []
    records_for_device = 0
    for source in sources:
        if not isinstance(source, dict) or set(source) != _SOURCE_FIELDS:
            raise ValueError('History snapshot source fields must match the version 1 schema.')
        name = source['name']
        if (not isinstance(name, str) or not name or name in ('.', '..')
                or '/' in name or '\\' in name or any(ord(char) < 32 for char in name)):
            raise ValueError('History snapshot source name must be a filename without a path.')
        digest = _hash(source['sha256'], 'source sha256')
        if digest != source['sha256']:
            raise ValueError('History snapshot source sha256 must use lowercase hex.')
        if not isinstance(source['format'], str) or source['format'] not in _FORMATS:
            raise ValueError('History snapshot source format is not recognized.')
        record_library = _record_library(source['library_id'], library_id)
        expected_scope = 'library' if record_library else 'reference'
        if source['library_id'] != record_library or source['scope'] != expected_scope:
            raise ValueError('History snapshot source scope must match its library_id (null for a reference).')
        total, matching = source['records_total'], source['records_for_device']
        if type(total) is not int or total < 1:
            raise ValueError('History snapshot records_total must be a positive integer.')
        if source['format'] == 'eidetic-export' and total != 1:
            raise ValueError('Export receipt records_total must be 1.')
        if type(matching) is not int or not 0 <= matching <= total:
            raise ValueError('History snapshot records_for_device must be an integer between zero and records_total.')
        records_for_device += matching
        source_keys.append((digest, name))
    if source_keys != sorted(set(source_keys)):
        raise ValueError('History snapshot sources must be sorted and unique by sha256 and name.')
    if value['coverage'] == 'unknown':
        if ids or sources:
            raise ValueError('History snapshot with unknown coverage must have no sample_ids or sources.')
    elif not sources:
        raise ValueError('History snapshot provided_records_only coverage requires sources.')
    if len(ids) > records_for_device or bool(ids) != bool(records_for_device):
        raise ValueError('History snapshot sample_ids are inconsistent with records_for_device counts.')
    return copy.deepcopy(value)
