"""Exercise the inventory → approval → retrieval boundary with real files."""

import csv
import sqlite3
from pathlib import Path

import pytest

from librarytools.curate import (
    CurationError, LABEL_FIELDS, promote_favourites, undo_promotions,
)
from librarytools import curate, operations
from librarytools.find import Query, load_index, search, write_crate
from librarytools.inventory import LibraryDatabase, scan_library


def _collection(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    for name, payload in (("kick-a.wav", b"kick"), ("snare-b.wav", b"snare")):
        source = root / "CATALOGUE" / "fixtures" / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(payload)
    db = LibraryDatabase(tmp_path / "library.sqlite")
    scan_library(root, db)
    rows = [
        dict(zip(LABEL_FIELDS, (
            location.sample_id, location.path.as_posix(), role, "favourite",
            role, "short", "tone:dark", "heard",
        )))
        for location, role in zip(db.current_locations(), ("KICK", "SNARE"))
    ]
    labels = tmp_path / "labels.tsv"
    _write_labels(labels, rows)
    return root, db, labels, rows


def _write_labels(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LABEL_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


@pytest.mark.parametrize("rescan", [False, True])
def test_promoted_catalogue_samples_are_retrievable_for_export(tmp_path, rescan):
    root, db, labels, _ = _collection(tmp_path)
    promoted = promote_favourites(root, db, labels, run_id="session")
    if rescan:
        scan_library(root, db)

    results = search(load_index(db), Query(curated_only=True))

    assert len(results) == 2
    assert {root / match.path for match in results} == set(promoted)
    assert len(load_index(db)) == 2  # Exact copies must not duplicate search results.
    pytest.importorskip("sampletools")
    from sampletools.config import get_spec
    from sampletools.export import build_crate_plan

    crate = tmp_path / "kit.tsv"
    write_crate(results, crate, "approved kit")
    plan = build_crate_plan(get_spec("digitakt"), crate, root)
    assert {item.src for item in plan.items} == set(promoted)


def test_promotion_undo_removes_curated_search_results_without_rescan(tmp_path):
    root, db, labels, _ = _collection(tmp_path)
    promote_favourites(root, db, labels, run_id="session")
    scan_library(root, db)
    undo_promotions(root, db, "session")

    assert not search(load_index(db), Query(curated_only=True))
    assert {match.zone for match in load_index(db)} == {"CATALOGUE"}
    assert all(location.zone != "CURATED" for location in db.current_locations())


@pytest.mark.parametrize("problem", ["changed", "missing", "collision", "duplicate", "obstruction"])
def test_promotion_preflights_the_entire_selection_before_writing(tmp_path, problem):
    root, db, labels, rows = _collection(tmp_path)
    if problem == "changed":
        (root / rows[1]["current_path"]).write_bytes(b"changed since listening")
    elif problem == "missing":
        (root / rows[1]["current_path"]).unlink()
    elif problem == "collision":
        destination = root / "CURATED" / "SNARE" / f"snare_short_fixtures_{rows[1]['sample_id'][:8]}.wav"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"existing output")
    elif problem == "duplicate":
        _write_labels(labels, [*rows, rows[0]])
    else:
        obstruction = root / "CURATED" / "SNARE"
        obstruction.parent.mkdir(parents=True)
        obstruction.write_bytes(b"not a directory")
    before = {p: p.read_bytes() for p in (root / "CURATED").rglob("*") if p.is_file()}

    with pytest.raises((CurationError, OSError)):
        promote_favourites(root, db, labels, run_id="session")

    after = {p: p.read_bytes() for p in (root / "CURATED").rglob("*") if p.is_file()}
    assert after == before
    assert db.promotions() == []
    assert all(db.tags_for(row["sample_id"]) == [] for row in rows)
    with sqlite3.connect(db.path) as connection:
        assert connection.execute("select count(*) from reviews").fetchone()[0] == 0


@pytest.mark.parametrize("interference", ["source", "destination"])
def test_promotion_rechecks_each_copy_after_preflight(tmp_path, monkeypatch, interference):
    root, db, labels, rows = _collection(tmp_path)
    second_destination = root / "CURATED" / "SNARE" / f"snare_short_fixtures_{rows[1]['sample_id'][:8]}.wav"
    copy_file = operations.copy_exclusive

    def copy_then_change_later_file(source, destination):
        result = copy_file(source, destination)
        if source == root / rows[0]["current_path"]:
            if interference == "source":
                (root / rows[1]["current_path"]).write_bytes(b"changed during promotion")
            else:
                second_destination.parent.mkdir(parents=True)
                second_destination.write_bytes(b"another process wrote this")
        return result

    monkeypatch.setattr(operations, "copy_exclusive", copy_then_change_later_file)

    with pytest.raises(CurationError):
        promote_favourites(root, db, labels, run_id="session")

    # An incomplete operation blocks normal index opens; inspect its settled rows read-only.
    with sqlite3.connect(f"file:{db.path}?mode=ro", uri=True) as connection:
        assert connection.execute("select count(*) from promotions").fetchone()[0] == 1
    if interference == "destination":
        assert second_destination.read_bytes() == b"another process wrote this"
    else:
        assert not second_destination.exists()


@pytest.mark.parametrize(("role", "long_form"), [
    ("DRUM-LOOP", True), ("BASS-LOOP", True), ("SYNTH-LOOP", True),
    ("VOCAL-LOOP", True), ("TEXTURE-DRONE", True),
    ("HAT-OPEN", False), ("RIM", False), ("STAB-CHORD", False),
])
def test_search_crates_preserve_approved_role_and_descriptor(tmp_path, role, long_form):
    root, db, labels, rows = _collection(tmp_path)
    rows[0].update(true_role=role, descriptor="warm, loose & airy")
    _write_labels(labels, rows[:1])
    promote_favourites(root, db, labels, run_id="session")
    results = search(load_index(db), Query(curated_only=True))
    crate = tmp_path / "kit.tsv"

    write_crate(results, crate, "approved selection")

    with crate.open() as handle:
        exported = list(csv.DictReader(handle, delimiter="\t"))
    assert len(exported) == 1
    assert exported[0]["role"] == role
    assert exported[0]["descriptor"] == "warm, loose & airy"
    if long_form:
        pytest.importorskip("sampletools")
        from sampletools.config import get_spec
        from sampletools.export import ExportError, build_crate_plan

        for device in ("digitakt", "tr8s"):
            with pytest.raises(ExportError, match="one-shot"):
                build_crate_plan(get_spec(device), crate, root)


@pytest.mark.parametrize(("query_role", "canonical_role"), [
    ("KICKS", "KICK"), ("BASS", "BASS-LOOP"),
    ("SYNTH-STAB-CHORD", "SYNTH-LOOP"), ("VOCALS", "VOCAL-LOOP"),
    ("HATS-CYM", "HAT-OPEN"), ("CLAP-SNARE", "RIM"),
])
def test_broad_role_search_still_finds_promoted_favourites(tmp_path, query_role, canonical_role):
    root, db, labels, rows = _collection(tmp_path)
    rows[0]["true_role"] = canonical_role
    _write_labels(labels, rows[:1])
    promote_favourites(root, db, labels, run_id="session")

    results = search(load_index(db), Query(curated_only=True, groups={"role": (query_role,)}))

    assert len(results) == 1
    assert results[0].path.parts[:2] == ("CURATED", canonical_role)
