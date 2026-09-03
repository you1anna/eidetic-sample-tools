"""Inspect recorded promotions without creating database or audio state."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path


class HealthCheckError(ValueError):
    """Invalid inputs, unsafe records or data that cannot be read."""


@dataclass(frozen=True)
class FileCheck:
    path: str
    status: str
    sha256: str | None = None


@dataclass(frozen=True)
class PromotionCheck:
    sample_id: str
    run_id: str
    source: FileCheck
    curated: FileCheck
    quarantine: FileCheck | None
    status: str


@dataclass(frozen=True)
class HealthReport:
    root: str
    run_id: str | None
    promotions: list[PromotionCheck]

    @property
    def summary(self) -> dict[str, int]:
        return {
            "checked": len(self.promotions),
            "healthy": sum(row.status == "healthy" for row in self.promotions),
            "quarantined": sum(row.status == "quarantined" for row in self.promotions),
            "discrepancies": sum(row.status == "discrepancy" for row in self.promotions),
        }

    @property
    def exit_code(self) -> int:
        return 1 if self.summary["discrepancies"] else 0

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "summary": self.summary}

    def text(self) -> str:
        if not self.promotions:
            return "No promotions recorded; this check does not assess the rest of the library."
        lines = [f"Recorded promotion check: {self.root}"]
        for row in self.promotions:
            lines.append(f"{row.run_id or '(unnamed run)'} / {row.sample_id}: {row.status}")
            for label, result in (
                ("source", row.source), ("curated", row.curated), ("quarantine", row.quarantine),
            ):
                if result is not None:
                    lines.append(f"  {label}: {result.status} — {result.path}")
        lines.append("; ".join(f"{name}: {count}" for name, count in self.summary.items()))
        return "\n".join(lines)


def _relative_path(value: object, field: str, *, allow_empty: bool = False) -> Path:
    if not isinstance(value, str) or "\x00" in value or (not value and not allow_empty):
        raise HealthCheckError(f"invalid {field} in promotion record")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or (not path.parts and not allow_empty):
        raise HealthCheckError(f"invalid {field} in promotion record: {value!r}")
    return path


def _bounded_path(root: Path, relative: Path) -> Path:
    path = root / relative
    if not path.resolve().is_relative_to(root):
        raise HealthCheckError(f"promotion path escapes the library: {relative}")
    return path


def _inspect(root: Path, relative: Path, sample_id: str) -> FileCheck:
    path = _bounded_path(root, relative)
    try:
        path.stat()
    except FileNotFoundError:
        return FileCheck(relative.as_posix(), "missing")
    if not path.is_file():
        raise HealthCheckError(f"expected an audio file: {relative}")
    with path.open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    return FileCheck(relative.as_posix(), "ok" if actual == sample_id else "changed", actual)


def _database_state(database: Path) -> tuple[tuple[int, ...] | None, ...]:
    """Reject pending journals and record changes without opening SQLite state."""
    state = []
    for suffix in ("", "-wal", "-journal"):
        path = database.with_name(database.name + suffix)
        try:
            stat = path.stat()
        except FileNotFoundError:
            if not suffix:
                raise
            state.append(None)
            continue
        state.append((stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
        if suffix and stat.st_size:
            # SQLite PERSIST commits zero the 28-byte rollback-journal header.
            # Such retained journals are cold; nonempty WALs may hold newer rows.
            if suffix == "-journal":
                with path.open("rb") as journal:
                    if journal.read(28) == b"\x00" * 28:
                        continue
            raise HealthCheckError(
                f"library database has journal evidence that cannot be checked without "
                f"recovery or checkpointing: {path}; finish other database work before retrying"
            )
    return tuple(state)


def check_promotions(root: Path, database: Path, run_id: str | None = None) -> HealthReport:
    """Check historical records against bytes on disk; never bootstrap an inventory."""
    try:
        root = root.resolve()
        if not root.is_dir():
            raise HealthCheckError(f"library root is not a directory: {root}")
        if not database.is_file():
            raise HealthCheckError(f"library database not found: {database}")
        database = database.resolve()
        # LibraryDatabase.__init__ creates directories and updates the schema.
        # mode=ro alone can create WAL/SHM sidecars. immutable avoids those writes,
        # but ignores journals, so reject pending evidence and detect observed
        # changes around the query. This is not an atomic concurrent snapshot.
        before = _database_state(database)
        with closing(sqlite3.connect(
            database.as_uri() + "?mode=ro&immutable=1", uri=True,
        )) as connection:
            connection.row_factory = sqlite3.Row
            query = "select sample_id, run_id, source_path, curated_path from promotions"
            parameters: tuple[str, ...] = ()
            if run_id is not None:
                query += " where run_id = ?"
                parameters = (run_id,)
            records = connection.execute(query + " order by run_id, curated_path", parameters).fetchall()
        if _database_state(database) != before:
            raise HealthCheckError("library database changed during the check; retry when it is idle")
        if run_id is not None and not records:
            raise HealthCheckError(f"no promotions recorded for run: {run_id}")

        # Validate every path before opening any recorded audio, including the
        # existing undo location. Presence there is evidence, not an inferred cause.
        paths = []
        for record in records:
            sample_id = record["sample_id"]
            if not isinstance(sample_id, str) or not re.fullmatch(r"[0-9a-f]{64}", sample_id):
                raise HealthCheckError("invalid sample_id in promotion record")
            source = _relative_path(record["source_path"], "source_path")
            curated = _relative_path(record["curated_path"], "curated_path")
            if curated.parts[0] != "CURATED" or len(curated.parts) < 2:
                raise HealthCheckError(f"curated_path is not below CURATED/: {curated}")
            run = _relative_path(record["run_id"], "run_id", allow_empty=True)
            quarantine = Path("_QUARANTINE/promotion-undo") / run / curated
            for relative in (source, curated, quarantine):
                _bounded_path(root, relative)
            paths.append((record, source, curated, quarantine))

        results = []
        for record, source, curated, quarantine in paths:
            sample_id = record["sample_id"]
            original_check = _inspect(root, source, sample_id)
            curated_check = _inspect(root, curated, sample_id)
            quarantine_check = (
                _inspect(root, quarantine, sample_id) if curated_check.status == "missing" else None
            )
            status = "discrepancy"
            if original_check.status == "ok":
                if curated_check.status == "ok":
                    status = "healthy"
                elif quarantine_check is not None and quarantine_check.status == "ok":
                    status = "quarantined"
            results.append(PromotionCheck(
                sample_id, record["run_id"], original_check, curated_check, quarantine_check, status,
            ))
        return HealthReport(str(root), run_id, results)
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        raise HealthCheckError(f"cannot read promotion evidence: {exc}") from exc
