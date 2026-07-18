import gzip
from pathlib import Path

from abletontools.read import load_als
from abletontools.index import set_summary

ALS_XML = b"""<?xml version="1.0"?><Ableton><LiveSet>
<Tracks>
  <MidiTrack><Name><EffectiveName Value="Kick"/></Name></MidiTrack>
  <AudioTrack><Name><EffectiveName Value="Bass"/></Name></AudioTrack>
</Tracks>
<Scenes>
  <Scene Name="A"/>
  <Scene Name="B"/>
</Scenes>
<MasterTrack>
  <DeviceChain>
    <Mixer><Tempo><Manual Value="138"/></Tempo></Mixer>
    <DeviceChain>
      <Devices>
        <Reverb Id="0"/>
        <Delay Id="1"/>
      </Devices>
    </DeviceChain>
  </DeviceChain>
</MasterTrack>
</LiveSet></Ableton>"""


def _root(tmp_path: Path):
    p = tmp_path / "a.als"
    p.write_bytes(gzip.compress(ALS_XML))
    return load_als(p), p


def test_set_summary_extracts_tempo_tracks_scenes_devices(tmp_path):
    root, path = _root(tmp_path)
    info = set_summary(root, path)
    assert info.path == path
    assert info.tempo == 138.0
    assert "Kick" in info.tracks
    assert "Bass" in info.tracks
    assert info.scene_count == 2
    assert info.devices == ["Reverb", "Delay"]


def test_set_summary_handles_missing_nodes(tmp_path):
    minimal = b"<?xml version=\"1.0\"?><Ableton><LiveSet></LiveSet></Ableton>"
    p = tmp_path / "b.als"
    p.write_bytes(gzip.compress(minimal))
    root = load_als(p)
    info = set_summary(root, p)
    assert info.tempo is None
    assert info.tracks == []
    assert info.scene_count == 0
    assert info.devices == []
