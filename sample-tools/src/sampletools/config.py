"""Paths and per-device export specifications.

All values are overridable via environment variables so the tool works even if
the SSD mounts at a different point or the library is relocated:

    SAMPLES_ROOT   required unless --root is supplied
    EXPORT_ROOT    default: <SAMPLES_ROOT>/_EXPORT
"""

from __future__ import annotations

import os
import math
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

SAMPLES_ROOT = Path(os.environ['SAMPLES_ROOT']).expanduser() if os.environ.get('SAMPLES_ROOT', '').strip() else None
EXPORT_ROOT = (Path(os.environ['EXPORT_ROOT']).expanduser() if os.environ.get('EXPORT_ROOT', '').strip()
               else SAMPLES_ROOT / '_EXPORT' if SAMPLES_ROOT else None)


def require_root(root: Path | None) -> Path:
    if root is None:
        raise ValueError('No sample library selected; pass --root PATH or set SAMPLES_ROOT.')
    return Path(root).expanduser()
DEFAULT_PROFILE_CONFIG = Path.home() / ".config" / "eidetic-sample-tools" / "config.toml"

# Source extensions ffmpeg can decode into our 16-bit/44.1 WAV target.
SOURCE_EXTS: tuple[str, ...] = (".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg")


@dataclass(frozen=True)
class DeviceSpec:
    """Target audio format + filename constraints for one piece of hardware."""

    name: str          # canonical lowercase key
    export_dir: str    # subfolder name under EXPORT_ROOT
    rate: int          # sample rate (Hz)
    bits: int          # bit depth
    channels: int | None  # 1 = force mono fold-down; None = preserve source
    name_warn: int     # warn if the output basename exceeds this many chars
    can_sync: bool     # True if a mounted card can receive a plain file copy
    sync_note: str     # guidance shown when --sync is used
    max_project_samples: int | None = None
    max_folder_files: int | None = None
    max_total_seconds: float | None = None

    @property
    def codec(self) -> str:
        # 16-bit little-endian PCM WAV. (AIFF would be s16be — not used here.)
        return "pcm_s16le"


DEVICE_SPECS: dict[str, DeviceSpec] = {
    "octatrack": DeviceSpec(
        name="octatrack",
        export_dir="OCTATRACK",
        rate=44100,
        bits=16,
        channels=None,  # OT handles mono + stereo
        name_warn=64,
        can_sync=True,  # CF card is a plain filesystem
        sync_note="Octatrack reads WAVs from any folder on the CF card.",
    ),
    "digitakt": DeviceSpec(
        name="digitakt",
        export_dir="DIGITAKT",
        rate=48000,
        bits=16,
        channels=1,  # Digitakt MK1 is mono-only
        max_project_samples=127,
        name_warn=24,  # small screen; long names truncate
        can_sync=False,  # +Drive is not a mountable disk
        sync_note=(
            "Digitakt +Drive is not a plain disk — drag the staged folder into the "
            "Elektron Transfer app instead of using --sync."
        ),
    ),
    "tr8s": DeviceSpec(
        name="tr8s",
        export_dir="TR8S",
        rate=48000,
        bits=16,
        channels=1,  # efficient default for drum one-shots; crate rows may preserve stereo
        max_folder_files=256,
        max_total_seconds=600.0,
        name_warn=120,
        can_sync=True,  # SD card is a plain filesystem
        sync_note=(
            "Copies to the SD card; you may still need to Import the samples from the "
            "TR-8S front panel depending on firmware."
        ),
    ),
}


def get_spec(device: str) -> DeviceSpec:
    key = device.strip().lower()
    if key not in DEVICE_SPECS:
        valid = ", ".join(sorted(DEVICE_SPECS))
        raise KeyError(f"unknown device {device!r}; valid devices: {valid}")
    return DEVICE_SPECS[key]


def get_profile_spec(
    device: str, profile: str | None, *, profile_root: Path | None = None,
) -> DeviceSpec:
    """Resolve sample conversion capability from a portable profile."""
    base = get_spec(device)
    if profile is None:
        profile = os.environ.get("MUSIC_TOOLS_PROFILE")
    if profile is None and DEFAULT_PROFILE_CONFIG.is_file():
        with DEFAULT_PROFILE_CONFIG.open("rb") as fh:
            profile = tomllib.load(fh).get("profile")
    if not profile:
        return base
    if profile_root is None:
        profile_root = Path(__file__).resolve().parents[3] / "profiles"
        if not profile_root.is_dir():
            profile_root = Path(__file__).parent / 'resources' / 'profiles'
    studio_path = profile_root / "studios" / f"{profile}.toml"
    if not studio_path.is_file():
        raise KeyError(f"unknown studio profile {profile!r}")
    with studio_path.open("rb") as fh:
        studio = tomllib.load(fh)
    device_id = {"digitakt": "digitakt-mki", "octatrack": "octatrack-mkii", "tr8s": "tr8s"}[base.name]
    if device_id not in {
        item.get("id") for item in studio.get("devices", []) if item.get("enabled", True)
    }:
        raise KeyError(f"device {device_id!r} is not enabled by profile {profile!r}")
    with (profile_root / "devices" / f"{device_id}.toml").open("rb") as fh:
        raw = tomllib.load(fh)
    channels = {"mono": 1, "mono-default": 1, "preserve": None}[str(raw["channels"])]
    capacities = {
        field: raw.get(field, getattr(base, field))
        for field in ("max_project_samples", "max_folder_files", "max_total_seconds")
    }
    for field, value in capacities.items():
        if value is None:
            continue
        valid_types = (int, float) if field == "max_total_seconds" else (int,)
        if type(value) not in valid_types or not math.isfinite(value) or value <= 0:
            raise ValueError(f"invalid device capacity {field}: expected a positive finite number")
    return replace(
        base, rate=int(raw["sample_rate"]), bits=int(raw["bits"]), channels=channels,
        **capacities,
    )


def manifest_path(device: str, *, samples_root: Path | None = None) -> Path:
    """Prefer the selected library's manifest, then checkout or packaged defaults."""
    root = samples_root or SAMPLES_ROOT
    if root is not None:
        portable = root / '.eidetic' / 'manifests' / f'{get_spec(device).name}.txt'
        if portable.is_file():
            return portable
    legacy = Path(__file__).resolve().parents[2] / "manifests" / f"{get_spec(device).name}.txt"
    return legacy if legacy.is_file() else Path(__file__).parent / 'resources' / 'manifests' / f'{get_spec(device).name}.txt'
