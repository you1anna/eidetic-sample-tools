"""Read-only checks must describe file evidence without repairing it."""

import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest

from librarytools import curate_cli


def _fixture(tmp_path, *, rows=True):
    root = tmp_path / "other library"
    source = root / "PACKS" / "kit" / "hit.wav"
    curated = root / "CURATED" / "PERC" / "hit.wav"
    source.parent.mkdir(parents=True)
    curated.parent.mkdir(parents=True)
    source.write_bytes(b"kick")
    curated.write_bytes(b"kick")
    sample_id = hashlib.sha256(b"kick").hexdigest()
    database = tmp_path / "index.sqlite"
    # A retained promotion table is sufficient; checking must not add the
    # current inventory schema or require a fresh scan.
    with sqlite3.connect(database) as connection:
        connection.execute(
            "create table promotions (sample_id text not null, curated_path text not null, "
            "source_path text not null, promoted_at text not null, run_id text not null, "
            "primary key(sample_id, curated_path))"
        )
        if rows:
            connection.execute(
                "insert into promotions values (?, ?, ?, ?, ?)",
                (sample_id, "CURATED/PERC/hit.wav", "PACKS/kit/hit.wav", "2026-01-01", "take-1"),
            )
    connection.close()
    return root, database, source, curated


def _check(root, database, capsys, *options):
    result = curate_cli.main([
        "--root", str(root), "--library-db", str(database), "check", "--json", *options,
    ])
    output = capsys.readouterr()
    assert output.err == ""
    return result, json.loads(output.out)


def _snapshot(root):
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*") if path.is_file()
    }


def test_check_hashes_both_copies_without_mutating_files_or_schema(tmp_path, capsys):
    root, database, _, _ = _fixture(tmp_path)
    before = _snapshot(tmp_path)

    code, report = _check(root, database, capsys)

    assert code == 0
    assert report["summary"] == {
        "checked": 1, "healthy": 1, "quarantined": 0, "discrepancies": 0,
    }
    row = report["promotions"][0]
    assert row["source"]["status"] == row["curated"]["status"] == "ok"
    assert row["source"]["sha256"] == row["sample_id"]
    assert row["curated"]["sha256"] == row["sample_id"]
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("journal_mode", ["WAL", "PERSIST", "TRUNCATE"])
def test_check_closed_database_never_creates_or_updates_sidecars(tmp_path, capsys, journal_mode):
    root, database, _, _ = _fixture(tmp_path)
    connection = sqlite3.connect(database)
    connection.execute(f"pragma journal_mode={journal_mode}")
    connection.execute("update promotions set promoted_at = '2026-01-02'")
    connection.commit()
    connection.close()
    before = _snapshot(tmp_path)

    code, report = _check(root, database, capsys)

    assert code == 0
    assert report["summary"]["healthy"] == 1
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("journal_mode", ["WAL", "DELETE"])
def test_check_rejects_pending_journal_evidence_without_ignoring_or_mutating_it(
    tmp_path, capsys, journal_mode,
):
    root, database, _, _ = _fixture(tmp_path, rows=False)
    writer = sqlite3.connect(database)
    try:
        writer.execute(f"pragma journal_mode={journal_mode}")
        writer.execute(
            "insert into promotions values (?, ?, ?, ?, ?)",
            (hashlib.sha256(b"kick").hexdigest(), "CURATED/PERC/hit.wav",
             "PACKS/kit/hit.wav", "2026-01-01", "take-1"),
        )
        if journal_mode == "WAL":
            writer.commit()  # This committed promotion exists only in the WAL.
        before = _snapshot(tmp_path)

        code, report = _check(root, database, capsys)

        assert code == 2
        assert "journal" in report["error"].lower()
        assert _snapshot(tmp_path) == before
    finally:
        writer.close()


def test_check_rejects_database_changes_during_the_record_query(tmp_path, capsys, monkeypatch):
    root, database, _, _ = _fixture(tmp_path)
    writer = sqlite3.connect(database)
    writer.execute("pragma journal_mode=WAL")
    writer.close()
    original_connect = sqlite3.connect
    changed = False

    def connect_with_concurrent_write(*args, **kwargs):
        reader = original_connect(*args, **kwargs)

        def write_during_query():
            nonlocal changed
            if not changed:
                changed = True
                writer = original_connect(database)
                writer.execute("update promotions set run_id = 'new-run'")
                writer.commit()
                writer.close()
            return 0

        reader.set_progress_handler(write_during_query, 1)
        return reader

    monkeypatch.setattr(sqlite3, "connect", connect_with_concurrent_write)
    code, report = _check(root, database, capsys)

    assert changed
    assert code == 2
    assert "changed" in report["error"].lower() or "journal" in report["error"].lower()


@pytest.mark.parametrize("which", ["source", "curated"])
@pytest.mark.parametrize("change", ["missing", "changed"])
def test_check_reports_missing_or_changed_bytes_without_restoring(tmp_path, capsys, which, change):
    root, database, source, curated = _fixture(tmp_path)
    path = source if which == "source" else curated
    if change == "missing":
        path.unlink()
    else:
        stat = path.stat()
        path.write_bytes(b"else")  # Same size and mtime: a metadata-only check is insufficient.
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    before = _snapshot(tmp_path)

    code, report = _check(root, database, capsys)

    assert code == 1
    assert report["summary"]["discrepancies"] == 1
    assert report["promotions"][0][which]["status"] == change
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("payload, expected_code", [(b"kick", 0), (b"changed", 1)])
def test_check_distinguishes_matching_quarantine_from_unexplained_absence(
    tmp_path, capsys, payload, expected_code,
):
    root, database, _, curated = _fixture(tmp_path)
    curated.unlink()
    quarantine = root / "_QUARANTINE/promotion-undo/take-1/CURATED/PERC/hit.wav"
    quarantine.parent.mkdir(parents=True)
    quarantine.write_bytes(payload)
    before = _snapshot(tmp_path)

    code, report = _check(root, database, capsys)

    assert code == expected_code
    assert report["promotions"][0]["curated"]["status"] == "missing"
    assert report["promotions"][0]["quarantine"]["status"] == ("ok" if code == 0 else "changed")
    assert report["summary"]["quarantined"] == (1 if code == 0 else 0)
    assert _snapshot(tmp_path) == before


def test_check_quarantined_copy_does_not_hide_changed_original(tmp_path, capsys):
    root, database, source, curated = _fixture(tmp_path)
    quarantine = root / "_QUARANTINE/promotion-undo/take-1/CURATED/PERC/hit.wav"
    quarantine.parent.mkdir(parents=True)
    curated.rename(quarantine)
    source.write_bytes(b"changed")

    code, report = _check(root, database, capsys)

    assert code == 1
    assert report["promotions"][0]["source"]["status"] == "changed"
    assert report["promotions"][0]["quarantine"]["status"] == "ok"


def test_check_run_filter_excludes_other_runs(tmp_path, capsys):
    root, database, _, _ = _fixture(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "insert into promotions values (?, ?, ?, ?, ?)",
            ("a" * 64, "CURATED/PERC/absent.wav", "PACKS/absent.wav", "2026-01-02", "take-2"),
        )
    connection.close()

    code, report = _check(root, database, capsys, "--run-id", "take-1")

    assert code == 0
    assert report["summary"]["checked"] == 1
    assert report["promotions"][0]["run_id"] == "take-1"


def test_check_unknown_run_is_an_input_error(tmp_path, capsys):
    root, database, _, _ = _fixture(tmp_path)
    code, report = _check(root, database, capsys, "--run-id", "unknown")
    assert code == 2
    assert "unknown" in report["error"]


def test_check_empty_history_does_not_claim_a_complete_library(tmp_path, capsys):
    root, database, _, _ = _fixture(tmp_path, rows=False)
    code = curate_cli.main(["--root", str(root), "--library-db", str(database), "check"])
    assert code == 0
    assert "no promotions recorded" in capsys.readouterr().out.lower()


def test_check_missing_database_does_not_create_it_or_its_parent(tmp_path, capsys):
    root = tmp_path / "samples"
    root.mkdir()
    database = tmp_path / "absent" / "library.sqlite"
    code, report = _check(root, database, capsys)
    assert code == 2
    assert "database" in report["error"].lower()
    assert not database.parent.exists()


@pytest.mark.parametrize("invalid", ["missing-root", "corrupt-database", "missing-table"])
def test_check_invalid_inputs_return_errors_without_mutating(tmp_path, capsys, invalid):
    root, database, _, _ = _fixture(tmp_path)
    if invalid == "missing-root":
        root = root / "absent"
    elif invalid == "corrupt-database":
        database.write_bytes(b"not sqlite")
    else:
        with sqlite3.connect(database) as connection:
            connection.execute("drop table promotions")
        connection.close()
    before = _snapshot(tmp_path)
    code, report = _check(root, database, capsys)
    assert code == 2
    assert report["error"]
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("field,value", [
    ("source_path", "../outside.wav"),
    ("curated_path", "../../outside.wav"),
    ("curated_path", "PACKS/kit/hit.wav"),
    ("sample_id", "not-a-hash"),
    ("run_id", "../../outside"),
])
def test_check_rejects_unsafe_or_invalid_records(tmp_path, capsys, field, value):
    root, database, _, _ = _fixture(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute(f"update promotions set {field} = ?", (value,))
    connection.close()
    code, report = _check(root, database, capsys)
    assert code == 2
    assert report["error"]


@pytest.mark.parametrize("which", ["source", "curated", "quarantine"])
def test_check_rejects_symlinks_outside_the_library(tmp_path, capsys, which):
    root, database, source, curated = _fixture(tmp_path)
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"kick")
    if which == "quarantine":
        curated.unlink()
        path = root / "_QUARANTINE/promotion-undo/take-1/CURATED/PERC/hit.wav"
        path.parent.mkdir(parents=True)
    else:
        path = source if which == "source" else curated
        path.unlink()
    path.symlink_to(outside)
    code, report = _check(root, database, capsys)
    assert code == 2
    assert report["error"]


def test_check_directory_in_place_of_audio_is_an_error(tmp_path, capsys):
    root, database, source, _ = _fixture(tmp_path)
    source.unlink()
    source.mkdir()
    code, report = _check(root, database, capsys)
    assert code == 2
    assert report["error"]
