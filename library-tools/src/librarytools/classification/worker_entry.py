"""Private command-line entry for a single short-lived model process."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .workers import run_real_worker_job


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private embedding worker")
    parser.add_argument("job", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--library-lock-fd", type=int)
    args = parser.parse_args(argv)
    if args.library_lock_fd is None:
        run_real_worker_job(args.job, args.report)
    else:
        from ..inventory import LibraryDatabase
        from ..locking import adopt_inherited_library_lock
        raw = json.loads(args.job.read_text(encoding="utf-8"))
        root = Path(raw["library_root"])
        # The descriptor is only useful for the exact identified, compatible library.
        database = LibraryDatabase(Path(raw["cache_path"]), readonly=True)
        database.bind_root(root, create=False)
        with adopt_inherited_library_lock(root, args.library_lock_fd):
            run_real_worker_job(args.job, args.report)
    return 0


if __name__ == "__main__":  # pragma: no cover - subprocess entry
    raise SystemExit(main())
