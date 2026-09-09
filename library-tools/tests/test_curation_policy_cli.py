import csv
from pathlib import Path

import pytest

from librarytools.curate import LABEL_FIELDS
from librarytools.curate_cli import main
from librarytools.inventory import LibraryDatabase, scan_library


def _run(args):
    try:
        return main([str(arg) for arg in args])
    except SystemExit as error:
        return error.code


def test_small_custom_collection_can_prepare_promote_and_export_views(tmp_path):
    root = tmp_path / "SAMPLES"
    source = root / "PACKS" / "kick.wav"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"approved kick")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    scan_library(root, db)
    quotas = tmp_path / "quotas.toml"
    quotas.write_text('[quotas]\nKICK = 1\n')
    packet = tmp_path / "packet"
    base = ["--root", root, "--library-db", db.path]

    assert _run([*base, "prepare", "--output-dir", packet, "--quotas", quotas]) == 0
    labels = packet / "labels.tsv"
    with labels.open() as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert len(rows) == 1
    rows[0].update(decision="favourite", true_role="KICK", descriptor="short")
    with labels.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LABEL_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    assert _run([*base, "promote", "--labels", labels, "--run-id", "kit"]) == 0

    output = tmp_path / "views"
    assert _run([
        *base, "views", "--labels", labels, "--output-dir", output,
        "--quotas", quotas, "--name", "live-kit",
    ]) == 0
    with (output / "live-kit-one-shots.tsv").open() as handle:
        crate = list(csv.DictReader(handle, delimiter="\t"))
    assert len(crate) == 1
    assert crate[0]["source_path"].startswith("CURATED/KICK/")
    assert (output / "live-kit-all.tsv").is_file()
    assert (output / "ableton-curated.tsv").is_file()


@pytest.mark.parametrize("body", [
    '[quotas]\nKCIK = 1\n',
    '[quotas]\nKICK = -1\n',
    '[quotas]\nKICK = true\n',
    '[quotas]\nKICK = 1.5\n',
    '[quotas]\nKICK = 0\n',
    'KICK = 1\n',
    '[quotas\n',
])
def test_invalid_quotas_fail_before_creating_an_index_or_packet(tmp_path, capsys, body):
    quotas = tmp_path / "quotas.toml"
    quotas.write_text(body)
    database = tmp_path / "absent" / "library.sqlite"
    packet = tmp_path / "packet"

    assert _run([
        "--root", tmp_path, "--library-db", database, "prepare", "--output-dir", packet, "--quotas", quotas,
    ]) == 2

    assert "invalid quotas" in capsys.readouterr().err.lower()
    assert not database.parent.exists()
    assert not packet.exists()


def test_custom_crate_name_cannot_escape_output_directory(tmp_path, capsys):
    database = tmp_path / "absent" / "library.sqlite"
    output = tmp_path / "views"

    assert _run([
        "--root", tmp_path, "--library-db", database, "views", "--labels", tmp_path / "labels.tsv",
        "--output-dir", output, "--name", "../escape",
    ]) == 2

    assert "crate name" in capsys.readouterr().err.lower()
    assert not database.parent.exists()
    assert not output.exists()
