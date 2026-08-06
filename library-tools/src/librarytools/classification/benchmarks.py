"""Ear-benchmark schemas, scoring, selection and derived audition files."""

from __future__ import annotations

import csv
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .domain import (
    AUDITION_GROUPS,
    CONTENTS,
    FORMS,
    Classification,
    ClassificationError,
)


BENCHMARK_FIELDS = (
    "sample_id", "current_path", "stratum", "predicted_form", "predicted_content",
    "predicted_audition_group", "true_form", "true_content",
    "true_audition_group", "notes",
)
BENCHMARK_STRATA = (
    "form-boundary", "loop-content", "drum-one-shot", "vocal-form",
    "out-of-brief", "control",
)
MIN_FORM_CORRECT = 22
# A 24-row benchmark cannot represent exactly 80%; 19/24 is the nearest
# practical boundary to the operator-approved approximately 20% group error.
MIN_CONTENT_GROUP_CORRECT = 19


@dataclass(frozen=True)
class BenchmarkScore:
    form_correct: int
    content_correct: int
    group_correct: int
    content_group_correct: int
    total: int
    ready: bool
    passed: bool


def score_benchmark(rows: Sequence[Mapping[str, str]]) -> BenchmarkScore:
    ready_rows = [
        row for row in rows
        if row.get("true_form") and row.get("true_content") and row.get("true_audition_group")
    ]
    expected_strata = Counter({stratum: 4 for stratum in BENCHMARK_STRATA})
    structurally_valid = (
        len(rows) == 24
        and len({row.get("sample_id", "") for row in rows}) == 24
        and all(row.get("sample_id") and row.get("current_path") for row in rows)
        and Counter(row.get("stratum", "") for row in rows) == expected_strata
    )
    truths_valid = all(
        row.get("true_form") in FORMS
        and row.get("true_content") in CONTENTS
        and row.get("true_audition_group") in AUDITION_GROUPS
        for row in ready_rows
    )
    ready = structurally_valid and len(ready_rows) == 24 and truths_valid
    form_correct = sum(row.get("form") == row.get("true_form") for row in ready_rows)
    content_correct = sum(row.get("content") == row.get("true_content") for row in ready_rows)
    group_correct = sum(
        row.get("audition_group") == row.get("true_audition_group") for row in ready_rows
    )
    content_group_correct = sum(
        row.get("content") == row.get("true_content")
        and row.get("audition_group") == row.get("true_audition_group")
        for row in ready_rows
    )
    return BenchmarkScore(
        form_correct=form_correct,
        content_correct=content_correct,
        group_correct=group_correct,
        content_group_correct=content_group_correct,
        total=len(ready_rows),
        ready=ready,
        passed=(
            ready
            and form_correct >= MIN_FORM_CORRECT
            and content_group_correct >= MIN_CONTENT_GROUP_CORRECT
        ),
    )


def select_benchmark_rows(rows: Sequence[Mapping[str, str]]) -> list[Mapping[str, str]]:
    selected: list[Mapping[str, str]] = []
    used: set[str] = set()
    for stratum in BENCHMARK_STRATA:
        candidates = sorted(
            (row for row in rows if row.get("stratum") == stratum),
            key=lambda row: str(row.get("sample_id", "")),
        )
        for row in candidates:
            sample_id = str(row.get("sample_id", ""))
            if sample_id not in used:
                selected.append(row)
                used.add(sample_id)
            if sum(item.get("stratum") == stratum for item in selected) == 4:
                break
    if len(selected) != 24:
        raise ClassificationError("benchmark requires four unique candidates in each of six strata")
    return selected


def benchmark_strata(rows: Sequence[Classification]) -> dict[str, str]:
    """Assign four unique candidates to each benchmark stratum deterministically."""
    remaining = {row.sample_id: row for row in rows}
    assigned: dict[str, str] = {}

    def take(stratum: str, key) -> None:
        candidates = sorted(remaining.values(), key=key)
        for row in candidates[:4]:
            assigned[row.sample_id] = stratum
            remaining.pop(row.sample_id)

    take(
        "out-of-brief",
        lambda row: (row.content != "OUT_OF_BRIEF", -row.content_confidence, row.sample_id),
    )
    take(
        "vocal-form",
        lambda row: (row.content != "VOCAL", row.form_confidence, row.sample_id),
    )
    take(
        "loop-content",
        lambda row: (
            row.form != "LOOP",
            row.content not in {"PERCUSSION", "FULL_DRUMS"},
            row.content_confidence,
            row.sample_id,
        ),
    )
    take(
        "drum-one-shot",
        lambda row: (
            row.form != "ONE_SHOT",
            row.content not in {"RIM", "TOM", "PERCUSSION"},
            row.content_confidence,
            row.sample_id,
        ),
    )
    take("form-boundary", lambda row: (row.form_confidence, row.content_confidence, row.sample_id))
    take("control", lambda row: (-min(row.form_confidence, row.content_confidence), row.sample_id))
    if len(assigned) != 24:
        raise ClassificationError("benchmark requires at least 24 classified samples")
    return assigned


def write_benchmark_sheet(
    path: Path,
    rows: Sequence[Classification],
    strata: Mapping[str, str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=BENCHMARK_FIELDS, delimiter="\t")
        writer.writeheader()
        for row in rows:
            if row.sample_id not in strata:
                continue
            writer.writerow({
                "sample_id": row.sample_id,
                "current_path": row.current_path.as_posix(),
                "stratum": strata[row.sample_id],
                "predicted_form": row.form,
                "predicted_content": row.content,
                "predicted_audition_group": row.audition_group,
                "true_form": "",
                "true_content": "",
                "true_audition_group": "",
                "notes": "",
            })
    temporary.replace(path)


def refresh_benchmark_predictions(
    path: Path,
    classifications: Mapping[str, Classification],
) -> list[dict[str, str]]:
    """Refresh machine columns while preserving all human-entered benchmark fields."""
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if tuple(reader.fieldnames or ()) != BENCHMARK_FIELDS:
            raise ClassificationError("benchmark-labels.tsv has an unexpected schema")
        raw_rows = list(reader)

    saved_rows: list[dict[str, str]] = []
    merged: list[dict[str, str]] = []
    for raw in raw_rows:
        predicted = classifications.get(raw["sample_id"])
        if predicted is None:
            raise ClassificationError(f"benchmark sample is not classified: {raw['sample_id']}")
        if Path(raw["current_path"]) != predicted.current_path:
            raise ClassificationError(f"benchmark sample path is stale: {raw['sample_id']}")
        refreshed = {
            **raw,
            "predicted_form": predicted.form,
            "predicted_content": predicted.content,
            "predicted_audition_group": predicted.audition_group,
        }
        saved_rows.append(refreshed)
        merged.append({
            **refreshed,
            "form": predicted.form,
            "content": predicted.content,
            "audition_group": predicted.audition_group,
        })

    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=BENCHMARK_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(saved_rows)
    temporary.replace(path)
    return merged


def read_benchmark_with_predictions(
    path: Path,
    classifications: Mapping[str, Classification],
) -> list[dict[str, str]]:
    """Read benchmark truth and merge current predictions without changing the sheet."""
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if tuple(reader.fieldnames or ()) != BENCHMARK_FIELDS:
            raise ClassificationError("benchmark-labels.tsv has an unexpected schema")
        merged: list[dict[str, str]] = []
        for raw in reader:
            predicted = classifications.get(raw["sample_id"])
            if predicted is None:
                raise ClassificationError(f"benchmark sample is not classified: {raw['sample_id']}")
            merged.append({
                **raw,
                "form": predicted.form,
                "content": predicted.content,
                "audition_group": predicted.audition_group,
            })
    return merged


def read_benchmark_truth(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if tuple(reader.fieldnames or ()) != BENCHMARK_FIELDS:
            raise ClassificationError("benchmark-labels.tsv has an unexpected schema")
        return {
            row["sample_id"]: {
                "true_form": row["true_form"],
                "true_content": row["true_content"],
                "true_audition_group": row["true_audition_group"],
            }
            for row in reader
            if row["true_form"] and row["true_content"] and row["true_audition_group"]
        }


def write_benchmark_audition(root: Path, benchmark_path: Path) -> None:
    with benchmark_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    playlist_path = benchmark_path.parent / "benchmark.m3u8"
    lines = ["#EXTM3U", *(str((root / row["current_path"]).resolve()) for row in rows)]
    playlist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    playlists_dir = benchmark_path.parent / "benchmark-playlists"
    if playlists_dir.exists():
        shutil.rmtree(playlists_dir)
    playlists_dir.mkdir()
    index_lines = [
        "# Classifier benchmark playlists",
        "",
        "Each playlist contains four samples. Enter the heard truth in `../benchmark-labels.tsv`.",
        "",
        "| Stratum | Files | Playlist |",
        "|---|---:|---|",
    ]
    for stratum in BENCHMARK_STRATA:
        stratum_rows = [row for row in rows if row["stratum"] == stratum]
        stratum_lines = [
            "#EXTM3U",
            *(str((root / row["current_path"]).resolve()) for row in stratum_rows),
        ]
        filename = f"{stratum}.m3u8"
        (playlists_dir / filename).write_text(
            "\n".join(stratum_lines) + "\n", encoding="utf-8",
        )
        index_lines.append(f"| `{stratum}` | {len(stratum_rows)} | [{filename}]({filename}) |")
    (playlists_dir / "README.md").write_text(
        "\n".join(index_lines) + "\n", encoding="utf-8",
    )
    readme = benchmark_path.parent / "benchmark-README.md"
    readme.write_text(
        "# Classifier ear benchmark\n\n"
        "Listen to `benchmark.m3u8`, then fill `true_form`, `true_content`, "
        "`true_audition_group` and optional `notes` in `benchmark-labels.tsv`.\n\n"
        "Allowed form values: `ONE_SHOT`, `LOOP`, `PHRASE`, `LONG_FORM`.\n\n"
        "Allowed content values: `RIM`, `TOM`, `PERCUSSION`, `FULL_DRUMS`, `VOCAL`, "
        "`OUT_OF_BRIEF`.\n",
        encoding="utf-8",
    )
