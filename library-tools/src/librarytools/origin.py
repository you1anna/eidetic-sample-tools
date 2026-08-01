"""Recover pack origin for samples whose paths were flattened by earlier sorting.

Role-folder sorting moved pack audio into ``CATALOGUE/<ROLE>/`` and renamed it with
:func:`review.proposed_name`, which appends the source token as ``..._<source>``.  The pack
identity therefore survives in the filename even though the path no longer shows it, and
935 orphaned ``.wav.asd`` sidecars in ``PACKS/`` mark where the audio used to sit.

Nothing here assumes today's zone names.  Origin is read from whichever evidence survives —
a surviving folder, or the filename token — and is then stored against the content hash, so
a resolved origin outlives any future reorganisation of the library.  Read-only for audio.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .review import ROLE_FOLDERS, normalise_token

# Recovered tokens are the *second* path component at move time (``review._source_token``),
# so they name a pack's sample sub-folder rather than the pack itself.  These map the
# observed tokens back onto a pack identity worth reading in search output.
ORIGIN_ALIASES: dict[str, str] = {
    "sa909_samples": "goldbaby-super-analog-909",
    "tapesh101_samples": "goldbaby-tape-sh101",
    "sp1200vol2_samples": "goldbaby-sp1200-vol2",
    "sp1200_samples": "goldbaby-sp1200",
    "sean": "sean-archive",
    "seanbackup": "sean-archive",
    "sean_backup": "sean-archive",
}

UNKNOWN = "unknown"

# Folder names that describe library structure rather than provenance.  Anything here is
# skipped when scanning a path for an origin, so the scan keeps working if zones are
# renamed, added or nested differently later.  Extend via ``structural=`` rather than
# editing call sites.
GENERIC_TOKENS: frozenset[str] = frozenset({
    "samples", "sample", "audio", "wav", "wavs", "aiff", "loops", "one-shots", "oneshots",
    "hits", "sounds", "files", "loose", "misc", "new", "old", "sorted", "unsorted",
})

STRUCTURAL_ZONES: frozenset[str] = frozenset({
    "packs", "catalogue", "curated", "presets", "midi", "_legacy", "_review",
    "_export", "_to-delete", "_quarantine", "00_inbox", "_packs", "drum-kits",
})

# A token seen this many times is treated as a real source folder rather than a parse
# accident, and becomes eligible for longest-suffix matching.
VOCABULARY_MIN_COUNT = 3

# Confidence ranks, highest first.  Used to keep a stored origin from being downgraded by a
# later scan that has less evidence to work with.
CONFIDENCE_RANK: dict[str, int] = {"exact": 3, "parsed": 2, "guessed": 1, "none": 0}

_BPM_FIELD_RE = re.compile(r"^\d{2,3}$")
_KEY_FIELD_RE = re.compile(r"^[a-g][sb]?m?$")
# `sort.py` appends a numeric suffix when a destination name is taken, so `sa909_samples-2`
# is the same source folder as `sa909_samples`.
_COLLISION_SUFFIX_RE = re.compile(r"-\d+$")


@dataclass(frozen=True)
class Origin:
    """A resolved origin plus how confident we are and how we got there."""

    origin: str
    confidence: str  # exact | parsed | guessed | none
    method: str
    token: str = ""

    def beats(self, other: "Origin | None") -> bool:
        """True if this resolution should replace ``other`` in the index."""
        if other is None or other.origin == UNKNOWN:
            return self.origin != UNKNOWN
        return CONFIDENCE_RANK[self.confidence] > CONFIDENCE_RANK[other.confidence]


def structural_names(extra: frozenset[str] | None = None) -> frozenset[str]:
    """Folder names that never identify a pack, in normalised form.

    Everything is passed through ``normalise_token`` so the set matches what the scan
    actually compares against — ``_LEGACY`` normalises to ``legacy``, not ``_legacy``.
    """
    names = GENERIC_TOKENS | STRUCTURAL_ZONES | frozenset(ROLE_FOLDERS) | (extra or frozenset())
    return frozenset(normalise_token(name) for name in names)


def is_generated_name(stem: str) -> bool:
    """True if this filename was written by :func:`review.proposed_name`.

    ``normalise_token`` lowercases everything it emits, so any uppercase means the file was
    moved but never renamed and its underscores belong to the vendor (``SineBass7_SP1200F``,
    ``AME_115_C_Lux_Bass``).  Parsing those yields invented provenance, so they are refused.
    """
    return stem == stem.lower()


def strip_collision_suffix(token: str) -> str:
    """Drop the numeric suffix `sort.py` adds when a destination name is already taken."""
    return _COLLISION_SUFFIX_RE.sub("", token)


def split_origin_token(stem: str) -> str:
    """Return the source token from a one-shot style ``{prefix}-{desc}_{source}`` stem.

    :func:`review._description` joins words with ``-`` only, so the first underscore is the
    boundary between the generated description and the source token.  The token itself may
    contain underscores (``sa909_samples``), which is why everything after it is kept.
    """
    if "_" not in stem or not is_generated_name(stem):
        return ""
    return stem.split("_", 1)[1]


def _looks_like_loop_name(stem: str) -> bool:
    """Loop names are ``{bpm}_{key}_{desc}_{source}``, so the first field is a bare tempo."""
    head = stem.split("_", 1)[0]
    return bool(_BPM_FIELD_RE.match(head) or _KEY_FIELD_RE.match(head))


def build_token_vocabulary(stems: list[str]) -> Counter[str]:
    """Count candidate source tokens across the library.

    Built from the unambiguous one-shot names only; loop names are resolved afterwards by
    matching against this vocabulary, since their extra ``{bpm}_{key}`` fields make the
    first-underscore rule unreliable.
    """
    counts: Counter[str] = Counter()
    for stem in stems:
        if _looks_like_loop_name(stem):
            continue
        token = split_origin_token(stem)
        if token:
            counts[token] += 1
    return counts


def canonical_origin(
    token: str,
    structural: frozenset[str] | None = None,
    strip_collision: bool = False,
) -> str:
    """Map a recovered token onto a stable, readable pack identity.

    ``strip_collision`` only applies to tokens read out of a filename, where `sort.py` may
    have appended ``-2``.  Folder names are never stripped: a pack legitimately called
    ``riemann-kollektion-riemann-tribal-techno-1`` must keep its trailing number.
    """
    if strip_collision:
        token = strip_collision_suffix(token)
    if not token:
        return UNKNOWN
    if token in ORIGIN_ALIASES:
        return ORIGIN_ALIASES[token]
    if token in (structural if structural is not None else structural_names()):
        return UNKNOWN
    return normalise_token(token).replace("_", "-")


def resolve_from_filename(
    stem: str,
    vocabulary: Counter[str] | None = None,
    structural: frozenset[str] | None = None,
) -> Origin:
    """Recover origin from a flattened filename, preferring a known source token."""
    if vocabulary and is_generated_name(stem):
        known = [
            token
            for token, count in vocabulary.items()
            if count >= VOCABULARY_MIN_COUNT and stem.endswith(f"_{token}")
        ]
        if known:
            # Longest wins: `sp1200vol2_samples` must beat a bare `samples`.
            token = max(known, key=len)
            origin = canonical_origin(token, structural, strip_collision=True)
            if origin != UNKNOWN:
                return Origin(origin, "parsed", "filename-token", token)

    token = split_origin_token(stem)
    origin = canonical_origin(token, structural, strip_collision=True)
    if origin == UNKNOWN:
        return Origin(UNKNOWN, "none", "generic-token" if token else "no-token-in-filename")
    return Origin(origin, "guessed", "filename-token-fallback", token)


def resolve_from_path(rel: Path, structural: frozenset[str] | None = None) -> Origin:
    """Take the shallowest surviving folder that names a pack rather than the structure.

    Component 0 is the top-level zone whatever it is called, so the scan starts at 1 and
    skips role folders and generic containers.  This keeps working if the library is
    reorganised, renamed or nested more deeply.
    """
    structural = structural if structural is not None else structural_names()
    for part in rel.parts[1:-1]:
        origin = canonical_origin(normalise_token(part), structural)
        if origin != UNKNOWN:
            return Origin(origin, "exact", "path-folder", part)
    return Origin(UNKNOWN, "none", "no-pack-folder-in-path")


def resolve_library(
    locations: list[tuple[str, Path]],
    structural: frozenset[str] | None = None,
) -> dict[str, Origin]:
    """Resolve origin for every ``(sample_id, path)``, keeping the best answer per sample.

    Because the key is the content hash, a sample that also sits somewhere with intact
    provenance inherits it: a flattened copy in a role folder gets the origin of its twin
    still living in a pack folder.  That is evidence, not a guess — the bytes are identical.
    """
    structural = structural if structural is not None else structural_names()
    vocabulary = build_token_vocabulary([path.stem for _, path in locations])

    best: dict[str, Origin] = {}
    for sample_id, path in locations:
        resolved = resolve_origin(path, vocabulary, structural)
        # Seed unconditionally so a sample that resolves nowhere is still reported as
        # unknown rather than dropping out of the result entirely.
        if sample_id not in best or resolved.beats(best[sample_id]):
            best[sample_id] = resolved
    return best


def resolve_origin(
    rel: Path,
    vocabulary: Counter[str] | None = None,
    structural: frozenset[str] | None = None,
) -> Origin:
    """Resolve one location's origin from whatever evidence survived.

    A surviving pack folder is the strongest evidence and wins; otherwise the filename token
    left behind by renaming is used.  The method behind each answer is always recorded, and
    nothing is guessed silently.
    """
    structural = structural if structural is not None else structural_names()
    from_path = resolve_from_path(rel, structural)
    if from_path.origin != UNKNOWN:
        return from_path
    return resolve_from_filename(rel.stem, vocabulary, structural)
