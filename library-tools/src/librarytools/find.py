"""Query the sample index by tag, and rank by sound.

Keyword tags narrow across the library; they cannot narrow *within* a pack, because 7,826
Goldbaby SA909 samples share every keyword tag they will ever have.  Similarity ranking over
measured acoustics is the only thing that splits them, so ``--like`` matters more here than
any amount of vocabulary work.

Read-only.  Nothing in this module moves, renames or converts audio.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from .featurecache import FEATURE_COLUMNS
from .inventory import LibraryDatabase
from .origin import is_generated_name
from .review import _description, classify_role

# Review roles are broad folders; the exporter's crate vocabulary is per-instrument.  Where a
# folder covers several instruments the filename decides, falling back to the commonest.
ROLE_TO_EXPORT: dict[str, str] = {
    "KICKS": "KICK",
    "CLAP-SNARE": "SNARE",
    "HATS-CYM": "HAT-CLOSED",
    "PERC": "PERC",
    "BASS": "BASS",
    "SYNTH-STAB-CHORD": "STAB-CHORD",
    "DRONE-ATMOS": "TEXTURE-DRONE",
    "FX-RISE-IMPACT": "FX",
    "VOCALS": "VOCAL",
    "DRUM-LOOPS": "DRUM-LOOP",
}

_ROLE_REFINEMENTS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "CLAP-SNARE": (
        ("CLAP", ("clap", "cp")),
        ("RIM", ("rim", "rimshot", "rs")),
        ("SNARE", ("snare", "sd")),
    ),
    "HATS-CYM": (
        ("HAT-OPEN", ("open", "ohh", "oh-", "openhat")),
        ("HAT-CLOSED", ("closed", "chh", "clhat", "hhc")),
        ("RIDE", ("ride",)),
        ("CYMBAL", ("crash", "cymbal", "cym")),
        ("SHAKER", ("shaker", "tamb")),
        ("HAT-CLOSED", ()),
    ),
    "PERC": (
        ("TOM", ("tom", "timbale")),
        ("PERC", ()),
    ),
}


@dataclass(frozen=True)
class Match:
    sample_id: str
    path: Path
    role: str
    origin: str
    zone: str = "ROOT"
    tags: tuple[str, ...] = ()
    distance: float | None = None
    picks: int = 0

    @property
    def name(self) -> str:
        return self.path.stem


@dataclass
class Query:
    terms: tuple[str, ...] = ()
    groups: dict[str, tuple[str, ...]] = field(default_factory=dict)
    any_: bool = False
    curated_only: bool = False

    def describe(self) -> str:
        parts = list(self.terms)
        parts += [f"{group}={value}" for group, values in self.groups.items() for value in values]
        if self.curated_only:
            parts.append("zone=CURATED")
        return " ".join(parts) or "(all)"


# `proposed_name` prefixes flattened files with their role, so a snare is called
# `clap-snare-...` and a closed hat `hat-cym-...`. Matching instrument words against the raw
# name therefore calls every snare a CLAP and every hat a CYMBAL; the prefix goes first.
_NAME_ROLE_PREFIXES: tuple[str, ...] = (
    "clap-snare-", "hat-cym-", "synth-stab-", "drone-atmos-", "kick-", "perc-",
    "bass-", "fx-", "vocal-", "review-",
)


def _strip_role_prefix(text: str) -> str:
    name = text.rsplit("/", 1)[-1].lower()
    for prefix in _NAME_ROLE_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def export_role(review_role: str, text: str) -> str:
    """Map a broad review role onto the exporter's per-instrument crate vocabulary."""
    lowered = _strip_role_prefix(text)
    for candidate, needles in _ROLE_REFINEMENTS.get(review_role, ()):
        if not needles or any(needle in lowered for needle in needles):
            return candidate
    return ROLE_TO_EXPORT.get(review_role, "PERC")


# `proposed_name` prefixes every flattened file with its role, so the leading word carries no
# information the crate's own role column does not already give.
_ROLE_WORDS = frozenset({
    "kick", "clap", "snare", "hat", "cym", "perc", "bass", "synth", "stab", "drone",
    "atmos", "fx", "vocal", "review", "bd", "sd", "hh", "loop",
})


def descriptor_for(path: Path) -> str:
    """A short human word for the crate row, taken from the sample's own name.

    This ends up on the hardware as ``BD01_<descriptor>_<hash>.wav``, so it should be the
    most distinctive word available.  The trailing ``_<origin>`` is only stripped from names
    the sorter generated; a vendor's own ``AU_HHT_kick_one_shot_balancer`` means every part
    of the stem counts, and the longest word ("balancer") beats the vendor prefix ("au").
    """
    stem = path.stem
    if is_generated_name(stem):
        stem = stem.split("_", 1)[0]
    words = [word for word in _description(stem).split("-") if word and not word.isdigit()]

    useful = [word for word in words if len(word) >= 3 and word not in _ROLE_WORDS]
    if useful:
        return max(useful, key=len)[:8]
    fallback = [word for word in words if len(word) >= 3]
    if fallback:
        return max(fallback, key=len)[:8]
    return words[0][:8] if words else "sample"


# Role and origin are stored as tags so they stay queryable, but they have their own
# columns in the output and would only crowd the style/character one.
_DISPLAY_SKIP_GROUPS = frozenset({"role", "origin"})


def load_index(database: LibraryDatabase) -> list[Match]:
    """Read every indexed sample with its tags and origin."""
    origins = database.origins()
    picks = database.pick_counts()

    matches: list[Match] = []
    seen: set[str] = set()
    for location in database.current_locations():
        if location.sample_id in seen:
            continue
        seen.add(location.sample_id)
        tags = tuple(sorted(
            tag for group, tag in database.tags_for(location.sample_id)
            if group not in _DISPLAY_SKIP_GROUPS
        ))
        origin, _, _ = origins.get(location.sample_id, ("unknown", "none", ""))
        matches.append(
            Match(
                sample_id=location.sample_id,
                path=location.path,
                role=classify_role(location.path).role,
                origin=origin,
                zone=location.zone,
                tags=tags,
                picks=picks.get(location.sample_id, 0),
            )
        )
    return matches


def _haystack(match: Match) -> set[str]:
    words = set(match.tags)
    words.add(match.origin)
    words.add(match.role.lower())
    words.update(part for part in match.path.as_posix().lower().replace("_", "-").split("/"))
    return words


def matches_query(match: Match, query: Query) -> bool:
    if query.curated_only and match.zone != "CURATED":
        return False

    haystack = _haystack(match)
    text = match.path.as_posix().lower() + " " + " ".join(match.tags) + " " + match.origin

    for group, values in query.groups.items():
        tagged = {tag for tag in match.tags}
        if group == "origin":
            if not any(value in match.origin for value in values):
                return False
        elif group == "role":
            if not any(value.upper() == match.role for value in values):
                return False
        elif not any(value in tagged for value in values):
            return False

    if not query.terms:
        return True
    hits = [
        term for term in query.terms
        if term in haystack or term in text
    ]
    return bool(hits) if query.any_ else len(hits) == len(query.terms)


def search(matches: list[Match], query: Query) -> list[Match]:
    return [match for match in matches if matches_query(match, query)]


def family(match: Match) -> tuple[str, str]:
    """Group round-robin takes of one sound together.

    Goldbaby-style packs ship the same hit eight times (``...-aorig-r1``, ``-r2``, ``-r3``),
    so a plain alphabetical list answers "find me a bongo" with eight copies of one bongo.
    The first few description words identify the sound; the take number does not.
    """
    stem = match.path.stem.split("_", 1)[0]
    words = [word for word in stem.split("-") if word]
    return (match.origin, "-".join(words[:3]))


def spread(matches: list[Match]) -> list[Match]:
    """Round-robin across sound families so the first results show variety, not takes."""
    grouped: dict[tuple[str, str], list[Match]] = {}
    for match in matches:
        grouped.setdefault(family(match), []).append(match)
    for group in grouped.values():
        group.sort(key=lambda item: item.path.as_posix())

    ordered: list[Match] = []
    queues = sorted(grouped.items(), key=lambda item: item[0])
    depth = 0
    while len(ordered) < len(matches):
        for _, group in queues:
            if depth < len(group):
                ordered.append(group[depth])
        depth += 1
    return ordered


# ---------------------------------------------------------------- similarity


def _vectors(database: LibraryDatabase) -> dict[str, list[float | None]]:
    raw = database.features()
    return {
        sample_id: [json.loads(payload).get(column) for column in FEATURE_COLUMNS]
        for sample_id, payload in raw.items()
    }


def _ranges(vectors: dict[str, list[float | None]]) -> list[tuple[float, float]]:
    ranges: list[tuple[float, float]] = []
    for index in range(len(FEATURE_COLUMNS)):
        values = [
            vector[index] for vector in vectors.values()
            if vector[index] is not None
        ]
        if values:
            low, high = min(values), max(values)
            ranges.append((low, high if high > low else low + 1.0))
        else:
            ranges.append((0.0, 1.0))
    return ranges


def distance(
    left: list[float | None],
    right: list[float | None],
    ranges: list[tuple[float, float]],
) -> float | None:
    """Euclidean distance over min-max normalised dimensions present in both samples.

    Plain and inspectable on purpose: no clustering and no model, so there is nothing here
    that can quietly miscalibrate the way the drum classifier did.
    """
    total = 0.0
    used = 0
    for index, (low, high) in enumerate(ranges):
        a, b = left[index], right[index]
        if a is None or b is None:
            continue
        span = high - low
        total += ((a - low) / span - (b - low) / span) ** 2
        used += 1
    if not used:
        return None
    return (total / used) ** 0.5


def rank_by_similarity(
    database: LibraryDatabase, target_id: str, candidates: list[Match],
) -> list[Match]:
    """Order candidates by how close they sound to ``target_id``."""
    vectors = _vectors(database)
    target = vectors.get(target_id)
    if target is None:
        raise KeyError(f"no measured features for {target_id}")
    ranges = _ranges(vectors)

    scored: list[Match] = []
    for match in candidates:
        vector = vectors.get(match.sample_id)
        if vector is None:
            continue
        gap = distance(target, vector, ranges)
        if gap is None:
            continue
        scored.append(replace(match, distance=gap))
    return sorted(scored, key=lambda item: (item.distance, item.path.as_posix()))


def resolve_target(matches: list[Match], reference: str) -> str:
    """Accept either a sample_id or any path fragment that identifies one sample."""
    for match in matches:
        if match.sample_id == reference:
            return match.sample_id
    hits = [match for match in matches if reference in match.path.as_posix()]
    if not hits:
        raise KeyError(f"nothing in the index matches {reference!r}")
    if len(hits) > 1:
        joined = ", ".join(hit.path.as_posix() for hit in hits[:4])
        raise KeyError(f"{reference!r} matches {len(hits)} samples: {joined} …")
    return hits[0].sample_id


# ---------------------------------------------------------------- outputs


def write_m3u8(root: Path, matches: list[Match], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(str(root / match.path) for match in matches)
    path.write_text(body + ("\n" if matches else ""), encoding="utf-8")


CRATE_FIELDS = ("sample_id", "source_path", "role", "descriptor", "reason")


def write_crate(matches: list[Match], path: Path, reason: str) -> None:
    """Write the exact crate schema ``sampletools.export.read_crate_tsv`` expects."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(CRATE_FIELDS)
        for match in matches:
            writer.writerow([
                match.sample_id,
                match.path.as_posix(),
                export_role(match.role, match.path.as_posix()),
                descriptor_for(match.path),
                reason,
            ])
