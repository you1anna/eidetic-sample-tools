import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SetInfo:
    path: Path
    tempo: float | None
    tracks: list[str]
    scene_count: int
    devices: list[str]
    mtime: float


def set_summary(root: ET.Element, path: Path) -> SetInfo:
    tempo_el = root.find(".//Tempo/Manual")
    tempo = float(tempo_el.get("Value")) if tempo_el is not None else None

    tracks: list[str] = []
    for track in root.iter():
        if track.tag in ("MidiTrack", "AudioTrack"):
            name_el = track.find(".//Name/EffectiveName")
            if name_el is not None and name_el.get("Value"):
                tracks.append(name_el.get("Value"))

    scene_count = len(root.findall(".//Scenes/Scene"))

    devices = [child.tag for devices_el in root.iter("Devices") for child in devices_el]

    return SetInfo(
        path=path,
        tempo=tempo,
        tracks=tracks,
        scene_count=scene_count,
        devices=devices,
        mtime=path.stat().st_mtime if path.exists() else 0.0,
    )


def to_tsv_row(info: SetInfo) -> str:
    fields = [
        str(info.path),
        "" if info.tempo is None else str(info.tempo),
        str(len(info.tracks)),
        ",".join(info.tracks),
        str(info.scene_count),
        ",".join(info.devices),
        str(info.mtime),
    ]
    return "\t".join(fields)


def to_json(info: SetInfo) -> str:
    return json.dumps(
        {
            "path": str(info.path),
            "tempo": info.tempo,
            "tracks": info.tracks,
            "scene_count": info.scene_count,
            "devices": info.devices,
            "mtime": info.mtime,
        }
    )
