"""Shared data shapes and constants for sample analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import config

AUDIO_EXTS: frozenset[str] = config.SOURCE_EXTS
DOC_EXTS: frozenset[str] = frozenset({".pdf", ".txt", ".md", ".rtf", ".nfo", ".url"})
DEVICE_SAMPLE_EXTS: frozenset[str] = frozenset({".wav", ".aif", ".aiff"})
DEVICE_SKIP_TOKENS: tuple[str, ...] = ("audio demo", "demo", "preview", "audition")
CURATED_ONE_SHOT_ROLES: frozenset[str] = frozenset({"KICKS", "CLAP-SNARE", "HATS-CYM", "PERC"})
CURATED_LONG_AUDIO_SECONDS: float = 3.0
CURATED_LONG_TAIL_MS: float = 3000.0
_ROLE_SIGNAL_SPLIT_RE = re.compile(r"[^a-z0-9]+")
ROLE_CONFLICT_SIGNALS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("KICKS", ("bassdrum", "bass drum", "bdrum", "kick", "kicks", "bd")),
    ("CLAP-SNARE", ("clap", "claps", "snare", "snares", "rim", "sd", "rs")),
    ("HATS-CYM", ("hihat", "hi hat", "hat", "hats", "hh", "cymbal", "cym", "ride", "crash", "shaker")),
    ("PERC", (
        "perc", "percussion", "conga", "bongo", "tom", "agogo", "tribal",
        "cabasa", "cabassa", "cow", "clave", "block", "tamb", "quijada",
        "timbale", "timb", "tabla", "triangle", "guiro", "maraca", "whistle",
        "finger", "fingers",
    )),
    ("DRUM-LOOPS", ("drum loop", "top loop", "beat loop", "loop", "loops", "groove", "grooves")),
    ("BASS", ("bass", "reese")),
    ("SYNTH-STAB-CHORD", ("synth", "stab", "chord", "pluck", "arp", "lead", "sh101", "acid", "guitar", "keys", "piano")),
    ("DRONE-ATMOS", ("drone", "drones", "pad", "pads", "atmos", "ambience", "ambient", "texture", "textures", "field")),
    ("FX-RISE-IMPACT", (
        "fx", "sfx", "impact", "riser", "rise", "uplifter", "downlifter",
        "sweep", "swell", "noise", "scratch", "door", "chime",
    )),
    ("VOCALS", ("vocal", "vocals", "vox", "voice", "voices", "acapella", "accapella")),
)


@dataclass(frozen=True)
class OtSet:
    set_name: str
    project_root: Path
    audio_pool_root: Path
    project_file_count: int
    strd_file_count: int
    audio_file_count: int
    doc_path: Path | None
    inferred_device: str = "octatrack"
    handling_policy: str = "preserve-set"


@dataclass(frozen=True)
class SourceRow:
    path: Path
    source_kind: str
    source_name: str
    processing_tag: str
    processing_reason: str


@dataclass(frozen=True)
class FeatureRow:
    path: Path
    source_kind: str
    source_name: str
    role: str
    sample_type: str
    bpm: str
    key: str
    tempo_fit: str
    duration: float | None
    duration_s: float | None
    peak: float | None
    rms: float | None
    crest: float | None
    attack_ms: float | None
    tail_ms: float | None
    head_silence_ms: float | None
    tail_silence_ms: float | None
    centroid_hz: float | None
    flatness: float | None
    sub_ratio: float | None
    low_ratio: float | None
    mid_ratio: float | None
    high_ratio: float | None
    onset_density: float | None
    zcr: float | None
    audio_error: str
    proposed_name: str
    review_reason: str
    processing_tag: str
    processing_reason: str
    character_tags: str
    tag_reasons: str


@dataclass(frozen=True)
class CrateEntry:
    path: Path
    reason: str


@dataclass(frozen=True)
class ClusterRow:
    path: Path
    role: str
    cluster_label: str
    distance_to_centroid: float
    is_representative: bool


@dataclass(frozen=True)
class CuratedRoleConflict:
    path: Path
    current_role: str
    issues: str
    reasons: str
    suggested_action: str


@dataclass(frozen=True)
class KickGateRow:
    path: Path
    current_role: str
    sample_type: str
    duration_s: float | None
    attack_ms: float | None
    tail_ms: float | None
    sub_ratio: float | None
    low_ratio: float | None
    mid_ratio: float | None
    high_ratio: float | None
    centroid_hz: float | None
    flatness: float | None
    onset_density: float | None
    zcr: float | None
    kick_gate: str
    confidence: str
    reasons: str
    review_action: str
