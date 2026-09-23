"""Editing a dictated grievance by voice, without a model anywhere near it.

A citizen finishes a two-minute complaint, hears it read back, and says
"change five days to three days". Before this module existed the sentence
went through `answer_intent.read`, which found content in it and returned
REPLACE — so the entire grievance was thrown away and replaced by the six
words of the edit instruction. The petition that reached the officer said
"Change five days to three days." and nothing else.

WHY THERE IS NO MODEL HERE. The instruction was "do not invent edits; only
apply exactly what the citizen requests", and that is not a prompt, it is a
property. An LLM handed a paragraph and "change five days to three days"
returns a paragraph — usually the right one, sometimes tidied, occasionally
reworded, and there is no way to tell which from the outside. A complaint is
evidence. So every edit here is a literal operation on the citizen's own
characters:

    substitute   find these exact words, put those exact words there
    remove       find these exact words, or the last sentence, and drop them
    append       put these exact words on the end

Nothing is rephrased, nothing is summarised, and an instruction that does not
resolve to one of those three is REFUSED with a question rather than guessed
at. `apply` cannot return text containing a word the citizen did not say,
which is the one guarantee worth having.

THE FOUR REFUSALS, each of which asks instead of acting:

    no_target    "change that"          — which part?
    not_found    the words are not in the grievance
    only_one     "remove the last sentence" when there is only one
    would_empty  the edit would delete the whole complaint

WHAT THIS IS NOT FOR. Ordinary continuations — "also, the drain is blocked",
"I have one more thing" — are not edits and must not come here; they reopen
the microphone. See `answer_intent.continuation`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .spoken_numbers import spoken_cardinal

Language = Literal["en", "ta"]
Action = Literal["substitute", "remove", "remove_last", "append", "unclear"]


@dataclass(frozen=True)
class EditRequest:
    """What the citizen asked for, as parsed. Nothing has been applied yet."""

    action: Action
    target: str = ""
    replacement: str = ""
    # Set only when `action` is "unclear": which question to ask back.
    problem: str = ""


@dataclass(frozen=True)
class EditResult:
    """What applying it did, or why it was refused."""

    ok: bool
    text: str = ""
    problem: str = ""
    # For the sentence read back afterwards: the words that changed.
    target: str = ""
    replacement: str = ""


# --------------------------------------------------------------------------- #
# Reading the instruction
# --------------------------------------------------------------------------- #
#
# Matched against the whole utterance and anchored at the start, because an
# edit instruction is the whole of what the citizen says. A grievance that
# happens to contain "change the water supply to the street" is dictated
# content and arrives on a different path entirely — this only ever runs while
# a captured grievance is sitting on the table awaiting confirmation.

_LEAD = (r"(?:please\s+|can\s+you\s+|could\s+you\s+|i\s+want\s+to\s+"
         r"|i\s+want\s+you\s+to\s+|just\s+|also\s+|and\s+also\s+|and\s+"
         r"|actually\s+|sorry\s+|no\s+|oh\s+)*")
_TAIL = r"(?:\s+please|\s+instead|\s+in\s+the\s+grievance|\s+in\s+my\s+grievance)*[.!?]*$"

_SUBSTITUTE_EN = (
    re.compile(_LEAD + r"(?:change|correct|update)\s+(?P<a>.+?)\s+(?:to|into)\s+(?P<b>.+?)" + _TAIL, re.I),
    re.compile(_LEAD + r"replace\s+(?P<a>.+?)\s+(?:with|by)\s+(?P<b>.+?)" + _TAIL, re.I),
    re.compile(_LEAD + r"(?:say|put|write)\s+(?P<b>.+?)\s+instead\s+of\s+(?P<a>.+?)" + _TAIL, re.I),
    re.compile(_LEAD + r"instead\s+of\s+(?P<a>.+?)\s+(?:say|put|write|make\s+it)\s+(?P<b>.+?)" + _TAIL, re.I),
    re.compile(_LEAD + r"(?P<a>.+?)\s+should\s+(?:be|say)\s+(?P<b>.+?)" + _TAIL, re.I),
)

# "remove the last sentence". Deliberately its own pattern: "the last
# sentence" is a position, not a phrase to search for, and searching for the
# literal words "the last sentence" inside a complaint finds nothing.
_REMOVE_LAST_EN = re.compile(
    _LEAD + r"(?:remove|delete|drop|take\s+out|take\s+off|cut)\s+(?:the\s+)?last\s+"
    r"(?:sentence|line|part|bit|one)" + _TAIL, re.I)

_REMOVE_EN = re.compile(
    _LEAD + r"(?:remove|delete|drop|take\s+out|take\s+off)\s+(?:the\s+(?:words?|part|phrase|line)\s+)?"
    r"(?P<a>.+?)" + _TAIL, re.I)

_APPEND_EN = (
    re.compile(_LEAD + r"(?:add|append|include)\s+(?:a\s+)?(?:line|sentence|point|note)\s+"
               r"(?:saying|that\s+says|which\s+says)\s+(?P<b>.+?)" + _TAIL, re.I),
    re.compile(_LEAD + r"(?:add|append|include|mention|note)\s+(?:that|this|the\s+fact\s+that)\s+(?P<b>.+?)" + _TAIL, re.I),
    re.compile(_LEAD + r"(?:add|append|include)\s+(?P<b>.+?)\s+(?:to|at)\s+the\s+end" + _TAIL, re.I),
    re.compile(_LEAD + r"(?:add|append)\s+(?P<b>.+?)" + _TAIL, re.I),
)

# Instructions that name an operation and no operand. These are the ones the
# brief singles out: "Change that." must produce "Which part would you like
# to change?", never a guess.
_VAGUE_EN = re.compile(
    _LEAD + r"(?:change|correct|fix|update|replace|remove|delete|edit|redo)\s+"
    r"(?:that|this|it|the\s+(?:thing|part|bit|words?))?" + _TAIL, re.I)


# Tamil. Written around the quotative என்று / என்பதை rather than around word
# order, because that is what actually marks the operand in spoken Tamil and
# it survives the word order moving about:
#
#   ஐந்து நாட்கள் என்பதை மூன்று நாட்கள் என்று மாற்றவும்
#   [  target  ]        [ replacement ]        change
#
# The stems are stems on purpose (மாற்ற, நீக்க, சேர்க்க): Tamil inflects by
# suffix and the citizen may say மாற்றவும், மாற்றுங்கள் or மாற்ற வேண்டும்.
_CHANGE_TA = "மாற்ற"
_REMOVE_TA = ("நீக்க", "எடுத்துவிட")
_ADD_TA = "சேர்க்க"

# Anchored at the start and matched with `search`, not `fullmatch`: the verb
# carries a suffix the citizen chooses — மாற்றவும், மாற்றுங்கள், மாற்ற
# வேண்டும் — and pinning the end of the string means pinning a suffix
# table. The START is what has to be exact, because that is where the
# citizen's own words are.
#
# The case markers are listed LONGEST FIRST. Alternation takes the first
# branch that matches, and "ஐ" is a letter as well as a marker: ordering
# என்பதை before it keeps "ஐந்து நாட்கள் என்பதை" whole.
# ONLY THE QUOTATIVE என்பதை MARKS THE TARGET. The bare accusative was
# listed here as "ஐ" and was pure liability, for two reasons found by
# probing it:
#
#   It never matched an accusative. Written Tamil forms the accusative with
#   the vowel SIGN ை (U+0BC8) on the end of a word — "நாட்களை" — not with
#   the independent letter ஐ (U+0B90), which only ever begins a word.
#
#   And it matched something else. Tamil is searched without word
#   boundaries, and ஐ opens "ஐந்து", the word for five. So
#   "மேலும் ஐந்து நாட்கள் என்பதை மூன்று நாட்கள் என்று மாற்றவும்" parsed with
#   the marker landing INSIDE "ஐந்து": target "மேலும்", replacement
#   "ந்து நாட்கள் என்பதை மூன்று நாட்கள்" — a word cut in half.
#
# Adding ை instead would be worse: it ends ordinary Tamil words by the
# dozen and would claim a marker in the middle of any sentence. A citizen
# who says the bare-accusative form is asked WHICH PART, which is this
# module's answer to everything it cannot read exactly.
_MARKER_TA = r"(?:என்பதற்கு|என்பதை)"

# Discourse particles that can open a spoken instruction and are no part of
# the words being changed. Trimmed from the FRONT of the captured target
# only — the same treatment `answer_intent._as_answer` gives an English
# lead-in, and for the same reason: "மேலும் ஐந்து நாட்கள்" is the citizen
# saying "and also, five days", and "மேலும்" is not in their complaint.
_LEAD_TA = ("மேலும்", "இன்னும்", "அப்புறம்", "பிறகு", "அப்பறம்",
            "சரி", "சரிதான்", "பின்", "அது", "இது", "அந்த", "இந்த")


def _trim_lead_ta(text: str) -> str:
    """Drop leading particles, never anything else."""
    words = text.split()
    while words and words[0] in _LEAD_TA:
        words = words[1:]
    return " ".join(words) if words else text
_QUOTE_TA = r"(?:என்று|என|ஆக)"

_SUBSTITUTE_TA = re.compile(
    r"^(?P<a>.+?)\s*" + _MARKER_TA + r"\s*(?P<b>.+?)\s*" + _QUOTE_TA + r"\s*" + _CHANGE_TA)
_REMOVE_LAST_TA = re.compile(
    r"^\s*கடைசி\s*(?:வரி|வாக்கிய|பகுதி)\S*\s*(?:\S+\s+)?(?:" + "|".join(_REMOVE_TA) + ")")
_REMOVE_TA_RE = re.compile(
    r"^(?P<a>.+?)\s*" + _MARKER_TA + r"\s*(?:\S+\s+)?(?:" + "|".join(_REMOVE_TA) + ")")
_APPEND_TA = re.compile(
    r"^(?P<b>.+?)\s*" + _QUOTE_TA + r"\s*(?:\S+\s+)?" + _ADD_TA)

# "அதை மாற்றவும்" — change that. The vague case, in Tamil.
_VAGUE_TA = re.compile(
    r"^(?:அதை|இதை|அது|இது|அந்த|இந்த)?\s*(?:" + _CHANGE_TA + r"|திருத்த)\S*\s*\S*$")

_STRIP = " \t\n\r,.;:!?—–-\"'‘’“”"


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(_STRIP)


def read_edit(text: str, language: Language = "en") -> EditRequest | None:
    """Parse one spoken instruction, or return None if it is not an edit.

    None means "this is not an edit" and the caller falls through to the
    ordinary confirm / retry / continue reading. It is the common answer:
    "yes", "that's wrong", "also the drain is blocked" all return None.
    """
    spoken = _clean(text)
    if not spoken:
        return None

    # Tamil first when the session is Tamil, but BOTH are always tried: a
    # citizen in a Tamil session saying "change five days to three days" is
    # ordinary here, and so is the reverse.
    order = (_read_tamil, _read_english) if language == "ta" else (_read_english, _read_tamil)
    for reader in order:
        found = reader(spoken)
        if found is not None:
            return found
    return None


def _read_english(spoken: str) -> EditRequest | None:
    # The vague forms are tested BEFORE the operand patterns. "change that"
    # matches `_REMOVE_EN`-shaped greed otherwise and would send the word
    # "that" off to be searched for inside the complaint.
    if _VAGUE_EN.fullmatch(spoken):
        return EditRequest("unclear", problem="no_target")

    for pattern in _SUBSTITUTE_EN:
        hit = pattern.fullmatch(spoken)
        if hit:
            target, replacement = _clean(hit.group("a")), _clean(hit.group("b"))
            if not target:
                return EditRequest("unclear", problem="no_target")
            if not replacement:
                return EditRequest("unclear", problem="no_replacement", target=target)
            return EditRequest("substitute", target=target, replacement=replacement)

    if _REMOVE_LAST_EN.fullmatch(spoken):
        return EditRequest("remove_last")

    hit = _REMOVE_EN.fullmatch(spoken)
    if hit:
        target = _clean(hit.group("a"))
        if not target or target.lower() in ("that", "this", "it"):
            return EditRequest("unclear", problem="no_target")
        return EditRequest("remove", target=target)

    for pattern in _APPEND_EN:
        hit = pattern.fullmatch(spoken)
        if hit:
            addition = _clean(hit.group("b"))
            # No content after the cue. "Add one more point" is somebody
            # announcing more, not dictating it; it belongs on the
            # continuation path, which reopens the microphone.
            if not addition or _announces_only(addition):
                return None
            return EditRequest("append", replacement=addition)
    return None


# What is left of "add one more point" once "add" has gone. Each of these is
# an announcement that more is coming rather than the thing itself.
_ANNOUNCEMENT = {
    "more", "one more", "another", "another one", "something", "something else",
    "one more point", "one more thing", "another point", "another thing",
    "a point", "a line", "a sentence", "to that", "to it", "some more",
    "more details", "more detail", "more information", "more info",
}


def _announces_only(text: str) -> bool:
    return _clean(text).lower() in _ANNOUNCEMENT


def _read_tamil(spoken: str) -> EditRequest | None:
    if _VAGUE_TA.fullmatch(spoken):
        return EditRequest("unclear", problem="no_target")

    hit = _SUBSTITUTE_TA.search(spoken)
    if hit:
        target = _trim_lead_ta(_clean(hit.group("a")))
        replacement = _clean(hit.group("b"))
        if target and replacement:
            return EditRequest("substitute", target=target, replacement=replacement)
        return EditRequest("unclear", problem="no_target")

    if _REMOVE_LAST_TA.search(spoken):
        return EditRequest("remove_last")

    hit = _REMOVE_TA_RE.search(spoken)
    if hit:
        target = _trim_lead_ta(_clean(hit.group("a")))
        if target:
            return EditRequest("remove", target=target)
        return EditRequest("unclear", problem="no_target")

    hit = _APPEND_TA.search(spoken)
    if hit:
        # NOT trimmed. An addition is the citizen's own sentence and every
        # word of it is theirs to keep; a particle at the front of a target
        # is a pointer, a particle at the front of an addition is prose.
        addition = _clean(hit.group("b"))
        if addition:
            return EditRequest("append", replacement=addition)
    return None


# --------------------------------------------------------------------------- #
# Applying it
# --------------------------------------------------------------------------- #

# Number words a transcription may render either way. "five days" and "5 days"
# are the same phrase to the citizen and different strings to `str.find`, and
# a refusal to locate words the citizen can plainly see on screen is the most
# annoying possible failure.
_WORD_FOR = {
    "0": ("zero",), "1": ("one",), "2": ("two",), "3": ("three",), "4": ("four",),
    "5": ("five",), "6": ("six",), "7": ("seven",), "8": ("eight",), "9": ("nine",),
    "10": ("ten",), "11": ("eleven",), "12": ("twelve",), "15": ("fifteen",),
    "20": ("twenty",), "30": ("thirty",), "100": ("hundred",),
}


def _number_variants(phrase: str) -> list[str]:
    """The phrase with its numbers written the other way round.

    Deterministic and bounded: each token is swapped independently and only
    if it is unambiguously a number on its own. Nothing else about the
    phrase is altered.
    """
    tokens = phrase.split()
    swapped, changed = [], False
    for token in tokens:
        bare = token.strip(_STRIP)
        digits = spoken_cardinal(bare, "en") if bare.isalpha() else None
        if digits is not None:
            swapped.append(token.replace(bare, str(digits)))
            changed = True
            continue
        if bare.isdigit() and bare in _WORD_FOR:
            swapped.append(token.replace(bare, _WORD_FOR[bare][0]))
            changed = True
            continue
        swapped.append(token)
    return [" ".join(swapped)] if changed else []


def _find_all(haystack: str, needle: str) -> list[tuple[int, int]]:
    """Every case-insensitive occurrence, as (start, end) in the ORIGINAL.

    Case-insensitive because a transcription capitalises the first word of a
    sentence and the citizen does not say capitals. The span is into the
    original string, so what is kept around the edit is the citizen's own
    text untouched.
    """
    if not needle:
        return []
    spots, at = [], 0
    low_hay, low_needle = haystack.lower(), needle.lower()
    while True:
        at = low_hay.find(low_needle, at)
        if at < 0:
            return spots
        spots.append((at, at + len(needle)))
        at += len(needle)


# How many characters of suffix a Tamil word may carry beyond the form the
# citizen spoke. ஆக, ஆகவும், ில், கள், த்தில் — the case and adverbial endings
# are all short. The cap is what keeps this from matching a different word
# that happens to start the same way.
_MAX_SUFFIX = 6

# The Tamil vowel-canceller, U+0BCD.
_VIRAMA = "்"


def _find_stem(haystack: str, needle: str) -> tuple[list[tuple[int, int]], int]:
    """The target as the STEM of a longer word, suffix and all.

    WHY THIS IS NEEDED, and it is needed only for Tamil. The citizen says
    "ஐந்து நாட்கள்" — five days, the dictionary form. What they dictated a
    minute earlier, and what is on the screen, is "ஐந்து நாட்களாக" — the
    same words carrying the adverbial ending Tamil requires in that
    position. A literal search finds nothing and the citizen is told their
    own words are not in their own complaint.

    THE VIRAMA IS WHY A PLAIN PREFIX TEST FAILS. "நாட்கள்" ends in ள +
    ், the mark that says the consonant carries no vowel. Add a vowel
    suffix and that mark is REPLACED by the vowel sign: ள் becomes ளா. So
    the spoken form is not a prefix of the written one by a single
    character, and the trailing virama has to come off before the search.

    THE SUFFIX IS CARRIED OVER RATHER THAN DROPPED. The characters beyond
    the stem are the citizen's own. Splicing "மூன்று நாட்கள்" in without
    them leaves "மூன்று நாட்கள் தண்ணீர் வரவில்லை", a sentence with a
    hole in its grammar; carrying them gives "மூன்று நாட்களாக", which is
    what was asked for. Nothing is invented — the suffix is copied off the
    word it was already on.

    ENGLISH DOES NOT USE THIS. English does not inflect this way, and the
    rule would match "part" inside "particular". The caller only reaches
    here for a non-ASCII target.

    Returns the spans and the length of the stem that matched, so the caller
    knows where the suffix begins.
    """
    stem = needle.rstrip(_VIRAMA)
    if not stem:
        return [], 0
    spots = []
    for match in re.finditer(re.escape(stem), haystack, re.I):
        end = match.end()
        while end < len(haystack) and not haystack[end].isspace():
            end += 1
        # A bounded suffix, and never a zero-length one: an exact match was
        # already tried and failed, so a span that stops where the stem does
        # is the same span again.
        if 0 < end - match.end() <= _MAX_SUFFIX:
            spots.append((match.start(), end))
    return spots, len(stem)


def _locate(grievance: str, target: str) -> tuple[list[tuple[int, int]], str, int]:
    """Where the target is.

    Returns the spans, the form that actually matched, and the length of the
    stem when the match ran past the spoken form into a suffix — 0 when it
    was an exact match and there is no suffix to carry.
    """
    for candidate in (target, *_number_variants(target)):
        spots = _find_all(grievance, candidate)
        if spots:
            return spots, candidate, 0
    if not target.isascii():
        spots, stem_len = _find_stem(grievance, target)
        if spots:
            return spots, target, stem_len
    return [], target, 0


# A sentence ends at ., ! or ? — Tamil uses the same full stop. The split
# keeps the punctuation with the sentence it ends.
_SENTENCES = re.compile(r"[^.!?।]+[.!?।]*")


def sentences(text: str) -> list[str]:
    return [piece for piece in (p.strip() for p in _SENTENCES.findall(text)) if piece]


def contains(grievance: str, target: str) -> bool:
    """Are these words in the complaint, allowing for how they were written?

    The same search `apply` uses, exposed so a caller can check BEFORE
    committing to an edit. Used at the "which part?" step: a phrase that is
    not in the grievance is a misheard one, and asking again beats
    substituting against text that never contained it.
    """
    spots, _, _ = _locate(str(grievance or ""), _clean(target))
    return bool(spots)


def apply(grievance: str, request: EditRequest, *, limit: int | None = None) -> EditResult:
    """Carry out one parsed edit, or refuse it with a reason.

    The returned text contains no character the citizen did not dictate,
    except the characters of the replacement they just spoke. Whitespace
    around a removal is tidied and nothing else is.
    """
    text = str(grievance or "")
    if request.action == "unclear":
        return EditResult(False, problem=request.problem or "no_target")

    if request.action == "remove_last":
        parts = sentences(text)
        if len(parts) < 2:
            # Removing the only sentence is not an edit, it is starting
            # again — and starting again has its own word, which the citizen
            # should be asked for rather than have assumed for them.
            return EditResult(False, problem="only_one")
        updated = " ".join(parts[:-1])
        return EditResult(True, text=_tidy(updated), target=parts[-1])

    if request.action == "append":
        addition = _clean(request.replacement)
        if not addition:
            return EditResult(False, problem="no_replacement")
        joined = f"{text.rstrip()} {addition}".strip() if text.strip() else addition
        if limit is not None and len(joined) > limit:
            return EditResult(False, problem="too_long")
        return EditResult(True, text=_tidy(joined), replacement=addition)

    spots, found, stem_len = _locate(text, request.target)
    if not spots:
        return EditResult(False, problem="not_found", target=request.target)

    if request.action == "remove":
        # A removal takes the whole word including its suffix. There is
        # nothing left for the suffix to attach to.
        updated = _splice(text, spots, "")
        if not _clean(updated):
            return EditResult(False, problem="would_empty", target=found)
        return EditResult(True, text=_tidy(updated), target=found)

    # substitute. Every occurrence, because "change five days to three days"
    # said of a complaint that says "five days" twice means both — and the
    # citizen sees the result and is asked again before anything is saved.
    replacement = _clean(request.replacement)
    if not replacement:
        return EditResult(False, problem="no_replacement", target=found)
    if stem_len:
        # The suffix REPLACES the virama, it does not follow it — the same
        # rule that let the stem be found in the first place, applied to the
        # replacement. Without this, நாட்கள் + ாக comes out as "நாட்கள்ாக",
        # which is not a word.
        stemmed = (replacement.rstrip(_VIRAMA)
                   if request.target.endswith(_VIRAMA) else replacement)
        # Each occurrence keeps its own ending: the same stem can appear
        # twice in a complaint with two different cases on it.
        updated = _splice_inflected(text, spots, stemmed, stem_len)
    else:
        updated = _splice(text, spots, replacement)
    if limit is not None and len(updated) > limit:
        return EditResult(False, problem="too_long")
    return EditResult(True, text=_tidy(updated), target=found, replacement=replacement)


def _splice(text: str, spots: list[tuple[int, int]], insert: str) -> str:
    out, last = [], 0
    for start, end in spots:
        out.append(text[last:start])
        out.append(insert)
        last = end
    out.append(text[last:])
    return "".join(out)


def _splice_inflected(text: str, spots: list[tuple[int, int]],
                      insert: str, stem_len: int) -> str:
    """Replace the stem and keep the suffix that was sitting on it."""
    out, last = [], 0
    for start, end in spots:
        out.append(text[last:start])
        out.append(insert + text[start + stem_len:end])
        last = end
    out.append(text[last:])
    return "".join(out)


def _tidy(text: str) -> str:
    """Close the gap a removal leaves, and nothing more.

    Only whitespace and orphaned punctuation, never words: " the drain  ,
    is" becomes "the drain, is" and no sentence is rebuilt, recapitalised or
    repunctuated on the citizen's behalf.
    """
    out = re.sub(r"\s+", " ", text)
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)
    out = re.sub(r"([,;:])\s*([,.;:!?])", r"\2", out)
    out = re.sub(r"^[\s,.;:]+", "", out)
    return out.strip()
