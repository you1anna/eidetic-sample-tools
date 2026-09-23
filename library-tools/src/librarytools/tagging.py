"""Tag rules: a tag is a named saved predicate over evidence, not a per-file sticker.

Rules live in ``vocabulary.toml`` and are evaluated against three kinds of evidence — the
recovered origin, the path text, and measured acoustics.  Correcting a wrong tag means
editing one rule and regenerating, never re-labelling files, which is what makes "derive,
then correct" survive a library this size.

Read-only for audio: this module writes tags to the index and nothing else.
"""

from __future__ import annotations

import re
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from .lexical import terms_pattern, words_text
from .review import classify_role

DEFAULT_VOCABULARY = Path(__file__).resolve().parents[2] / "vocabulary.toml"
if not DEFAULT_VOCABULARY.is_file():
    DEFAULT_VOCABULARY = Path(__file__).parent / 'resources' / 'vocabulary.toml'

_COMPARISON_RE = re.compile(r"^(>=|<=|>|<|==)\s*(-?\d+(?:\.\d+)?)$")


class VocabularyError(ValueError):
    pass


@dataclass(frozen=True)
class Sample:
    """The evidence one sample offers a rule."""

    sample_id: str
    path: Path
    origin: str = ""
    role: str = ""
    features: dict[str, float | None] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.path.as_posix().lower()

    @cached_property
    def text_words(self) -> str:
        return words_text(self.path.as_posix())

    @cached_property
    def origin_words(self) -> str:
        return words_text(self.origin)


@dataclass(frozen=True)
class Rule:
    """A schema-2 lexical rule, or an explicitly loaded legacy schema-1 rule."""

    name: str
    group: str
    origins: tuple[str, ...] = ()
    origin_matches: tuple[str, ...] = ()
    name_matches: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    features: tuple[tuple[str, str, float], ...] = ()
    name_suffixes: tuple[str, ...] = ()
    schema_version: int = 2

    @property
    def has_selectors(self) -> bool:
        return bool(self.origins or self.origin_matches or self.name_matches or self.name_suffixes)

    def matches(self, sample: Sample) -> bool:
        """Constraints must all hold; at least one selector must fire if any are given."""
        if self.roles and sample.role not in self.roles:
            return False
        for column, op, threshold in self.features:
            value = sample.features.get(column)
            if value is None or not _compare(value, op, threshold):
                return False
        if not self.has_selectors:
            # A rule with only constraints (a pure acoustic rule) fires on those alone.
            return bool(self.features)
        if sample.origin and sample.origin in self.origins:
            return True
        if self.schema_version == 1:
            # Existing custom files keep their declared substring semantics. They
            # opt into lexical matching only by explicitly selecting schema 2.
            return any(needle in sample.origin for needle in self.origin_matches) or any(
                needle in sample.text for needle in self.name_matches
            )
        if self.origin_matches and terms_pattern(self.origin_matches).search(sample.origin_words):
            return True
        if self.name_matches and terms_pattern(self.name_matches).search(sample.text_words):
            return True
        # Literal final stem tokens: `_x.wav` and `_x2.wav`, never a directory,
        # `x20` or `x2extra`. Keep this separate from word/digit normalization.
        stem = sample.path.stem.lower()
        return any(stem.endswith(separator + suffix)
                   for suffix in self.name_suffixes for separator in ("_", "-", " "))


def _compare(value: float, op: str, threshold: float) -> bool:
    if op == ">=":
        return value >= threshold
    if op == "<=":
        return value <= threshold
    if op == ">":
        return value > threshold
    if op == "<":
        return value < threshold
    return value == threshold


def _parse_features(raw: object, tag_name: str) -> tuple[tuple[str, str, float], ...]:
    if not raw:
        return ()
    if not isinstance(raw, dict):
        raise VocabularyError(f"tag {tag_name!r}: features must be a table")
    parsed: list[tuple[str, str, float]] = []
    for column, expression in raw.items():
        match = _COMPARISON_RE.match(str(expression).strip())
        if not match:
            raise VocabularyError(
                f"tag {tag_name!r}: cannot read feature test {column}={expression!r}; "
                'expected something like ">=0.60"'
            )
        parsed.append((str(column), match.group(1), float(match.group(2))))
    return tuple(parsed)


def _lower_tuple(raw: object) -> tuple[str, ...]:
    return tuple(str(item).lower() for item in (raw or ()))


def load_vocabulary(path: Path | None = None, *, payload: bytes | None = None) -> list[Rule]:
    """Read schema 2 word rules or schema 1 legacy substring rules.

    Schema 1 remains supported without changing custom predicates. Schema 2 uses
    the shared musical aliases and adds literal final-stem ``name_suffixes``.
    """
    path = path or DEFAULT_VOCABULARY
    try:
        data = tomllib.loads((payload if payload is not None else path.read_bytes()).decode('utf-8'))
    except FileNotFoundError as exc:
        raise VocabularyError(f"vocabulary not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise VocabularyError(f"invalid TOML in {path}: {exc}") from exc

    schema_version = data.get("schema_version")
    if schema_version not in (1, 2):
        raise VocabularyError(f"unsupported vocabulary schema in {path}")

    rules: list[Rule] = []
    seen: set[tuple[str, str]] = set()
    for entry in data.get("tag", []):
        name = str(entry.get("name", "")).strip().lower()
        group = str(entry.get("group", "")).strip().lower()
        if not name or not group:
            raise VocabularyError(f"every tag needs a name and a group; got {entry!r}")
        if (group, name) in seen:
            raise VocabularyError(f"duplicate tag {group}/{name}")
        seen.add((group, name))
        raw_suffixes = entry.get("name_suffixes", [])
        if not isinstance(raw_suffixes, list) or any(not isinstance(value, str) for value in raw_suffixes):
            raise VocabularyError(f"tag {name!r}: name_suffixes must be an array of strings")
        suffixes = _lower_tuple(raw_suffixes)
        if suffixes and (schema_version != 2 or any(
                not re.fullmatch(r"[a-z][a-z0-9]*", suffix) for suffix in suffixes)):
            raise VocabularyError(
                f"tag {name!r}: name_suffixes requires schema 2 and literal letter/digit tokens"
            )
        rules.append(
            Rule(
                name=name,
                group=group,
                origins=_lower_tuple(entry.get("origins")),
                origin_matches=_lower_tuple(entry.get("origin_matches")),
                name_matches=_lower_tuple(entry.get("name_matches")),
                roles=tuple(str(role) for role in entry.get("roles", ())),
                features=_parse_features(entry.get("features"), name),
                name_suffixes=suffixes,
                schema_version=schema_version,
            )
        )
    return rules


def build_sample(
    sample_id: str,
    rel: Path,
    origin: str = "",
    features: dict[str, float | None] | None = None,
) -> Sample:
    """Assemble one sample's evidence.

    Role comes from :func:`review.classify_role` rather than from the folder it happens to
    sit in, so tagging keeps working if the library is restructured.
    """
    return Sample(
        sample_id=sample_id,
        path=rel,
        origin=origin.lower(),
        role=classify_role(rel).role,
        features=features or {},
    )


def tags_for(sample: Sample, rules: list[Rule]) -> list[tuple[str, str]]:
    """Return ``(group, tag)`` pairs for one sample, including its origin."""
    tags = [(rule.group, rule.name) for rule in rules if rule.matches(sample)]
    if sample.origin and sample.origin != "unknown":
        tags.append(("origin", sample.origin))
    if sample.role:
        tags.append(("role", sample.role))
    return tags


def count_rules(
    samples: list[Sample], rules: list[Rule], examples: int = 3,
) -> dict[tuple[str, str], tuple[int, list[str]]]:
    """Count what each rule would tag, with examples — the evidence for a proposal review."""
    counts: Counter[tuple[str, str]] = Counter()
    shown: dict[tuple[str, str], list[str]] = {}
    for sample in samples:
        for rule in rules:
            if rule.matches(sample):
                key = (rule.group, rule.name)
                counts[key] += 1
                if len(shown.setdefault(key, [])) < examples:
                    shown[key].append(sample.path.as_posix())
    return {
        (group, name): (counts.get((group, name), 0), shown.get((group, name), []))
        for group, name in ((rule.group, rule.name) for rule in rules)
    }
