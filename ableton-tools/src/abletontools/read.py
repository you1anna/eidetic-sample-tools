import gzip
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterator


class AlsParseError(Exception):
    pass


def load_als(path: Path) -> ET.Element:
    try:
        with gzip.open(path, "rb") as f:
            tree = ET.parse(f)
    except (OSError, ET.ParseError) as exc:
        raise AlsParseError(f"{path}: {exc}") from exc
    return tree.getroot()


def iter_sets(root: Path) -> Iterator[Path]:
    for path in root.rglob("*.als"):
        if "Backup" in path.relative_to(root).parts[:-1]:
            continue
        if path.name.startswith("."):
            continue
        yield path
