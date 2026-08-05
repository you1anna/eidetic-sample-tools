import csv
import gzip
from pathlib import Path

import pytest

from librarytools import curate, curate_cli
from librarytools.curate import (
    CurationError,
    apply_migration,
    plan_catalogue_migration,
    prepare_packet,
    promote_favourites,
    read_labels,
    undo_promotions,
    validate_labels,
    write_consumer_views,
)
from librarytools.inventory import LibraryDatabase, scan_library


def _audio(path: Path, payload: bytes = b"audio") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _als(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb") as fh:
        fh.write(text.encode())


def test_migration_aborts_when_ableton_set_references_curated(tmp_path):
    root = tmp_path / "SAMPLES"
    _audio(root / "CURATED" / "KICKS" / "a.wav")
    ableton = tmp_path / "ABLETON_PROJECTS"
    _als(ableton / "track.als", '<Path Value="../SAMPLES/CURATED/KICKS/a.wav"/>')
    db = LibraryDatabase(tmp_path / "library.sqlite")
    scan_library(root, db)

    with pytest.raises(CurationError, match="Ableton Set"):
        plan_catalogue_migration(root, ableton, db)


def test_migration_preserves_legacy_folders_and_routes_loose_sources(tmp_path):
    root = tmp_path / "SAMPLES"
    _audio(root / "CURATED" / "CLAP-SNARE" / "a.wav")
    _audio(root / "SEAN" / "b.wav", b"b")
    _audio(root / "Audentity Records Hardgroove House and Techno" / "c.wav", b"c")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    scan_library(root, db)

    plan = plan_catalogue_migration(root, tmp_path / "missing-ableton", db)
    pairs = {(item.src.relative_to(root), item.dest.relative_to(root)) for item in plan}

    assert (Path("CURATED/CLAP-SNARE"), Path("CATALOGUE/CLAP-SNARE")) in pairs
    assert (Path("SEAN"), Path("CATALOGUE/_LEGACY/SEAN")) in pairs
    assert (
        Path("Audentity Records Hardgroove House and Techno"),
        Path("PACKS/audentity-records-hardgroove-house-and-techno"),
    ) in pairs


def test_apply_migration_moves_without_overwrite_and_creates_empty_curated(tmp_path):
    root = tmp_path / "SAMPLES"
    source = _audio(root / "CURATED" / "KICKS" / "a.wav")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    scan_library(root, db)
    plan = plan_catalogue_migration(root, tmp_path / "ableton", db)

    undo = tmp_path / "undo.tsv"
    counts = apply_migration(root, plan, undo)

    assert counts == {"moved": 1, "exists": 0, "missing": 0}
    assert not source.exists()
    assert (root / "CATALOGUE" / "KICKS" / "a.wav").exists()
    assert (root / "CURATED").is_dir()
    assert undo.is_file()


def test_prepare_packet_writes_identity_labels_and_playlist(tmp_path):
    root = tmp_path / "SAMPLES"
    _audio(root / "CATALOGUE" / "KICKS" / "big-kick.wav")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    scan = scan_library(root, db)
    out = tmp_path / "packet"

    count = prepare_packet(root, db, out, quotas={"KICK": 1}, multiplier=2)

    assert count == 1
    rows = list(csv.DictReader((out / "labels.tsv").open(), delimiter="\t"))
    assert len(rows[0]["sample_id"]) == 64
    assert rows[0]["suggested_role"] == "KICK"
    assert rows[0]["decision"] == ""
    assert (out / "audition.m3u8").read_text().strip().endswith("big-kick.wav")
    assert scan.scan_id in (out / "packet-meta.json").read_text()


def test_prepare_packet_does_not_publish_name_derived_category_playlists(tmp_path):
    root = tmp_path / "SAMPLES"
    kick = _audio(root / "CATALOGUE" / "KICKS" / "big-kick.wav")
    perc = _audio(root / "CATALOGUE" / "PERC" / "metal-perc.wav", b"perc")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    scan_library(root, db)
    out = tmp_path / "packet"

    count = prepare_packet(
        root, db, out, quotas={"KICK": 1, "PERC": 1}, multiplier=1
    )

    assert count == 2
    assert (out / "audition.m3u8").read_text().splitlines() == [
        "#EXTM3U", str(kick), str(perc),
    ]
    assert not (out / "playlists").exists()


def test_prepare_packet_writes_empty_combined_playlist(tmp_path):
    root = tmp_path / "SAMPLES"
    root.mkdir()
    db = LibraryDatabase(tmp_path / "library.sqlite")
    scan_library(root, db)
    out = tmp_path / "packet"

    count = prepare_packet(root, db, out, quotas={"KICK": 1}, multiplier=1)

    assert count == 0
    assert (out / "audition.m3u8").read_text() == "#EXTM3U\n"
    assert not (out / "playlists").exists()


def test_regenerate_packet_playlists_requires_audio_classification_and_follows_trimmed_labels(tmp_path):
    root = tmp_path / "SAMPLES"
    kick = _audio(root / "CATALOGUE" / "KICKS" / "big-kick.wav")
    _audio(root / "CATALOGUE" / "PERC" / "metal-perc.wav", b"perc")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    scan_library(root, db)
    packet = tmp_path / "packet"
    prepare_packet(root, db, packet, quotas={"KICK": 1, "PERC": 1}, multiplier=1)
    labels = packet / "labels.tsv"
    rows = list(csv.DictReader(labels.open(), delimiter="\t"))
    with labels.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys(), delimiter="\t")
        writer.writeheader()
        writer.writerow(rows[0])

    classification = packet / "classification.tsv"
    classification.write_text(
        "sample_id\tcurrent_path\tform\tcontent\taudition_group\tform_confidence\tcontent_confidence\tevidence\tclassifier_version\n"
        f"{rows[0]['sample_id']}\t{rows[0]['current_path']}\tONE_SHOT\tRIM\trim-one-shots\t0.9\t0.8\ttest\thybrid-v1\n",
        encoding="utf-8",
    )

    paths = curate.regenerate_packet_playlists(labels)

    assert set(paths) == {"combined", "index", "rim-one-shots"}
    assert not (packet / "playlists" / "perc.m3u8").exists()
    assert (packet / "playlists" / "rim-one-shots.m3u8").read_text().splitlines() == [
        "#EXTM3U", str(kick),
    ]
    assert (packet / "audition.m3u8").read_text().splitlines() == [
        "#EXTM3U", str(kick),
    ]


def test_regenerate_packet_playlists_requires_packet_metadata(tmp_path):
    packet = tmp_path / "packet"
    packet.mkdir()
    labels = packet / "labels.tsv"
    labels.write_text("\t".join(curate.LABEL_FIELDS) + "\n", encoding="utf-8")

    with pytest.raises(CurationError, match="packet-meta.json"):
        curate.regenerate_packet_playlists(labels)


def test_regenerate_packet_playlists_requires_classification_sheet(tmp_path):
    root = tmp_path / "SAMPLES"
    root.mkdir()
    packet = tmp_path / "packet"
    packet.mkdir()
    labels = packet / "labels.tsv"
    labels.write_text("\t".join(curate.LABEL_FIELDS) + "\n", encoding="utf-8")
    (packet / "packet-meta.json").write_text(
        '{"schema_version": 2, "root": "' + str(root) + '"}\n', encoding="utf-8",
    )

    with pytest.raises(CurationError, match="classification.tsv"):
        curate.regenerate_packet_playlists(labels)


@pytest.mark.parametrize("metadata", ["{broken", "{}"])
def test_regenerate_packet_playlists_rejects_invalid_packet_metadata(
    tmp_path, metadata,
):
    packet = tmp_path / "packet"
    packet.mkdir()
    labels = packet / "labels.tsv"
    labels.write_text("\t".join(curate.LABEL_FIELDS) + "\n", encoding="utf-8")
    (packet / "packet-meta.json").write_text(metadata, encoding="utf-8")

    with pytest.raises(CurationError, match="invalid packet metadata"):
        curate.regenerate_packet_playlists(labels)


def test_playlists_cli_regenerates_packet_without_library_database(tmp_path, capsys):
    root = tmp_path / "SAMPLES"
    _audio(root / "CATALOGUE" / "KICKS" / "big-kick.wav")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    scan_library(root, db)
    packet = tmp_path / "packet"
    prepare_packet(root, db, packet, quotas={"KICK": 1}, multiplier=1)
    label_row = next(csv.DictReader((packet / "labels.tsv").open(), delimiter="\t"))
    (packet / "classification.tsv").write_text(
        "sample_id\tcurrent_path\tform\tcontent\taudition_group\tform_confidence\tcontent_confidence\tevidence\tclassifier_version\n"
        f"{label_row['sample_id']}\t{label_row['current_path']}\tONE_SHOT\tRIM\trim-one-shots\t0.9\t0.8\ttest\thybrid-v1\n",
        encoding="utf-8",
    )

    rc = curate_cli.main(["playlists", "--labels", str(packet / "labels.tsv")])

    assert rc == 0
    assert capsys.readouterr().out == f"category playlists: 1 -> {packet / 'playlists'}\n"


def test_archive_rejected_name_derived_playlists_is_one_time_and_non_destructive(tmp_path):
    packet = tmp_path / "packet"
    old = packet / "playlists"
    old.mkdir(parents=True)
    (old / "tom.m3u8").write_text("#EXTM3U\n/old/tom.wav\n", encoding="utf-8")
    (packet / "audition.m3u8").write_text("#EXTM3U\n/old/tom.wav\n", encoding="utf-8")

    assert curate.archive_rejected_playlists(packet) is True
    assert not old.exists()
    assert (packet / "archive" / "name-derived-playlists" / "tom.m3u8").read_text() == (
        "#EXTM3U\n/old/tom.wav\n"
    )
    assert (packet / "archive" / "name-derived-audition.m3u8").is_file()

    old.mkdir()
    (old / "new.m3u8").write_text("#EXTM3U\n/new.wav\n", encoding="utf-8")
    assert curate.archive_rejected_playlists(packet) is False
    assert (old / "new.m3u8").is_file()


def test_validate_requires_role_and_descriptor_for_favourite(tmp_path):
    labels = tmp_path / "labels.tsv"
    labels.write_text(
        "sample_id\tcurrent_path\tsuggested_role\tdecision\ttrue_role\tdescriptor\ttags\tnotes\n"
        + "a" * 64 + "\tCATALOGUE/KICKS/a.wav\tKICK\tfavourite\t\t\t\t\n",
        encoding="utf-8",
    )

    with pytest.raises(CurationError, match="true_role"):
        validate_labels(read_labels(labels))


def test_promote_favourite_verifies_hash_and_copies_with_provenance(tmp_path):
    root = tmp_path / "SAMPLES"
    src = _audio(root / "CATALOGUE" / "KICKS" / "big-kick.wav", b"kick-audio")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    scan_library(root, db)
    location = db.current_locations()[0]
    packet = tmp_path / "packet"
    packet.mkdir()
    (packet / "labels.tsv").write_text(
        "sample_id\tcurrent_path\tsuggested_role\tdecision\ttrue_role\tdescriptor\ttags\tnotes\n"
        f"{location.sample_id}\t{location.path}\tKICK\tfavourite\tKICK\tsub-dark\ttone:dark\tgood\n",
        encoding="utf-8",
    )

    promoted = promote_favourites(root, db, packet / "labels.tsv", run_id="run1")

    assert len(promoted) == 1
    dest = promoted[0]
    assert dest.exists() and dest.read_bytes() == src.read_bytes()
    assert dest.parent == root / "CURATED" / "KICK"
    assert location.sample_id[:8] in dest.name
    assert db.promotions()[0]["source_path"] == location.path.as_posix()
    assert db.tags_for(location.sample_id) == [("tone", "dark")]


def test_promotion_rejects_changed_source(tmp_path):
    root = tmp_path / "SAMPLES"
    src = _audio(root / "CATALOGUE" / "KICKS" / "a.wav", b"old")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    scan_library(root, db)
    location = db.current_locations()[0]
    labels = tmp_path / "labels.tsv"
    labels.write_text(
        "sample_id\tcurrent_path\tsuggested_role\tdecision\ttrue_role\tdescriptor\ttags\tnotes\n"
        f"{location.sample_id}\t{location.path}\tKICK\tfavourite\tKICK\tshort\t\t\n",
        encoding="utf-8",
    )
    src.write_bytes(b"changed")

    with pytest.raises(CurationError, match="hash changed"):
        promote_favourites(root, db, labels, run_id="run1")


def test_promotion_rejects_packet_from_older_complete_scan(tmp_path):
    root = tmp_path / "SAMPLES"
    _audio(root / "CATALOGUE" / "KICKS" / "a.wav", b"kick")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    scan_library(root, db)
    packet = tmp_path / "packet"
    prepare_packet(root, db, packet, quotas={"KICK": 1}, multiplier=1)
    rows = list(csv.DictReader((packet / "labels.tsv").open(), delimiter="\t"))
    rows[0].update(decision="favourite", true_role="KICK", descriptor="short")
    with (packet / "labels.tsv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys(), delimiter="\t")
        writer.writeheader(); writer.writerows(rows)
    scan_library(root, db)

    with pytest.raises(CurationError, match="stale packet"):
        promote_favourites(root, db, packet / "labels.tsv", run_id="run1")


def test_consumer_views_use_promoted_paths_and_split_one_shots(tmp_path):
    root = tmp_path / "SAMPLES"
    _audio(root / "CATALOGUE" / "KICKS" / "a.wav", b"kick")
    _audio(root / "CATALOGUE" / "LOOPS" / "loop.wav", b"loop")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    scan_library(root, db)
    by_path = {row.path.as_posix(): row for row in db.current_locations()}
    labels = tmp_path / "labels.tsv"
    labels.write_text(
        "sample_id\tcurrent_path\tsuggested_role\tdecision\ttrue_role\tdescriptor\ttags\tnotes\n"
        f"{by_path['CATALOGUE/KICKS/a.wav'].sample_id}\tCATALOGUE/KICKS/a.wav\tKICK\tfavourite\tKICK\tshort\t\t\n"
        f"{by_path['CATALOGUE/LOOPS/loop.wav'].sample_id}\tCATALOGUE/LOOPS/loop.wav\tDRUM-LOOP\tfavourite\tDRUM-LOOP\tsparse\t\t\n",
        encoding="utf-8",
    )
    promote_favourites(root, db, labels, run_id="run1")

    paths = write_consumer_views(db, labels, tmp_path / "views", quotas={"KICK": 1, "DRUM-LOOP": 1})

    one_shots = list(csv.DictReader(paths["one_shots"].open(), delimiter="\t"))
    all_rows = list(csv.DictReader(paths["all"].open(), delimiter="\t"))
    assert [row["role"] for row in one_shots] == ["KICK"]
    assert {row["role"] for row in all_rows} == {"KICK", "DRUM-LOOP"}
    assert all(row["source_path"].startswith("CURATED/") for row in all_rows)
    assert paths["ableton"].is_file()


def test_promotion_undo_moves_copy_to_quarantine_without_deleting(tmp_path):
    root = tmp_path / "SAMPLES"
    _audio(root / "CATALOGUE" / "KICKS" / "a.wav", b"kick")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    scan_library(root, db)
    location = db.current_locations()[0]
    labels = tmp_path / "labels.tsv"
    labels.write_text(
        "sample_id\tcurrent_path\tsuggested_role\tdecision\ttrue_role\tdescriptor\ttags\tnotes\n"
        f"{location.sample_id}\t{location.path}\tKICK\tfavourite\tKICK\tshort\t\t\n",
        encoding="utf-8",
    )
    promoted = promote_favourites(root, db, labels, run_id="run1")[0]

    moved = undo_promotions(root, db, "run1")

    assert moved == 1
    assert not promoted.exists()
    quarantined = list((root / "_QUARANTINE" / "promotion-undo" / "run1").rglob("*.wav"))
    assert len(quarantined) == 1 and quarantined[0].read_bytes() == b"kick"
