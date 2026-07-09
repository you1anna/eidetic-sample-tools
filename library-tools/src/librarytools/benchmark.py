"""Human-labelled drum-role benchmark: select, freeze, score.

The drum CNN-LSTM was downgraded after failing a route calibration 0/10 (see
``decisions/2026-07-09-drum-role-classifier-downgraded.md``). That failure was anecdotal — one
route, no measured recall. This module builds a small ear-labelled ground-truth set so any
classifier (the current model or a candidate repo) can be *scored* with per-role precision/recall
and a confusion matrix instead of guessed at.

Read-only with respect to the sample library: nothing here moves, renames, or tags a sample. The
only writes are manifest/label/scorecard artifacts under a dated output directory.

Two stages with a human gate between them:

1. ``write_prepare_artifacts`` picks ~25 samples per drum role, stratified across spectral centroid
   so bright/tonal (SP-1200-style) material is represented and not just easy canonical thumps, and
   emits an audition packet whose ``labels.tsv`` has an empty ``true_role`` column.
2. Robin fills ``true_role`` by ear; ``read_labels`` loads that ground truth and ``score`` grades a
   model's predictions against it.
"""

from __future__ import annotations

import csv
import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

# Reuse the audio extension set the classifier already agrees on.
from .classifier import AUDIO_EXTS

ROLE_ORDER: tuple[str, ...] = ("KICKS", "CLAP-SNARE", "HATS-CYM", "PERC")

# What a human may write in true_role. OTHER = none of the four drum roles / a contaminant.
TRUE_ROLE_VALUES: frozenset[str] = frozenset({*ROLE_ORDER, "OTHER"})

# Roles a model prediction is collapsed into for scoring. Anything a model suggests that is not one
# of the four target drum roles (BASS, REVIEW, ...) becomes OTHER, matching the human vocabulary.
SCORE_ROLES: tuple[str, ...] = (*ROLE_ORDER, "OTHER")

_LABEL_FIELDS: tuple[str, ...] = (
    "sample_id",
    "path",
    "folder_role",
    "centroid_hz",
    "sub_ratio",
    "true_role",
    "notes",
)


# ---- data types ------------------------------------------------------------------------------


@dataclass(frozen=True)
class BenchmarkItem:
    sample_id: str
    path: Path            # relative to the library root, e.g. CURATED/KICKS/pack/a.wav
    folder_role: str
    centroid_hz: float | None
    sub_ratio: float | None

    @property
    def source_group(self) -> str:
        """Immediate sub-directory under CURATED/<role>/ (the vendor pack), or _root."""
        parts = self.path.parts
        return parts[2] if len(parts) > 3 else "_root"


@dataclass(frozen=True)
class LabelledItem:
    sample_id: str
    path: Path
    folder_role: str
    true_role: str


@dataclass(frozen=True)
class RoleScore:
    precision: float
    recall: float
    f1: float
    support: int  # number of true items in this role


@dataclass(frozen=True)
class Scorecard:
    overall_accuracy: float
    per_role: dict[str, RoleScore]
    confusion: dict[tuple[str, str], int]  # (true_role, predicted_role) -> count
    total: int


# ---- ids -------------------------------------------------------------------------------------


def sample_id(relpath: str) -> str:
    return hashlib.sha256(relpath.encode()).hexdigest()[:12]


# ---- feature loading -------------------------------------------------------------------------


def _to_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_features(path: Path) -> dict[str, tuple[float | None, float | None]]:
    """Map library-relative path -> (centroid_hz, sub_ratio) from a sample-features tsv.

    Columns are located by header name so the loader survives layout changes. Rows whose numeric
    cells are blank/unparseable yield ``(None, None)`` rather than raising.
    """
    table: dict[str, tuple[float | None, float | None]] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        fields = reader.fieldnames or []
        if "path" not in fields:
            raise ValueError("features tsv missing 'path' column")
        for row in reader:
            table[row["path"]] = (
                _to_float(row.get("centroid_hz", "")),
                _to_float(row.get("sub_ratio", "")),
            )
    return table


# ---- item building ---------------------------------------------------------------------------


def build_items(
    root: Path,
    role: str,
    features: dict[str, tuple[float | None, float | None]],
) -> list[BenchmarkItem]:
    """Walk CURATED/<role>/ on disk and join acoustic features by relative path.

    Disk is the source of truth for what exists to audition; the features tsv only supplies the
    centroid/sub_ratio used for stratification. Files absent from the tsv keep ``None`` features
    and fall into the feature-less stratum during selection.
    """
    role_dir = root / "CURATED" / role
    items: list[BenchmarkItem] = []
    if not role_dir.is_dir():
        return items
    for path in sorted(role_dir.rglob("*")):
        if not path.is_file() or path.name.startswith("._"):
            continue
        if path.suffix.lower() not in AUDIO_EXTS:
            continue
        rel = path.relative_to(root)
        centroid, sub = features.get(rel.as_posix(), (None, None))
        items.append(
            BenchmarkItem(
                sample_id=sample_id(rel.as_posix()),
                path=rel,
                folder_role=role,
                centroid_hz=centroid,
                sub_ratio=sub,
            )
        )
    return items


# ---- stratified selection --------------------------------------------------------------------


def _spread_pick(items: list[BenchmarkItem], k: int) -> list[BenchmarkItem]:
    """Pick k items from a bucket, greedily spreading across source groups. Deterministic."""
    ordered = sorted(items, key=lambda i: i.path.as_posix())
    if k >= len(ordered):
        return ordered
    picked: list[BenchmarkItem] = []
    used: set[str] = set()
    remaining = list(ordered)
    while len(picked) < k and remaining:
        choice = next((i for i in remaining if i.source_group not in used), None)
        if choice is None:  # every group already represented in this pass — start a new pass
            used = set()
            choice = remaining[0]
        picked.append(choice)
        used.add(choice.source_group)
        remaining.remove(choice)
    return picked


def _allocate(bucket_sizes: list[int], size: int) -> list[int]:
    """Largest-remainder allocation of `size` picks across buckets, capped by each bucket's size."""
    total = sum(bucket_sizes)
    if total <= size:
        return list(bucket_sizes)
    raw = [size * s / total for s in bucket_sizes]
    quota = [int(x) for x in raw]
    remainder = size - sum(quota)
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - quota[i]), i))
    idx = 0
    while remainder > 0 and order:
        i = order[idx % len(order)]
        if quota[i] < bucket_sizes[i]:
            quota[i] += 1
            remainder -= 1
        idx += 1
        if idx > len(order) * size:  # safety valve — cannot place more
            break
    return quota


def select_benchmark(
    items: list[BenchmarkItem],
    size: int = 25,
    num_buckets: int = 5,
) -> list[BenchmarkItem]:
    """Deterministically choose ~size items stratified by spectral centroid.

    Items are ranked by centroid and split into contiguous quantile buckets, with a trailing
    bucket for feature-less items. Picks are allocated proportionally across buckets and, within a
    bucket, spread across vendor sub-directories. This guarantees the bright/tonal tail (the
    material that broke the model) is sampled, not just the dense low-centroid mode.
    """
    ordered = sorted(items, key=lambda i: i.path.as_posix())
    if len(ordered) <= size:
        return ordered

    with_feat = sorted(
        (i for i in ordered if i.centroid_hz is not None),
        key=lambda i: (i.centroid_hz, i.path.as_posix()),
    )
    without = [i for i in ordered if i.centroid_hz is None]

    buckets: list[list[BenchmarkItem]] = []
    if with_feat:
        per = math.ceil(len(with_feat) / num_buckets)
        tmp: list[list[BenchmarkItem]] = [[] for _ in range(num_buckets)]
        for idx, item in enumerate(with_feat):
            tmp[min(num_buckets - 1, idx // per)].append(item)
        buckets.extend(b for b in tmp if b)
    if without:
        buckets.append(without)

    quotas = _allocate([len(b) for b in buckets], size)
    selected: list[BenchmarkItem] = []
    for bucket, quota in zip(buckets, quotas):
        selected.extend(_spread_pick(bucket, quota))
    return sorted(selected, key=lambda i: i.path.as_posix())


# ---- prepare artifacts -----------------------------------------------------------------------


def _role_slug(role: str) -> str:
    return role.lower()


def _write_manifest(output_dir: Path, picks: dict[str, list[BenchmarkItem]]) -> None:
    manifest = output_dir / "benchmark-manifest.tsv"
    with manifest.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(["sample_id", "path", "folder_role", "centroid_hz", "sub_ratio"])
        for role in ROLE_ORDER:
            for item in picks.get(role, []):
                writer.writerow(
                    [
                        item.sample_id,
                        item.path.as_posix(),
                        item.folder_role,
                        "" if item.centroid_hz is None else f"{item.centroid_hz:.3f}",
                        "" if item.sub_ratio is None else f"{item.sub_ratio:.4f}",
                    ]
                )
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    (output_dir / "benchmark-manifest.sha256").write_text(
        f"{digest}  {manifest.name}\n", encoding="utf-8"
    )


def _write_role_packet(
    role_dir: Path,
    root: Path,
    role: str,
    picks: list[BenchmarkItem],
) -> None:
    role_dir.mkdir(parents=True, exist_ok=True)

    with (role_dir / "labels.tsv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(_LABEL_FIELDS)
        for item in picks:
            writer.writerow(
                [
                    item.sample_id,
                    item.path.as_posix(),
                    item.folder_role,
                    "" if item.centroid_hz is None else f"{item.centroid_hz:.3f}",
                    "" if item.sub_ratio is None else f"{item.sub_ratio:.4f}",
                    "",  # true_role — Robin fills by ear
                    "",  # notes
                ]
            )

    playlist = ["#EXTM3U", *(str(root / item.path) for item in picks)]
    (role_dir / "audition.m3u8").write_text("\n".join(playlist) + "\n", encoding="utf-8")

    checklist = [
        f"# Benchmark audition: {role}",
        "",
        f"Files: {len(picks)}",
        "",
        f"Listen to each file and set `true_role` in labels.tsv to one of: {', '.join(sorted(TRUE_ROLE_VALUES))}.",
        "OTHER = not one of the four drum roles (e.g. a bass note, a loop, a contaminant).",
        "Judge by EAR only — ignore the folder it currently sits in.",
        "",
    ]
    checklist.extend(
        f"- [ ] `{root / item.path}` — centroid "
        f"{'n/a' if item.centroid_hz is None else f'{item.centroid_hz:.0f} Hz'} — `{item.sample_id}`"
        for item in picks
    )
    (role_dir / "checklist.md").write_text("\n".join(checklist) + "\n", encoding="utf-8")


def write_prepare_artifacts(
    root: Path,
    features_path: Path,
    output_dir: Path,
    per_role: int = 25,
) -> dict[str, Path]:
    """Build and freeze the benchmark audition packet. Returns role -> packet directory."""
    features = load_features(features_path) if features_path.is_file() else {}
    output_dir.mkdir(parents=True, exist_ok=True)
    audition_root = output_dir / "audition"

    picks: dict[str, list[BenchmarkItem]] = {}
    role_dirs: dict[str, Path] = {}
    for role in ROLE_ORDER:
        items = build_items(root, role, features)
        chosen = select_benchmark(items, size=per_role)
        picks[role] = chosen
        role_dir = audition_root / _role_slug(role)
        _write_role_packet(role_dir, root, role, chosen)
        role_dirs[role] = role_dir

    _write_manifest(output_dir, picks)
    return role_dirs


# ---- label reading ---------------------------------------------------------------------------


def read_labels(output_dir: Path) -> list[LabelledItem]:
    """Collect Robin's ear labels across every role packet. Raises if any row is unlabelled."""
    audition_root = output_dir / "audition"
    labelled: list[LabelledItem] = []
    for labels_file in sorted(audition_root.glob("*/labels.tsv")):
        with labels_file.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                true_role = (row.get("true_role") or "").strip()
                if not true_role:
                    raise ValueError(f"unlabelled row in {labels_file}: {row.get('path')}")
                if true_role not in TRUE_ROLE_VALUES:
                    raise ValueError(f"invalid true_role {true_role!r} in {labels_file}")
                labelled.append(
                    LabelledItem(
                        sample_id=row["sample_id"],
                        path=Path(row["path"]),
                        folder_role=row["folder_role"],
                        true_role=true_role,
                    )
                )
    return labelled


# ---- scoring ---------------------------------------------------------------------------------


def score(pairs: list[tuple[str, str]]) -> Scorecard:
    """Grade (true_role, predicted_role) pairs into per-role precision/recall/F1 + confusion."""
    confusion: dict[tuple[str, str], int] = {}
    correct = 0
    for true_role, predicted in pairs:
        confusion[(true_role, predicted)] = confusion.get((true_role, predicted), 0) + 1
        if true_role == predicted:
            correct += 1

    per_role: dict[str, RoleScore] = {}
    for role in SCORE_ROLES:
        tp = confusion.get((role, role), 0)
        predicted_role = sum(c for (_, p), c in confusion.items() if p == role)
        true_role_total = sum(c for (t, _), c in confusion.items() if t == role)
        precision = tp / predicted_role if predicted_role else 0.0
        recall = tp / true_role_total if true_role_total else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        per_role[role] = RoleScore(precision=precision, recall=recall, f1=f1, support=true_role_total)

    total = len(pairs)
    return Scorecard(
        overall_accuracy=(correct / total) if total else 0.0,
        per_role=per_role,
        confusion=confusion,
        total=total,
    )


def format_scorecard(card: Scorecard, model: str) -> str:
    """Render a scorecard as a Markdown report (per-role table + confusion matrix)."""
    lines = [
        f"# Drum-role benchmark scorecard — model: {model}",
        "",
        f"Samples scored: {card.total}",
        f"Overall accuracy: {card.overall_accuracy:.3f}",
        "",
        "## Per-role",
        "",
        "| role | precision | recall | f1 | support |",
        "| --- | --- | --- | --- | --- |",
    ]
    for role in SCORE_ROLES:
        s = card.per_role[role]
        lines.append(
            f"| {role} | {s.precision:.3f} | {s.recall:.3f} | {s.f1:.3f} | {s.support} |"
        )

    lines += ["", "## Confusion (rows = true, cols = predicted)", ""]
    header = "| true \\ pred | " + " | ".join(SCORE_ROLES) + " |"
    lines.append(header)
    lines.append("| --- | " + " | ".join("---" for _ in SCORE_ROLES) + " |")
    for true_role in SCORE_ROLES:
        cells = [str(card.confusion.get((true_role, p), 0)) for p in SCORE_ROLES]
        lines.append(f"| {true_role} | " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)
