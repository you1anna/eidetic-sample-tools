"""Portable studio/device profile loading.

Profiles contain actionable capabilities only.  The external Studio knowledge
base remains the authority for cabling and physical setup detail.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path


PROFILE_ROOT = Path(__file__).resolve().parents[3] / "profiles"
DEFAULT_CONFIG = Path.home() / ".config" / "eidetic-music-tools" / "config.toml"
_VERSION_RE = re.compile(r"\*\*Document version:\*\*\s*([^\s]+)")
_UPDATED_RE = re.compile(r"\*\*Last updated:\*\*\s*(\d{4}-\d{2}-\d{2})")


class ProfileError(ValueError):
    pass


@dataclass(frozen=True)
class DeviceProfile:
    id: str
    display_name: str
    role: str = ""
    enabled: bool = True
    sample_rate: int = 44_100
    bits: int = 16
    channels: str = "preserve"
    transfer: str = "manual"
    import_root: str = ""
    max_project_samples: int | None = None
    max_total_samples: int | None = None
    max_folder_files: int | None = None
    max_total_seconds: float | None = None
    max_folder_depth: int | None = None
    preserves_stereo: bool = True
    timestretch: bool = False
    probationary: bool = False
    usb_audio: bool = False
    usb_midi: bool = False


@dataclass(frozen=True)
class CaptureInput:
    channels: str
    role: str
    physical: str


@dataclass(frozen=True)
class StudioProfile:
    id: str
    display_name: str
    source_document: str
    source_version: str
    source_updated: str
    session_rate: int
    ableton_version: str
    clock_master: str
    primary_audition: str
    primary_performance_sampler: str
    devices: tuple[DeviceProfile, ...]
    capture_inputs: dict[str, CaptureInput]
    constraints: tuple[str, ...]

    def device(self, device_id: str) -> DeviceProfile:
        for item in self.devices:
            if item.id == device_id:
                return item
        raise ProfileError(f"unknown device {device_id!r} in profile {self.id!r}")


def _read_toml(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError as exc:
        raise ProfileError(f"profile file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"invalid TOML in {path}: {exc}") from exc
    if data.get("schema_version") != 1:
        raise ProfileError(f"unsupported profile schema in {path}")
    return data


def _selected_name(name: str | None, config_path: Path) -> str:
    if name:
        return name
    if env_name := os.environ.get("MUSIC_TOOLS_PROFILE"):
        return env_name
    if config_path.is_file():
        data = _read_local_config(config_path)
        if configured := data.get("profile"):
            return str(configured)
    return "eidetic-studio"


def _read_local_config(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"invalid local config {path}: {exc}") from exc


def resolve_profile(
    name: str | None = None,
    config_path: Path | None = None,
    profile_root: Path = PROFILE_ROOT,
) -> StudioProfile:
    config_path = config_path or DEFAULT_CONFIG
    selected = _selected_name(name, config_path)
    studio_path = profile_root / "studios" / f"{selected}.toml"
    if not studio_path.is_file():
        raise ProfileError(f"unknown studio profile {selected!r}")
    studio = _read_toml(studio_path)

    devices: list[DeviceProfile] = []
    for binding in studio.get("devices", []):
        if not isinstance(binding, dict) or "id" not in binding:
            raise ProfileError(f"malformed device binding in {studio_path}")
        device_id = str(binding["id"])
        raw = _read_toml(profile_root / "devices" / f"{device_id}.toml")
        raw.pop("schema_version", None)
        device = DeviceProfile(**raw)
        devices.append(replace(
            device,
            role=str(binding.get("role", "")),
            enabled=bool(binding.get("enabled", True)),
        ))

    capture = {
        channels: CaptureInput(channels, str(value["role"]), str(value["physical"]))
        for channels, value in dict(studio.get("capture_inputs", {})).items()
    }
    constraints = tuple(str(item) for item in studio.get("constraints", []))
    return StudioProfile(
        id=str(studio["id"]),
        display_name=str(studio["display_name"]),
        source_document=str(studio["source_document"]),
        source_version=str(studio["source_version"]),
        source_updated=str(studio["source_updated"]),
        session_rate=int(studio["session_rate"]),
        ableton_version=str(studio["ableton_version"]),
        clock_master=str(studio["clock_master"]),
        primary_audition=str(studio["primary_audition"]),
        primary_performance_sampler=str(studio["primary_performance_sampler"]),
        devices=tuple(devices),
        capture_inputs=capture,
        constraints=constraints,
    )


def validate_source_kb(profile: StudioProfile, path: Path) -> list[str]:
    try:
        header = "\n".join(path.read_text(encoding="utf-8").splitlines()[:40])
    except OSError as exc:
        raise ProfileError(f"cannot read Studio KB {path}: {exc}") from exc
    version = _VERSION_RE.search(header)
    updated = _UPDATED_RE.search(header)
    warnings: list[str] = []
    if not version or version.group(1) != profile.source_version:
        found = version.group(1) if version else "missing"
        warnings.append(f"source version drift: profile={profile.source_version}, kb={found}")
    if not updated or updated.group(1) != profile.source_updated:
        found = updated.group(1) if updated else "missing"
        warnings.append(f"source updated drift: profile={profile.source_updated}, kb={found}")
    return warnings
