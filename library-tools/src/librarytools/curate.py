"""Human-gated catalogue migration, audition packets, and promotion."""

from __future__ import annotations

import csv
import gzip
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import moves, review
from .classification.packets import classification_digest, read_classification_audit
from .classification.review import ReviewSession
from .inventory import LibraryDatabase, InventoryLocation, sha256_file
from .packet_classifier import AUDITION_GROUPS, PacketClassifierError, read_classifications
from .curation_policy import (
    LONG_ROLES, ONE_SHOT_ROLES, PILOT_QUOTAS, TRUSTED_ROLES, validate_crate_name,
)


DECISIONS = frozenset({"reject", "keep", "favourite"})
TAG_GROUPS = frozenset({"envelope", "tone", "texture", "source", "device"})
LABEL_FIELDS = (
    "sample_id", "current_path", "suggested_role", "decision", "true_role",
    "descriptor", "tags", "notes",
)


class CurationError(ValueError):
    pass


@dataclass(frozen=True)
class LabelRow:
    sample_id: str
    current_path: Path
    suggested_role: str
    decision: str
    true_role: str
    descriptor: str
    tags: str
    notes: str


_LOOSE_SOURCES = (
    (
        "Audentity Records Hardgroove House and Techno",
        "PACKS/audentity-records-hardgroove-house-and-techno",
        "vendor-pack",
    ),
    (
        "Elektron.Caught.on.Tape.808+909.Sound.Pack.for.Elektron.Octatrack",
        "PACKS/elektron-caught-on-tape-808-909-octatrack",
        "preserve-set",
    ),
    (
        "Elektron.Cult.of.SP.1200.Sound.Pack.for.Elektron.Octatrack",
        "PACKS/elektron-cult-of-sp1200-octatrack",
        "preserve-set",
    ),
)


def ableton_curated_references(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    found: list[Path] = []
    for path in sorted(root.rglob("*.als")):
        rel_parts = path.relative_to(root).parts
        if any(part.lower() in {"archive", "backup"} for part in rel_parts):
            continue
        try:
            with gzip.open(path, "rb") as fh:
                data = fh.read()
        except (OSError, EOFError):
            data = path.read_bytes()
        if b"CURATED" in data:
            found.append(path)
    return found


def _verify_plan_sources(root: Path, plan: list[moves.Move], database: LibraryDatabase) -> None:
    locations = database.current_locations()
    for item in plan:
        prefix = item.src.relative_to(root)
        for location in locations:
            if location.path == prefix or prefix in location.path.parents:
                path = root / location.path
                if not path.is_file() or sha256_file(path) != location.sample_id:
                    raise CurationError(f"hash changed since inventory scan: {location.path}")


def plan_catalogue_migration(
    root: Path, ableton_root: Path, database: LibraryDatabase,
) -> list[moves.Move]:
    if database.latest_complete_scan() is None:
        raise CurationError("a complete inventory scan is required")
    references = ableton_curated_references(ableton_root)
    if references:
        raise CurationError(f"Ableton Set references CURATED: {references[0]}")
    plan: list[moves.Move] = []
    curated = root / "CURATED"
    if curated.is_dir():
        for source in sorted(path for path in curated.iterdir() if path.is_dir()):
            plan.append(moves.Move(source, root / "CATALOGUE" / source.name, "legacy-catalogue"))
    if (root / "SEAN").is_dir():
        plan.append(moves.Move(root / "SEAN", root / "CATALOGUE" / "_LEGACY" / "SEAN", "legacy-personal"))
    for source_name, dest_rel, tag in _LOOSE_SOURCES:
        source = root / source_name
        if source.is_dir():
            plan.append(moves.Move(source, root / dest_rel, tag))
    collisions = [item.dest for item in plan if item.dest.exists()]
    if collisions:
        raise CurationError(f"migration destination exists: {collisions[0]}")
    _verify_plan_sources(root, plan, database)
    return plan


def apply_migration(
    root: Path, plan: list[moves.Move], undo_path: Path,
) -> dict[str, int]:
    counts = moves.apply_plan(plan, undo_path)
    if counts["exists"] or counts["missing"]:
        raise CurationError(f"migration incomplete: {counts}")
    (root / "CURATED").mkdir(parents=True, exist_ok=True)
    return counts


def _suggested_role(path: Path) -> str:
    text = " ".join(part.lower().replace("_", " ").replace("-", " ") for part in path.parts)
    checks = (
        ("HAT-OPEN", ("open hat", "openh", "ohh")),
        ("HAT-CLOSED", ("closed hat", "closedh", "chh")),
        ("DRUM-LOOP", ("drum loop", "top loop", "beat loop")),
        ("BASS-LOOP", ("bass loop", "bassloop")),
        ("SYNTH-LOOP", ("synth loop", "chord loop")),
        ("VOCAL-LOOP", ("vocal loop", "vox loop")),
        ("TEXTURE-DRONE", ("texture", "drone", "atmos", "ambient")),
        ("KICK", ("kick", "bassdrum", "bass drum", " bd ")),
        ("SNARE", ("snare", " sd ")),
        ("CLAP", ("clap",)), ("RIM", ("rim",)),
        ("SHAKER", ("shaker",)), ("RIDE", ("ride",)),
        ("CYMBAL", ("cymbal", " cym ", "crash")), ("TOM", ("tom",)),
        ("PERC", ("perc", "conga", "bongo", "cowbell", "clave")),
        ("BASS", ("bass", "sub", "reese")),
        ("STAB-CHORD", ("stab", "chord", "synth", "pluck")),
        ("FX", (" fx ", "impact", "riser", "noise")),
        ("VOCAL", ("vocal", "vox", "voice")),
    )
    padded = f" {text} "
    for role, tokens in checks:
        if any(token in padded for token in tokens):
            return role
    return ""


def _diverse(candidates: list[InventoryLocation], limit: int) -> list[InventoryLocation]:
    by_source: dict[str, list[InventoryLocation]] = {}
    for item in sorted(candidates, key=lambda row: (row.source_name, row.sample_id, row.path.as_posix())):
        by_source.setdefault(item.source_name, []).append(item)
    selected: list[InventoryLocation] = []
    while len(selected) < limit and any(by_source.values()):
        for source in sorted(by_source):
            if by_source[source] and len(selected) < limit:
                selected.append(by_source[source].pop(0))
    return selected


def _write_m3u8(path: Path, sources: list[Path]) -> None:
    lines = ["#EXTM3U", *(str(source) for source in sources)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def archive_rejected_playlists(packet_dir: Path) -> bool:
    """Archive the first name-derived playlist set exactly once before replacement."""
    playlists = packet_dir / "playlists"
    target = packet_dir / "archive" / "name-derived-playlists"
    if not playlists.is_dir() or target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(playlists), str(target))
    combined = packet_dir / "audition.m3u8"
    if combined.is_file():
        shutil.copy2(combined, target.parent / "name-derived-audition.m3u8")
    return True


def write_audition_playlists(
    root: Path,
    labels_path: Path,
    classification_path: Path,
    *,
    archive_rejected: bool = False,
) -> dict[str, Path]:
    rows = read_labels(labels_path)
    try:
        classifications = read_classifications(classification_path)
    except PacketClassifierError as exc:
        raise CurationError(str(exc)) from exc
    by_id = {row.sample_id: row for row in classifications}
    root = root.resolve()
    grouped: dict[str, list[tuple[float, Path]]] = {}
    for row in rows:
        classification = by_id.get(row.sample_id)
        if classification is None or classification.current_path != row.current_path:
            raise CurationError(f"classification missing or stale for: {row.current_path}")
        source = (root / row.current_path).resolve()
        if not source.is_relative_to(root):
            raise CurationError(f"sample path escapes root: {row.current_path}")
        if not source.is_file() or sha256_file(source) != row.sample_id:
            raise CurationError(f"sample is missing or changed: {row.current_path}")
        confidence = min(classification.form_confidence, classification.content_confidence)
        grouped.setdefault(classification.audition_group, []).append((confidence, source))

    ordered_groups = [group for group in AUDITION_GROUPS if group in grouped]
    combined: list[Path] = []
    for group in ordered_groups:
        grouped[group].sort(key=lambda item: (-item[0], str(item[1])))
        combined.extend(source for _, source in grouped[group])

    output_dir = labels_path.parent
    combined_path = output_dir / "audition.m3u8"
    playlists_dir = output_dir / "playlists"
    generated = {"combined": combined_path}
    index_lines = [
        "# Audition playlists",
        "",
        "Listen category by category, then record every decision in `../labels.tsv`.",
        "",
        "| Category | Files | Playlist |",
        "|---|---:|---|",
    ]
    publish_root = Path(tempfile.mkdtemp(prefix=".playlist-publish-", dir=output_dir))
    staged_playlists = publish_root / "playlists"
    staged_combined = publish_root / "audition.m3u8"
    staged_playlists.mkdir()
    try:
        _write_m3u8(staged_combined, combined)
        if not grouped:
            index_lines.extend(["", "No categories are present in this label sheet."])
        for role in ordered_groups:
            filename = f"{role}.m3u8"
            _write_m3u8(
                staged_playlists / filename,
                [source for _, source in grouped[role]],
            )
            generated[role] = playlists_dir / filename
            index_lines.append(
                f"| `{role}` | {len(grouped[role])} | [{filename}]({filename}) |"
            )
        index_lines.extend([
            "",
            "[Complete packet](../audition.m3u8) follows the category table above; within each "
            "category, confidence runs from highest to lowest.",
        ])
        (staged_playlists / "README.md").write_text(
            "\n".join(index_lines) + "\n", encoding="utf-8",
        )

        previous_playlists = publish_root / "previous-playlists"
        previous_combined = publish_root / "previous-audition.m3u8"
        archive_target = output_dir / "archive" / "name-derived-playlists"
        archive_created = False
        try:
            if playlists_dir.exists() or playlists_dir.is_symlink():
                playlists_dir.replace(previous_playlists)
            if combined_path.exists() or combined_path.is_symlink():
                combined_path.replace(previous_combined)
            staged_playlists.replace(playlists_dir)
            staged_combined.replace(combined_path)
            if archive_rejected and previous_playlists.exists() and not archive_target.exists():
                archive_target.parent.mkdir(parents=True, exist_ok=True)
                archive_created = True
                shutil.copytree(previous_playlists, archive_target)
                if previous_combined.is_file():
                    shutil.copy2(
                        previous_combined,
                        archive_target.parent / "name-derived-audition.m3u8",
                    )
        except OSError:
            if archive_created and archive_target.exists():
                shutil.rmtree(archive_target)
                archived_combined = archive_target.parent / "name-derived-audition.m3u8"
                if archived_combined.exists():
                    archived_combined.unlink()
            if playlists_dir.exists() or playlists_dir.is_symlink():
                if playlists_dir.is_dir() and not playlists_dir.is_symlink():
                    shutil.rmtree(playlists_dir)
                else:
                    playlists_dir.unlink()
            if combined_path.exists() or combined_path.is_symlink():
                combined_path.unlink()
            if previous_playlists.exists() or previous_playlists.is_symlink():
                previous_playlists.replace(playlists_dir)
            if previous_combined.exists() or previous_combined.is_symlink():
                previous_combined.replace(combined_path)
            raise
    finally:
        shutil.rmtree(publish_root, ignore_errors=True)

    generated["index"] = playlists_dir / "README.md"
    return generated


def regenerate_packet_playlists(labels_path: Path) -> dict[str, Path]:
    metadata_path = labels_path.parent / "packet-meta.json"
    if not metadata_path.is_file():
        raise CurationError(f"packet-meta.json is missing beside {labels_path.name}")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CurationError(f"invalid packet metadata: {exc}") from exc
    root = metadata.get("root")
    if not isinstance(root, str) or not root.strip():
        raise CurationError("invalid packet metadata: root must be a non-empty path")
    root_path = Path(root)
    if not root_path.is_dir():
        raise CurationError(f"invalid packet metadata: sample root is not a directory: {root}")
    benchmark = metadata.get("benchmark")
    if not isinstance(benchmark, dict) or not benchmark.get("ready") or not benchmark.get("passed"):
        raise CurationError("benchmark quality gate has not passed")
    classification_path = labels_path.parent / "classification.tsv"
    if not classification_path.is_file():
        raise CurationError(f"classification.tsv is missing beside {labels_path.name}")
    if metadata.get("schema_version", 0) >= 3:
        digest = metadata.get("classification_digest")
        context = metadata.get("classification_context")
        review_metadata = metadata.get("review")
        if not isinstance(digest, str) or not isinstance(context, dict):
            raise CurationError("classification digest metadata is missing")
        if (
            not isinstance(review_metadata, dict)
            or not review_metadata.get("ready")
            or not review_metadata.get("passed")
            or review_metadata.get("classification_digest") != digest
        ):
            raise CurationError("exception review quality gate has not passed")
        try:
            candidates = read_classification_audit(
                labels_path.parent / "classification-audit.jsonl"
            )
            if classification_digest(candidates, context) != digest:
                raise CurationError("classification audit digest does not match packet metadata")
            with (labels_path.parent / "benchmark-labels.tsv").open(
                encoding="utf-8", newline="",
            ) as benchmark_fh:
                benchmark_sample_ids = tuple(
                    row["sample_id"]
                    for row in csv.DictReader(benchmark_fh, delimiter="\t")
                )
            if len(benchmark_sample_ids) != 24 or len(set(benchmark_sample_ids)) != 24:
                raise CurationError("frozen benchmark must contain 24 unique samples")
            session = ReviewSession.open(
                labels_path.parent / "review-state.json",
                candidates,
                digest,
                benchmark_sample_ids=benchmark_sample_ids,
            )
            if not session.queue.gate().passed:
                raise CurationError("exception review quality gate has not passed")
            resolved_digest = session.queue.resolution_digest()
            if metadata.get("resolution_digest") != resolved_digest:
                raise CurationError("human resolution digest does not match packet metadata")
            expected = session.queue.resolved_classifications()
            actual = read_classifications(classification_path)
        except PacketClassifierError as exc:
            raise CurationError(str(exc)) from exc
        signature = lambda row: (
            row.sample_id,
            row.current_path,
            row.form,
            row.content,
            row.audition_group,
        )
        if [signature(row) for row in actual] != [signature(row) for row in expected]:
            raise CurationError("classification.tsv does not match completed review state")
    should_archive = (
        not metadata.get("audio_playlists_published")
        and not (labels_path.parent / "archive" / "name-derived-playlists").exists()
    )
    generated = write_audition_playlists(
        root_path,
        labels_path,
        classification_path,
        archive_rejected=should_archive,
    )
    metadata["audio_playlists_published"] = True
    if metadata.get("schema_version", 0) >= 3:
        metadata["published_digest"] = metadata["resolution_digest"]
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return generated


def prepare_packet(
    root: Path,
    database: LibraryDatabase,
    output_dir: Path,
    *,
    quotas: dict[str, int] | None = None,
    multiplier: int = 2,
) -> int:
    scan_id = database.latest_complete_scan()
    if scan_id is None:
        raise CurationError("a complete inventory scan is required")
    quotas = quotas or PILOT_QUOTAS
    grouped: dict[str, list[InventoryLocation]] = {role: [] for role in quotas}
    for item in database.current_locations():
        if item.zone == "CURATED":
            continue
        role = _suggested_role(item.path)
        if role in grouped:
            grouped[role].append(item)
    selected: list[tuple[str, InventoryLocation]] = []
    for role, quota in quotas.items():
        selected.extend((role, item) for item in _diverse(grouped[role], quota * multiplier))
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "labels.tsv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=LABEL_FIELDS, delimiter="\t")
        writer.writeheader()
        for role, item in selected:
            writer.writerow({
                "sample_id": item.sample_id, "current_path": item.path.as_posix(),
                "suggested_role": role, "decision": "", "true_role": "",
                "descriptor": "", "tags": "", "notes": "",
            })
    (output_dir / "packet-meta.json").write_text(
        json.dumps({"schema_version": 2, "scan_id": scan_id, "root": str(root)}, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_m3u8(output_dir / "audition.m3u8", [root / item.path for _, item in selected])
    return len(selected)


def read_labels(path: Path) -> list[LabelRow]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if tuple(reader.fieldnames or ()) != LABEL_FIELDS:
            raise CurationError("labels.tsv has an unexpected schema")
        return [LabelRow(
            sample_id=row["sample_id"], current_path=Path(row["current_path"]),
            suggested_role=row["suggested_role"], decision=row["decision"].strip().lower(),
            true_role=row["true_role"].strip().upper(), descriptor=row["descriptor"].strip(),
            tags=row["tags"].strip(), notes=row["notes"].strip(),
        ) for row in reader]


def validate_labels(rows: list[LabelRow]) -> None:
    for index, row in enumerate(rows, start=2):
        if len(row.sample_id) != 64 or any(ch not in "0123456789abcdef" for ch in row.sample_id):
            raise CurationError(f"row {index}: invalid sample_id")
        if row.decision not in DECISIONS:
            raise CurationError(f"row {index}: decision must be reject, keep, or favourite")
        if row.decision == "favourite":
            if row.true_role not in TRUSTED_ROLES:
                raise CurationError(f"row {index}: favourite requires a valid true_role")
            if not row.descriptor:
                raise CurationError(f"row {index}: favourite requires a descriptor")
        _parse_tags(row.tags, row_number=index)


def _parse_tags(value: str, *, row_number: int) -> list[tuple[str, str]]:
    parsed: list[tuple[str, str]] = []
    for raw in filter(None, (item.strip() for item in value.split(";"))):
        group, separator, tag = raw.partition(":")
        if not separator or group not in TAG_GROUPS or not tag:
            raise CurationError(f"row {row_number}: invalid controlled tag {raw!r}")
        parsed.append((group, tag))
    return parsed


def promote_favourites(
    root: Path,
    database: LibraryDatabase,
    labels_path: Path,
    *,
    run_id: str,
) -> list[Path]:
    meta_path = labels_path.parent / "packet-meta.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("scan_id") != database.latest_complete_scan():
            raise CurationError("stale packet: a newer complete inventory scan exists")
        if Path(str(meta.get("root", ""))) != root:
            raise CurationError("stale packet: sample root does not match")
    rows = read_labels(labels_path)
    validate_labels(rows)
    current = {item.path: item for item in database.current_locations()}
    plan: list[tuple[LabelRow, InventoryLocation, Path | None]] = []
    destinations: set[Path] = set()
    for row in rows:
        location = current.get(row.current_path)
        if location is None or location.sample_id != row.sample_id:
            raise CurationError(f"stale or missing source: {row.current_path}")
        source = root / row.current_path
        if not source.is_file():
            raise CurationError(f"stale or missing source: {row.current_path}")
        if sha256_file(source) != row.sample_id:
            raise CurationError(f"hash changed since inventory scan: {row.current_path}")
        dest = None
        if row.decision == "favourite":
            role_token = review.normalise_token(row.true_role)
            descriptor = review.normalise_token(row.descriptor)
            source_token = review.normalise_token(location.source_name)
            name = f"{role_token}_{descriptor}_{source_token}_{row.sample_id[:8]}{source.suffix.lower()}"
            dest = root / "CURATED" / row.true_role / name
            if dest.exists() or dest.is_symlink() or dest in destinations:
                raise CurationError(f"curated destination exists or is repeated: {dest}")
            for parent in dest.parents:
                if (parent.exists() or parent.is_symlink()) and not parent.is_dir():
                    raise CurationError(f"curated destination parent is not a directory: {parent}")
            destinations.add(dest)
        plan.append((row, location, dest))

    # Validate the whole selection before recording decisions or copying audio.
    promoted: list[Path] = []
    for row, location, dest in plan:
        source = root / row.current_path
        if sha256_file(source) != row.sample_id:
            raise CurationError(f"hash changed since inventory scan: {row.current_path}")
        if dest is not None and (dest.exists() or dest.is_symlink()):
            raise CurationError(f"curated destination exists: {dest}")
        database.record_review(
            row.sample_id, labels_path.parent.name, row.decision, row.true_role,
            row.descriptor, row.notes,
        )
        database.record_tags(row.sample_id, _parse_tags(row.tags, row_number=0))
        if dest is None:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        rel_dest = dest.relative_to(root)
        database.record_promotion(row.sample_id, rel_dest, row.current_path, run_id)
        database.record_file(root, dest, location.scan_id)
        promoted.append(dest)
    return promoted


def write_consumer_views(
    database: LibraryDatabase,
    labels_path: Path,
    output_dir: Path,
    *,
    quotas: dict[str, int] | None = None,
    name: str = "foundation-v1",
) -> dict[str, Path]:
    validate_crate_name(name)
    rows = read_labels(labels_path)
    validate_labels(rows)
    favourites = [row for row in rows if row.decision == "favourite"]
    quotas = quotas or PILOT_QUOTAS
    counts = {role: sum(row.true_role == role for row in favourites) for role in quotas}
    shortages = {role: quota - counts[role] for role, quota in quotas.items() if counts[role] < quota}
    if shortages:
        detail = ", ".join(f"{role}:{count}" for role, count in shortages.items())
        raise CurationError(f"pilot quota shortages: {detail}")
    promotion_by_id = {
        str(item["sample_id"]): Path(str(item["curated_path"]))
        for item in database.promotions()
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    fields = ("sample_id", "source_path", "role", "descriptor", "reason")
    all_path = output_dir / f"{name}-all.tsv"
    one_path = output_dir / f"{name}-one-shots.tsv"
    ableton_path = output_dir / "ableton-curated.tsv"

    def crate_rows(items: list[LabelRow]) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for row in items:
            curated = promotion_by_id.get(row.sample_id)
            if curated is None:
                raise CurationError(f"favourite has not been promoted: {row.sample_id}")
            result.append({
                "sample_id": row.sample_id, "source_path": curated.as_posix(),
                "role": row.true_role, "descriptor": row.descriptor,
                "reason": row.tags,
            })
        return result

    all_crate_rows = crate_rows(favourites)
    one_crate_rows = [row for row in all_crate_rows if row["role"] in ONE_SHOT_ROLES]
    for path, output_rows in ((all_path, all_crate_rows), (one_path, one_crate_rows)):
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields, delimiter="\t")
            writer.writeheader()
            writer.writerows(output_rows)
    with ableton_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=("sample_id", "path", "role", "descriptor", "tags"),
            delimiter="\t",
        )
        writer.writeheader()
        for row in all_crate_rows:
            writer.writerow({
                "sample_id": row["sample_id"], "path": row["source_path"],
                "role": row["role"], "descriptor": row["descriptor"],
                "tags": row["reason"],
            })
    (output_dir / "ableton-tags.md").write_text(
        "# Ableton Live 12 suggested tags\n\n"
        "Add only `CURATED/` to Places. Use role, descriptor, source, and tags from "
        "`ableton-curated.tsv` for saved searches.\n",
        encoding="utf-8",
    )
    return {"all": all_path, "one_shots": one_path, "ableton": ableton_path}


def undo_promotions(root: Path, database: LibraryDatabase, run_id: str) -> int:
    selected = [item for item in database.promotions() if item["run_id"] == run_id]
    moved = 0
    for item in selected:
        source = root / str(item["curated_path"])
        rel = Path(str(item["curated_path"]))
        dest = root / "_QUARANTINE" / "promotion-undo" / run_id / rel
        status = moves.safe_move(source, dest)
        if status == "exists":
            raise CurationError(f"promotion undo destination exists: {dest}")
        if status == "missing":
            raise CurationError(f"promoted copy missing: {source}")
        database.mark_missing(rel)
        moved += 1
    return moved
