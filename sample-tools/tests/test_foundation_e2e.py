"""Synthetic acceptance path across library-tools and sample-tools."""

import csv
import hashlib
import math
import struct
import wave
from pathlib import Path

from librarytools.curate import promote_favourites, write_consumer_views
from librarytools.inventory import LibraryDatabase, scan_library
from sampletools import config, export as export_mod
from sampletools.probe import probe


def _wav(path: Path, frequency: int) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 44_100
    frames = bytearray()
    for index in range(rate // 50):
        value = int(8_000 * math.sin(2 * math.pi * frequency * index / rate))
        frames.extend(struct.pack("<h", value))
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(rate)
        fh.writeframes(bytes(frames))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_scan_promote_views_and_device_exports(tmp_path, monkeypatch):
    root = tmp_path / "SAMPLES"
    kick_id = _wav(root / "CATALOGUE" / "KICKS" / "kick.wav", 60)
    loop_id = _wav(root / "CATALOGUE" / "DRUM-LOOPS" / "loop.wav", 220)
    db = LibraryDatabase(tmp_path / "sample-library.sqlite")
    scan_library(root, db)
    labels = tmp_path / "labels.tsv"
    labels.write_text(
        "sample_id\tcurrent_path\tsuggested_role\tdecision\ttrue_role\tdescriptor\ttags\tnotes\n"
        f"{kick_id}\tCATALOGUE/KICKS/kick.wav\tKICK\tfavourite\tKICK\tsub\ttone:dark\t\n"
        f"{loop_id}\tCATALOGUE/DRUM-LOOPS/loop.wav\tDRUM-LOOP\tfavourite\tDRUM-LOOP\tsparse\t\t\n",
        encoding="utf-8",
    )
    promote_favourites(root, db, labels, run_id="foundation-v1")
    views = write_consumer_views(
        db, labels, tmp_path / "views", quotas={"KICK": 1, "DRUM-LOOP": 1}
    )
    monkeypatch.setattr(export_mod, "EXPORT_ROOT", tmp_path / "EXPORT")

    digitakt = config.get_spec("digitakt")
    dt_plan = export_mod.build_crate_plan(digitakt, views["one_shots"], root)
    export_mod.export_device(digitakt, plan=dt_plan)
    dt_info = probe(tmp_path / "EXPORT" / "DIGITAKT" / dt_plan.items[0].out_rel)

    octatrack = config.get_spec("octatrack")
    ot_plan = export_mod.build_crate_plan(octatrack, views["all"], root)
    export_mod.export_device(octatrack, plan=ot_plan)
    ot_infos = [probe(tmp_path / "EXPORT" / "OCTATRACK" / item.out_rel) for item in ot_plan.items]

    assert (dt_info.rate, dt_info.bits, dt_info.channels) == (48_000, 16, 1)
    assert len(ot_infos) == 2
    assert all(info.rate == 44_100 for info in ot_infos)
    assert list(csv.DictReader(views["ableton"].open(), delimiter="\t"))
