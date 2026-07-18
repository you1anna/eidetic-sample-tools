import argparse
import os
import sys
from pathlib import Path

from .index import set_summary, to_tsv_row
from .read import AlsParseError, iter_sets, load_als
from .samples import classify, sample_refs

TSV_HEADER = "path\ttempo\ttrack_count\ttracks\tscene_count\tdevices\tmtime"


def _default_roots() -> list[Path]:
    env = os.environ.get("ALS_ROOTS")
    if env:
        return [Path(p) for p in env.split(":") if p]
    return [
        Path("/Users/macbookair/Music/Ableton"),
        Path("/Volumes/Extreme SSD/Production"),
    ]


def _roots_from_args(args: argparse.Namespace) -> list[Path]:
    if args.root:
        return [Path(args.root)]
    return _default_roots()


def index_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="als-index")
    parser.add_argument("--root", help="single root to scan (overrides ALS_ROOTS)")
    parser.add_argument("--out", required=True, help="output directory for the TSV report")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    tsv_path = out_dir / "als-index.tsv"

    rows = [TSV_HEADER]
    skipped = []
    for root in _roots_from_args(args):
        if not root.exists():
            continue
        for als_path in iter_sets(root):
            try:
                tree_root = load_als(als_path)
            except AlsParseError as exc:
                skipped.append(str(exc))
                continue
            info = set_summary(tree_root, als_path)
            rows.append(to_tsv_row(info))

    tsv_path.write_text("\n".join(rows) + "\n")
    print(f"Wrote {len(rows) - 1} Set(s) to {tsv_path}")
    for msg in skipped:
        print(f"skipped (parse error): {msg}", file=sys.stderr)
    return 0


def samples_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="als-samples")
    parser.add_argument("--root", help="single root to scan (overrides ALS_ROOTS)")
    parser.add_argument("--out", required=True, help="output directory for the TSV report")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    tsv_path = out_dir / "als-samples.tsv"

    rows = ["set_path\tsample_path\tstatus"]
    present_count = 0
    missing_count = 0
    skipped = []
    for root in _roots_from_args(args):
        if not root.exists():
            continue
        for als_path in iter_sets(root):
            try:
                tree_root = load_als(als_path)
            except AlsParseError as exc:
                skipped.append(str(exc))
                continue
            refs = sample_refs(tree_root, set_dir=als_path.parent)
            result = classify(refs)
            for ref in result["present"]:
                rows.append(f"{als_path}\t{ref.resolved}\tpresent")
                present_count += 1
            for ref in result["missing"]:
                rows.append(f"{als_path}\t{ref.resolved}\tmissing")
                missing_count += 1

    tsv_path.write_text("\n".join(rows) + "\n")
    print(f"present: {present_count}, missing: {missing_count} -> {tsv_path}")
    for msg in skipped:
        print(f"skipped (parse error): {msg}", file=sys.stderr)
    return 0


def main() -> int:
    return index_main()


if __name__ == "__main__":
    sys.exit(main())
