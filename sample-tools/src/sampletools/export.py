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
from dataclasses import dataclass, field
from pathlib import Path

from .config import EXPORT_ROOT, SAMPLES_ROOT, SOURCE_EXTS, DeviceSpec
from .convert import convert_file
from . import naming, probe as probe_mod


@dataclass
class Item:
    """One resolved source->output pair plus any warnings."""

    src: Path
    out_name: str
    warnings: list[str] = field(default_factory=list)
    out_rel: Path | None = None
    spec_override: DeviceSpec | None = None


@dataclass
class Plan:
    """The full resolved export plan for a device."""

    spec: DeviceSpec
    items: list[Item]
    missing: list[str]  # manifest entries that matched nothing


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


def read_crate_tsv(path: Path) -> list[CrateRow]:
    expected = ("sample_id", "source_path", "role", "descriptor", "reason")
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if tuple(reader.fieldnames or ()) != expected:
            raise ExportError("crate TSV has an unexpected schema")
        rows = [CrateRow(
            row["sample_id"], Path(row["source_path"]), row["role"].upper(),
            row["descriptor"], row["reason"],
        ) for row in reader]
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
    samples_root: Path = SAMPLES_ROOT,
) -> Plan:
    rows = read_crate_tsv(crate_path)
    if spec.name in {"digitakt", "tr8s"} and any(row.role in LONG_FORM_ROLES for row in rows):
        raise ExportError(f"{spec.name} foundation crate must contain one-shot roles only")
    if spec.name == "digitakt" and len(rows) > 127:
        raise ExportError(f"Digitakt project capacity is 127 samples, crate has {len(rows)}")
    if spec.name == "tr8s" and len(rows) > 256:
        raise ExportError(f"TR-8S import folder capacity is 256 files, crate has {len(rows)}")
    crate_name = naming.normalise_base(crate_path.stem)
    per_role: dict[str, int] = {}
    names: set[str] = set()
    items: list[Item] = []
    total_duration = 0.0
    for row in rows:
        source = samples_root / row.source_path
        if not source.is_file():
            raise ExportError(f"missing crate source: {row.source_path}")
        if _sha256(source) != row.sample_id:
            raise ExportError(f"hash changed for crate source: {row.source_path}")
        if spec.name == "tr8s":
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
            override = DeviceSpec(
                name=spec.name, export_dir=spec.export_dir, rate=spec.rate, bits=spec.bits,
                channels=None, name_warn=spec.name_warn, can_sync=spec.can_sync,
                sync_note=spec.sync_note,
            )
        items.append(Item(source, name, [], out_rel, override))
    if spec.name == "tr8s" and total_duration > 600.0:
        raise ExportError(f"TR-8S user-sample capacity is 600 seconds, crate has {total_duration:.1f}")
    return Plan(spec, items, [])


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


def _resolve_pattern(pattern: str) -> list[Path]:
    """Resolve a manifest pattern to concrete audio files under SAMPLES_ROOT."""
    p = Path(pattern)
    base = p if p.is_absolute() else (SAMPLES_ROOT / p)

    if any(ch in pattern for ch in "*?["):
        root = SAMPLES_ROOT
        matches = [m for m in root.glob(pattern) if m.is_file()]
    elif base.is_dir():
        matches = [m for m in base.rglob("*") if m.is_file()]
    elif base.is_file():
        matches = [base]
    else:
        matches = []

    return sorted(m for m in matches if m.suffix.lower() in SOURCE_EXTS)


def build_plan(spec: DeviceSpec) -> Plan:
    from .config import manifest_path

    entries = parse_manifest(manifest_path(spec.name))
    items: list[Item] = []
    missing: list[str] = []
    taken: set[str] = set()

    for pattern, rename in entries:
        files = _resolve_pattern(pattern)
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

    return Plan(spec=spec, items=items, missing=missing)


def export_device(
    spec: DeviceSpec,
    *,
    dry_run: bool = False,
    force: bool = False,
    plan: Plan | None = None,
) -> tuple[int, int]:
    """Run the export. Returns (converted, skipped)."""
    plan = plan or build_plan(spec)
    out_dir = EXPORT_ROOT / spec.export_dir
    converted = skipped = 0

    for item in plan.items:
        dest = out_dir / (item.out_rel or Path(item.out_name))
        if dest.exists() and not force:
            skipped += 1
            continue
        if dry_run:
            converted += 1
            continue
        convert_file(item.src, dest, item.spec_override or spec)
        converted += 1

    return converted, skipped


def sync_to_card(spec: DeviceSpec, dest_root: Path) -> int:
    """Copy EXPORT_ROOT/<DEVICE>/ into a mounted card. Returns files copied."""
    src_dir = EXPORT_ROOT / spec.export_dir
    # Profile crates already contain the hardware-native root (for example
    # ROLAND/TR-8S/SAMPLE or EIDETIC-CURATED/AUDIO).  Legacy flat exports keep
    # the historical EIDETIC-<DEVICE> wrapper.
    nested = any(path.is_dir() for path in src_dir.iterdir()) if src_dir.is_dir() else False
    target = dest_root if nested else dest_root / f"EIDETIC-{spec.export_dir}"
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in sorted(src_dir.rglob("*.wav")):
        rel = f.relative_to(src_dir)
        (target / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target / rel)
        count += 1
    return count
