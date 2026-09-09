import json
import sys
from types import SimpleNamespace

import pytest

from librarytools import ai_cli


def test_doctor_reports_missing_dependencies_without_loading_models(monkeypatch, capsys):
    monkeypatch.setattr(ai_cli, 'installed_versions', lambda: {'torch': None})
    assert ai_cli.main(['doctor']) == 2
    report = json.loads(capsys.readouterr().out)
    assert report['packages']['torch'] is None
    assert len(report['models']) == 2


def test_download_requests_only_pinned_models_and_required_files(monkeypatch):
    calls = []
    def download(**kwargs):
        calls.append(kwargs)
        return '/cache/model'
    monkeypatch.setitem(sys.modules, 'huggingface_hub', SimpleNamespace(snapshot_download=download))
    assert len(ai_cli.download_models()) == 2
    assert [(c['repo_id'], c['revision']) for c in calls] == [(m.model_id, m.revision) for m in ai_cli.MODEL_SPECS]
    assert all(c['max_workers'] == 2 and c['allow_patterns'] == list(ai_cli.MODEL_FILES) for c in calls)


def test_check_is_offline_and_restores_environment_after_failure(monkeypatch):
    import os
    from librarytools.classification import workers
    monkeypatch.delenv('HF_HUB_OFFLINE', raising=False)
    monkeypatch.setenv('DO_NOT_TRACK', 'existing')
    def fail(*args, **kwargs):
        assert os.environ['HF_HUB_OFFLINE'] == '1'
        assert kwargs == {'batch_size': 1, 'threads': 1, 'timeout': 10}
        raise ValueError('synthetic failure')
    monkeypatch.setattr(workers, 'generate_model_votes', fail)
    with pytest.raises(ValueError, match='synthetic failure'):
        ai_cli.check_models(threads=1, timeout=10)
    assert 'HF_HUB_OFFLINE' not in os.environ
    assert os.environ['DO_NOT_TRACK'] == 'existing'
