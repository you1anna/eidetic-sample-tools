"""Shared word boundaries and explicit musical aliases for names and rule evidence.

Only listed aliases join or expand words. There is no general substring fallback:
``rap`` stays separate from ``Trap`` and ``Vibraphone``. Letter/digit boundaries
keep model numbers intact, so ``TR8`` reads ``tr 8`` and ``TR808`` reads ``tr 808``.
"""

from __future__ import annotations

import re
from functools import lru_cache

_CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
_WORD_RE = re.compile(r"[a-z]+|[0-9]+")

# These are lexical equivalents, independent of a sample's inferred role. Plurals
# remain plural so the common optional-plural matcher keeps its existing meaning.
_WORD_ALIASES = {
    "hihat": "hi hat",
    "hihats": "hi hats",
    "ohat": "open hat",
    "ohats": "open hats",
    "percussion": "perc",
    "percussions": "percs",
}


def words_text(text: str) -> str:
    """Lowercase words with punctuation, camel-case and letter/digit boundaries.

    ``BigKick01_Hard`` reads ``big kick 01 hard``; ``SA909_BD`` reads ``sa 909 bd``.
    Explicit aliases make ``hihat`` / ``hi hat`` / ``hi-hat`` equivalent and let
    ``perc`` find ``Percussion`` even when the sound has another inferred role.
    """
    words = _WORD_RE.findall(_CAMEL_RE.sub(" ", text).lower())
    return " ".join(_WORD_ALIASES.get(word, word) for word in words)


@lru_cache(maxsize=1024)
def terms_pattern(terms: tuple[str, ...]) -> re.Pattern[str]:
    """Literal whole words/phrases, allowing a final plural, in ``words_text`` output.

    Punctuation normalizes to word boundaries. Wildcards and regular expressions
    have no special meaning; intentional compounds belong in the vocabulary.
    """
    alternatives = [re.escape(words) for term in terms if (words := words_text(term))]
    if not alternatives:
        return re.compile(r"(?!)")
    return re.compile(r"(?<!\S)(?:" + "|".join(alternatives) + r")(?:s|es)?(?!\S)")
