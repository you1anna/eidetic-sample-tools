"""Safe, human-gated cleanup planning from a saved drum-role audit."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path


SOURCE_ROLE_ORDER = ("KICKS", "CLAP-SNARE", "HATS-CYM", "PERC")
VALID_DESTINATIONS = frozenset(
    {"KICKS", "CLAP-SNARE", "HATS-CYM", "PERC", "BASS", "REVIEW"}
)
AUDIT_FIELDS = frozenset(
    {
        "path",
        "current_role",
        "authoritative",
        "top_class",
        "top_prob",
        "kick_prob",
        "suggested_role",
        "agree",
        "band",
        "note",
    }
)


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    path: Path
    current_role: str
    suggested_role: str
    top_class: str
    top_prob: float

    @property
    def route(self) -> tuple[str, str]:
        return self.current_role, self.suggested_role

    @property
    def source_group(self) -> str:
        parts = self.path.parts
        return parts[2] if len(parts) > 3 else "_root"


def _candidate_id(path: str, current_role: str, suggested_role: str) -> str:
    value = f"{path}\0{current_role}\0{suggested_role}".encode()
    return hashlib.sha256(value).hexdigest()[:12]


def read_trust_mismatches(path: Path) -> list[Candidate]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        missing = AUDIT_FIELDS - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"audit missing columns: {', '.join(sorted(missing))}")
        rows = list(reader)

    candidates: list[Candidate] = []
    for row in rows:
        if not (
            row["authoritative"] == "yes"
            and row["agree"] == "no"
            and row["band"] == "trust"
        ):
            continue
        current = row["current_role"]
        suggested = row["suggested_role"]
        rel = Path(row["path"])
        if (
            rel.parts[:2] != ("CURATED", current)
            or rel.is_absolute()
            or ".." in rel.parts
        ):
            raise ValueError(f"candidate outside current CURATED role: {rel}")
        if current not in SOURCE_ROLE_ORDER:
            raise ValueError(f"unsupported source role: {current}")
        if suggested not in VALID_DESTINATIONS:
            raise ValueError(f"unsupported suggested role: {suggested}")
        candidates.append(
            Candidate(
                candidate_id=_candidate_id(row["path"], current, suggested),
                path=rel,
                current_role=current,
                suggested_role=suggested,
                top_class=row["top_class"],
                top_prob=float(row["top_prob"]),
            )
        )
    return sorted(
        candidates,
        key=lambda item: (
            SOURCE_ROLE_ORDER.index(item.current_role),
            item.suggested_role,
            item.path.as_posix(),
        ),
    )


def group_routes(
    candidates: list[Candidate],
) -> dict[tuple[str, str], list[Candidate]]:
    grouped: dict[tuple[str, str], list[Candidate]] = {}
    for item in candidates:
        grouped.setdefault(item.route, []).append(item)
    return dict(
        sorted(
            grouped.items(),
            key=lambda item: (
                SOURCE_ROLE_ORDER.index(item[0][0]),
                item[0][1],
            ),
        )
    )


def select_calibration(
    candidates: list[Candidate],
    size: int = 10,
) -> list[Candidate]:
    if size < 1:
        raise ValueError("calibration size must be positive")
    ordered = sorted(candidates, key=lambda item: item.path.as_posix())
    if len(ordered) <= size:
        return ordered

    selected = [
        min(ordered, key=lambda item: (item.top_prob, item.path.as_posix()))
    ]
    remaining = [item for item in ordered if item != selected[0]]
    while len(selected) < size:
        groups = {item.source_group for item in selected}

        def rank(item: Candidate) -> tuple[int, float, str]:
            confidence_distance = min(
                abs(item.top_prob - chosen.top_prob) for chosen in selected
            )
            return (
                -int(item.source_group not in groups),
                -confidence_distance,
                item.path.as_posix(),
            )

        chosen = min(remaining, key=rank)
        selected.append(chosen)
        remaining.remove(chosen)
    return sorted(selected, key=lambda item: item.path.as_posix())
