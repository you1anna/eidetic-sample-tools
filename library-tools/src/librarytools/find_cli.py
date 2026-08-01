"""`sample-find` — find samples by style, type and origin, then load hardware from them.

Read-only.  Writes only playlists and crate manifests; it has no apply path and cannot move,
rename or convert audio.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config, find as find_mod
from .inventory import LibraryDatabase


def _print_table(matches: list[find_mod.Match], show_paths: bool) -> None:
    if not matches:
        return
    style_width = max((len(" ".join(match.tags[:3])) for match in matches), default=0)
    style_width = min(max(style_width, 10), 28)
    origin_width = min(max((len(match.origin) for match in matches), default=0), 34)

    header = f"{'ROLE':<16}  {'STYLE/CHAR':<{style_width}}  {'ORIGIN':<{origin_width}}  NAME"
    print(header)
    for match in matches:
        tags = " ".join(match.tags[:3])[:style_width]
        origin = match.origin[:origin_width]
        name = match.path.as_posix() if show_paths else match.name
        near = f"  ~{match.distance:.3f}" if match.distance is not None else ""
        print(f"{match.role:<16}  {tags:<{style_width}}  {origin:<{origin_width}}  {name}{near}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="sample-find",
        description="Search the sample index by tag and by sound. Never changes audio.",
    )
    ap.add_argument("terms", nargs="*", help="tags, origins or name fragments to match")
    ap.add_argument("--root", type=Path, default=config.SAMPLES_ROOT, help="library root")
    ap.add_argument(
        "--library-db",
        type=Path,
        default=config.MANIFEST_DIR / "sample-library.sqlite",
        help="library index to search",
    )
    ap.add_argument("--role", action="append", default=[], help="restrict to a review role")
    ap.add_argument("--style", action="append", default=[], help="restrict to a style tag")
    ap.add_argument("--gear", action="append", default=[], help="restrict to a gear tag")
    ap.add_argument(
        "--character", action="append", default=[], help="restrict to a character tag",
    )
    ap.add_argument("--origin", action="append", default=[], help="restrict to an origin")
    ap.add_argument("--any", dest="any_", action="store_true", help="match any term, not all")
    ap.add_argument(
        "--curated-only", action="store_true",
        help="restrict to samples already promoted into CURATED/ (required for a crate sample-export will accept)",
    )
    ap.add_argument("--like", help="rank by similarity to this sample (path fragment or id)")
    ap.add_argument("--preferred", action="store_true", help="put previously kept samples first")
    ap.add_argument(
        "--no-spread",
        dest="spread",
        action="store_false",
        help="list alphabetically instead of spreading across sound families",
    )
    ap.add_argument("--limit", type=int, default=30, help="maximum results (0 for no limit)")
    ap.add_argument("--paths", action="store_true", help="print full relative paths")
    ap.add_argument("--m3u8", type=Path, help="write an audition playlist here")
    ap.add_argument("--crate", type=Path, help="write a crate TSV for sample-export")
    ap.add_argument("--kit-id", help="record these results as picks under this kit id")
    args = ap.parse_args(argv)

    if not args.library_db.is_file():
        print(
            f"no index at {args.library_db}; run sample-tag --rescan --apply first",
            file=sys.stderr,
        )
        return 2

    database = LibraryDatabase(args.library_db)
    everything = find_mod.load_index(database)
    if not everything:
        print("index is empty; run sample-tag --rescan --apply first", file=sys.stderr)
        return 2

    groups: dict[str, tuple[str, ...]] = {}
    for name, values in (
        ("role", args.role), ("style", args.style), ("gear", args.gear),
        ("character", args.character), ("origin", args.origin),
    ):
        if values:
            groups[name] = tuple(value.lower() for value in values)

    query = find_mod.Query(
        terms=tuple(term.lower() for term in args.terms),
        groups=groups,
        any_=args.any_,
        curated_only=args.curated_only,
    )
    results = find_mod.search(everything, query)

    if args.like:
        try:
            target = find_mod.resolve_target(everything, args.like)
            results = find_mod.rank_by_similarity(database, target, results)
        except KeyError as exc:
            print(f"--like: {exc}", file=sys.stderr)
            return 2
    elif args.preferred:
        results = sorted(results, key=lambda m: (-m.picks, m.path.as_posix()))
    elif args.spread:
        results = find_mod.spread(results)
    else:
        results = sorted(results, key=lambda m: m.path.as_posix())

    found = len(results)
    if args.limit > 0:
        results = results[: args.limit]

    _print_table(results, args.paths)
    print(f"\n{len(results)} shown of {found} matching '{query.describe()}'")

    if args.m3u8:
        find_mod.write_m3u8(args.root, results, args.m3u8)
        print(f"  playlist: {args.m3u8}")
    if args.crate:
        find_mod.write_crate(results, args.crate, query.describe())
        print(f"  crate: {args.crate}")
        uncurated = sum(1 for match in results if match.zone != "CURATED")
        if uncurated:
            print(
                f"  ⚠ {uncurated} of {len(results)} row(s) are not under CURATED/ yet; "
                "sample-export rejects them until sample-curate promotes them"
            )
        print(f"  next:  sample-export octatrack --crate {args.crate} --list")
    if args.kit_id:
        for match in results:
            database.record_pick(match.sample_id, args.kit_id, query.describe())
        print(f"  recorded {len(results)} picks under kit '{args.kit_id}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
