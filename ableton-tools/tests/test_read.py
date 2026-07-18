import gzip
from pathlib import Path

from abletontools.read import load_als, iter_sets, AlsParseError

ALS_XML = b"""<?xml version="1.0"?><Ableton><LiveSet>
<Tracks><MidiTrack><Name><EffectiveName Value="Kick"/></Name></MidiTrack></Tracks>
<MasterTrack><DeviceChain><Mixer><Tempo><Manual Value="138"/></Tempo></Mixer></DeviceChain></MasterTrack>
</LiveSet></Ableton>"""


def _mk(p: Path) -> Path:
    p.write_bytes(gzip.compress(ALS_XML))
    return p


def test_load_ok(tmp_path):
    root = load_als(_mk(tmp_path / "a.als"))
    assert root.tag == "Ableton"


def test_bad_file_raises_parse_error(tmp_path):
    (tmp_path / "b.als").write_bytes(b"not gzip")
    try:
        load_als(tmp_path / "b.als")
        assert False
    except AlsParseError:
        pass


def test_iter_sets_finds_als_skips_backup(tmp_path):
    _mk(tmp_path / "a.als")
    _mk(tmp_path / "b.als")
    backup_dir = tmp_path / "Backup"
    backup_dir.mkdir()
    _mk(backup_dir / "c.als")
    found = sorted(p.name for p in iter_sets(tmp_path))
    assert found == ["a.als", "b.als"]
