import gzip
from pathlib import Path

from abletontools.cli import index_main, samples_main

ALS_XML = b"""<?xml version="1.0"?><Ableton><LiveSet>
<Tracks><MidiTrack><Name><EffectiveName Value="Kick"/></Name></MidiTrack></Tracks>
<MasterTrack><DeviceChain><Mixer><Tempo><Manual Value="138"/></Tempo></Mixer></DeviceChain></MasterTrack>
</LiveSet></Ableton>"""


def test_index_main_writes_tsv(tmp_path):
    root_dir = tmp_path / "sets"
    root_dir.mkdir()
    (root_dir / "a.als").write_bytes(gzip.compress(ALS_XML))
    out_dir = tmp_path / "out"

    index_main(["--root", str(root_dir), "--out", str(out_dir)])

    tsv = out_dir / "als-index.tsv"
    assert tsv.exists()
    lines = tsv.read_text().splitlines()
    assert len(lines) == 2  # header + 1 row
    assert "138.0" in lines[1]


def test_index_main_skips_malformed_without_crashing(tmp_path, capsys):
    root_dir = tmp_path / "sets"
    root_dir.mkdir()
    (root_dir / "good.als").write_bytes(gzip.compress(ALS_XML))
    (root_dir / "bad.als").write_bytes(b"not gzip")
    out_dir = tmp_path / "out"

    index_main(["--root", str(root_dir), "--out", str(out_dir)])

    tsv = (out_dir / "als-index.tsv").read_text().splitlines()
    assert len(tsv) == 2  # header + only the good Set


def test_samples_main_reports_counts(tmp_path, capsys):
    root_dir = tmp_path / "sets"
    root_dir.mkdir()
    (root_dir / "a.als").write_bytes(gzip.compress(ALS_XML))
    out_dir = tmp_path / "out"

    samples_main(["--root", str(root_dir), "--out", str(out_dir)])

    captured = capsys.readouterr()
    assert "present" in captured.out.lower()
    assert "missing" in captured.out.lower()
