"""Private command-line entry for a single short-lived model process."""

from __future__ import annotations

import sys
from pathlib import Path

from .workers import run_real_worker_job


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        raise SystemExit("worker requires JOB_JSON REPORT_JSON")
    run_real_worker_job(Path(args[0]), Path(args[1]))
    return 0


if __name__ == "__main__":  # pragma: no cover - subprocess entry
    raise SystemExit(main())
