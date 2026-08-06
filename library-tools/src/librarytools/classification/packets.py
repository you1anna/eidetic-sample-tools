"""Versioned packet schemas and atomic derived-file persistence."""

from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from .domain import (
    AUDITION_GROUPS,
    CONTENTS,
    FORMS,
    Classification,
    ClassificationError,
)


CLASSIFICATION_FIELDS = (
    "sample_id", "current_path", "form", "content", "audition_group",
    "form_confidence", "content_confidence", "evidence", "classifier_version",
)


def write_classifications(path: Path, rows: Sequence[Classification]) -> None:
    """Atomically write the stable classification TSV snapshot."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CLASSIFICATION_FIELDS, delimiter="\t")
        writer.writeheader()
        for row in rows:
            data = asdict(row)
            data["current_path"] = row.current_path.as_posix()
            data["form_confidence"] = f"{row.form_confidence:.6f}"
            data["content_confidence"] = f"{row.content_confidence:.6f}"
            writer.writerow(data)
    temporary.replace(path)


def read_classifications(path: Path) -> list[Classification]:
    if not path.is_file():
        raise ClassificationError(
            f"classification.tsv is missing beside {path.parent / 'labels.tsv'}"
        )
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if tuple(reader.fieldnames or ()) != CLASSIFICATION_FIELDS:
            raise ClassificationError("classification.tsv has an unexpected schema")
        rows: list[Classification] = []
        seen: set[str] = set()
        for index, raw in enumerate(reader, start=2):
            sample_id = raw["sample_id"]
            if sample_id in seen:
                raise ClassificationError(f"classification.tsv row {index}: duplicate sample_id")
            if raw["form"] not in FORMS or raw["content"] not in CONTENTS:
                raise ClassificationError(
                    f"classification.tsv row {index}: invalid form/content"
                )
            if raw["audition_group"] not in AUDITION_GROUPS:
                raise ClassificationError(
                    f"classification.tsv row {index}: invalid audition_group"
                )
            seen.add(sample_id)
            rows.append(Classification(
                sample_id=sample_id,
                current_path=Path(raw["current_path"]),
                form=raw["form"],
                content=raw["content"],
                audition_group=raw["audition_group"],
                form_confidence=float(raw["form_confidence"]),
                content_confidence=float(raw["content_confidence"]),
                evidence=raw["evidence"],
                classifier_version=raw["classifier_version"],
            ))
    return rows
