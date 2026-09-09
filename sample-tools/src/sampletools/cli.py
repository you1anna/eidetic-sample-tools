"""Command-line entry point for sample-export."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import DEVICE_SPECS, EXPORT_ROOT, SAMPLES_ROOT, get_profile_spec
from . import export as export_mod


def _selected_plan(spec, crate: Path | None, samples_root: Path | None, export_root: Path | None):
    options = {}
    if samples_root is not None:
        options['samples_root'] = samples_root
    if export_root is not None:
        options['export_root'] = export_root
    return export_mod.build_crate_plan(spec, crate, **options) if crate else export_mod.build_plan(spec, **options)


def _print_plan(spec_name: str, *, profile: str | None, crate: Path | None,
                samples_root: Path | None = None, export_root: Path | None = None) -> int:
    spec = get_profile_spec(spec_name, profile)
    plan = _selected_plan(spec, crate, samples_root, export_root)
    print(f"\n[{spec.name}]  ->  {(plan.export_root or EXPORT_ROOT) / spec.export_dir}")
    print(f"  format: {spec.rate} Hz / {spec.bits}-bit / "
          f"{'mono' if spec.channels == 1 else 'preserve channels'}")
    if not plan.items:
        print("  (no files matched — manifest empty or patterns unresolved)")
    for item in plan.items:
        source_root = plan.samples_root or SAMPLES_ROOT
        rel = item.src.relative_to(source_root) if source_root in item.src.parents else item.src
        warn = f"  ⚠ {'; '.join(item.warnings)}" if item.warnings else ""
        status = export_mod.export_status(spec, item, export_root=plan.export_root)
        action = "" if status in {"new", "verified"} else "; requires --force"
        print(f"  {item.out_name:<40} <- {rel}{warn}  [{status}{action}]")
    for miss in plan.missing:
        print(f"  ✗ no match: {miss}")
    print(f"  total: {len(plan.items)} file(s), {len(plan.missing)} unresolved pattern(s)")
    return 0


def _run_export(spec_name: str, *, dry_run: bool, force: bool, sync: str | None,
                profile: str | None, crate: Path | None,
                samples_root: Path | None = None, export_root: Path | None = None) -> int:
    spec = get_profile_spec(spec_name, profile)
    plan = _selected_plan(spec, crate, samples_root, export_root)
    verb = "DRY-RUN" if dry_run else "EXPORT"
    print(f"[{verb}] {spec.name} -> {(plan.export_root or EXPORT_ROOT) / spec.export_dir}")
    converted, skipped = export_mod.export_device(spec, dry_run=dry_run, force=force, plan=plan)
    print(f"  {'would convert' if dry_run else 'converted'}: {converted}; reused (verified): {skipped}")

    if sync:
        if not spec.can_sync:
            print(f"  --sync not supported for {spec.name}: {spec.sync_note}")
            return 0
        if dry_run:
            if crate is None:
                print(f"  (dry-run) would sync {len(plan.items)} selected manifest file(s) to {sync}")
            else:
                print(f"  (dry-run) would sync {len(plan.items)} selected crate file(s) to {sync}")
            return 0
        dest = Path(sync)
        if not dest.is_dir():
            print(f"  --sync target not found: {dest}", file=sys.stderr)
            return 2
        try:
            copied = export_mod.sync_to_card(spec, dest, plan=plan)
        except export_mod.ExportError as exc:
            print(f"  --sync failed: {exc}", file=sys.stderr)
            return 2
        print(f"  synced {copied} file(s) to {dest}  ({spec.sync_note})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sample-export",
        description="Convert curated samples to device specs and stage them in _EXPORT/.",
    )
    parser.add_argument(
        "device", nargs="?", choices=sorted(DEVICE_SPECS),
        help="target device (omit with --all)",
    )
    parser.add_argument("--root", type=Path, help="attached sample library (defaults to $SAMPLES_ROOT)")
    parser.add_argument("--export-root", type=Path, help="staging root (with --root defaults to ROOT/_EXPORT)")
    parser.add_argument("--all", action="store_true", help="export every device")
    parser.add_argument("--list", action="store_true",
                        help="resolve the manifest and print planned files (no conversion)")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would convert without writing files")
    parser.add_argument("--force", action="store_true",
                        help="re-convert even if the output already exists")
    parser.add_argument("--sync", metavar="DEST",
                        help="copy the built device folder to a mounted card (CF/SD)")
    parser.add_argument("--profile", help="portable studio profile name")
    parser.add_argument("--crate", type=Path, help="versioned curated crate TSV")
    args = parser.parse_args(argv)

    samples_root = args.root if args.root is not None else SAMPLES_ROOT
    export_root = args.export_root if args.export_root is not None else (samples_root / "_EXPORT" if args.root is not None else EXPORT_ROOT)
    if not samples_root.is_dir():
        print(f"SAMPLES_ROOT not found: {samples_root}\n"
              f"Mount the SSD or set $SAMPLES_ROOT.", file=sys.stderr)
        return 2

    devices = sorted(DEVICE_SPECS) if args.all else ([args.device] if args.device else [])
    if not devices:
        parser.error("specify a device or --all")

    rc = 0
    for dev in devices:
        try:
            if args.list:
                rc |= _print_plan(dev, profile=args.profile, crate=args.crate, samples_root=samples_root, export_root=export_root)
            else:
                rc |= _run_export(
                    dev, dry_run=args.dry_run, force=args.force, sync=args.sync,
                    profile=args.profile, crate=args.crate,
                    samples_root=samples_root, export_root=export_root,
                )
        except (ValueError, KeyError, OSError, RuntimeError) as exc:
            print(f"{dev}: {exc}", file=sys.stderr)
            rc |= 2
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
