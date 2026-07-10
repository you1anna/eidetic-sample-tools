"""Conflict, gate, cluster, and crate rules for sample analysis."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from . import review
from .analyze_features import _curated_folder_role, _fmt_num, _has, _reason
from .analyze_types import (
    CURATED_LONG_AUDIO_SECONDS,
    CURATED_LONG_TAIL_MS,
    CURATED_ONE_SHOT_ROLES,
    DEVICE_SAMPLE_EXTS,
    DEVICE_SKIP_TOKENS,
    ROLE_CONFLICT_SIGNALS,
    _ROLE_SIGNAL_SPLIT_RE,
    ClusterRow,
    CrateEntry,
    CuratedRoleConflict,
    FeatureRow,
    KickGateRow,
    OtSet,
)

try:
    import numpy as np
except ImportError:  # pragma: no cover - cluster output is skipped without Tier-1 deps.
    np = None  # type: ignore[assignment]

def _curated_content_path(rel: Path) -> Path:
    if len(rel.parts) >= 3 and rel.parts[0] == "CURATED":
        return Path(*rel.parts[2:])
    return rel


def _normalised_signal_text(rel: Path) -> tuple[str, set[str]]:
    text = " ".join(
        part.lower().replace("_", " ").replace("-", " ").replace(".", " ")
        for part in rel.parts
    )
    tokens = {token for token in _ROLE_SIGNAL_SPLIT_RE.split(text) if token}
    return text, tokens


def _token_matches_signal(token: str, signal: str) -> bool:
    return token == signal or token.startswith(signal)


def _signal_reasons(rel: Path, role: str) -> list[str]:
    text, tokens = _normalised_signal_text(rel)
    reasons: list[str] = []
    for signal_role, signals in ROLE_CONFLICT_SIGNALS:
        if signal_role != role:
            continue
        for raw_signal in signals:
            signal = raw_signal.lower().replace("-", " ")
            if " " in signal:
                if signal in text:
                    reasons.append(raw_signal)
            elif any(_token_matches_signal(token, signal) for token in tokens):
                reasons.append(raw_signal)
    return reasons


def curated_role_conflict(row: FeatureRow) -> CuratedRoleConflict | None:
    current_role = _curated_folder_role(row.path)
    if current_role is None:
        return None
    content_path = _curated_content_path(row.path)
    issues: list[str] = []
    reasons: list[str] = []

    def add(issue: str, reason: str) -> None:
        if issue not in issues:
            issues.append(issue)
        if reason not in reasons:
            reasons.append(reason)

    for signal_role, _signals in ROLE_CONFLICT_SIGNALS:
        if signal_role == current_role:
            continue
        for reason in _signal_reasons(content_path, signal_role):
            add(signal_role, f"{signal_role}:{reason}")

    if current_role in CURATED_ONE_SHOT_ROLES:
        if row.sample_type == "loop":
            add("DRUM-LOOPS", "sample_type:loop")
        duration = row.duration if row.duration is not None else row.duration_s
        if duration is not None and duration > CURATED_LONG_AUDIO_SECONDS:
            add("long-audio", f"duration={duration:.2f}s")
        elif row.tail_ms is not None and row.tail_ms > CURATED_LONG_TAIL_MS:
            add("long-audio", f"tail_ms={_fmt_num(row.tail_ms)}")

    if not issues:
        return None
    return CuratedRoleConflict(
        path=row.path,
        current_role=current_role,
        issues=";".join(issues),
        reasons=";".join(reasons),
        suggested_action="review-or-quarantine",
    )


def curated_role_conflicts(rows: list[FeatureRow]) -> list[CuratedRoleConflict]:
    conflicts = [conflict for row in rows if (conflict := curated_role_conflict(row)) is not None]
    return sorted(conflicts, key=lambda item: item.path.as_posix())


def _one_shot_role_cluster_issue(row: FeatureRow) -> bool:
    if row.role not in CURATED_ONE_SHOT_ROLES:
        return False
    if _signal_reasons(row.path, "DRUM-LOOPS"):
        return True
    duration = row.duration if row.duration is not None else row.duration_s
    if duration is not None and duration > CURATED_LONG_AUDIO_SECONDS:
        return True
    return row.tail_ms is not None and row.tail_ms > CURATED_LONG_TAIL_MS


# High-precision KICKS gate. Optimises for precision: a KICKS row becomes
# `likely_kick` only when cheap cached acoustic evidence strongly supports it.
# Ambiguous-but-plausible kicks stay in `review`; clear non-kicks are rejected.
KICK_MIN_LIKELY_SUB_RATIO = 0.55
KICK_MIN_LIKELY_LOW_RATIO = 0.55
KICK_MAX_LIKELY_HIGH_RATIO = 0.25
KICK_MAX_LIKELY_DURATION_S = 0.90
KICK_MAX_LIKELY_TAIL_MS = 450.0
KICK_MAX_LIKELY_CENTROID_HZ = 2200.0
KICK_MAX_LIKELY_FLATNESS = 0.45
KICK_MAX_LIKELY_ONSET_DENSITY = 2.0
# crest = peak/RMS. High crest is spiky/clicky; a kick with real body sits lower.
# Measured median crest of strong low-end kicks in the library is ~3.3, so a 2.0
# floor only excludes near-DC / no-transient sustained tones, not real kicks.
KICK_MIN_LIKELY_CREST = 2.0
KICK_MAX_LIKELY_ZCR = 0.12

# Strong-reject thresholds (looser than the likely band; the gap routes to review).
KICK_REJECT_DURATION_S = 3.0
KICK_REJECT_ONSET_DENSITY = 4.0
KICK_REJECT_HIGH_RATIO = 0.45
KICK_REJECT_CENTROID_HZ = 3500.0
KICK_REJECT_CENTROID_MIN_SUB = 0.45
KICK_REJECT_ZCR = 0.18
KICK_REJECT_MID_CLICK_TAIL_MS = 250.0
KICK_REJECT_MID_CLICK_SUB_RATIO = 0.30
KICK_REJECT_MID_CLICK_MID_RATIO = 0.35
KICK_REJECT_MID_CLICK_CENTROID_HZ = 1500.0


def _kick_gate_row(
    row: FeatureRow,
    gate: str,
    confidence: str,
    reasons: list[str],
    review_action: str,
) -> KickGateRow:
    return KickGateRow(
        path=row.path,
        current_role=row.role,
        sample_type=row.sample_type,
        duration_s=row.duration_s if row.duration_s is not None else row.duration,
        attack_ms=row.attack_ms,
        tail_ms=row.tail_ms,
        sub_ratio=row.sub_ratio,
        low_ratio=row.low_ratio,
        mid_ratio=row.mid_ratio,
        high_ratio=row.high_ratio,
        centroid_hz=row.centroid_hz,
        flatness=row.flatness,
        onset_density=row.onset_density,
        zcr=row.zcr,
        kick_gate=gate,
        confidence=confidence,
        reasons=";".join(reasons),
        review_action=review_action,
    )


def kick_gate(row: FeatureRow) -> KickGateRow:
    """Bucket a KICKS row as likely_kick / review / reject_as_kick.

    Deterministic evidence ladder over existing cached acoustic features and the
    curated-role conflict signals. Manifest-only: never moves or renames files.
    """
    # 1. Not a KICKS row: out of this gate's scope.
    if row.role != "KICKS":
        return _kick_gate_row(row, "review", "low", ["not-kicks-scope"], "not-kicks-scope")

    # 2. Existing curated-role conflict signals (clap/snare/hat/cym/bass/synth/FX/
    #    vocal/drum-loop names, loop sample_type, or long one-shot-role duration).
    conflict = curated_role_conflict(row)
    if conflict is not None:
        return _kick_gate_row(
            row, "reject_as_kick", "high", [f"role-conflict:{conflict.issues}"], "keep-out-of-kicks"
        )

    # 3. Missing decode / acoustic evidence: cannot confidently pass.
    duration_s = row.duration_s if row.duration_s is not None else row.duration
    required = (
        duration_s, row.sub_ratio, row.low_ratio, row.high_ratio, row.centroid_hz,
        row.tail_ms, row.onset_density, row.zcr, row.crest,
    )
    if row.audio_error or any(value is None for value in required):
        reason = "decode-error" if row.audio_error else "missing-acoustic-features"
        return _kick_gate_row(row, "review", "low", [reason], "decode-or-manual-review")

    # 4. Loop / long / dense evidence: not a kick one-shot.
    if (
        row.sample_type == "loop"
        or duration_s >= KICK_REJECT_DURATION_S
        or row.onset_density >= KICK_REJECT_ONSET_DENSITY
    ):
        reasons: list[str] = []
        if row.sample_type == "loop":
            reasons.append("sample_type:loop")
        if duration_s >= KICK_REJECT_DURATION_S:
            reasons.append(_reason("duration_s", duration_s))
        if row.onset_density >= KICK_REJECT_ONSET_DENSITY:
            reasons.append(_reason("onset_density", row.onset_density))
        return _kick_gate_row(row, "reject_as_kick", "high", reasons, "keep-out-of-kicks")

    # 5. Short midrange transient: click/percussion with too little sub body,
    #    not a kick. This deliberately uses acoustic shape, not name tokens.
    if (
        row.mid_ratio is not None
        and row.tail_ms <= KICK_REJECT_MID_CLICK_TAIL_MS
        and row.sub_ratio < KICK_REJECT_MID_CLICK_SUB_RATIO
        and row.mid_ratio >= KICK_REJECT_MID_CLICK_MID_RATIO
        and row.centroid_hz >= KICK_REJECT_MID_CLICK_CENTROID_HZ
    ):
        reasons = [
            _reason("tail_ms", row.tail_ms),
            _reason("sub_ratio", row.sub_ratio),
            _reason("mid_ratio", row.mid_ratio),
            _reason("centroid_hz", row.centroid_hz),
        ]
        return _kick_gate_row(row, "reject_as_kick", "high", reasons, "keep-out-of-kicks")

    # 6. High-frequency / noisy spectral profile: hat/cymbal/noise, not kick.
    if (
        row.high_ratio >= KICK_REJECT_HIGH_RATIO
        or (row.centroid_hz >= KICK_REJECT_CENTROID_HZ and row.sub_ratio < KICK_REJECT_CENTROID_MIN_SUB)
        or row.zcr >= KICK_REJECT_ZCR
    ):
        reasons = []
        if row.high_ratio >= KICK_REJECT_HIGH_RATIO:
            reasons.append(_reason("high_ratio", row.high_ratio))
        if row.centroid_hz >= KICK_REJECT_CENTROID_HZ and row.sub_ratio < KICK_REJECT_CENTROID_MIN_SUB:
            reasons.append(f"{_reason('centroid_hz', row.centroid_hz)};{_reason('sub_ratio', row.sub_ratio)}")
        if row.zcr >= KICK_REJECT_ZCR:
            reasons.append(_reason("zcr", row.zcr))
        return _kick_gate_row(row, "reject_as_kick", "high", reasons, "keep-out-of-kicks")

    # 7. Strong likely-kick evidence: every precision gate passes.
    likely = (
        row.sub_ratio >= KICK_MIN_LIKELY_SUB_RATIO
        and row.low_ratio >= KICK_MIN_LIKELY_LOW_RATIO
        and row.high_ratio <= KICK_MAX_LIKELY_HIGH_RATIO
        and duration_s <= KICK_MAX_LIKELY_DURATION_S
        and row.tail_ms <= KICK_MAX_LIKELY_TAIL_MS
        and row.centroid_hz <= KICK_MAX_LIKELY_CENTROID_HZ
        and (row.flatness is None or row.flatness <= KICK_MAX_LIKELY_FLATNESS)
        and row.onset_density <= KICK_MAX_LIKELY_ONSET_DENSITY
        and row.crest >= KICK_MIN_LIKELY_CREST
        and row.zcr <= KICK_MAX_LIKELY_ZCR
    )
    if likely:
        reasons = [
            _reason("sub_ratio", row.sub_ratio),
            _reason("crest", row.crest),
            _reason("centroid_hz", row.centroid_hz),
        ]
        return _kick_gate_row(row, "likely_kick", "high", reasons, "audition-as-kick")

    # 8. Plausible but not high-precision: hold for a human ear-check.
    return _kick_gate_row(row, "review", "medium", ["mixed-evidence"], "ear-check-before-kick")


def kick_audit(rows: list[FeatureRow]) -> list[KickGateRow]:
    return sorted(
        [
            kick_gate(row)
            for row in rows
            if row.role == "KICKS" or (_curated_folder_role(row.path) or row.role) == "KICKS"
        ],
        key=lambda item: item.path.as_posix(),
    )


def _passes_kick_gate(row: FeatureRow) -> bool:
    # KICKS review rows stay visible in kick-audit-latest.tsv, but only
    # likely_kick rows can become representatives or device-crate picks.
    return row.role != "KICKS" or kick_gate(row).kick_gate == "likely_kick"


def _fmt_audit_value(value: float | None) -> str:
    return _fmt_num(value) if value is not None else ""

CLUSTER_FEATURES: tuple[str, ...] = (
    "duration_s",
    "rms",
    "crest",
    "attack_ms",
    "tail_ms",
    "centroid_hz",
    "flatness",
    "sub_ratio",
    "low_ratio",
    "mid_ratio",
    "high_ratio",
    "onset_density",
    "zcr",
)


def _cluster_vector(row: FeatureRow) -> list[float] | None:
    text = row.path.as_posix().lower().replace("_", " ").replace("-", " ")
    if _has(text, *DEVICE_SKIP_TOKENS):
        return None
    if curated_role_conflict(row) is not None:
        return None
    if _one_shot_role_cluster_issue(row):
        return None
    if not _passes_kick_gate(row):
        return None
    if row.audio_error:
        return None
    values: list[float] = []
    for field in CLUSTER_FEATURES:
        value = getattr(row, field)
        if value is None:
            return None
        values.append(float(value))
    return values


def _cluster_count(size: int) -> int:
    if size < 4:
        return 1
    return min(8, max(2, size // 30))


def _normalise(matrix):
    if np is None:  # pragma: no cover
        raise RuntimeError("numpy is not installed")
    means = matrix.mean(axis=0)
    stds = matrix.std(axis=0)
    stds[stds == 0] = 1.0
    return (matrix - means) / stds


def _initial_centroids(matrix, count: int):
    if np is None:  # pragma: no cover
        raise RuntimeError("numpy is not installed")
    chosen = [0]
    while len(chosen) < count:
        existing = matrix[chosen]
        distances = np.min(np.linalg.norm(matrix[:, None, :] - existing[None, :, :], axis=2), axis=1)
        distances[chosen] = -1.0
        chosen.append(int(np.argmax(distances)))
    return matrix[chosen].copy()


def _kmeans(matrix, count: int):
    if np is None:  # pragma: no cover
        raise RuntimeError("numpy is not installed")
    centroids = _initial_centroids(matrix, count)
    labels = np.zeros(len(matrix), dtype=int)
    for _ in range(25):
        distances = np.linalg.norm(matrix[:, None, :] - centroids[None, :, :], axis=2)
        next_labels = np.argmin(distances, axis=1)
        if np.array_equal(labels, next_labels):
            break
        labels = next_labels
        for idx in range(count):
            members = matrix[labels == idx]
            if len(members):
                centroids[idx] = members.mean(axis=0)
    return labels, centroids


def _average(rows: list[FeatureRow], field: str) -> float | None:
    values = [getattr(row, field) for row in rows if getattr(row, field) is not None]
    return sum(values) / len(values) if values else None


def _acoustic_label_for_cluster(rows: list[FeatureRow]) -> str:
    traits: list[str] = []
    sub_ratio = _average(rows, "sub_ratio")
    centroid = _average(rows, "centroid_hz")
    flatness = _average(rows, "flatness")
    tail_ms = _average(rows, "tail_ms")
    onset_density = _average(rows, "onset_density")
    duration = _average(rows, "duration")
    if sub_ratio is not None and sub_ratio >= 0.60:
        traits.append("subby")
    elif centroid is not None and centroid >= 3500:
        traits.append("bright")
    elif centroid is not None and centroid <= 500:
        traits.append("dark")
    if flatness is not None and flatness >= 0.35:
        traits.append("noisy")
    elif flatness is not None and flatness <= 0.05:
        traits.append("tonal")
    if tail_ms is not None and tail_ms <= 250:
        traits.append("short")
    elif tail_ms is not None and tail_ms >= 1000:
        traits.append("long")
    if onset_density is not None and duration is not None and duration >= 1.0:
        if onset_density <= 2.0:
            traits.append("sparse")
        elif onset_density >= 8.0:
            traits.append("busy")
    return "-".join(traits[:3]) if traits else "balanced"


def _label_for_cluster(rows: list[FeatureRow], used: set[str]) -> str:
    counts: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    order = 0
    for row in sorted(rows, key=lambda item: item.path.as_posix()):
        for tag in row.character_tags.split(";"):
            if not tag:
                continue
            if tag not in first_seen:
                first_seen[tag] = order
                order += 1
            counts[tag] = counts.get(tag, 0) + 1
    ranked = sorted(counts, key=lambda tag: (-counts[tag], first_seen[tag], tag))
    base = "-".join(ranked[:2]) if ranked else _acoustic_label_for_cluster(rows)
    label = base
    suffix = 2
    while label in used:
        label = f"{base}-{suffix}"
        suffix += 1
    used.add(label)
    return label


def cluster_within_role(rows: list[FeatureRow]) -> list[ClusterRow]:
    """Cluster rows within each role using deterministic k-means over acoustic features."""
    if np is None:
        return []
    assignments: list[ClusterRow] = []
    by_role: dict[str, list[tuple[FeatureRow, list[float]]]] = {}
    for row in sorted(rows, key=lambda item: item.path.as_posix()):
        vector = _cluster_vector(row)
        if vector is None:
            continue
        by_role.setdefault(row.role, []).append((row, vector))

    for role, items in sorted(by_role.items()):
        role_rows = [item[0] for item in items]
        matrix = _normalise(np.asarray([item[1] for item in items], dtype=float))
        count = _cluster_count(len(items))
        labels, centroids = _kmeans(matrix, count)
        used_labels: set[str] = set()
        for cluster_id in sorted(set(int(label) for label in labels)):
            positions = [idx for idx, label in enumerate(labels) if int(label) == cluster_id]
            cluster_rows = [role_rows[idx] for idx in positions]
            cluster_label = _label_for_cluster(cluster_rows, used_labels)
            distances = {
                idx: float(np.linalg.norm(matrix[idx] - centroids[cluster_id]))
                for idx in positions
            }
            representative = min(positions, key=lambda idx: (distances[idx], role_rows[idx].path.as_posix()))
            for idx in positions:
                assignments.append(
                    ClusterRow(
                        path=role_rows[idx].path,
                        role=role,
                        cluster_label=cluster_label,
                        distance_to_centroid=distances[idx],
                        is_representative=idx == representative,
                    )
                )
    return sorted(assignments, key=lambda item: (item.role, item.cluster_label, item.path.as_posix()))

def _crate_reason(row: FeatureRow) -> str:
    fields = [row.role, row.sample_type, row.character_tags]
    return ";".join(field for field in fields if field)


def _one_shot_candidate(row: FeatureRow) -> bool:
    if row.role not in {"KICKS", "CLAP-SNARE", "HATS-CYM", "PERC"}:
        return False
    if row.sample_type != "one-shot":
        return False
    return row.duration is None or row.duration <= 3.0


def _curated_role_matches(row: FeatureRow) -> bool:
    if row.source_kind != "curated-sample":
        return True
    return (
        len(row.path.parts) >= 2
        and row.path.parts[0] == "CURATED"
        and row.path.parts[1] == row.role
    )


def _device_one_shot_candidate(row: FeatureRow) -> bool:
    text = row.path.as_posix().lower().replace("_", " ").replace("-", " ")
    return (
        _one_shot_candidate(row)
        and row.path.suffix.lower() in DEVICE_SAMPLE_EXTS
        and not _has(text, *DEVICE_SKIP_TOKENS)
        and _curated_role_matches(row)
        and curated_role_conflict(row) is None
        and _passes_kick_gate(row)
    )


def _audition_candidate(row: FeatureRow) -> bool:
    text = row.path.as_posix().lower().replace("_", " ").replace("-", " ")
    return (
        not _has(text, *DEVICE_SKIP_TOKENS)
        and _curated_role_matches(row)
        and curated_role_conflict(row) is None
        and _passes_kick_gate(row)
    )


def _octatrack_candidate(row: FeatureRow) -> bool:
    return _audition_candidate(row) and row.path.suffix.lower() in DEVICE_SAMPLE_EXTS


def _entry(row: FeatureRow) -> CrateEntry:
    return CrateEntry(row.path, _crate_reason(row))


def _flat_file_family(name: str) -> str:
    stem = Path(name).stem.lower()
    main, source = stem.split("_", 1) if "_" in stem else (stem, "")
    shaped = []
    last = ""
    for char in main.replace("_", "-"):
        value = "#" if char.isdigit() else char
        if value == "#" and last == "#":
            continue
        shaped.append(value)
        last = value
    family = "".join(shaped).strip("-") or main
    if source:
        return f"{source.replace('_', '-')}/{family}"
    return family


def _crate_family(row: FeatureRow) -> str:
    parts = row.path.parts
    if row.source_kind == "curated-sample" and len(parts) >= 3:
        if len(parts) >= 4:
            return "/".join(parts[:3])
        return "/".join([parts[0], parts[1], _flat_file_family(parts[2])])
    if row.source_kind == "octatrack-set-audio":
        try:
            audio_idx = parts.index("AUDIO")
        except ValueError:
            return row.source_name
        end = min(len(parts) - 1, audio_idx + 4)
        return "/".join(parts[:end])
    if len(parts) >= 3:
        return "/".join(parts[:3])
    return row.source_name or row.path.parent.as_posix()


def _diverse_rows(
    rows: list[FeatureRow],
    limit: int,
    family_key: Callable[[FeatureRow], str] | None = None,
) -> list[FeatureRow]:
    key = family_key or _crate_family
    groups: dict[str, list[FeatureRow]] = {}
    order: list[str] = []
    for row in rows:
        family = key(row)
        if family not in groups:
            groups[family] = []
            order.append(family)
        groups[family].append(row)

    selected: list[FeatureRow] = []
    while len(selected) < limit:
        progressed = False
        for family in order:
            if not groups[family]:
                continue
            selected.append(groups[family].pop(0))
            progressed = True
            if len(selected) >= limit:
                break
        if not progressed:
            break
    return selected


def _balanced_one_shots(
    rows: list[FeatureRow],
    quotas: dict[str, int],
    max_entries: int,
    family_key: Callable[[FeatureRow], str] | None = None,
) -> list[CrateEntry]:
    by_role: dict[str, list[FeatureRow]] = {
        role: [row for row in rows if row.role == role and _device_one_shot_candidate(row)]
        for role in quotas
    }
    selected: list[FeatureRow] = []
    seen: set[Path] = set()
    for role, quota in quotas.items():
        for row in _diverse_rows(by_role[role], quota, family_key):
            selected.append(row)
            seen.add(row.path)
    leftovers = _diverse_rows(
        [row for role in quotas for row in by_role[role] if row.path not in seen],
        max_entries - len(selected),
        family_key,
    )
    for row in leftovers:
        if len(selected) >= max_entries:
            break
        selected.append(row)
    return [_entry(row) for row in selected[:max_entries]]


def _balanced_role_rows(
    rows: list[FeatureRow],
    quotas: dict[str, int],
    max_entries: int,
    predicate: Callable[[FeatureRow], bool],
    family_key: Callable[[FeatureRow], str] | None = None,
) -> list[FeatureRow]:
    selected: list[FeatureRow] = []
    seen: set[Path] = set()
    for role, quota in quotas.items():
        candidates = [
            row for row in rows
            if row.role == role and row.path not in seen and predicate(row)
        ]
        for row in _diverse_rows(candidates, quota, family_key):
            selected.append(row)
            seen.add(row.path)
    fallback = [
        row for row in rows
        if row.path not in seen and predicate(row)
    ]
    for row in _diverse_rows(fallback, max_entries - len(selected), family_key):
        if len(selected) >= max_entries:
            break
        selected.append(row)
        seen.add(row.path)
    return selected[:max_entries]


def _octatrack_bed_rows(
    rows: list[FeatureRow],
    max_entries: int,
    family_key: Callable[[FeatureRow], str] | None = None,
) -> list[FeatureRow]:
    selected: list[FeatureRow] = []
    seen: set[Path] = set()
    ot_pool = _balanced_role_rows(
        rows,
        {"KICKS": 4, "CLAP-SNARE": 4, "HATS-CYM": 4, "PERC": 4},
        16,
        lambda row: row.source_kind == "octatrack-set-audio" and _octatrack_candidate(row),
        family_key,
    )
    for row in ot_pool:
        selected.append(row)
        seen.add(row.path)
    selected.extend(
        _balanced_role_rows(
            [row for row in rows if row.path not in seen],
            {"DRUM-LOOPS": 18, "DRONE-ATMOS": 18, "SYNTH-STAB-CHORD": 14, "FX-RISE-IMPACT": 14},
            max_entries - len(selected),
            _octatrack_candidate,
            family_key,
        )
    )
    return selected[:max_entries]


def build_crates(
    rows: list[FeatureRow],
    ot_sets: list[OtSet] | None = None,
    clusters: list[ClusterRow] | None = None,
) -> dict[str, list[CrateEntry]]:
    """Build small deterministic device-aware crate suggestions."""
    sorted_rows = sorted(rows, key=lambda row: row.path.as_posix())
    cluster_index = {row.path: row.cluster_label for row in clusters or []}

    def family_key(row: FeatureRow) -> str:
        label = cluster_index.get(row.path)
        return f"{row.role}/{label}" if label else _crate_family(row)

    crates: dict[str, list[CrateEntry]] = {
        "digitakt/punchy-techno-kit.txt": _balanced_one_shots(
            sorted_rows,
            {"KICKS": 8, "CLAP-SNARE": 6, "HATS-CYM": 10, "PERC": 8},
            32,
            family_key,
        ),
        "tr8s/909-plus-weird-perc.txt": _balanced_one_shots(
            sorted_rows,
            {"KICKS": 12, "CLAP-SNARE": 12, "HATS-CYM": 20, "PERC": 20},
            64,
            family_key,
        ),
        "ableton/dub-techno-favourites.txt": [
            _entry(row)
            for row in _balanced_role_rows(
                sorted_rows,
                {
                    "DRUM-LOOPS": 18,
                    "DRONE-ATMOS": 18,
                    "SYNTH-STAB-CHORD": 18,
                    "BASS": 14,
                    "FX-RISE-IMPACT": 12,
                    "VOCALS": 8,
                    "PERC": 4,
                    "HATS-CYM": 2,
                    "CLAP-SNARE": 1,
                    "KICKS": 1,
                },
                96,
                _audition_candidate,
                family_key,
            )
        ],
        "octatrack/dub-loop-bed-132.txt": [
            _entry(row) for row in _octatrack_bed_rows(sorted_rows, 64, family_key)
        ],
    }
    for ot_set in sorted(ot_sets or [], key=lambda item: item.project_root.as_posix()):
        slug = review.normalise_token(ot_set.set_name)
        crates[f"octatrack/{slug}-set.txt"] = [
            CrateEntry(ot_set.project_root, "install-as-set;preserve-set")
        ]
    return crates
