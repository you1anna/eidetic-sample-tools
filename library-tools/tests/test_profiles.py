from pathlib import Path

import pytest

from librarytools.profiles import ProfileError, resolve_profile, validate_source_kb


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_resolve_eidetic_profile_models_actionable_studio_capabilities(monkeypatch, tmp_path):
    monkeypatch.delenv("MUSIC_TOOLS_PROFILE", raising=False)
    profile = resolve_profile("eidetic-studio", config_path=tmp_path / "missing.toml")

    assert profile.session_rate == 48_000
    assert profile.clock_master == "octatrack-mkii"
    assert profile.source_version == "v2.4"
    assert profile.device("digitakt-mki").sample_rate == 48_000
    assert profile.device("digitakt-mki").probationary is True
    assert profile.device("octatrack-mkii").sample_rate == 44_100
    assert profile.device("tr8s").import_root == "ROLAND/TR-8S/SAMPLE"
    assert profile.capture_inputs["7-8"].role == "soundcraft-main-sum"
    assert "octatrack-usb-cf-only" in profile.constraints


def test_profile_precedence_cli_then_environment_then_local_config(monkeypatch, tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('profile = "eidetic-studio"\n', encoding="utf-8")
    monkeypatch.setenv("MUSIC_TOOLS_PROFILE", "eidetic-studio")

    assert resolve_profile("eidetic-studio", config_path=config).id == "eidetic-studio"
    assert resolve_profile(None, config_path=config).id == "eidetic-studio"


def test_unknown_profile_is_rejected(tmp_path):
    with pytest.raises(ProfileError, match="unknown studio profile"):
        resolve_profile("missing", config_path=tmp_path / "missing.toml")


def test_source_kb_validation_reads_header_only(tmp_path):
    kb = tmp_path / "studio.md"
    kb.write_text(
        "# Eidetic Studio — Knowledge Base\n\n"
        "**Document version:** v2.4\n"
        "**Last updated:** 2026-07-09\n"
        "archive should never be inspected\n",
        encoding="utf-8",
    )
    profile = resolve_profile("eidetic-studio", config_path=tmp_path / "missing.toml")

    assert validate_source_kb(profile, kb) == []


def test_source_kb_validation_reports_version_drift(tmp_path):
    kb = tmp_path / "studio.md"
    kb.write_text("**Document version:** v2.5\n**Last updated:** 2026-07-10\n", encoding="utf-8")
    profile = resolve_profile("eidetic-studio", config_path=tmp_path / "missing.toml")

    warnings = validate_source_kb(profile, kb)
    assert any("version" in warning for warning in warnings)
    assert any("updated" in warning for warning in warnings)
