from __future__ import annotations

import csv
from pathlib import Path

from librarytools import analyze


def _make(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    return path


def test_detect_ot_set_registers_project_audio_and_docs(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    pack = root / "PACKS" / "Caught on Tape 808+909"
    _make(pack / "project.work")
    _make(pack / "bank01.work")
    _make(pack / "arr01.work")
    _make(pack / "pattern.strd")
    _make(pack / "AUDIO" / "COT_BD_Orig.wav")
    _make(pack / "Install Guide.pdf")

    sets = analyze.detect_ot_sets(root)

    assert len(sets) == 1
    assert sets[0].set_name == "Caught on Tape 808+909"
    assert sets[0].project_root == Path("PACKS/Caught on Tape 808+909")
    assert sets[0].audio_pool_root == Path("PACKS/Caught on Tape 808+909/AUDIO")
    assert sets[0].project_file_count == 3
    assert sets[0].strd_file_count == 1
    assert sets[0].audio_file_count == 1
    assert sets[0].doc_path == Path("PACKS/Caught on Tape 808+909/Install Guide.pdf")
    assert sets[0].handling_policy == "preserve-set"


def test_write_ot_sets_outputs_tsv(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    pack = root / "PACKS" / "Cult of SP1200"
    _make(pack / "project.work")
    _make(pack / "AUDIO" / "SP_Kick_TapeSat.wav")
    out = tmp_path / "ot-sets.tsv"

    analyze.write_ot_sets(out, analyze.detect_ot_sets(root))

    rows = list(csv.DictReader(out.open(), delimiter="\t"))
    assert rows[0]["set_name"] == "Cult of SP1200"
    assert rows[0]["inferred_device"] == "octatrack"
    assert rows[0]["handling_policy"] == "preserve-set"
