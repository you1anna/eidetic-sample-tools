"""Install-time model download and offline verification using synthetic audio only."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import sys
import tempfile
import time

from .classification.models import MODEL_SPECS
from .classification.workers import DEFAULT_TIMEOUT, validate_worker_limits

MODEL_FILES = ('config.json', 'preprocessor_config.json', 'pytorch_model.bin',
               'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json',
               'vocab.json', 'merges.txt')


def download_models() -> list[dict]:
    from huggingface_hub import snapshot_download
    results = []
    for spec in MODEL_SPECS:
        print(f'Downloading/checking {spec.model_id}@{spec.revision}', file=sys.stderr, flush=True)
        path = snapshot_download(repo_id=spec.model_id, revision=spec.revision,
                                 allow_patterns=list(MODEL_FILES), max_workers=2)
        results.append({'model_id': spec.model_id, 'revision': spec.revision, 'path': path})
    return results


def check_models(*, threads: int = 2, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Exercise both real workers and cache reuse, always without network access."""
    import numpy as np
    import soundfile as sf
    from .classification.cache import EmbeddingCache
    from .classification.workers import SampleRef, generate_model_votes

    validate_worker_limits(1, threads, timeout)
    # Worker imports happen in fresh processes, so these settings take effect
    # even if another command imported huggingface_hub in the parent already.
    keys = ('HF_HUB_OFFLINE', 'HF_HUB_DISABLE_TELEMETRY', 'DO_NOT_TRACK')
    previous = {key: os.environ.get(key) for key in keys}
    try:
        os.environ.update({key: '1' for key in keys})
        with tempfile.TemporaryDirectory(prefix='eidetic-ai-check-') as directory:
            scratch = Path(directory)
            path = scratch / 'tone.wav'
            sf.write(path, np.sin(2 * np.pi * 220 * np.arange(48000) / 48000), 48000)
            samples = [SampleRef(hashlib.sha256(path.read_bytes()).hexdigest(), path)]
            cache = EmbeddingCache(scratch / 'library.sqlite')
            started = time.monotonic()
            votes, cold = generate_model_votes(MODEL_SPECS, samples, cache,
                                              batch_size=1, threads=threads, timeout=timeout)
            cold_seconds = time.monotonic() - started
            started = time.monotonic()
            cached_votes, warm = generate_model_votes(MODEL_SPECS, samples, cache,
                                                     batch_size=1, threads=threads, timeout=timeout)
            warm_seconds = time.monotonic() - started
            if (votes != cached_votes or any(r.embedded != 1 for r in cold)
                    or any(r.embedded != 0 or r.cache_hits != 1 or not r.prompt_cache_hit for r in warm)):
                raise ValueError('model/cache verification failed')
            return {'verified': True, 'offline': True, 'synthetic_samples': 1,
                    'threads': threads, 'cold_seconds': round(cold_seconds, 3),
                    'cached_seconds': round(warm_seconds, 3),
                    'workers': [asdict(report) for report in cold],
                    'packages': installed_versions()}
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def installed_versions() -> dict:
    result = {}
    for name in ('librarytools', 'torch', 'transformers', 'librosa', 'numpy', 'soundfile', 'huggingface-hub'):
        try:
            result[name] = version(name)
        except PackageNotFoundError:
            result[name] = None
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('doctor', help='show installed versions without loading models or accessing the network')
    commands.add_parser('download', help='explicitly download the two pinned checkpoints to the Hugging Face cache')
    check = commands.add_parser('check', help='test both cached models offline on one synthetic sound; never scans a library')
    check.add_argument('--threads', type=int, default=2)
    check.add_argument('--worker-timeout', type=float, default=DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)
    try:
        if args.command == 'doctor':
            packages = installed_versions()
            print(json.dumps({'packages': packages, 'models': [asdict(spec) for spec in MODEL_SPECS]}, indent=2))
            return 0 if all(packages.values()) else 2
        if args.command == 'download':
            report = {'models': download_models()}
        else:
            report = check_models(threads=args.threads, timeout=args.worker_timeout)
        print(json.dumps(report, indent=2))
        return 0
    except (ImportError, ValueError, OSError) as exc:
        print(f'AI setup failed: {exc}\nUse the pinned AI installation; run sample-ai download before the offline check.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
