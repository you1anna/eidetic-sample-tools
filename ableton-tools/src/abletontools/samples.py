import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SampleRef:
    raw_path: str
    relative_path: str | None
    resolved: Path


def sample_refs(root_el: ET.Element, set_dir: Path | None = None) -> list[SampleRef]:
    refs = []
    for file_ref in root_el.findall(".//SampleRef//FileRef"):
        path_el = file_ref.find("Path")
        rel_el = file_ref.find("RelativePath")
        raw_path = path_el.get("Value") if path_el is not None else ""
        relative_path = rel_el.get("Value") if rel_el is not None else None

        resolved = Path(raw_path) if raw_path else None
        if resolved is None or not resolved.is_absolute() or not resolved.exists():
            if relative_path and set_dir is not None:
                candidate = (set_dir / relative_path).resolve()
                if candidate.exists() or resolved is None:
                    resolved = candidate

        if resolved is None:
            resolved = Path(raw_path)

        refs.append(SampleRef(raw_path=raw_path, relative_path=relative_path, resolved=resolved))
    return refs


def classify(refs: list[SampleRef]) -> dict[str, list[SampleRef]]:
    present = [r for r in refs if r.resolved.exists()]
    missing = [r for r in refs if not r.resolved.exists()]
    return {"present": present, "missing": missing}
