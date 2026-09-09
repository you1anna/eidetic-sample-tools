"""Manifest parsing + export orchestration.

A manifest (manifests/<device>.txt) is a plain text file. Each non-blank,
non-`#` line is one entry, resolved relative to SAMPLES_ROOT (absolute paths
also accepted). Entries may be:

    KICKS/Goldbaby-Super-Analog-909/kick-01.wav        # a single file
    DRUM-LOOPS/Riemann-Tribal-Techno-1/*.wav           # a glob
    PERC/conga.wav => conga-hi                          # rename the output base

Output lands in EXPORT_ROOT/<DEVICE>/<normalised-name>.wav and is idempotent:
existing outputs are skipped unless force=True.
"""

from __future__ import annotations

import shutil
import csv
import hashlib
import io
import json
import os
import tempfile
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path

from .config import EXPORT_ROOT, SAMPLES_ROOT, SOURCE_EXTS, DeviceSpec
from .convert import convert_file
from . import naming, probe as probe_mod, receipts
from .export_state import StateError, library_writer


@dataclass
class Item:
    """One resolved source->output pair plus any warnings."""

    src: Path
    out_name: str
    warnings: list[str] = field(default_factory=list)
    out_rel: Path | None = None
    spec_override: DeviceSpec | None = None
    sample_id: str | None = None


@dataclass
class Plan:
    """The full resolved export plan for a device."""

    spec: DeviceSpec
    items: list[Item]
    missing: list[str]  # manifest entries that matched nothing
    samples_root: Path | None = None
    export_root: Path | None = None


class ExportError(ValueError):
    pass


@dataclass(frozen=True)
class CrateRow:
    sample_id: str
    source_path: Path
    role: str
    descriptor: str
    reason: str


ROLE_CODES: dict[str, str] = {
    "KICK": "BD", "SNARE": "SD", "CLAP": "CP", "RIM": "RS",
    "HAT-CLOSED": "CH", "HAT-OPEN": "OH", "SHAKER": "SH",
    "CYMBAL": "CY", "RIDE": "RD", "TOM": "TM", "PERC": "PC",
    "BASS": "BS", "STAB-CHORD": "ST", "FX": "FX", "VOCAL": "VX",
    "DRUM-LOOP": "DL", "BASS-LOOP": "BL", "SYNTH-LOOP": "SL",
    "VOCAL-LOOP": "VL", "TEXTURE-DRONE": "TX",
}
LONG_FORM_ROLES = frozenset({"DRUM-LOOP", "BASS-LOOP", "SYNTH-LOOP", "VOCAL-LOOP", "TEXTURE-DRONE"})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def read_crate_tsv(path: Path, *, require_approval: bool = False) -> list[CrateRow]:
    metadata = path.with_suffix(path.suffix + ".metadata.json")
    data = {}
    if metadata.exists():
        try:
            data = json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ExportError(f"invalid crate metadata: {metadata}") from exc
        if (not isinstance(data, dict) or data.get("format") != "eidetic-crate"
                or type(data.get("version")) is not int or data["version"] != 1):
            raise ExportError(f"unsupported crate metadata version: {metadata}")
    payload = path.read_bytes()
    if "sha256" in data and data["sha256"] != hashlib.sha256(payload).hexdigest():
        raise ExportError(f"crate metadata hash does not match TSV: {path}; preserve and regenerate the crate pair")
    expected = ("sample_id", "source_path", "role", "descriptor", "reason")
    with io.StringIO(payload.decode("utf-8"), newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if tuple(reader.fieldnames or ()) != expected:
            raise ExportError("crate TSV has an unexpected schema")
        rows: list[CrateRow] = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ExportError(f"crate row {reader.line_num}: expected exactly five TSV fields")
            rows.append(CrateRow(
                row["sample_id"], Path(row["source_path"]), row["role"].upper(),
                row["descriptor"], row["reason"],
            ))
    if require_approval and 'approval' in data:
        approval = data['approval']
        if not isinstance(approval, dict) or approval.get('status') != 'approved':
            raise ExportError('search crate requires review: recorded active promotion and favourite approval are missing')
        evidence = approval.get('rows')
        if not isinstance(evidence, list) or any(not isinstance(row, dict) or row.get('status') != 'approved' for row in evidence):
            raise ExportError('search crate approval evidence is incomplete; regenerate it after review')
        if [(row.get('sample_id'), row.get('source_path')) for row in evidence] != [(row.sample_id, row.source_path.as_posix()) for row in rows]:
            raise ExportError('search crate approval evidence does not match its rows; regenerate it after review')
    return rows


def _compact_name(row: CrateRow, index: int) -> str:
    try:
        code = ROLE_CODES[row.role]
    except KeyError as exc:
        raise ExportError(f"unknown trusted role {row.role!r}") from exc
    descriptor = naming.normalise_base(row.descriptor)[:8] or "sample"
    return f"{code}{index:02}_{descriptor}_{row.sample_id[:4]}.wav"


def build_crate_plan(
    spec: DeviceSpec,
    crate_path: Path,
    samples_root: Path | None = None,
    *, export_root: Path | None = None,
) -> Plan:
    samples_root = samples_root or SAMPLES_ROOT
    rows = read_crate_tsv(crate_path, require_approval=True)
    if spec.name in {"digitakt", "tr8s"} and any(row.role in LONG_FORM_ROLES for row in rows):
        raise ExportError(f"{spec.name} foundation crate must contain one-shot roles only")
    if spec.max_project_samples is not None and len(rows) > spec.max_project_samples:
        raise ExportError(
            f"{spec.name} project capacity is {spec.max_project_samples} samples, crate has {len(rows)}"
        )
    if spec.max_folder_files is not None and len(rows) > spec.max_folder_files:
        raise ExportError(
            f"{spec.name} import folder capacity is {spec.max_folder_files} files, crate has {len(rows)}"
        )
    crate_name = naming.normalise_base(crate_path.stem)
    curated_root = (samples_root / "CURATED").resolve()
    per_role: dict[str, int] = {}
    names: set[str] = set()
    items: list[Item] = []
    total_duration = 0.0
    for row in rows:
        source = samples_root / row.source_path
        if not source.is_file():
            raise ExportError(f"missing crate source: {row.source_path}")
        if not source.resolve().is_relative_to(curated_root):
            raise ExportError(
                f"crate source is not under CURATED/: {row.source_path} "
                "(promote it with sample-curate first)"
            )
        if _sha256(source) != row.sample_id:
            raise ExportError(f"hash changed for crate source: {row.source_path}")
        if spec.max_total_seconds is not None:
            total_duration += probe_mod.probe(source).duration or 0.0
        per_role[row.role] = per_role.get(row.role, 0) + 1
        name = _compact_name(row, per_role[row.role])
        if name in names:
            raise ExportError(f"duplicate compact output name: {name}")
        names.add(name)
        if spec.name == "digitakt":
            out_rel = Path(crate_name) / row.role / name
        elif spec.name == "tr8s":
            out_rel = Path("ROLAND/TR-8S/SAMPLE") / crate_name / name
        else:
            out_rel = Path("EIDETIC-CURATED/AUDIO") / crate_name / row.role / name
        override = None
        if spec.name == "tr8s" and "stereo-essential" in row.reason:
            override = replace(spec, channels=None)
        items.append(Item(source, name, [], out_rel, override, row.sample_id))
    if spec.max_total_seconds is not None and total_duration > spec.max_total_seconds:
        raise ExportError(
            f"{spec.name} user-sample capacity is {spec.max_total_seconds:g} seconds, "
            f"crate has {total_duration:.1f}"
        )
    return Plan(spec, items, [], samples_root, export_root)


def parse_manifest(path: Path) -> list[tuple[str, str | None]]:
    """Return (pattern, rename_base|None) tuples from a manifest file."""
    if not path.exists():
        return []
    entries: list[tuple[str, str | None]] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=>" in line:
            pattern, _, rename = line.partition("=>")
            entries.append((pattern.strip(), rename.strip() or None))
        else:
            entries.append((line, None))
    return entries


def _resolve_pattern(pattern: str, samples_root: Path | None = None) -> list[Path]:
    """Resolve a manifest pattern to concrete audio files under SAMPLES_ROOT."""
    samples_root = samples_root or SAMPLES_ROOT
    p = Path(pattern)
    base = p if p.is_absolute() else (samples_root / p)

    if any(ch in pattern for ch in "*?["):
        root = samples_root
        matches = [m for m in root.glob(pattern) if m.is_file()]
    elif base.is_dir():
        matches = [m for m in base.rglob("*") if m.is_file()]
    elif base.is_file():
        matches = [base]
    else:
        matches = []

    return sorted(m for m in matches if m.suffix.lower() in SOURCE_EXTS)


def build_plan(spec: DeviceSpec, *, samples_root: Path | None = None, export_root: Path | None = None) -> Plan:
    from .config import manifest_path

    samples_root = samples_root or SAMPLES_ROOT
    entries = parse_manifest(manifest_path(spec.name, samples_root=samples_root))
    items: list[Item] = []
    missing: list[str] = []
    taken: set[str] = set()

    for pattern, rename in entries:
        files = _resolve_pattern(pattern, samples_root)
        if not files:
            missing.append(pattern)
            continue
        for src in files:
            if rename and len(files) == 1:
                out = f"{naming.normalise_base(rename)}.wav"
            else:
                out = naming.output_name(src)
            out = naming.dedupe(out, taken)
            warnings: list[str] = []
            if naming.too_long(out, spec.name_warn):
                warnings.append(f"name >{spec.name_warn} chars (will truncate on device)")
            items.append(Item(src=src, out_name=out, warnings=warnings))

    return Plan(spec=spec, items=items, missing=missing, samples_root=samples_root, export_root=export_root)


def _export_destination(spec: DeviceSpec, item: Item, export_root: Path | None = None) -> Path:
    root = (export_root or EXPORT_ROOT) / spec.export_dir
    destination = root / _safe_sync_relative(item.out_rel or Path(item.out_name))
    if not destination.resolve().is_relative_to(root.resolve()) or destination.is_symlink():
        raise ExportError(f"export destination escapes export root: {destination}")
    if destination.exists() and not destination.is_file():
        raise ExportError(f"invalid export destination: {destination}")
    return destination


def export_status(spec: DeviceSpec, item: Item, *, versions: dict | None = None,
                  export_root: Path | None = None) -> str:
    """Inspect whether the staged bytes are reusable without changing anything."""
    source_hash = _sha256(item.src)
    if item.sample_id is not None and source_hash != item.sample_id:
        raise ExportError(f"hash changed for crate source: {item.src}")
    destination = _export_destination(spec, item, export_root)
    if not destination.exists():
        return "new"
    return receipts.check(destination, source_hash, item.spec_override or spec,
                          versions if versions is not None else receipts.runtime())


def _convert_verified(item: Item, destination: Path, spec: DeviceSpec,
                      versions: dict, root: Path | None) -> None:
    source_hash = _sha256(item.src)
    if item.sample_id is not None and source_hash != item.sample_id:
        raise ExportError(f"hash changed for crate source: {item.src}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + destination.stem + ".", suffix=".wav", dir=destination.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        convert_file(item.src, temporary, spec)
        if _sha256(item.src) != source_hash:
            raise ExportError(f"source changed during conversion: {item.src}")
        info = probe_mod.probe(temporary)
        expected_channels = spec.channels
        if expected_channels is None:
            expected_channels = probe_mod.probe(item.src).channels
        if (info.rate != spec.rate or info.bits != spec.bits or info.channels != expected_channels
                or info.channels not in (1, 2) or info.duration is None or info.duration <= 0):
            raise ExportError(f"converted output has invalid format: {destination}")
        from .export_state import check_state
        library_id = check_state(root) if root is not None else None
        data = receipts.make(temporary, item.src, source_hash, spec, versions, root=root, library_id=library_id)
        with temporary.open("rb") as fh:
            os.fsync(fh.fileno())
        # Publish the WAV first. A crash before the receipt leaves it unverified,
        # so it requires --force rather than becoming a silently reusable result.
        temporary.replace(destination)
        receipts.atomic_json(receipts.receipt_path(destination), data)
    finally:
        temporary.unlink(missing_ok=True)


def export_device(spec: DeviceSpec, *, dry_run: bool = False, force: bool = False,
                  plan: Plan | None = None) -> tuple[int, int]:
    plan = plan or build_plan(spec)
    if dry_run:
        return _export_device(spec, dry_run=True, force=force, plan=plan)
    try:
        with library_writer(plan.samples_root or SAMPLES_ROOT, "sample-export"):
            return _export_device(spec, force=force, plan=plan)
    except StateError as exc:
        raise ExportError(str(exc)) from exc


def _export_device(
    spec: DeviceSpec,
    *,
    dry_run: bool = False,
    force: bool = False,
    plan: Plan | None = None,
) -> tuple[int, int]:
    """Return (converted, verified reused); stale files require explicit --force."""
    plan = plan or build_plan(spec)
    versions = receipts.runtime() if any(_export_destination(spec, i, plan.export_root).exists() for i in plan.items) or (plan.items and not dry_run) else {}
    prepared = [(item, _export_destination(spec, item, plan.export_root), export_status(spec, item, versions=versions, export_root=plan.export_root))
                for item in plan.items]
    blocked = [(destination, status) for _, destination, status in prepared
               if status not in ("new", "verified") and not force]
    if blocked and not dry_run:
        details = "; ".join(f"{path}: {status}" for path, status in blocked)
        raise ExportError(f"{details}; rebuild derived output with --force")
    converted = skipped = 0
    for item, destination, status in prepared:
        if status == "verified" and not force:
            skipped += 1
            continue
        if dry_run:
            if status not in ("new", "verified") and not force:
                print(f"  {destination}: {status}; requires --force")
            else:
                converted += 1
            continue
        _convert_verified(item, destination, item.spec_override or spec, versions, plan.samples_root)
        converted += 1
    return converted, skipped


def _safe_sync_relative(path: Path) -> Path:
    if path.is_absolute() or not path.parts or path == Path(".") or ".." in path.parts:
        raise ExportError(f"invalid staged export path: {path}")
    return path


def _sync_pairs(spec: DeviceSpec, dest_root: Path, plan: Plan | None) -> list[tuple[Path, Path]]:
    """Resolve and validate every staged source/card destination before copying."""
    if not dest_root.is_dir():
        raise ExportError(f"sync target not found: {dest_root}")

    src_dir = (plan.export_root if plan and plan.export_root else EXPORT_ROOT) / spec.export_dir
    export_root = src_dir.resolve()
    card_root = dest_root.resolve()
    if plan is None:
        # Profile crates already contain the hardware-native root (for example
        # ROLAND/TR-8S/SAMPLE or EIDETIC-CURATED/AUDIO). Legacy flat exports
        # keep the historical EIDETIC-<DEVICE> wrapper.
        nested = any(path.is_dir() for path in src_dir.iterdir()) if src_dir.is_dir() else False
        target_root = card_root if nested else card_root / f"EIDETIC-{spec.export_dir}"
        sources = [
            (staged, staged.relative_to(src_dir))
            for staged in sorted(src_dir.rglob("*.wav"))
        ] if src_dir.is_dir() else []
    else:
        target_root = card_root if any(item.out_rel is not None for item in plan.items) else card_root / f"EIDETIC-{spec.export_dir}"
        sources = [
            (src_dir / _safe_sync_relative(item.out_rel or Path(item.out_name)),
             _safe_sync_relative(item.out_rel or Path(item.out_name)))
            for item in plan.items
        ]

    pairs: list[tuple[Path, Path]] = []
    for staged, relative in sources:
        resolved_staged = staged.resolve()
        if not resolved_staged.is_relative_to(export_root):
            raise ExportError(f"staged export escapes export root: {staged}")
        if not staged.is_file():
            raise ExportError(f"missing staged export: {staged}")

        destination = target_root / _safe_sync_relative(relative)
        resolved_parent = destination.parent.resolve()
        if not resolved_parent.is_relative_to(card_root):
            raise ExportError(f"sync destination escapes card root: {destination}")
        ancestor = card_root
        for part in destination.parent.relative_to(card_root).parts:
            ancestor /= part
            if ancestor.is_symlink() and not ancestor.exists():
                raise ExportError(f"destination ancestor is a dangling symlink: {ancestor}")
            if ancestor.exists() and not ancestor.is_dir():
                raise ExportError(f"destination ancestor is not a directory: {ancestor}")
        if destination.is_dir() or destination.is_symlink():
            raise ExportError(f"invalid sync destination: {destination}")
        pairs.append((staged, destination))
    return pairs


def sync_to_card(spec: DeviceSpec, dest_root: Path, *, plan: Plan | None = None) -> int:
    try:
        with library_writer(plan.samples_root if plan and plan.samples_root else SAMPLES_ROOT,
                            "sample-export --sync"):
            return _sync_to_card(spec, dest_root, plan=plan)
    except StateError as exc:
        raise ExportError(str(exc)) from exc


def _sync_to_card(spec: DeviceSpec, dest_root: Path, *, plan: Plan | None = None) -> int:
    """Copy selected stages atomically; persist copy evidence separately from playback."""
    pairs = _sync_pairs(spec, dest_root, plan)
    if not pairs:
        return 0
    # Every path is preflighted above before inspecting reuse evidence. No card
    # writes occur if any selected stage is damaged, stale or unverified.
    if plan is not None:
        versions = receipts.runtime()
        for item in plan.items:
            status = export_status(spec, item, versions=versions, export_root=plan.export_root)
            if status != "verified":
                raise ExportError(f"cannot transfer {item.out_name}: {status}; rebuild with --force")
    else:
        for staged, _ in pairs:
            evidence = receipts.read_receipt(staged)
            if evidence is None or evidence.get("output_sha256") != _sha256(staged):
                raise ExportError(f"unverified or damaged staged export receipt: {staged}; rebuild with --force")
    operation_id = str(uuid.uuid4())
    library_root = plan.samples_root if plan and plan.samples_root else SAMPLES_ROOT
    record_path = library_root / ".eidetic" / "transfers" / f"{operation_id}.json"
    if record_path.parent.is_symlink():
        raise ExportError(f"transfer evidence directory must not be a symlink: {record_path.parent}")
    selected_export_root = plan.export_root if plan and plan.export_root else EXPORT_ROOT
    data = {"format": "eidetic-transfer", "version": 1, "operation_id": operation_id,
            "created_at": receipts.now(), "device": spec.name, "destination_root": str(dest_root.resolve()),
            "status": "in_progress", "hardware_verification": "unverified",
            "items": [{"source": str(source.relative_to(selected_export_root)),
                       "destination": str(destination.relative_to(dest_root.resolve())),
                       "output_sha256": _sha256(source), "status": "pending"}
                      for source, destination in pairs]}
    receipts.atomic_json(record_path, data)
    try:
        for (staged, destination), entry in zip(pairs, data["items"]):
            expected_hash = entry["output_sha256"]
            entry["status"] = "copying"
            receipts.atomic_json(record_path, data)
            if not destination.is_file() or _sha256(destination) != expected_hash:
                destination.parent.mkdir(parents=True, exist_ok=True)
                fd, name = tempfile.mkstemp(prefix="." + destination.name + ".", suffix=".tmp", dir=destination.parent)
                os.close(fd)
                temporary = Path(name)
                try:
                    shutil.copy2(staged, temporary)
                    if _sha256(temporary) != expected_hash or _sha256(staged) != expected_hash:
                        raise ExportError(f"staged output changed during transfer: {staged}")
                    with temporary.open("rb") as fh:
                        os.fsync(fh.fileno())
                    temporary.replace(destination)
                finally:
                    temporary.unlink(missing_ok=True)
            if _sha256(destination) != expected_hash:
                raise ExportError(f"transferred output hash mismatch: {destination}")
            entry["status"] = "verified"
            receipts.atomic_json(record_path, data)
    except BaseException as exc:
        data["status"] = "interrupted"
        data["error"] = str(exc)
        receipts.atomic_json(record_path, data)
        raise
    data["status"] = "complete"
    data["completed_at"] = receipts.now()
    receipts.atomic_json(record_path, data)
    return len(pairs)
