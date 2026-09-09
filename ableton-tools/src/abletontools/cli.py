import argparse
import os
import sys
from pathlib import Path

from .index import set_summary, to_tsv_row
from .reports import ReportRun
from .samples import classify, sample_refs

TSV_HEADER = "path\ttempo\ttrack_count\ttracks\tscene_count\tdevices\tmtime"


def _default_roots() -> list[Path]:
    env = os.environ.get("ALS_ROOTS")
    return [Path(p).expanduser() for p in (env or '').split(os.pathsep) if p.strip()]


def _roots_from_args(args: argparse.Namespace) -> list[Path]:
    if args.root:
        return [Path(args.root).expanduser()]
    return _default_roots()


def index_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="als-index")
    parser.add_argument("--root", help="single root to scan (overrides ALS_ROOTS)")
    parser.add_argument("--out", required=True, help="output directory for the TSV report")
    args = parser.parse_args(argv)

    if not _roots_from_args(args):
        parser.error('No Ableton roots selected; pass --root PATH or set ALS_ROOTS.')

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    tsv_path = out_dir / "als-index.tsv"

    rows = [TSV_HEADER]
    run = ReportRun(_roots_from_args(args), 'als-index')
    for als_path, tree_root, observation in run.sets():
        try:
            info = set_summary(tree_root, als_path)
            info.mtime = observation['mtime_ns'] / 1e9
            rows.append(to_tsv_row(info))
        except (ValueError, TypeError, OSError) as exc:
            run.report_error(observation, exc)
    try:
        run.publish(tsv_path, rows)
    except (OSError, ValueError) as exc:
        print(f'report publication failed: {exc}', file=sys.stderr)
        return 2

    print(f"Wrote {len(rows) - 1} Set(s) to {tsv_path}")
    for msg in run.data["errors"]:
        print(f"incomplete report: {msg}", file=sys.stderr)
    return 0


def samples_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="als-samples")
    parser.add_argument("--root", help="single root to scan (overrides ALS_ROOTS)")
    parser.add_argument("--out", required=True, help="output directory for the TSV report")
    args = parser.parse_args(argv)

    if not _roots_from_args(args):
        parser.error('No Ableton roots selected; pass --root PATH or set ALS_ROOTS.')

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    tsv_path = out_dir / "als-samples.tsv"

    rows = ["set_path\tsample_path\tstatus"]
    present_count = 0
    missing_count = 0
    run = ReportRun(_roots_from_args(args), 'als-samples')
    for als_path, tree_root, observation in run.sets():
        try:
            refs = sample_refs(tree_root, set_dir=als_path.parent)
            result = classify(refs)
            for ref in result["present"]:
                rows.append(f"{als_path}\t{ref.resolved}\tpresent")
                present_count += 1
            for ref in result["missing"]:
                rows.append(f"{als_path}\t{ref.resolved}\tmissing")
                missing_count += 1
        except (ValueError, TypeError, OSError) as exc:
            run.report_error(observation, exc)
    try:
        run.publish(tsv_path, rows)
    except (OSError, ValueError) as exc:
        print(f'report publication failed: {exc}', file=sys.stderr)
        return 2

    print(f"present: {present_count}, missing: {missing_count} -> {tsv_path}")
    for msg in run.data["errors"]:
        print(f"incomplete report: {msg}", file=sys.stderr)
    return 0


def main() -> int:
    return index_main()


if __name__ == "__main__":
    sys.exit(main())
