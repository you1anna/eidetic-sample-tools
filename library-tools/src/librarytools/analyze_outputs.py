"""Manifest writers for sample analysis."""

from __future__ import annotations

import csv
from pathlib import Path

from .analyze_rules import _fmt_audit_value
from .analyze_types import (
    ClusterRow,
    CrateEntry,
    CuratedRoleConflict,
    FeatureRow,
    KickGateRow,
    OtSet,
    SourceRow,
)
from .featurecache import FEATURE_COLUMNS
from .inventory import LibraryDatabase


def add_inventory_identity(
    path: Path,
    database: LibraryDatabase,
    scan_id: str,
    path_column: str = "path",
) -> None:
    """Prefix a generated TSV with scan/sample identity columns."""
    if not path.is_file():
        return
    identities = {
        item.path.as_posix(): item.sample_id for item in database.current_locations()
    }
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if not reader.fieldnames or path_column not in reader.fieldnames:
            return
        fieldnames = ["scan_id", "sample_id", *reader.fieldnames]
        rows = list(reader)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "scan_id": scan_id,
                "sample_id": identities.get(row[path_column], ""),
                **row,
            })
    tmp.replace(path)

def write_source_registry(path: Path, rows: list[SourceRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow([
            "path",
            "source_kind",
            "source_name",
            "processing_tag",
            "processing_reason",
        ])
        for row in rows:
            writer.writerow([
                row.path.as_posix(),
                row.source_kind,
                row.source_name,
                row.processing_tag,
                row.processing_reason,
            ])

def write_features(path: Path, rows: list[FeatureRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow([
            "path",
            "source_kind",
            "source_name",
            "role",
            "sample_type",
            "bpm",
            "key",
            "tempo_fit",
            "duration",
            *FEATURE_COLUMNS,
            "audio_error",
            "proposed_name",
            "review_reason",
            "processing_tag",
            "processing_reason",
            "character_tags",
            "tag_reasons",
        ])
        for row in rows:
            writer.writerow([
                row.path.as_posix(),
                row.source_kind,
                row.source_name,
                row.role,
                row.sample_type,
                row.bpm,
                row.key,
                row.tempo_fit,
                f"{row.duration:.3f}" if row.duration is not None else "",
                *[
                    f"{getattr(row, column):.6g}" if getattr(row, column) is not None else ""
                    for column in FEATURE_COLUMNS
                ],
                row.audio_error,
                row.proposed_name,
                row.review_reason,
                row.processing_tag,
                row.processing_reason,
                row.character_tags,
                row.tag_reasons,
            ])

def write_kick_audit(path: Path, rows: list[KickGateRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow([
            "path", "current_role", "sample_type", "duration_s", "attack_ms", "tail_ms",
            "sub_ratio", "low_ratio", "mid_ratio", "high_ratio", "centroid_hz",
            "flatness", "onset_density", "zcr", "kick_gate", "confidence",
            "reasons", "review_action",
        ])
        for row in rows:
            writer.writerow([
                row.path.as_posix(), row.current_role, row.sample_type,
                _fmt_audit_value(row.duration_s), _fmt_audit_value(row.attack_ms),
                _fmt_audit_value(row.tail_ms), _fmt_audit_value(row.sub_ratio),
                _fmt_audit_value(row.low_ratio), _fmt_audit_value(row.mid_ratio),
                _fmt_audit_value(row.high_ratio), _fmt_audit_value(row.centroid_hz),
                _fmt_audit_value(row.flatness), _fmt_audit_value(row.onset_density),
                _fmt_audit_value(row.zcr), row.kick_gate, row.confidence,
                row.reasons, row.review_action,
            ])

def write_curated_role_conflicts(path: Path, rows: list[CuratedRoleConflict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow([
            "path",
            "current_role",
            "issues",
            "reasons",
            "suggested_action",
        ])
        for row in rows:
            writer.writerow([
                row.path.as_posix(),
                row.current_role,
                row.issues,
                row.reasons,
                row.suggested_action,
            ])

def write_clusters(path: Path, rows: list[ClusterRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow([
            "path",
            "role",
            "cluster_label",
            "distance_to_centroid",
            "is_representative",
        ])
        for row in rows:
            writer.writerow([
                row.path.as_posix(),
                row.role,
                row.cluster_label,
                f"{row.distance_to_centroid:.6g}",
                "yes" if row.is_representative else "",
            ])

def write_crates(output_dir: Path, crates: dict[str, list[CrateEntry]]) -> None:
    crate_root = output_dir / "crates"
    for name, entries in sorted(crates.items()):
        path = crate_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            fh.write(f"# generated by sample-analyze: {name}\n")
            for entry in entries:
                if entry.reason:
                    fh.write(f"# {entry.reason}\n")
                fh.write(f"{entry.path.as_posix()}\n")

def write_report(
    path: Path,
    ot_sets: list[OtSet],
    sources: list[SourceRow],
    features: list[FeatureRow],
    crates: dict[str, list[CrateEntry]],
    clusters: list[ClusterRow] | None = None,
    curated_conflicts: list[CuratedRoleConflict] | None = None,
    kick_audit_rows: list[KickGateRow] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    source_counts: dict[str, int] = {}
    for row in sources:
        source_counts[row.source_kind] = source_counts.get(row.source_kind, 0) + 1
    role_counts: dict[str, int] = {}
    for row in features:
        role_counts[row.role] = role_counts.get(row.role, 0) + 1

    lines = [
        "# Sample Intelligence Pilot",
        "",
        f"OT Sets: {len(ot_sets)}",
        f"Source Rows: {len(sources)}",
        f"Feature Rows: {len(features)}",
        "",
        "## Source Kinds",
    ]
    if source_counts:
        lines.extend(f"- {kind}: {count}" for kind, count in sorted(source_counts.items()))
    else:
        lines.append("- none")
    lines.extend(["", "## Roles"])
    if role_counts:
        lines.extend(f"- {role}: {count}" for role, count in sorted(role_counts.items()))
    else:
        lines.append("- none")
    lines.extend(["", "## Crates"])
    for name, entries in sorted(crates.items()):
        lines.append(f"- {name}: {len(entries)}")
    if clusters:
        lines.extend(["", "## Clusters"])
        cluster_counts: dict[tuple[str, str], int] = {}
        representatives: dict[tuple[str, str], Path] = {}
        for row in clusters:
            key = (row.role, row.cluster_label)
            cluster_counts[key] = cluster_counts.get(key, 0) + 1
            if row.is_representative:
                representatives[key] = row.path
        for key, count in sorted(cluster_counts.items()):
            rep = representatives.get(key)
            suffix = f" — rep: {rep.as_posix()}" if rep else ""
            lines.append(f"- {key[0]}/{key[1]}: {count}{suffix}")
    if curated_conflicts is not None:
        lines.extend(["", "## Curated Role Conflicts"])
        lines.append(f"- total: {len(curated_conflicts)}")
        issue_counts: dict[str, int] = {}
        for row in curated_conflicts:
            for issue in row.issues.split(";"):
                issue_counts[issue] = issue_counts.get(issue, 0) + 1
        for issue, count in sorted(issue_counts.items()):
            lines.append(f"- {issue}: {count}")
    if kick_audit_rows is not None:
        lines.extend(["", "## KICKS Gate"])
        gate_counts: dict[str, int] = {}
        for row in kick_audit_rows:
            gate_counts[row.kick_gate] = gate_counts.get(row.kick_gate, 0) + 1
        for gate in ("likely_kick", "review", "reject_as_kick"):
            lines.append(f"- {gate}: {gate_counts.get(gate, 0)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def write_ot_sets(path: Path, sets: list[OtSet]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow([
            "set_name",
            "project_root",
            "audio_pool_root",
            "project_file_count",
            "strd_file_count",
            "audio_file_count",
            "doc_path",
            "inferred_device",
            "handling_policy",
        ])
        for item in sets:
            writer.writerow([
                item.set_name,
                item.project_root.as_posix(),
                item.audio_pool_root.as_posix(),
                item.project_file_count,
                item.strd_file_count,
                item.audio_file_count,
                item.doc_path.as_posix() if item.doc_path else "",
                item.inferred_device,
                item.handling_policy,
            ])
