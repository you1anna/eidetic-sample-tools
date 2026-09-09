"""Small, versioned evidence files for rebuildable exports and transfers."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .config import DeviceSpec
from .convert import _ffmpeg_bin


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def runtime() -> dict[str, str]:
    try:
        package_version = version('sampletools')
    except PackageNotFoundError:
        package_version = 'uninstalled'
    result = subprocess.run([_ffmpeg_bin(), '-version'], capture_output=True, text=True, check=True)
    return {'tool_version': package_version, 'ffmpeg_version': result.stdout.splitlines()[0]}


def settings(spec: DeviceSpec) -> dict:
    return {'device': spec.name, 'rate': spec.rate, 'bits': spec.bits,
            'channels': spec.channels, 'codec': spec.codec, 'container': 'wav',
            'conversion_version': 1}


def receipt_path(output: Path) -> Path:
    return output.with_suffix(output.suffix + '.receipt.json')


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.tmp', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write('\n')
            fh.flush()
            os.fsync(fh.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_receipt(output: Path) -> dict | None:
    try:
        data = json.loads(receipt_path(output).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get('format') != 'eidetic-export' or type(data.get('version')) is not int or data['version'] != 1:
        return None
    return data


def check(output: Path, source_hash: str, spec: DeviceSpec, versions: dict) -> str:
    if not output.exists():
        return 'new'
    data = read_receipt(output)
    if data is None:
        return 'unverified: receipt missing, invalid or unsupported'
    if data.get('source_sha256') != source_hash:
        return 'stale: source changed'
    if data.get('settings') != settings(spec):
        return 'stale: conversion settings changed'
    if any(data.get(key) != value for key, value in versions.items()):
        return 'stale: conversion software changed'
    if data.get('output_sha256') != sha256(output):
        return 'damaged: output hash changed'
    return 'verified'


def make(output: Path, source: Path, source_hash: str, spec: DeviceSpec,
         versions: dict, *, root: Path | None = None, library_id: str | None = None) -> dict:
    relative_source = source.resolve()
    if root is not None and relative_source.is_relative_to(root.resolve()):
        relative_source = relative_source.relative_to(root.resolve())
    return {'format': 'eidetic-export', 'version': 1, 'created_at': now(),
            'source_path': relative_source.as_posix(), 'source_sha256': source_hash,
            'library_id': library_id, 'settings': settings(spec), **versions,
            'output_sha256': sha256(output), 'output_size': output.stat().st_size,
            'software_validation': 'passed', 'hardware_verification': 'unverified'}
