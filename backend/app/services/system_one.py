"""System-1: fast typed decisions, and nothing else.

WHAT THIS LAYER IS. Four questions that have to be answered on every
attachment and every grievance, that are cheap to get wrong because
something downstream checks them, and that nothing was answering before:

    what KIND of problem is this        candidate category, for the RAG to verify
    whose document IS this              own previous petition, or somebody else's
    does it bear on this complaint      relevance, already measured by overlap
    should a person look at this        review triage for the officer portal

WHAT IT IS NOT. It is not the intent reader. `domain/answer_intent.py` scores
1.000 on the 244-case set at 0.16ms with no model, and `docs/laya-decision.md`
records why nothing is going to beat that. It is not the department, the Act,
the Rule or the authority — those come from the government corpus through
`knowledge/`, verified, or they are not printed at all. And it is not
permitted to write anything: every method here RETURNS A DECISION. The
workflow decides what to do with it.

THE RULE THAT OUTRANKS EVERY ANSWER HERE:

    1. the citizen's confirmed data
    2. the citizen's corrections
    3. confirmed attachment evidence
    4. verified government RAG
    5. never a guess

A classification is evidence ABOUT a document. It is never identity. The
relationship classifier below exists precisely because that line was crossed
once: a name read off an attached PDF replaced the name a citizen had typed.

PROVIDERS. `DeterministicProvider` ships and is the default. `LayaProvider`
is a seam, disabled, and refuses to load rather than pulling a multi-gigabyte
dependency into an image that has neither torch nor transformers. Both answer
the same questions and both may answer UNKNOWN, which every caller must
handle — that is what makes the swap safe.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from ..domain.languages import has_indic as _has_indic
from ..domain.taxonomy import taxonomy as _taxonomy

log = logging.getLogger(__name__)

# Every classifier here can say it does not know, and callers must cope with
# it. Forcing an uncertain input into the nearest label is how a third
# party's petition becomes the citizen's own.
UNKNOWN = "UNKNOWN"

# Read from `app/taxonomy/grievance.yaml`, which is loaded and validated at
# import. A malformed file stops the service starting, which is where an
# administrator sees it — rather than halfway through a citizen's interview.
#
# OTHER and UNKNOWN are appended here rather than listed in the file: they
# are not things to complain about, they are what this module says when the
# text names something else or names nothing.
_TAXONOMY = _taxonomy()
CATEGORIES = (*_TAXONOMY.names, "OTHER", UNKNOWN)

RELATIONSHIPS = ("OWN_PREVIOUS_PETITION", "THIRD_PARTY_SUPPORTING_DOCUMENT",
                 "ACKNOWLEDGEMENT", "GOVERNMENT_RESPONSE", "CERTIFICATE",
                 "PHOTO_EVIDENCE", "GENERAL_SUPPORTING_DOCUMENT", "UNRELATED", UNKNOWN)

RELEVANCE = ("HIGHLY_RELEVANT", "PARTIALLY_RELEVANT", "UNRELATED", UNKNOWN)

# The names `attachment_relevance` has always used, mapped to this layer's.
# One table, because two copies of it drift and the second copy is the one
# that silently stops matching.
_RELEVANCE_LEVELS = {"high": "HIGHLY_RELEVANT", "partial": "PARTIALLY_RELEVANT",
                     "unrelated": "UNRELATED", "unknown": UNKNOWN}

ROUTES = ("DETERMINISTIC", "SYSTEM1", "SYSTEM2_LLM", "RAG_REQUIRED")


@dataclass(frozen=True)
class Decision:
    """One typed answer, with why, and with what it is worth.

    `value` is always from the task's own list. Free-form decision text is
    what this type exists to prevent: a caller cannot branch safely on a
    sentence.
    """

    value: str
    confidence: float = 0.0
    reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def known(self) -> bool:
        return self.value != UNKNOWN

    def as_dict(self) -> dict[str, Any]:
        return {"value": self.value, "confidence": round(self.confidence, 2),
                "reason": self.reason, "evidence": self.evidence}


# --------------------------------------------------------------------------- #
# Words
# --------------------------------------------------------------------------- #
#
# Every script in one table per category, because a citizen at a Tamil
# counter says "தண்ணீர்" and the transcript of the same sentence from an
# English session says "water". Neither is the primary form.
#
# FIVE LANGUAGES, NOT TWO. Malayalam, Telugu and Hindi were added to the
# interview, the document and the analysis panel and never to this table. The
# benchmark scored each of them at 0.000 — not "poorly", but every grievance
# UNKNOWN, always — because there was not one word of any of the three here to
# match. The words below are the ordinary ones a counter hears; they are not
# translations of the English list, because the complaint a citizen states is
# not a translation of the complaint somebody else stated.

_CATEGORY_WORDS: dict[str, tuple[str, ...]] = _TAXONOMY.words()

# A document that says it is a reply from an office. Checked before the
# petition markers, because a government response quotes the petition it is
# answering and carries the same words.
_RESPONSE_WORDS = ("in reply to", "with reference to your petition",
                   "your petition dated", "this office", "sanctioned",
                   "rejected", "disposed", "உங்கள் மனுவிற்கு", "பதிலளிக்கிறேன்",
                   "அலுவலக குறிப்பு", "நிராகரிக்கப்பட்டது", "அனுமதிக்கப்பட்டது")

_ACKNOWLEDGEMENT_WORDS = ("acknowledgement", "acknowledgment", "receipt",
                          "received your petition", "token",
                          "ஒப்புகை", "பெறுகைச் சீட்டு", "ரசீது")

_PETITION_WORDS = ("petition", "respected sir", "respected madam",
                   "i request", "humbly request", "subject:",
                   "மனு", "மதிப்பிற்குரிய", "கேட்டுக்கொள்கிறேன்", "பொருள்:")

# The subset that means SOMEBODY WROTE THIS AS A PETITION — a salutation, a
# subject line, a request — as opposed to merely mentioning the word.
#
# The distinction is not academic. A real previous petition almost always
# carries its own acknowledgement number, and the bare word "acknowledgement"
# was enough to have it filed as a receipt, because receipts are checked
# first. Meanwhile a genuine receipt says "we have received your petition",
# so the word "petition" cannot be used to rule one out either. What
# separates them is who is speaking: a petition addresses an officer and asks
# for something; a receipt reports that something arrived.
_AUTHORED_MARKERS = ("respected sir", "respected madam", "i request",
                     "humbly request", "subject:",
                     "மதிப்பிற்குரிய", "கேட்டுக்கொள்கிறேன்", "பொருள்:")

_CERTIFICATE_WORDS = ("certificate", "certified that", "certify that",
                      "this is to certify", "சான்றிதழ்", "சான்றளிக்கப்படுகிறது")

# WHERE IT HAPPENED, NOT WHAT IS WRONG. "Sewage is overflowing onto the
# main road" is a sanitation complaint that contains the word road, and an
# unweighted table scored it 1-1 and gave up. These words count for less:
# they place a complaint, and only carry it when nothing else does. It is
# the same lesson as "street", one step short of deleting the word — ROAD
# still needs "road" to classify "the road has never been laid".
#
# "light" is here for a different reason: bare "light" is how a Tanglish
# speaker says street light ("street la light eriyala"), but it is also how
# anyone says a household light. Weak, it wins when nothing else is present
# and loses to மின்சாரம் when that is.
_WEAK_WORDS = _TAXONOMY.weak

# TWO COMPLAINTS, OR ONE COMPLAINT IN A PLACE? Weighted scoring answers
# "sewage overflowing onto the road" correctly and then answers "both the
# drainage and the water pipeline need repair" wrongly, because in the
# second the citizen really is reporting two things. The difference is not
# in the nouns, which is why counting them could never separate the two —
# it is that the second sentence COORDINATES them, and Tamil says so
# explicitly with the clitic உம் on each noun: "சாலையும் ... குடிநீரும்".
# Each language marks "and also" its own way. Tamil's உம் is a clitic on each
# noun; Malayalam's ഉം is the same device; Telugu and Hindi use separate words.
# Without these a two-subject complaint in Malayalam is answered confidently
# with one of its two subjects, which is the one failure this rule exists for.
_COORDINATION = _TAXONOMY.coordination
_STRONG, _WEAK = _TAXONOMY.strong_weight, _TAXONOMY.weak_weight
_CONFIDENCE_BASE = _TAXONOMY.confidence_base
_CONFIDENCE_PER_POINT = _TAXONOMY.confidence_per_point
_CONFIDENCE_CEILING = _TAXONOMY.confidence_ceiling
# How much to trust each kind of UNKNOWN. Not zero: see the file.
_UNKNOWN_CONFIDENCE = _TAXONOMY.unknown_confidence


def _weight(found: list[str], text: str = "",
            spans: list[tuple[int, int]] | None = None) -> int:
    """How much evidence these matches really are.

    A term listed as scenery counts half. So does a term that only ever
    appears inside a landmark phrase — half rather than nothing, because
    "near the overflowing drain" really is about a drain.
    """
    spans = spans or []
    total = 0
    for word in found:
        if word in _WEAK_WORDS:
            total += _WEAK
        elif text and _only_scenery(word, text, spans):
            total += _WEAK
        else:
            total += _STRONG
    return total


_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


# Tamil's pure-consonant mark. A suffix REPLACES it rather than following
# it, which is why plain substring matching silently fails on inflection:
# குடிநீர் + உம் is written குடிநீரும், and the needle குடிநீர் does not
# occur in that string at all. Benchmark cases died on this before it was
# seen — the word for drinking water went unmatched in a sentence about
# drinking water, and the sentence was classified from the other noun in
# it. Dropping the mark leaves குடிநீர, a prefix of both forms.
_VIRAMA = "்"

# The same mark in each of the other scripts the service serves. Malayalam,
# Telugu and Devanagari inflect by suffix exactly as Tamil does, and each
# writes its pure-consonant mark at its own codepoint, so one constant could
# never have covered them.
_VIRAMAS = frozenset({
    "\u0bcd",   # Tamil       ்
    "\u0d4d",   # Malayalam   ്
    "\u0c4d",   # Telugu      ్
    "\u094d",   # Devanagari  ्
})

# --------------------------------------------------------------------------- #
# Romanised Tamil
# --------------------------------------------------------------------------- #
#
# A THIRD SCRIPT WITH A THIRD SET OF RULES. A citizen at a keyboard with no
# Tamil layout types தண்ணீர் as thanni, thanneer, thaneer or thani, and a
# speech recogniser produces a fourth spelling nobody would have written. None
# of these is a misspelling — there is no correct romanisation of Tamil — so a
# word list can only ever chase them.
#
# The variation is systematic, which means it can be normalised away instead:
#
#     doubled consonants    kuppai / kupai        gemination is not phonemic here
#     long vowels           thanneer / thanir     aa ee ii oo uu are length marks
#     compounds             kudineer / kudi neer  word division is a convention
#     digraphs              kuzhi / kuli          zh is one Tamil letter, ழ
#
# Both the needle and the text go through the same folding and are then
# matched as substrings — word boundaries are meaningless once spaces are
# removed, so a minimum length guards against noise instead.
#
# WHAT THIS DOES NOT FIX, and it is worth naming rather than pretending: an
# English loanword spelled phonetically ("pension" heard as "penshan") is not
# a systematic variation of anything, and the final holdout records it as a
# gap.
_ROMAN_FOLDS = (
    ("zh", "l"), ("sh", "s"),
    ("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("uu", "u"),
)
_MIN_ROMAN = 4


def fold_roman(text: str) -> str:
    """Collapse the spellings of one romanised Tamil word onto one form."""
    out = "".join(c for c in str(text or "").casefold() if c.isalpha())
    for a, b in _ROMAN_FOLDS:
        out = out.replace(a, b)
    # Doubled consonants, after the vowel folds so "ee" is not read as a
    # double first.
    result = []
    for ch in out:
        if result and result[-1] == ch and ch not in "aeiou":
            continue
        result.append(ch)
    return "".join(result)


# Romanised Tamil roots, kept apart from the English and Tamil tables because
# they are matched by a different rule. English stays word-bounded: "ration"
# must not be found inside "corporation", and folding would not save it.
_ROMANISED_WORDS: dict[str, tuple[str, ...]] = _TAXONOMY.romanised()
_ROMANISED_FOLDED: dict[str, tuple[tuple[str, str], ...]] = {
    category: tuple((word, fold_roman(word)) for word in words
                    if len(fold_roman(word)) >= _MIN_ROMAN)
    for category, words in _ROMANISED_WORDS.items()
}
# Spelled with a chr() rather than an escape on purpose: this exact
# sequence was corrupted once by a shell heredoc into a literal 0x08,
# which silently matched nothing and took every Latin word with it.
_BOUNDARY = chr(92) + "b"

_CONTRAST = _TAXONOMY.contrast
_SATISFIED = _TAXONOMY.satisfied

#: Sentence ends, plus the contrast words. Built from the taxonomy so a
#: department adding "ஆனாலும்" gets clause splitting for free.
_CLAUSE_BREAK = re.compile(
    "|".join([r"[.;!?\n]"] + [re.escape(marker) for marker in _CONTRAST]),
    re.IGNORECASE)


def _clauses(text: str) -> list[str]:
    """The text cut at sentence ends and contrast words."""
    return [part.strip() for part in _CLAUSE_BREAK.split(text) if part.strip()]


def _reports_satisfaction(clause: str) -> bool:
    """Does this clause say something is FINE rather than wrong?

    "the street light is working", "the drain is clear", "ठीक है". A clause
    like this names a category and is not a complaint about it, and counting
    it is how a one-subject grievance became a tie.
    """
    return any(marker in clause for marker in _SATISFIED)


_SCENERY = _TAXONOMY.scenery
_SCENERY_WINDOW = _TAXONOMY.scenery_window


def _scenery_spans(text: str) -> list[tuple[int, int]]:
    """Where in `text` a landmark or a piece of background is being given.

    Indian addresses are built from landmarks — opposite the temple, near the
    bus stand, behind the school — because that is how a place is found here.
    A category word inside one of those is saying WHICH thing, not WHAT is
    wrong, and counted as evidence it outvoted the actual subject: "the street
    light opposite the water tank" was filed under water supply.
    """
    spans: list[tuple[int, int]] = []
    for marker in _SCENERY:
        # THE SAME INFLECTION PROBLEM THE CATEGORY WORDS HAD, and it was
        # silently halving this rule's reach. Malayalam writes "അടുത്ത്" on
        # its own and "അടുത്തുള്ള" in a phrase — the suffix REPLACES the
        # pure-consonant mark, so the plain needle does not occur in the
        # inflected form at all. Measured: the landmark rule fired on English
        # and Tamil and never once on Malayalam, Telugu or Hindi.
        #
        # `_hits` already solves this for terms. Doing it here rather than
        # calling `_hits` because what is needed is the POSITION, which
        # `_hits` does not return.
        needles = [marker]
        if marker[-1:] in _VIRAMAS:
            needles.append(marker[:-1])
        for needle in needles:
            start = text.find(needle)
            while start != -1:
                spans.append((start, start + len(needle) + _SCENERY_WINDOW))
                start = text.find(needle, start + 1)
    return spans


def _only_scenery(needle: str, text: str, spans: list[tuple[int, int]]) -> bool:
    """True when EVERY occurrence of `needle` sits inside a landmark phrase.

    Every, not any: a word that appears once as a landmark and once as the
    complaint is still the complaint.
    """
    if not spans:
        return False
    position = text.find(needle)
    if position == -1:
        return False
    while position != -1:
        if not any(start <= position < end for start, end in spans):
            return False
        position = text.find(needle, position + 1)
    return True


_COMPLAINT_MARKERS = _TAXONOMY.complaint_markers
_COMPLAINT_MIN_WORDS = _TAXONOMY.complaint_min_words


def _looks_like_a_complaint(text: str) -> bool:
    """Is this a grievance about something unlisted, or is it nothing?

    Two signals, and BOTH are required, because either alone is wrong:

        length   a four-word plea is not a complaint about an unlisted
                 subject, it is a plea.
        a marker saying something is wrong or missing. Polite formulas are
                 deliberately excluded — "kindly", "request" and "please"
                 appear in every petition ever written, including the ones
                 that name nothing at all.

    Erring towards UNKNOWN on purpose. UNKNOWN sends the petition to a human
    who asks the citizen what it is about, which is recoverable. OTHER says
    "we understood you, there is simply no category", which closes that
    question — and closing it wrongly leaves a citizen unasked.
    """
    if len(text.split()) < _COMPLAINT_MIN_WORDS:
        return False
    return bool(_hits(f" {text} ", _COMPLAINT_MARKERS))


def _complaint_scope(text: str) -> str:
    """The part of the text that is actually complaining.

    Falls back to the whole text when every clause reports satisfaction:
    a citizen who wrote only good news has not filed a grievance, and
    guessing which clause was secretly the complaint is worse than reading
    the sentence whole.
    """
    clauses = _clauses(text)
    if len(clauses) < 2:
        return text
    complaining = [c for c in clauses if not _reports_satisfaction(c)]
    if not complaining or len(complaining) == len(clauses):
        return text
    return " ".join(complaining)


def _normalise(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def _hits(haystack: str, needles: tuple[str, ...]) -> list[str]:
    """Which phrases appear, matched by the rules of the script they are in.

    The two scripts need OPPOSITE rules, and using either one for both has
    now caused a measured failure:

        Tamil   substring, because a regex word boundary does not see the
                script, and the language inflects by suffix. Plus the virama
                fallback below, without which குடிநீர் does not occur in
                குடிநீரும் — the word for drinking water went unmatched in a
                sentence about drinking water.

        Latin   word boundary, because substring matching finds "ration"
                inside "corporation" and files a rubbish complaint under
                welfare schemes.
    """
    found = []
    for needle in needles:
        # ANY Indic script, not Tamil alone. This tested the Tamil block alone while
        # the service served five languages, so a Malayalam, Telugu or Hindi
        # needle fell through to the Latin branch and was matched with a word
        # boundary — and Python's \w does not see Indic combining marks, so
        # the match was against a mutilated word. The words and this test had
        # to change together; either one alone looks like a fix and is not.
        if _has_indic(needle):
            if needle in haystack:
                found.append(needle)
            elif needle[-1:] in _VIRAMAS and needle[:-1] in haystack:
                found.append(needle)          # the suffix replaced the mark
        elif re.search(_BOUNDARY + re.escape(needle), haystack):
            found.append(needle)
    return found


def _same_person(left: str, right: str) -> bool | None:
    """Whether two names are the same person. None when it cannot be told.

    Deliberately strict, and deliberately three-valued. "Harish Kumar" and
    "Harish Kumaresan" are not the same person, and a classifier that says
    they are is how a petition is filed under the wrong name. When either
    side is missing the answer is None, not False: an unnamed document is
    not evidence of a different person.
    """
    a, b = _normalise(left), _normalise(right)
    if not a or not b:
        return None
    if a == b:
        return True
    # One name written short and long — "Harish" against "Harish Kumar" —
    # is the same person written two ways, and only when the shorter is a
    # whole leading word of the longer.
    short, long_ = sorted((a, b), key=len)
    if long_.startswith(short + " "):
        return True
    return False


# --------------------------------------------------------------------------- #
# Providers
# --------------------------------------------------------------------------- #

class DeterministicProvider:
    """Tables and comparisons. No model, no network, no warm-up.

    Every answer is explainable to the citizen it affects, which for a
    government service is worth more than the last few points of accuracy
    on a benchmark.
    """

    name = "deterministic"

    def classify_grievance(self, *, grievance: str, language: str = "en") -> Decision:
        whole = _normalise(grievance)
        if len(whole) < 8:
            return Decision(UNKNOWN, _UNKNOWN_CONFIDENCE["nothing_said"],
                            "too little text to classify")

        # Clauses reporting that something is FINE are not complaints about it.
        # See `_complaint_scope`: this is what stops "the light is working but
        # the drain is blocked" being read as two subjects.
        text = _normalise(_complaint_scope(whole))
        folded = fold_roman(text)
        spans = _scenery_spans(text)
        scored: list[tuple[int, str, list[str]]] = []
        for category, words in _CATEGORY_WORDS.items():
            found = _hits(text, words)
            # Romanised Tamil, matched on the folded form. Added rather than
            # replacing, and de-duplicated, so a word that appears in both
            # tables is not counted twice and does not outweigh a real pair.
            found += [word for word, key in _ROMANISED_FOLDED.get(category, ())
                      if key in folded and word not in found]
            if found:
                scored.append((_weight(found, text, spans), category, found))
        if not scored:
            # TWO DIFFERENT SILENCES, and they need opposite handling.
            #
            # "Sir, kindly do the needful" names no subject: a human has to
            # ask the citizen what it is about. "There are stray dogs and two
            # children have been bitten" names a subject perfectly clearly —
            # it is just not one of the ten this service has words for.
            #
            # Both used to come back UNKNOWN, and OTHER was never returned by
            # any code path at all despite being in CATEGORIES and displayed
            # by the officer portal. So a real grievance about an unlisted
            # subject was indistinguishable from an empty one.
            if _looks_like_a_complaint(text):
                return Decision("OTHER", _UNKNOWN_CONFIDENCE["no_terms"],
                                "a grievance, but not one of the known subjects")
            return Decision(UNKNOWN, _UNKNOWN_CONFIDENCE["no_terms"],
                            "no category words present")

        scored.sort(reverse=True)
        best, runner = scored[0], (scored[1] if len(scored) > 1 else None)
        # ONLY AN EXACT TIE, and this was measured the hard way. A near-tie
        # rule — UNKNOWN whenever the runner-up held half the winner's
        # evidence — was written here to catch one two-subject case. It
        # bought that case and then failed TWO held-out ones, turning a
        # sewage complaint and a widow pension into UNKNOWN. A rule that
        # sends correctly-classified petitions to a human because a second
        # noun appeared is not caution, it is noise, and the officer pays
        # for it. Weighted scoring separates the subject from the setting;
        # a true tie still means two subjects and still means UNKNOWN.
        # Coordinated, and both sides carry real evidence: two complaints.
        # A weak word alone does not qualify — "and the road above it"
        # needs to be the subject of its own clause, not a location.
        # Any evidence on both sides is enough HERE, unlike the tie rule
        # below: these markers are explicit. A citizen who writes "both",
        # "as well as", or puts உம் on two nouns is saying there are two.
        if runner and _hits(f" {text} ", _COORDINATION):
            return Decision(UNKNOWN, _UNKNOWN_CONFIDENCE["coordinated"],
                            f"two complaints are coordinated: {best[1]}, {runner[1]}",
                            {"candidates": [best[1], runner[1]]})
        if runner and runner[0] == best[0]:
            return Decision(UNKNOWN, _UNKNOWN_CONFIDENCE["tied"],
                            f"two categories match equally: {best[1]}, {runner[1]}",
                            {"candidates": [best[1], runner[1]]})
        confidence = min(_CONFIDENCE_CEILING,
                         _CONFIDENCE_BASE + _CONFIDENCE_PER_POINT * best[0])
        return Decision(best[1], confidence,
                        f"matched {', '.join(best[2][:3])}",
                        {"matched": best[2][:5]})

    def classify_attachment_relationship(
            self, *, kind: str, text: str, citizen_name: str = "",
            document_name: str = "", language: str = "en") -> Decision:
        """Whose document this is, which is not the same as who wrote it.

        THE CASE THIS EXISTS FOR. A citizen called Harish attached a
        previous petition belonging to Sethubala. Nothing classified the
        relationship, so the document was treated as the citizen's own
        earlier petition and its details were offered as replacements for
        theirs. A petition went out under a name belonging to neither.

        A petition naming somebody else is a THIRD PARTY's document. It may
        be perfectly good evidence — a neighbour's complaint about the same
        road often is — but it is evidence, not identity.
        """
        body = _normalise(text)
        chosen = _normalise(kind)

        if chosen == "photo" or (not body and chosen in ("photo", "photo_evidence")):
            return Decision("PHOTO_EVIDENCE", 0.8, "a photograph")
        if not body:
            return Decision(UNKNOWN, 0.0, "nothing could be read from it")

        # Order matters. A government reply quotes the petition it answers,
        # so it carries every petition marker; checked first it is read
        # correctly, checked last it reads as a petition.
        if _hits(body, _RESPONSE_WORDS):
            return Decision("GOVERNMENT_RESPONSE", 0.75, "reads as a reply from an office")
        if _hits(body, _ACKNOWLEDGEMENT_WORDS) and not _hits(body, _AUTHORED_MARKERS):
            return Decision("ACKNOWLEDGEMENT", 0.8, "reads as a receipt")
        if _hits(body, _CERTIFICATE_WORDS) and not _hits(body, _PETITION_WORDS):
            return Decision("CERTIFICATE", 0.75, "reads as a certificate")

        if _hits(body, _PETITION_WORDS):
            same = _same_person(citizen_name, document_name)
            if same is True:
                return Decision("OWN_PREVIOUS_PETITION", 0.9,
                                "a petition naming this citizen",
                                {"document_name": document_name})
            if same is False:
                # The whole point. Named, and named as somebody else.
                return Decision("THIRD_PARTY_SUPPORTING_DOCUMENT", 0.85,
                                "a petition naming a different person",
                                {"document_name": document_name,
                                 "citizen_name": citizen_name})
            # A petition with no readable petitioner is NOT assumed to be
            # theirs. That assumption is the bug.
            return Decision(UNKNOWN, 0.3,
                            "a petition, but no petitioner could be read from it")

        return Decision("GENERAL_SUPPORTING_DOCUMENT", 0.5, "a supporting document")

    def classify_attachment_relevance(
            self, *, kind: str, text: str, grievance: str,
            readable: bool = True, language: str = "en") -> Decision:
        """Wraps the measurement that already exists rather than repeating it.

        `attachment_relevance.assess` has been scoring term overlap since
        before this layer, its thresholds were chosen against real
        documents, and a second opinion sitting beside it would be a second
        thing to keep in step.
        """
        from ..domain import attachment_relevance

        found = attachment_relevance.assess(
            kind=kind, text=text, grievance=grievance,
            readable=readable, language=language)
        return Decision(_RELEVANCE_LEVELS.get(found.level, UNKNOWN),
                        round(min(0.95, found.overlap * 3), 2) if found.overlap else 0.4,
                        found.reason, {"overlap": round(found.overlap, 3)})

    def needs_review(self, *, relationship: Decision, relevance: Decision,
                     category: Decision, attention: bool = False) -> Decision:
        """Whether a person should look at this before it is routed.

        Errs towards yes. An officer glancing at a petition that did not
        need it costs a few seconds; one that needed it and was not looked
        at is the failure this whole portal exists to prevent.
        """
        reasons = []
        if attention:
            reasons.append("the record is already flagged for attention")
        if relationship.value == "THIRD_PARTY_SUPPORTING_DOCUMENT":
            reasons.append("an attachment names a different person")
        if relationship.value == UNKNOWN:
            reasons.append("an attachment could not be placed")
        if relevance.value == "UNRELATED":
            reasons.append("an attachment does not appear to bear on the complaint")
        if category.value == UNKNOWN:
            reasons.append("the complaint did not classify")
        if not reasons:
            return Decision("NO", 0.7, "nothing needs a second look")
        return Decision("YES", 0.9, "; ".join(reasons), {"reasons": reasons})

    def needs_system2(self, *, utterance: str, language: str = "en") -> Decision:
        """Which layer should answer this, and nothing about the answer.

        Only two things genuinely need the expensive path: a request to
        rewrite the document, and a question about the law. Everything else
        the existing deterministic reader already settles, measured at
        1.000 on the 244-case set.
        """
        text = _normalise(utterance)
        if not text:
            return Decision("DETERMINISTIC", 0.9, "nothing said")
        legal = ("act", "rule", "section", "government order", "g.o",
                 "சட்டம்", "விதி", "அரசாணை", "பிரிவு")
        rewrite = ("rewrite", "reword", "more formal", "formally", "shorten",
                   "make it longer", "improve", "முறையாக", "சுருக்க", "மாற்றி எழுது")
        if _hits(text, legal):
            return Decision("RAG_REQUIRED", 0.8, "asks about the law")
        if _hits(text, rewrite):
            return Decision("SYSTEM2_LLM", 0.8, "asks for the document to be rewritten")
        return Decision("DETERMINISTIC", 0.85, "the existing reader settles this")


class LayaProvider:
    """A seam, deliberately not wired.

    `docs/laya-decision.md` records the assessment: on Laya's own published
    numbers the fine-tuned ceiling is 0.766 and the English checkpoint scores
    0.306 on non-English intent, against an incumbent measured here at 1.000,
    0.16ms and no dependency at all. The EC2 host has no GPU and the image
    has neither torch nor transformers.

    It is kept because the question will be asked again and the answer may
    change. `benchmarks/` can score any provider, so a future checkpoint can
    be measured on the same cases before anything is enabled.
    """

    name = "laya"

    def __init__(self) -> None:
        raise RuntimeError(
            "The Laya provider is not installed. See docs/laya-decision.md "
            "for the assessment, and benchmarks/ for the harness that would "
            "have to pass before enabling it.")


# --------------------------------------------------------------------------- #
# The engine
# --------------------------------------------------------------------------- #

class SystemOneEngine:
    """One place the rest of the service asks these four questions.

    A provider that fails, times out or answers below the confidence floor
    falls back to the deterministic one, so a classification layer can never
    be the reason a petition is not created.
    """

    def __init__(self, provider: Any | None = None, *, threshold: float = 0.0) -> None:
        self.provider = provider or DeterministicProvider()
        self.fallback = DeterministicProvider()
        self.threshold = threshold

    def _ask(self, method: str, **kwargs: Any) -> Decision:
        for source in (self.provider, self.fallback):
            try:
                answer = getattr(source, method)(**kwargs)
            except Exception as exc:  # noqa: BLE001
                log.warning("system_one.failed",
                            extra={"task": method, "provider": getattr(source, "name", "?"),
                                   "error": str(exc)[:160]})
                continue
            if answer.known and answer.confidence < self.threshold:
                log.info("system_one.below_threshold",
                         extra={"task": method, "confidence": answer.confidence})
                return Decision(UNKNOWN, answer.confidence,
                                "below the configured confidence floor")
            return answer
            # The loop continues only when a provider raised, so the
            # deterministic one is reached exactly when it is needed.
        return Decision(UNKNOWN, 0.0, "no provider could answer")

    def classify_grievance(self, **kwargs: Any) -> Decision:
        return self._ask("classify_grievance", **kwargs)

    def classify_attachment_relationship(self, **kwargs: Any) -> Decision:
        return self._ask("classify_attachment_relationship", **kwargs)

    def classify_attachment_relevance(self, **kwargs: Any) -> Decision:
        return self._ask("classify_attachment_relevance", **kwargs)

    def needs_review(self, **kwargs: Any) -> Decision:
        return self._ask("needs_review", **kwargs)

    def needs_system2(self, **kwargs: Any) -> Decision:
        return self._ask("needs_system2", **kwargs)


def engine(settings: Any | None = None) -> SystemOneEngine:
    """The configured engine. Deterministic unless told otherwise, and
    deterministic anyway if the alternative will not load."""
    from ..config import get_settings

    s = settings or get_settings()
    if not getattr(s, "system1_enabled", False):
        return SystemOneEngine()
    provider = None
    if getattr(s, "system1_provider", "deterministic") == "laya":
        try:
            provider = LayaProvider()
        except Exception as exc:  # noqa: BLE001
            log.warning("system_one.provider_unavailable",
                        extra={"error": str(exc)[:200]})
    return SystemOneEngine(
        provider, threshold=float(getattr(s, "system1_confidence_threshold", 0.0)))


# --------------------------------------------------------------------------- #
# The advisory record the attachment pipeline stores
# --------------------------------------------------------------------------- #

# Relationships that bar a document from being spoken about IN THE FIRST
# PERSON on a new petition — "I had previously submitted ... under
# acknowledgement number N".
#
# THE CASE THIS EXISTS FOR. A citizen called Harish attached a previous
# petition belonging to Sethubala and confirmed what had been read out of it.
# Nothing classified whose document it was, so the new petition claimed
# Sethubala's acknowledgement number as Harish's own history. The document was
# genuine, the number was genuine, and the sentence was false.
#
# IT IS A DENY-LIST, NOT AN ALLOW-LIST, and that is deliberate. Written the
# other way round — only OWN_PREVIOUS_PETITION may speak — every citizen whose
# acknowledgement slip has no legible petitioner name would silently lose the
# reference sentence they are entitled to, and most scanned slips have no
# legible name. The sentence is withheld on EVIDENCE that the document belongs
# to somebody else, not on absence of evidence that it belongs to them. The
# citizen's own confirmation still gates it, as it always has.
WITHHELD_FROM_FIRST_PERSON = frozenset({"THIRD_PARTY_SUPPORTING_DOCUMENT"})


#: A decision at or below this confidence rests on nothing but a weak word —
#: one that names where something happened rather than what it was. Derived,
#: not chosen: the confidence formula gives base + per_point for a single weak
#: match, and anything with one strong word scores above it.
_WEAK_EVIDENCE_CEILING = _CONFIDENCE_BASE + _CONFIDENCE_PER_POINT * _WEAK


async def classify_grievance(*, grievance: str, language: str = "en",
                             settings: Any = None) -> Decision:
    """The category, using meaning only where words were not enough.

    THE ORDER IS THE WHOLE DESIGN. The deterministic reader runs first and
    keeps everything it is confident about: it is free, instant, offline, and
    it can tell a citizen WHICH WORD it read. A cosine similarity cannot
    explain itself to anybody.

    The semantic step is asked only when the deterministic reader found
    nothing — not when it found too much. A grievance naming two subjects is
    answered UNKNOWN on purpose, because picking one silently drops the other,
    and a similarity score is exactly the wrong tool for overruling that.
    `candidates` in the evidence is how that case is recognised.

    Every failure here is silent and safe: no embedder, no network, nothing
    similar enough, or two meanings too close to separate, and the
    deterministic answer stands unchanged.
    """
    decision = engine(settings=settings).classify_grievance(
        grievance=grievance, language=language)

    # Two subjects were found, not none. Leave it for a human; a similarity
    # score is exactly the wrong tool for overruling that.
    if decision.evidence.get("candidates"):
        return decision

    # WHEN A SECOND OPINION IS WORTH ASKING FOR. Not only when the reader
    # found nothing, but also when all it found was a word that usually names
    # a PLACE rather than a subject.
    #
    # Measured: "stray cattle are being left on the main road at night" and
    # "the bins at the end of our road overflow" were both answered ROAD, both
    # on the single weak word "road", both at 0.63 — and the semantic reader
    # was never consulted because the lexical one had technically answered.
    # A complaint identified only by the word for where it happened is the
    # weakest evidence this reader produces, and it is exactly the case a
    # reading of the whole sentence settles.
    weak_only = decision.confidence <= _WEAK_EVIDENCE_CEILING
    if decision.value not in (UNKNOWN, "OTHER") and not weak_only:
        return decision

    try:
        from . import semantic_category

        reader = semantic_category.build(settings)
        if reader is None:
            return decision
        answer = await reader.classify(grievance)
    except Exception as exc:  # noqa: BLE001
        log.info("system_one.semantic_unavailable",
                 extra={"error": str(exc)[:160]})
        return decision

    if answer is None:
        return decision

    category, confidence, reason = answer
    if category == decision.value:
        # They agree. Keep the DETERMINISTIC decision: it carries the word it
        # matched, which is something a citizen or an officer can be shown,
        # and a cosine distance is not.
        return decision

    log.info("system_one.semantic_placed",
             extra={"was": decision.value, "now": category,
                    "confidence": confidence})
    return Decision(category, confidence, reason,
                    {"source": "semantic",
                     "deterministic": decision.value})


def describe_attachment(
        *, kind: str, text: str, grievance: str, citizen_name: str = "",
        document_name: str = "", readable: bool = True, language: str = "en",
        relevance_level: str = "", settings: Any = None) -> dict[str, Any]:
    """The advisory record for one attachment: whose it is, and whether a
    person should look at it.

    NEVER RAISES. An attachment that could not be classified is an attachment
    that is UNKNOWN, and UNKNOWN is a correct answer that the pipeline already
    handles. A classification layer must not be the reason a citizen cannot
    file a petition, so every failure here lands on the same safe default as
    an unreadable file.

    `relevance_level` is the raw level from `attachment_relevance.assess` when
    the caller has already run it — which the upload path has. Passing it
    keeps this from scoring the same overlap twice.
    """
    # Inside the guard, not above it. Building the engine reads settings and
    # may import a provider, and both can fail; constructed outside, a bad
    # configuration value would propagate out of here and take the upload
    # with it. There are two layers on purpose — the engine catches a
    # provider that misbehaves, and this catches everything else, including
    # the engine.
    try:
        engine_ = engine(settings)
        relationship = engine_.classify_attachment_relationship(
            kind=kind, text=text, citizen_name=citizen_name,
            document_name=document_name, language=language)
        if relevance_level:
            relevance = Decision(_RELEVANCE_LEVELS.get(relevance_level, UNKNOWN))
        else:
            relevance = engine_.classify_attachment_relevance(
                kind=kind, text=text, grievance=grievance,
                readable=readable, language=language)
        # The complaint's own category, computed here because the review
        # rule weighs it and because the officer portal shows it as a
        # SUGGESTION. It is a hint and nothing else: it does not pick a
        # department, an authority, an Act or a Rule, and it does not route.
        # It measured 0.778 on the one case set that never informed it,
        # which is a useful prompt for a human and nowhere near enough to
        # send a petition anywhere on its own.
        category = engine_.classify_grievance(
            grievance=grievance, language=language)
        review = engine_.needs_review(
            relationship=relationship, relevance=relevance,
            category=category, attention=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("system_one.describe_failed", extra={"error": str(exc)[:160]})
        # Unavailable is not evidence of anything. The attachment keeps the
        # behaviour it had before this layer existed — enclosed, listed, and
        # still gated by the citizen's own confirmation — and it is flagged
        # for an officer to look at.
        return {"value": UNKNOWN, "confidence": 0.0,
                "reason": "the classifier could not be reached",
                "source": "unavailable", "requires_review": True,
                "first_person_allowed": True}

    value = relationship.value
    # A supporting document that supports nothing in this grievance is not
    # "general support", it is unrelated. The two classifiers each hold half
    # of that: one knows the document has no recognisable type, the other
    # knows it shares nothing with the complaint.
    if value == "GENERAL_SUPPORTING_DOCUMENT" and relevance.value == "UNRELATED":
        value = "UNRELATED"

    return {
        "value": value,
        "confidence": round(relationship.confidence, 2),
        "reason": relationship.reason,
        "source": f"system-1/{engine_.provider.name}",
        "requires_review": review.value == "YES",
        # Precomputed rather than re-derived at composition time, so that the
        # rule lives in one place and a reader of the stored record can see
        # what was decided about it.
        "first_person_allowed": value not in WITHHELD_FROM_FIRST_PERSON,
        "evidence": relationship.evidence,
        # A HINT, and named like one everywhere it travels. Nothing in this
        # service may branch on it: department, authority, Act and Rule
        # continue to come from verified RAG and officer review.
        "suggested_category": category.value,
        "suggested_category_confidence": round(category.confidence, 2),
    }
