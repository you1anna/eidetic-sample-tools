"""Collection roles and configurable selection targets, independent of hardware."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


ONE_SHOT_ROLES = (
    "KICK", "SNARE", "CLAP", "RIM", "HAT-CLOSED", "HAT-OPEN", "SHAKER",
    "CYMBAL", "RIDE", "TOM", "PERC", "BASS", "STAB-CHORD", "FX", "VOCAL",
)
LONG_ROLES = ("DRUM-LOOP", "BASS-LOOP", "SYNTH-LOOP", "VOCAL-LOOP", "TEXTURE-DRONE")
TRUSTED_ROLES = frozenset((*ONE_SHOT_ROLES, *LONG_ROLES))
PILOT_QUOTAS = {
    "KICK": 12, "SNARE": 8, "CLAP": 8, "RIM": 4, "HAT-CLOSED": 10,
    "HAT-OPEN": 8, "SHAKER": 6, "CYMBAL": 4, "RIDE": 4, "TOM": 8,
    "PERC": 10, "BASS": 4, "STAB-CHORD": 4, "FX": 4, "VOCAL": 2,
    "DRUM-LOOP": 4, "BASS-LOOP": 2, "SYNTH-LOOP": 2,
    "VOCAL-LOOP": 4, "TEXTURE-DRONE": 4,
}


class CurationPolicyError(ValueError):
    pass


def load_quotas(path: Path | None) -> dict[str, int] | None:
    if path is None:
        return None
    try:
        with path.open("rb") as handle:
            quotas = tomllib.load(handle).get("quotas")
    except tomllib.TOMLDecodeError as exc:
        raise CurationPolicyError(f"invalid quotas in {path}: {exc}") from exc
    if not isinstance(quotas, dict) or not quotas:
        raise CurationPolicyError("invalid quotas: provide a non-empty [quotas] table")
    for role, count in quotas.items():
        if role not in TRUSTED_ROLES or type(count) is not int or count < 0:
            raise CurationPolicyError(
                f"invalid quotas: {role} must be a canonical role with a non-negative integer target"
            )
    if not any(quotas.values()):
        raise CurationPolicyError("invalid quotas: at least one target must be positive")
    return quotas


def validate_crate_name(name: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
        raise CurationPolicyError("crate name must use letters, digits, hyphens or underscores")
