"""Command-line entry point for sample-export."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import DEVICE_SPECS, EXPORT_ROOT, SAMPLES_ROOT, get_profile_spec
from . import export as export_mod


def _print_plan(spec_name: str, *, profile: str | None, crate: Path | None) -> int:
    spec = get_profile_spec(spec_name, profile)
    plan = export_mod.build_crate_plan(spec, crate) if crate else export_mod.build_plan(spec)
    print(f"\n[{spec.name}]  ->  {EXPORT_ROOT / spec.export_dir}")
    print(f"  format: {spec.rate} Hz / {spec.bits}-bit / "
          f"{'mono' if spec.channels == 1 else 'preserve channels'}")
    if not plan.items:
        print("  (no files matched — manifest empty or patterns unresolved)")
    for item in plan.items:
        rel = item.src.relative_to(SAMPLES_ROOT) if SAMPLES_ROOT in item.src.parents else item.src
        warn = f"  ⚠ {'; '.join(item.warnings)}" if item.warnings else ""
        print(f"  {item.out_name:<40} <- {rel}{warn}")
    for miss in plan.missing:
        print(f"  ✗ no match: {miss}")
    print(f"  total: {len(plan.items)} file(s), {len(plan.missing)} unresolved pattern(s)")
    return 0


def _run_export(spec_name: str, *, dry_run: bool, force: bool, sync: str | None,
                profile: str | None, crate: Path | None) -> int:
    spec = get_profile_spec(spec_name, profile)
    plan = export_mod.build_crate_plan(spec, crate) if crate else None
    verb = "DRY-RUN" if dry_run else "EXPORT"
    print(f"[{verb}] {spec.name} -> {EXPORT_ROOT / spec.export_dir}")
    converted, skipped = export_mod.export_device(spec, dry_run=dry_run, force=force, plan=plan)
    print(f"  {'would convert' if dry_run else 'converted'}: {converted}; skipped (exists): {skipped}")

    if sync:
        if not spec.can_sync:
            print(f"  --sync not supported for {spec.name}: {spec.sync_note}")
            return 0
        if dry_run:
            print(f"  (dry-run) would sync to {sync}")
            return 0
        dest = Path(sync)
        if not dest.is_dir():
            print(f"  --sync target not found: {dest}", file=sys.stderr)
            return 2
        copied = export_mod.sync_to_card(spec, dest)
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

    if not SAMPLES_ROOT.exists():
        print(f"SAMPLES_ROOT not found: {SAMPLES_ROOT}\n"
              f"Mount the SSD or set $SAMPLES_ROOT.", file=sys.stderr)
        return 2

    devices = sorted(DEVICE_SPECS) if args.all else ([args.device] if args.device else [])
    if not devices:
        parser.error("specify a device or --all")

    rc = 0
    for dev in devices:
        if args.list:
            rc |= _print_plan(dev, profile=args.profile, crate=args.crate)
        else:
            rc |= _run_export(
                dev, dry_run=args.dry_run, force=args.force, sync=args.sync,
                profile=args.profile, crate=args.crate,
            )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
