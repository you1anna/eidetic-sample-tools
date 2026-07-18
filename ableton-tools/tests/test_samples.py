import gzip
from pathlib import Path

from abletontools.read import load_als
from abletontools.samples import sample_refs, classify


def test_sample_refs_present_and_missing(tmp_path):
    real_file = tmp_path / "kick.wav"
    real_file.write_bytes(b"RIFF")

    als_xml = f"""<?xml version="1.0"?><Ableton><LiveSet>
<Tracks><AudioTrack><DeviceChain><MainSequencer><ClipSlotList>
<ClipSlot><ClipSlot><Value><AudioClip>
<SampleRef><FileRef>
<RelativePathType Value="0"/>
<Path Value="{real_file}"/>
<RelativePath Value="kick.wav"/>
</FileRef></SampleRef>
</AudioClip></Value></ClipSlot></ClipSlot>
</ClipSlotList></MainSequencer></DeviceChain></AudioTrack></Tracks>
<Tracks><AudioTrack><DeviceChain><MainSequencer><ClipSlotList>
<ClipSlot><ClipSlot><Value><AudioClip>
<SampleRef><FileRef>
<RelativePathType Value="0"/>
<Path Value="{tmp_path / 'missing.wav'}"/>
<RelativePath Value="missing.wav"/>
</FileRef></SampleRef>
</AudioClip></Value></ClipSlot></ClipSlot>
</ClipSlotList></MainSequencer></DeviceChain></AudioTrack></Tracks>
</LiveSet></Ableton>""".encode()

    als_path = tmp_path / "set.als"
    als_path.write_bytes(gzip.compress(als_xml))
    root = load_als(als_path)

    refs = sample_refs(root)
    assert len(refs) == 2

    result = classify(refs)
    present_names = {r.resolved.name for r in result["present"]}
    missing_names = {r.resolved.name for r in result["missing"]}
    assert present_names == {"kick.wav"}
    assert missing_names == {"missing.wav"}


def test_sample_refs_falls_back_to_relative_path(tmp_path):
    real_file = tmp_path / "snare.wav"
    real_file.write_bytes(b"RIFF")

    als_xml = f"""<?xml version="1.0"?><Ableton><LiveSet>
<Tracks><AudioTrack><DeviceChain><MainSequencer><ClipSlotList>
<ClipSlot><ClipSlot><Value><AudioClip>
<SampleRef><FileRef>
<RelativePathType Value="1"/>
<Path Value="/nonexistent/absolute/snare.wav"/>
<RelativePath Value="snare.wav"/>
</FileRef></SampleRef>
</AudioClip></Value></ClipSlot></ClipSlot>
</ClipSlotList></MainSequencer></DeviceChain></AudioTrack></Tracks>
</LiveSet></Ableton>""".encode()

    als_path = tmp_path / "set.als"
    als_path.write_bytes(gzip.compress(als_xml))
    root = load_als(als_path)

    refs = sample_refs(root, set_dir=tmp_path)
    result = classify(refs)
    assert {r.resolved.name for r in result["present"]} == {"snare.wav"}
