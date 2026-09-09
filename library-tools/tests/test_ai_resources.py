import subprocess

import pytest

from librarytools.classification.cache import EmbeddingCache
from librarytools.classification.domain import ClassificationError
from librarytools.classification.models import ModelSpec
from librarytools.classification.workers import EmbeddingWorker


@pytest.mark.parametrize('options', [{'batch_size': 0}, {'threads': 0}, {'timeout': 0}, {'timeout': float('inf')}])
def test_invalid_worker_limits_fail_before_starting_process(tmp_path, monkeypatch, options):
    cache = EmbeddingCache(tmp_path / 'cache.sqlite')
    def forbidden(*args, **kwargs):
        pytest.fail('invalid resource limits started a worker')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    with pytest.raises(ClassificationError):
        EmbeddingWorker().run(ModelSpec('fake', 'revision'), [], cache, **options)


def test_worker_timeout_is_bounded_and_actionable(tmp_path, monkeypatch):
    cache = EmbeddingCache(tmp_path / 'cache.sqlite')
    def timeout(command, **kwargs):
        assert kwargs['timeout'] == 3
        assert kwargs['env']['OMP_NUM_THREADS'] == '2'
        raise subprocess.TimeoutExpired(command, kwargs['timeout'])
    monkeypatch.setattr(subprocess, 'run', timeout)
    with pytest.raises(ClassificationError, match='timed out.*cached batches'):
        EmbeddingWorker().run(ModelSpec('fake', 'revision'), [], cache, threads=2, timeout=3)
