"""Where the emblem goes, read from what the citizen said.

Layout is not wording. "Move the logo to the right" has exactly one correct
outcome, and a model that is 95% reliable at it is 5% unreliable at something
nobody should have to check. So this is a table of words and a small amount of
arithmetic, in both languages, with no network call and no guessing: an
instruction either resolves to a placement or it does not, and one that does
not is left alone for the wording path to consider.

The placement lives on the session, so it survives every later regeneration —
a citizen who moved the emblem and then asked for the subject to be reworded
does not get the emblem moved back.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Align = Literal["left", "center", "right"]
Pages = Literal["all", "first", "none"]

# No emblem by default.
#
# A petition is a citizen's document, not the department's. Printing the state
# emblem on it by default makes a private representation look like something
# issued by the office it is addressed to, and that is the wrong impression to
# give an officer opening it — before anything is said about who may use the
# emblem and when.
#
# So it is off, and it goes on only when someone asks: a citizen saying "put the
# logo at the top", or a department setting LETTER_EMBLEM_PAGES for its own
# deployment. `DEFAULT_ALIGN` is where it lands when they do.
DEFAULT_ALIGN: Align = "center"
DEFAULT_PAGES: Pages = "none"


@dataclass(frozen=True)
class Placement:
    align: Align = DEFAULT_ALIGN
    pages: Pages = DEFAULT_PAGES

    def as_dict(self) -> dict[str, str]:
        return {"align": self.align, "pages": self.pages}

    @classmethod
    def from_state(cls, value: object, fallback: Placement | None = None) -> Placement:
        """Read a stored placement, falling back for anything unrecognised.

        A session written by an older build, or a hand-edited checkpoint, must
        still render. `fallback` is what a deployment configured; without one
        it is the module default, which is no emblem.
        """
        base = fallback or cls()
        if not isinstance(value, dict):
            return base
        align = value.get("align")
        pages = value.get("pages")
        return cls(
            align=align if align in ("left", "center", "right") else base.align,
            pages=pages if pages in ("all", "first", "none") else base.pages,
        )


def placement_for(stored: object, settings: object = None) -> Placement:
    """What this petition's emblem placement actually is.

    Precedence: what the citizen asked for on this session, then what the
    deployment configured, then nothing.

    `settings` is read by attribute rather than imported, so this module stays
    free of the configuration layer — everything else in `domain/` is pure and
    this is the one place that needs to know a deployment has an opinion.
    """
    fallback = Placement()
    if settings is not None:
        align = getattr(settings, "letter_emblem_align", DEFAULT_ALIGN)
        pages = getattr(settings, "letter_emblem_pages", DEFAULT_PAGES)
        fallback = Placement(
            align=align if align in ("left", "center", "right") else DEFAULT_ALIGN,
            pages=pages if pages in ("all", "first", "none") else DEFAULT_PAGES,
        )
    return Placement.from_state(stored, fallback)


# The thing being talked about. An instruction has to name it, or "move it to
# the right" would move the emblem when the citizen meant a line of the letter.
_SUBJECT = re.compile(
    r"\b(logo|emblem|seal|crest|symbol|image|picture)\b"
    r"|சின்னம்|சின்னத்தை|சின்னத்தின்|இலச்சினை|இலச்சினையை|லோகோ|லோகோவை|முத்திரை|முத்திரையை",
    re.I,
)

_REMOVE = re.compile(
    r"\b(remove|delete|drop|take (?:it |the \w+ )?off|without|no|hide"
    # "I don't want the logo shown" is a removal, but it reaches the word
    # "want" - which is how someone asks FOR the emblem. Spelled out here so
    # the negation is matched, because `_REMOVE` is tested before `_ADD` and
    # this is the only place the two can be told apart.
    r"|do\s*n'?o?t\s+(?:want|need|show|print|include|add|put|keep|like))\b"
    r"|நீக்கு|நீக்கவும்|வேண்டாம்|அகற்று|அகற்றவும்|மறை",
    re.I,
)

# Asking for it back. Needed because the emblem is off by default: without this
# the only way to turn it on would be to name a side or say "all pages", and
# "add the logo at the top" - the obvious way to ask - would do nothing.
_ADD = re.compile(
    r"\b(add|put|place|insert|show|include|print|display|want|need|with)\b"
    r"|சேர்|சேர்க்க|வை|வைக்க|போடு|போட|வேண்டும்|காட்டு",
    re.I,
)

_ALIGN_WORDS: tuple[tuple[re.Pattern[str], Align], ...] = (
    (re.compile(r"\b(left)\b|இடது|இடதுபுறம்|இடப்புறம்", re.I), "left"),
    (re.compile(r"\b(right)\b|வலது|வலதுபுறம்|வலப்புறம்", re.I), "right"),
    (re.compile(r"\b(cent(?:re|er)|middle|centred|centered)\b|நடு|நடுவில்|மையம்|மையத்தில்",
                re.I), "center"),
)

# "every page", "all pages", "எல்லா பக்கங்களிலும்"
_ALL_PAGES = re.compile(
    r"\b(all|every|each)\s+pages?\b|\bon\s+all\b"
    r"|எல்லா\s*பக்க|அனைத்து\s*பக்க|ஒவ்வொரு\s*பக்க",
    re.I,
)
# A Tamil word ending, spelled out rather than written `\w*`.
#
# `\w` does not match a Tamil combining mark: the virama in "பக்கம்" is
# category Mn and `str.isalnum()` is False for it, so `பக்க\w*` stops one
# character short of the end of the word and the rest of the pattern never
# lines up. "சின்னம் முதல் பக்கம் மட்டும்" matched nothing at all because of
# it. `[^\s]*` takes the whole word whatever it is made of.
_END = r"[^\s]*"

# "first page only", "only the first page", "முதல் பக்கம் மட்டும்"
_FIRST_ONLY = re.compile(
    r"\b(?:only|just)\b[^.]{0,20}\bfirst\s+page\b"
    r"|\bfirst\s+page\b[^.]{0,12}\b(?:only|alone)\b"
    r"|முதல்\s*பக்க" + _END + r"\s*மட்டும்",
    re.I,
)
# "not on the second page", "remove it from page 2", "இரண்டாம் பக்கத்தில் வேண்டாம்"
_NOT_LATER_PAGES = re.compile(
    r"\b(?:not|no|remove|without|omit)\b[^.]{0,28}"
    r"\b(?:second|2nd|other|later|remaining|subsequent|next)\s+pages?\b"
    r"|\bpage\s*2\b[^.]{0,16}\b(?:not|no|remove|without)\b"
    r"|\b(?:not|no|remove|without)\b[^.]{0,16}\bpage\s*2\b"
    r"|(?:இரண்டாம்|2வது|மற்ற|அடுத்த)\s*பக்க" + _END +
    r"\s*(?:வேண்டாம்|இல்லை|நீக்கு|நீக்கவும்|அகற்று)",
    re.I,
)


def read_instruction(text: str, current: Placement | None = None) -> Placement | None:
    """A new placement, or None when this was not about the emblem.

    Returning None is the important half. Most of what a citizen says after
    reading their petition is about the words, and a layout parser that
    answered "maybe" to those would quietly move the emblem every time somebody
    asked for a firmer closing paragraph.
    """
    said = str(text or "").strip()
    if not said or not _SUBJECT.search(said):
        return None

    now = current or Placement()
    align: Align = now.align
    pages: Pages = now.pages
    changed = False

    # Order matters: "not on the second page" contains "not", which would
    # otherwise read as a removal of the emblem altogether.
    if _FIRST_ONLY.search(said) or _NOT_LATER_PAGES.search(said):
        pages, changed = "first", True
    elif _ALL_PAGES.search(said):
        pages, changed = "all", True
    elif _REMOVE.search(said):
        pages, changed = "none", True
    elif _ADD.search(said):
        # "add the logo", with no side and no page named. Checked after removal
        # so that "I don't want the emblem shown" reads as the removal it is.
        pages, changed = "all", True

    for pattern, value in _ALIGN_WORDS:
        if pattern.search(said):
            align, changed = value, True
            break

    if not changed:
        return None
    # Asking for it somewhere specific is asking for it to be there at all.
    if pages == "none" and align != now.align:
        pages = now.pages if now.pages != "none" else "all"
    return Placement(align=align, pages=pages)


def describe(placement: Placement, language: str = "en") -> str:
    """What was done, in a sentence, so the citizen can see it took effect."""
    if language == "ta":
        if placement.pages == "none":
            return "மனுவிலிருந்து சின்னம் நீக்கப்பட்டது."
        where = {"left": "இடதுபுறம்", "center": "நடுவில்", "right": "வலதுபுறம்"}[placement.align]
        pages = ("முதல் பக்கத்தில் மட்டும்" if placement.pages == "first"
                 else "எல்லா பக்கங்களிலும்")
        return f"சின்னம் {pages} மேலே {where} வைக்கப்பட்டது."
    if placement.pages == "none":
        return "I have removed the emblem from the petition."
    where = {"left": "on the left", "center": "in the centre", "right": "on the right"}[
        placement.align]
    pages = "on the first page only" if placement.pages == "first" else "on every page"
    return f"I have put the emblem {where} at the top, {pages}."
