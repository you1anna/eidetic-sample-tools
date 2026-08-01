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
from pathlib import Path

from .review import classify_role

DEFAULT_VOCABULARY = Path(__file__).resolve().parents[2] / "vocabulary.toml"

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


@dataclass(frozen=True)
class Rule:
    name: str
    group: str
    origins: tuple[str, ...] = ()
    origin_matches: tuple[str, ...] = ()
    name_matches: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    features: tuple[tuple[str, str, float], ...] = ()

    @property
    def has_selectors(self) -> bool:
        return bool(self.origins or self.origin_matches or self.name_matches)

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
        if any(needle in sample.origin for needle in self.origin_matches):
            return True
        return any(needle in sample.text for needle in self.name_matches)


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


def load_vocabulary(path: Path | None = None) -> list[Rule]:
    """Read and validate the rule file."""
    path = path or DEFAULT_VOCABULARY
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError as exc:
        raise VocabularyError(f"vocabulary not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise VocabularyError(f"invalid TOML in {path}: {exc}") from exc

    if data.get("schema_version") != 1:
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
        rules.append(
            Rule(
                name=name,
                group=group,
                origins=_lower_tuple(entry.get("origins")),
                origin_matches=_lower_tuple(entry.get("origin_matches")),
                name_matches=_lower_tuple(entry.get("name_matches")),
                roles=tuple(str(role) for role in entry.get("roles", ())),
                features=_parse_features(entry.get("features"), name),
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
