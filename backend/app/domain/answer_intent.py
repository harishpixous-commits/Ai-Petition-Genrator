"""What a citizen means when the assistant reads their answer back to them.

The assistant says "I heard: twelve Kumar Street. Is that correct?" and the
citizen replies. This decides whether that reply means *yes, keep it*, *no,
let me say it again*, or *no — it is actually this instead*.

WHY NOT A KEYWORD LIST. People do not answer a machine's question in the
machine's words. "yeah that's right", "okay continue", "go ahead", "அடுத்தது
போகலாம்" all mean yes, and a table of exact matches sends the citizen round
the loop again for saying the ordinary thing. Equally, "no, it's twelve
Kumar Street" is not a request to retry — the correction is already in the
sentence, and asking them to repeat it is asking them to say it a third time.

THE TWO TRAPS THIS IS BUILT AROUND, both of which reverse the meaning:

    "not correct"    contains  "correct"
    "சரியில்லை"      contains  "சரி"

So refusal is tested BEFORE agreement, always. A classifier that checked
agreement first would read "that's not correct" as consent and commit the
wrong answer to a government form.

WHAT MAKES IT SAFE. Nothing here commits anything. CONFIRM commits the
answer the citizen has just heard read back; REPLACE swaps in what they said
instead and reads THAT back for confirmation in turn. There is no path from
speech to a saved field that does not pass through a read-back the citizen
agreed to.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Language = Literal["en", "ta"]
Intent = Literal["confirm", "retry", "replace"]

# Refusal. Tested first, and deliberately including the negated forms of the
# agreement words: "not correct" must never be read as "correct".
_REFUSE_EN = (
    "not correct", "not right", "incorrect", "thats wrong", "that is wrong",
    "its wrong", "it is wrong", "wrong", "mistake", "mistaken",
    "retry", "try again", "say again", "said again", "tell again",
    "tell you again", "say it again", "repeat", "repeating", "again",
    "change it", "change that", "want to change", "let me change",
    "let me repeat", "let me say", "let me tell", "redo", "start over",
    "no", "nope", "nah", "not that", "thats not",
)
_REFUSE_TA = (
    # "மீண்டும்" / "மறுபடியும்" — again. "திரும்ப" — back/again.
    "மீண்டும்", "மறுபடி",
    "திரும்ப",
    # "தவறு" — wrong. "சரியில்லை" — not right. Longer than "சரி" and tested
    # first, which is the whole reason the order matters.
    "தவற", "சரியில்ல",
    "தவறான",
    # "மாற்ற" — to change. Stem, because the suffix varies.
    "மாற்ற",
    # "இல்லை" — no / not. "இல்ல" is the spoken form; it is also a substring
    # of the written one, so listing it costs nothing and catches both.
    "இல்லை", "இல்ல", "வேண்டாம்",
)

# Agreement.
_AGREE_EN = (
    "thats correct", "that is correct", "correct", "confirmed", "confirm",
    "thats right", "that is right", "right", "yes", "yeah", "yep", "yup",
    "ya", "okay", "ok", "o k", "fine", "sure", "alright", "all right",
    "continue", "proceed", "go ahead", "move ahead", "moving ahead",
    "carry on", "next one", "next", "good", "perfect",
    "exactly", "done", "save it", "keep it",
)
_AGREE_TA = (
    # "ஆம்" / "ஆமாம்" — yes. "ஆமா" is the spoken form and is what a
    # transcription service returns for it far more often than "ஆமாம்".
    "ஆமாம்", "ஆமா", "ஆம்",
    # "சரிதான்" before "சரி": the longer form is stripped first so the
    # residual test below does not leave "தான்" behind looking like content.
    "சரிதான்", "சரி",
    # "தொடரலாம்" — let us continue. "அடுத்தது" — next.
    "தொடர", "அடுத்த",
    # "ஓகே" — okay. "இதுதான்" — this is it. "உறுதி" — confirm.
    "ஓகே", "இதுதான்",
    "உறுதி", "பரவாயில்ல",
)

# Words that carry no decision and should not count as a replacement when
# they are all that is left over.
_FILLER = (
    "please", "thanks", "thank", "you", "sir", "madam", "its", "it", "is",
    "that", "thats", "this", "the", "a", "i", "am", "was", "and", "so", "just",
    "whats", "theres", "im", "ive", "dont", "isnt",
    # Words that cannot be an answer on their own, and that are left behind
    # by a continuation cue: "I have one more thing" keeps "i have".
    # Deliberately NOT here: "one", "two", "yes" — each is a real answer to
    # some question this form asks.
    "have", "has", "had", "there", "thing", "things", "something", "mention",
    "forgot", "quite", "then", "can", "got", "ill", "well", "very", "really",
    "sorry", "again",
    "let", "me", "will", "ll", "want", "to", "my", "of", "for", "but",
    "நன்றி", "அது", "இது",
    "நான்", "எனக்கு",
    # Hesitation noises. Sarvam transcribes them, and two of them are long
    # enough to clear the residue floor and be offered back as an answer.
    "um", "uh", "erm", "hmm", "hm", "mm", "ah", "eh", "er",
    # Auxiliaries and "I say" verbs left behind once a stem is removed:
    # "மாற்ற வேண்டும்" keeps "வேண்டும்"; "திரும்ப சொல்லுகிறேன்" keeps the verb.
    "வேண்டும்", "போகலாம்", "சொல்கிறேன்", "சொல்லுகிறேன்", "சொல்லுறேன்",
    "சொல்றேன்", "பண்ணுங்க", "செய்யுங்கள்", "சொல்லி", "சொல்ல",
    "சொல்லுங்கள்", "சொல்லுங்க", "செய்", "ஆரம்பிக்கலாம்", "ஆரம்பிக்க",
    # "ஒன்று" (one) is here so that "இன்னும் ஒன்று இருக்கு" — "there is one
    # more" — is recognised as announcing more rather than as the citizen
    # correcting their answer to the word "one".
    #
    # THE COST, stated because it is a real one: a bare "ஒன்று" offered as a
    # correction reads as a refusal, and the citizen is asked again. None of
    # this form's six fields — name, age, mobile, address, Aadhaar,
    # grievance — takes "one" as an answer, so it is unreachable here. Adding
    # a field that counts something would make it reachable, and this line
    # is the first place to look.
    "ஒன்று", "ஒரு", "விஷயம்", "இருக்கு", "இருக்கிறது",
)

# A replacement has to carry some actual content. Below this many characters
# of residue, an utterance is treated as agreement or refusal with noise on
# the end rather than as a new answer — "yes ok" must not become an address.
#
# Numbers are exempt (see `read`). Dropping this to 2 to admit "no, 36" was
# tried and let a bare "um" through as a proposed answer; the floor stays and
# digits step around it instead.
MIN_REPLACEMENT_CHARS = 3


@dataclass(frozen=True)
class Reading:
    """What the citizen's reply means, and what is left of it."""

    intent: Intent
    # The new answer, when they corrected rather than asked to start again.
    # Empty for confirm and for a bare retry.
    replacement: str = ""


# Apostrophes are DELETED rather than turned into a space, which is what the
# general rule below would do to them. "that's all" became "that s all" and
# matched no phrase in any table, so a citizen ending their grievance with the
# commonest English phrase for it was not heard — while "that's correct"
# appeared to work only because "correct" is separately listed.
_APOSTROPHE = re.compile(r"['’ʼ`]")


def _normalise(text: str) -> str:
    """Lowercase, strip punctuation, collapse spaces. Tamil is untouched by
    the case fold and has no apostrophes to lose."""
    lowered = _APOSTROPHE.sub("", str(text or "").lower())
    cleaned = re.sub(r"[^\w\s஀-௿]+", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def _present(haystack: str, needles: tuple[str, ...]) -> bool:
    """Whether any phrase appears.

    English is matched on word boundaries so "no" does not fire inside
    "north". Tamil is matched as a substring, because `\\b` does not work
    against Tamil script and the language inflects by suffix — the stem
    "மாற்ற" has to match "மாற்றவேண்டும்".
    """
    return any(
        re.search(rf"(?<!\w){re.escape(n)}(?!\w)", haystack) if n.isascii()
        else n in haystack
        for n in needles
    )


def _strip(text: str, needles: tuple[str, ...]) -> str:
    """Remove EVERY occurrence of every phrase, longest first.

    Removing only the first match was a bug with four faces: "okay continue"
    kept "continue", "yeah that's right" kept "yeah", "let me repeat" kept
    "let me". Each looked like leftover content, so a plain agreement was
    read as a new answer and the citizen was asked to confirm their own
    "continue" as though it were their address.

    Longest first so "that's correct" is taken whole rather than leaving
    "that's" behind once "correct" has gone.

    Tamil stems remove the WHOLE WORD they appear in, not just the stem.
    Tamil inflects by suffix, so taking the stem out leaves the ending
    stranded: "தொடரலாம்" minus "தொடர" is "லாம்", four characters that look
    exactly like a new answer. Every Tamil agreement in the table was being
    read as the citizen correcting themselves.
    """
    out = text
    for needle in sorted(needles, key=len, reverse=True):
        if needle.isascii():
            out = re.sub(rf"(?<!\w){re.escape(needle)}(?!\w)", " ", out)
        elif needle in out:
            out = " ".join("" if needle in word else word for word in out.split())
    return out


def _residue(text: str) -> str:
    """What is left once every decision word and filler is taken out.

    Used ONLY to decide whether the citizen said anything substantial. It is
    deliberately not the value that gets used: it is lowercased, stripped of
    punctuation and has its filler removed, which turned "Water has not been
    supplied for five days" into "water has not been supplied five days" —
    a grievance with a word missing, printed on a government form.
    """
    rest = _strip(text, _REFUSE_EN + _REFUSE_TA + _AGREE_EN + _AGREE_TA)
    kept = [w for w in _normalise(rest).split() if w not in _FILLER]
    return " ".join(kept).strip()


# Words that may sit between "no," and the actual answer. Trimmed from the
# FRONT only, so nothing inside the citizen's sentence is touched.
_LEAD_IN = ("it is", "its", "it's", "that is", "thats", "that's", "i said",
            "i mean", "actually", "make it", "change it to", "change to")

# Longest first. "change it" sits in the refusal table and would otherwise be
# taken out of "change it to 24 Gandhi Road", leaving the answer starting
# with a dangling "to".
_ASCII_LEAD = tuple(sorted({*_REFUSE_EN, *_AGREE_EN, *_LEAD_IN},
                           key=len, reverse=True))
_TAMIL_LEAD = tuple(sorted({*_REFUSE_TA, *_AGREE_TA}, key=len, reverse=True))


def _as_answer(original: str) -> str:
    """The citizen's own words, with only the lead-in removed.

    Returns the ORIGINAL string from the point the content starts, so
    capitalisation, punctuation and every interior word survive. "no, it is
    12 Kumar Street" gives "12 Kumar Street", not "12 kumar street".
    """
    text = str(original or "").strip()
    changed = True
    while changed and text:
        changed = False
        head = text.lstrip(" ,.:;-—")
        lowered = head.lower()
        # Longest first, or "change it" is taken out of "change it to 24
        # Gandhi Road" and leaves a dangling "to" at the front of the answer.
        for phrase in _ASCII_LEAD:
            if lowered.startswith(phrase) and (
                    len(lowered) == len(phrase) or not lowered[len(phrase)].isalnum()):
                text, changed = head[len(phrase):], True
                break
        if not changed:
            for phrase in _TAMIL_LEAD:
                if head.startswith(phrase):
                    text, changed = head[len(phrase):], True
                    break
        if not changed:
            text = head
    return text.strip(" ,.:;-—")


def read(text: str, language: Language = "en") -> Reading:
    """Interpret a reply to "is that correct?".

    Order is the design. Refusal first, because the refusals contain the
    agreements as substrings in both languages. Then agreement. Anything
    else is the citizen simply saying the answer again, which is a
    correction and is treated as one.
    """
    spoken = _normalise(text)
    if not spoken:
        return Reading("retry")

    # Both languages' tables are consulted whatever the session language: a
    # citizen answering a Tamil question with "ok" is not a mistake, and
    # code-switching mid-sentence is ordinary here.
    refuses = _present(spoken, _REFUSE_EN + _REFUSE_TA)
    agrees = _present(spoken, _AGREE_EN + _AGREE_TA)
    rest = _residue(spoken)

    # Anything substantial left over is the answer itself. "no, it is twelve
    # Kumar Street" carries its own correction; making them repeat it is
    # asking a third time. "yes, twelve Kumar Street" agrees with nothing —
    # reading the first word as consent would commit the very answer they
    # are in the middle of correcting.
    # A bare digit counts: "no, 5" correcting a count is as real an answer
    # as any sentence, and the length floor exists to reject stray syllables,
    # not numbers.
    if len(rest) >= MIN_REPLACEMENT_CHARS or rest.isdigit():
        # The residue decided; the citizen's own words are what is used.
        return Reading("replace", _as_answer(text) or rest)

    if refuses:
        return Reading("retry")
    if agrees:
        return Reading("confirm")

    # Neither, and nothing left once filler was removed — too little to act
    # on. Asking again is the only safe reading.
    return Reading("retry")


# --------------------------------------------------------------------------- #
# Long-form dictation
#
# A grievance is told, not answered. These two readings exist only while one
# is being collected, and both are about the SHAPE of the turn rather than its
# content: whether the citizen has finished, and whether they want to carry on
# after being told they had.
# --------------------------------------------------------------------------- #

# "That is everything." Checked before an utterance is added to the grievance,
# so the word "finished" does not end up printed in the complaint.
_DONE_EN = (
    "finished", "i am finished", "im finished", "ive finished",
    "done", "i am done", "im done", "thats done",
    "thats all", "that is all", "thats it", "that is it",
    "thats everything", "that is everything", "nothing more",
    "nothing else", "no more", "end", "over", "complete", "completed",
    "i have finished", "i have said everything", "thats my complaint",
)
_DONE_TA = (
    # "முடிந்தது" — it is finished. "முடித்துவிட்டேன்" — I have finished.
    # "முடித்" covers both "முடித்தது" and "முடித்துவிட்டேன்": the stem is
    # the same and only the vowel sign after it differs, so matching the
    # longer "முடித்த" missed the commoner "முடித்துவிட்டேன்".
    "முடிந்த", "முடித்", "முடிச்ச", "முடிஞ்ச",
    # "அவ்வளவுதான்" — that is all. "இதுதான்" — this is it.
    "அவ்வளவு", "இவ்வளவு",
    "இதுதான்", "அதுதான்",
    # "போதும்" — enough.
    "போதும்",
)

# "There is more." Checked when the citizen is asked to confirm, so that
# continuing is not read as correcting.
_MORE_EN = (
    "one more thing", "one more", "another thing", "another issue",
    "another point", "another problem", "another", "something else",
    "add more", "add something",
    "add one more", "i want to add", "i would like to add", "want to add",
    "also", "and also", "additionally", "in addition", "furthermore",
    "i forgot", "i forgot to mention", "forgot to say", "let me add",
    "there is more", "theres more", "more to say", "continue", "carry on",
)
_MORE_TA = (
    # "இன்னும்" — more / still. "மேலும்" — furthermore.
    "இன்னும்", "மேலும்",
    # "சேர்க்க" — to add. Stem: the suffix varies.
    "சேர்க்க", "சேர்த்த",
    # "மறந்து" — having forgotten.
    "மறந்த", "மறந்து",
    # "இன்னொரு" — one more.
    "இன்னொரு",
)


def finished(text: str, language: Language = "en") -> bool:
    """Did the citizen just say they have said everything?

    True ONLY when that is all they said. "That's all" on its own ends the
    dictation; "that's all the water we get" is part of the complaint, and
    treating it as an ending would cut a citizen off mid-sentence and print
    their unfinished grievance on a government form.

    The residue test is what separates them: an utterance with content left
    over after the ending words are removed is content.
    """
    spoken = _normalise(text)
    if not spoken:
        return False
    if not _present(spoken, _DONE_EN + _DONE_TA):
        return False
    # Agreement words come out too. "okay, finished" and "yes that's all" are
    # endings with a politeness on the front, and counting the politeness as
    # content would keep the microphone open after the citizen had stopped.
    rest = _strip(spoken, _DONE_EN + _DONE_TA + _AGREE_EN + _AGREE_TA)
    kept = [w for w in _normalise(rest).split() if w not in _FILLER]
    return not kept


def wants_more(text: str, language: Language = "en") -> bool:
    """Is the citizen carrying on rather than answering the question?

    Asked only at the confirmation prompt, where "also, the drain is blocked"
    means keep going — not "replace my grievance with those five words",
    which is what the ordinary reading would have made of it.

    Unlike `finished`, this does NOT require the utterance to be nothing but
    the trigger. Someone who says "I forgot to mention the drain is blocked"
    has both announced more and given it, and the caller keeps the whole
    sentence: dropping the part that looks like a trigger would delete words
    from a complaint, which is the one thing this must never do.
    """
    spoken = _normalise(text)
    if not spoken:
        return False
    # An ending beats a continuation: "that's all, nothing more to add" says
    # stop, and "more" appears in it.
    if finished(spoken, language):
        return False
    return _present(spoken, _MORE_EN + _MORE_TA)


def continuation(text: str, language: Language = "en") -> str | None:
    """Is the citizen carrying on with their answer, and did they bring more?

    Returns:
        None  — not a continuation. Read it the ordinary way.
        ""    — they announced more and stopped ("I have one more thing").
                Reopen and wait.
        text  — they announced more AND gave it ("also the drain is
                blocked"). Reopen and keep every word of this.

    The third case returns the WHOLE utterance, not the part after the cue.
    "Also the drain is blocked" is how a person says it, and "also" is their
    word; trimming it to "the drain is blocked" would edit a complaint to
    make it tidier, which is the one thing this may never do.
    """
    if not wants_more(text, language):
        return None
    spoken = _normalise(text)
    rest = _strip(spoken, _MORE_EN + _MORE_TA + _AGREE_EN + _AGREE_TA)
    kept = [w for w in _normalise(rest).split() if w not in _FILLER]
    return str(text).strip() if kept else ""
