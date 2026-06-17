"""Filesystem mutations: move-only, never overwrite, always reversible."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Move:
    src: Path
    dest: Path
    tag: str  # bucket name (classify) or reason (dedupe)


def safe_move(src: Path, dest: Path) -> str:
    """Move src -> dest. Returns 'missing', 'exists', or 'moved'. Never overwrites."""
    if not src.exists():
        return "missing"
    if dest.exists():
        return "exists"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    return "moved"


def write_plan(path: Path, plan: list[Move]) -> None:
    """Write the planned moves as a TSV: src<TAB>dest<TAB>tag."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for m in plan:
            fh.write(f"{m.src}\t{m.dest}\t{m.tag}\n")


def apply_plan(plan: list[Move], undo_path: Path) -> dict[str, int]:
    """Execute moves; record reversible undo lines (dest<TAB>src) for moved files."""
    counts = {"moved": 0, "exists": 0, "missing": 0}
    undo_path.parent.mkdir(parents=True, exist_ok=True)
    with undo_path.open("w", encoding="utf-8") as undo:
        for m in plan:
            status = safe_move(m.src, m.dest)
            counts[status] += 1
            if status == "moved":
                undo.write(f"{m.dest}\t{m.src}\n")
    return counts
