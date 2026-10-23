"""The grievance taxonomy: loading it, and failing loudly when it is wrong.

`app/taxonomy/grievance.yaml` holds the service's working vocabulary for five
languages. This module turns it into the tables the classifier uses and
validates it on the way, because the alternative is discovering a typo in a
Telugu word list during a citizen's interview.

WHAT IS VALIDATED, and why each check earns its place:

    every category has at least one term          an empty category can never
                                                  be answered and would look
                                                  like a classifier fault

    terms are in the script their key claims      a Malayalam word filed under
                                                  `te` is matched against
                                                  Telugu text and never fires;
                                                  nothing fails, it just
                                                  quietly does not work

    no term is blank or whitespace                "" is a substring of every
                                                  string, so one blank entry
                                                  makes its category match
                                                  everything

    no term appears in two categories             a word that means two things
                                                  is evidence for neither, and
                                                  silently tips every tie

    `roman` terms survive folding                 a term shorter than the
                                                  minimum after folding is
                                                  dropped by the matcher, so
                                                  listing it is a lie

A FAILURE HERE IS A STARTUP FAILURE. That is deliberate: a department that
edits this file gets told immediately, by the service refusing to start, rather
than by a month of petitions quietly classified UNKNOWN.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .languages import DEVANAGARI, MALAYALAM, SUPPORTED, TAMIL, TELUGU

TAXONOMY_PATH = Path(__file__).resolve().parent.parent / "taxonomy" / "grievance.yaml"

#: Which pattern a term under each language key must match. English has none:
#: it is Latin, and so is every romanised form.
_SCRIPT_OF = {"ta": TAMIL, "ml": MALAYALAM, "te": TELUGU, "hi": DEVANAGARI}

#: Term keys allowed inside `terms:`. `roman` is not a language — it is a way
#: of writing several of them on a Latin keyboard.
_TERM_KEYS = (*SUPPORTED, "roman")


class TaxonomyError(ValueError):
    """The taxonomy file is wrong, and the service should not start."""


@dataclass(frozen=True)
class Category:
    """One thing a citizen can be complaining about."""

    name: str
    labels: dict[str, str]
    #: Every term in every language, flattened, for substring/boundary matching.
    terms: tuple[str, ...]
    #: Romanised forms, matched by folding rather than by boundary.
    roman: tuple[str, ...]
    #: Terms grouped by the language key they were listed under.
    by_language: dict[str, tuple[str, ...]]
    #: A CANDIDATE department, never a fact. See the file's own warning.
    routing: dict[str, Any]

    def label(self, language: str) -> str:
        return self.labels.get(language) or self.labels.get("en") or self.name


@dataclass(frozen=True)
class Taxonomy:
    """The whole file, validated."""

    version: int
    categories: dict[str, Category]
    weak: frozenset[str]
    coordination: tuple[str, ...]
    #: Markers that split "that part is fine" from "this part is not".
    contrast: tuple[str, ...]
    satisfied: tuple[str, ...]
    #: Phrases that introduce a landmark or background rather than the subject.
    scenery: tuple[str, ...]
    scenery_window: int
    #: Markers that say something is wrong, used to tell "names nothing" from
    #: "names something outside the ten subjects".
    complaint_markers: tuple[str, ...]
    complaint_min_words: int
    strong_weight: int
    weak_weight: int
    confidence_base: float
    confidence_per_point: float
    confidence_ceiling: float
    confidence_floor: float
    #: How much to trust each kind of UNKNOWN. See the file for why these are
    #: not zero.
    unknown_confidence: dict[str, float]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self.categories)

    def words(self) -> dict[str, tuple[str, ...]]:
        """The shape `system_one` has always used: category -> every term.

        Romanised forms are unioned in, because the live tables carried them in
        both places and the matcher de-duplicates: a word found by both rules
        is counted once.
        """
        return {
            name: tuple(dict.fromkeys(category.terms + category.roman))
            for name, category in self.categories.items()
        }

    def romanised(self) -> dict[str, tuple[str, ...]]:
        return {name: c.roman for name, c in self.categories.items()}


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TaxonomyError(f"{TAXONOMY_PATH.name}: {message}")


def _terms_of(name: str, block: Any) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    """Read and check one category's `terms:` block."""
    _require(isinstance(block, dict), f"{name}: `terms` must be a mapping")

    unknown = set(block) - set(_TERM_KEYS)
    _require(not unknown,
             f"{name}: unknown term group(s) {sorted(unknown)}; "
             f"allowed: {list(_TERM_KEYS)}")

    by_language: dict[str, tuple[str, ...]] = {}
    for key, values in block.items():
        _require(isinstance(values, list) and values,
                 f"{name}.{key}: must be a non-empty list")
        cleaned: list[str] = []
        for value in values:
            _require(isinstance(value, str),
                     f"{name}.{key}: {value!r} is not a string")
            # Not stripped: a trailing space is load-bearing in this table.
            # "eb " matches the utility and not the verb "ebb", and silently
            # trimming it would turn a precise term into a wrong one.
            _require(value.strip() != "",
                     f"{name}.{key}: blank term — a blank matches every text")
            pattern = _SCRIPT_OF.get(key)
            if pattern is not None:
                _require(bool(pattern.search(value)),
                         f"{name}.{key}: {value!r} is not written in the "
                         f"{key} script; a term filed under the wrong "
                         f"language never matches anything")
            cleaned.append(value)
        by_language[key] = tuple(cleaned)

    roman = by_language.get("roman", ())

    # A ROMANISED FORM SPELLED EXACTLY LIKE THE ENGLISH TERM IS A TRAP, and
    # this one cost a real regression. Romanised forms are matched on FOLDED
    # text with the spaces removed, so the match is a substring with no word
    # boundary. "ration" listed under `roman` is found inside "corporation",
    # and "the corporation has not lifted the rubbish" — a sanitation
    # complaint, and half the petitions in this state name a corporation —
    # tied with a welfare scheme and came out UNKNOWN.
    #
    # The English list already matches that word, with a word boundary, which
    # is the rule that is correct for it. Listing it twice adds nothing except
    # the false positive.
    english = {term.casefold() for term in by_language.get("en", ())}
    for term in roman:
        _require(term.casefold() not in english,
                 f"{name}.roman: {term!r} is spelled exactly like the English "
                 f"term and is already matched by it with a word boundary. "
                 f"Romanised terms are matched as substrings of folded text, "
                 f"so this one would also be found inside longer words.")

    return by_language, roman


def _load(path: Path) -> Taxonomy:
    _require(path.exists(), "file is missing")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    _require(isinstance(raw, dict), "top level must be a mapping")

    weights = raw.get("weights") or {}
    confidence = raw.get("confidence") or {}
    blocks = raw.get("categories")
    _require(isinstance(blocks, dict) and blocks, "`categories` is missing or empty")

    categories: dict[str, Category] = {}
    seen_terms: dict[str, str] = {}

    for name, block in blocks.items():
        _require(isinstance(block, dict), f"{name}: must be a mapping")
        by_language, roman = _terms_of(name, block.get("terms"))

        flat: list[str] = []
        for key, values in by_language.items():
            if key == "roman":
                continue
            flat.extend(values)
        _require(bool(flat) or bool(roman),
                 f"{name}: has no terms at all and could never be answered")

        for term in (*flat, *roman):
            folded = term.casefold()
            owner = seen_terms.get(folded)
            _require(owner is None or owner == name,
                     f"{term!r} is listed under both {owner} and {name}; "
                     f"a term that means two things is evidence for neither")
            seen_terms[folded] = name

        labels = block.get("label") or {}
        _require(isinstance(labels, dict), f"{name}: `label` must be a mapping")

        categories[name] = Category(
            name=name,
            labels={str(k): str(v) for k, v in labels.items()},
            terms=tuple(flat),
            roman=tuple(roman),
            by_language=by_language,
            routing=dict(block.get("routing") or {}),
        )

    weak = raw.get("weak") or []
    _require(isinstance(weak, list), "`weak` must be a list")
    coordination = raw.get("coordination") or []
    _require(isinstance(coordination, list) and coordination,
             "`coordination` must be a non-empty list")

    contrast = raw.get("contrast") or []
    satisfied = raw.get("satisfied") or []
    _require(isinstance(contrast, list), "`contrast` must be a list")
    _require(isinstance(satisfied, list), "`satisfied` must be a list")

    return Taxonomy(
        version=int(raw.get("version") or 1),
        categories=categories,
        weak=frozenset(str(w) for w in weak),
        coordination=tuple(str(c) for c in coordination),
        contrast=tuple(str(c) for c in contrast),
        satisfied=tuple(str(c) for c in satisfied),
        scenery=tuple(str(c) for c in (raw.get("scenery") or [])),
        scenery_window=int(raw.get("scenery_window") or 32),
        complaint_markers=tuple(
            str(c) for c in (raw.get("complaint_markers") or [])),
        complaint_min_words=int(raw.get("complaint_min_words") or 8),
        strong_weight=int(weights.get("strong", 2)),
        weak_weight=int(weights.get("weak", 1)),
        confidence_base=float(confidence.get("base", 0.55)),
        confidence_per_point=float(confidence.get("per_point", 0.08)),
        confidence_ceiling=float(confidence.get("ceiling", 0.95)),
        confidence_floor=float(confidence.get("floor", 0.0)),
        unknown_confidence={
            key: float(confidence.get(f"unknown_{key}", default))
            for key, default in (("nothing_said", 0.85), ("no_terms", 0.80),
                                 ("coordinated", 0.70), ("tied", 0.60))
        },
    )


@lru_cache(maxsize=1)
def taxonomy() -> Taxonomy:
    """The loaded taxonomy. Cached; call `reload()` after editing the file."""
    return _load(TAXONOMY_PATH)


def reload() -> Taxonomy:
    taxonomy.cache_clear()
    return taxonomy()
