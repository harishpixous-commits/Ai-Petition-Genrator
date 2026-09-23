"""What the assistant may say out loud, as opposed to what it shows.

A screen in a government office is read by the person standing at it. A speaker
is heard by everyone in the queue behind them. So the read-back that is
perfectly appropriate on screen —

    Aadhaar number: 2345 6789 0124
    Mobile number: +91 98765 43210

is not something to announce to a waiting room. What is spoken says that the
number was recorded, and where it is needed for the citizen to recognise it,
only the last four digits.

The rule this module keeps is that speech and display must never DISAGREE.
Speech may say less. It may never say something different, and it may never
claim something the screen does not show. A citizen who is told one thing and
shown another has no way to tell which is on their petition.
"""

from __future__ import annotations

import re
from typing import Any

from ..domain.fields import SENSITIVE_TYPES, SPEAK_NEVER_TYPES
from ..domain.phrasing import Language
from ..domain.templates import LetterTemplate
from .mask import mask_for_display, mask_pii

# Digits, in groups or not, long enough to be an identifier. Deliberately
# broad: a number that turns out to be harmless read aloud costs nothing,
# and one that turns out to be an Aadhaar cannot be taken back.
_LONG_NUMBER = re.compile(r"(?:\+?\d[\d\s-]{7,}\d)")

SPOKEN: dict[str, dict[str, str]] = {
    "recorded_identifier": {
        "en": "I have recorded your {label}.",
        "ta": "உங்கள் {label} பதிவு செய்யப்பட்டது.",
    },
    "ending_in": {
        "en": "I have recorded your {label} ending in {last4}.",
        "ta": "{last4} இல் முடியும் உங்கள் {label} பதிவு செய்யப்பட்டது.",
    },
    # Spoken INSTEAD of the question for an identifier that must never be
    # said in a room with a queue in it. The Tamil avoids putting the label
    # in the accusative, because it is interpolated: "{label} ஐ" produced
    # "ஆதார் எண் ஐ", which is not how the word is written.
    "type_it": {
        "en": ("For your security, please type your {label} in the box on "
               "screen rather than saying it aloud."),
        "ta": ("பாதுகாப்பிற்காக, உங்கள் {label} வாய்விட்டுச் சொல்லாமல் "
               "திரையில் உள்ள இடத்தில் உள்ளிடுங்கள்."),
    },
    "read_back": {
        "en": "I have all your details. Shall I prepare your petition?",
        "ta": "உங்கள் விவரங்கள் அனைத்தும் கிடைத்துவிட்டன. மனுவைத் தயாரிக்கட்டுமா?",
    },
    "ready": {
        "en": ("Your petition is ready and has passed verification. Would you "
               "like me to read it aloud?"),
        "ta": ("உங்கள் மனு தயாராகி சரிபார்க்கப்பட்டுவிட்டது. அதை வாசிக்கட்டுமா?"),
    },
    "preparing": {
        "en": "Certainly. I am preparing your petition now.",
        "ta": "சரி. உங்கள் மனுவை இப்போது தயாரிக்கிறேன்.",
    },
    "still_listening": {
        "en": "I am listening. Please answer when you are ready.",
        "ta": "நான் கேட்டுக்கொண்டிருக்கிறேன். தயாரானதும் பதில் சொல்லுங்கள்.",
    },
    "still_there": {
        "en": "Would you like to continue with this petition?",
        "ta": "இந்த மனுவைத் தொடர விரும்புகிறீர்களா?",
    },
    "not_caught": {
        "en": "Sorry, I did not catch that. Could you say it again?",
        "ta": "மன்னிக்கவும், அது எனக்குப் புரியவில்லை. மீண்டும் சொல்ல முடியுமா?",
    },
    # --- the per-answer read-back loop ------------------------------------
    #
    # Said after every answer the citizen gives, before it is used. The value
    # is quoted back so they hear what was actually captured rather than
    # discovering it on the finished petition, where a misheard house number
    # is a wasted trip to a government office.
    #
    # `heard` carries the answer with identifiers already masked by the
    # caller: the screen shows the full value to the person standing at it,
    # the speaker is heard by the queue behind them.
    # Used when the field being answered is not known — a bare quotation.
    "heard": {
        "en": "I heard: {answer}. Is that correct?",
        "ta": "நான் கேட்டது: {answer}. இது சரியா?",
    },
    # Preferred over `heard` wherever the field IS known, because naming it
    # is what lets the citizen catch the answer landing in the wrong place.
    # "I heard Harish" is agreeable even when Harish was meant to be the
    # town; "I have recorded your name as Harish" is not.
    "heard_field": {
        "en": "I have recorded your {label} as {answer}. Is that correct?",
        "ta": "உங்கள் {label} {answer} என்று பதிவு செய்துள்ளேன். இது சரியா?",
    },
    # For a number the room should not hear. The last four digits are what
    # every bank and telco shows for exactly this purpose: enough for the
    # citizen to recognise which number it is, not enough for the queue
    # behind them to write it down.
    "heard_last4": {
        "en": "I have recorded your {label} ending in {last4}. Is that correct?",
        "ta": "{last4} என்று முடியும் உங்கள் {label} பதிவு செய்துள்ளேன். இது சரியா?",
    },
    "say_again": {
        "en": "Okay, please tell me again.",
        "ta": "சரி, மீண்டும் சொல்லுங்கள்.",
    },
    "confirmed": {
        "en": "Saved.",
        "ta": "பதிவு செய்யப்பட்டது.",
    },
    # Distinct from `not_caught`. That one is said when something was heard
    # and judged not to be an answer; this is said when the transcription
    # came back with nothing in it at all.
    # --- long-form dictation (the grievance) ------------------------------
    #
    # Said INSTEAD of the ordinary question when the field being collected is
    # free text. A citizen asked "tell me your grievance" the way they were
    # asked their age answers in one sentence and stops; being told they may
    # take their time is what produces the complaint they actually have.
    # ONLY the pacing. The question itself lives in the template, where the
    # rest of the form's wording lives; this is the part that is true of
    # speaking and not of typing, and it is appended to the question rather
    # than replacing it.
    "long_intro": {
        "en": "You may take your time. When you are finished, say 'finished'.",
        "ta": ("தேவையான அளவு விரிவாக பேசலாம். நீங்கள் முடித்ததும் "
               "'முடிந்தது' என்று சொல்லலாம்."),
    },
    # After a long grievance. The text is NOT read back: two minutes of
    # speech read back is two minutes nobody listens to, and the whole of it
    # is on the screen in front of them.
    "long_captured": {
        "en": ("Your grievance has been recorded. Is this correct? You can "
               "say Yes, Retry, or tell me what you want to change."),
        "ta": ("உங்கள் குறை பதிவு செய்யப்பட்டுள்ளது. இது சரியா? "
               "'ஆம்', 'மீண்டும்', அல்லது மாற்ற வேண்டியதைச் சொல்லலாம்."),
    },
    # Retry, when the citizen rejects the whole grievance. Distinct from the
    # short-field `say_again`: "please tell me again", said of a two-minute
    # complaint, does not make clear that the whole thing is being redone.
    "long_say_again": {
        "en": "Okay. Please tell me your grievance again.",
        "ta": "சரி. உங்கள் குறையை மீண்டும் முழுமையாக சொல்லுங்கள்.",
    },
    "long_confirmed": {
        "en": "Grievance confirmed.",
        "ta": "குறை உறுதி செய்யப்பட்டது.",
    },
    "long_paused": {
        "en": "Paused. Say continue when you are ready.",
        "ta": "நிறுத்தப்பட்டது. தயாரானதும் தொடரலாம்.",
    },
    "long_resumed": {
        "en": "Please continue. I am listening.",
        "ta": "தொடர்ந்து சொல்லுங்கள். நான் கேட்டுக்கொண்டிருக்கிறேன்.",
    },
    # --- editing a captured grievance by voice ----------------------------
    #
    # Every one of these ends by asking again. An edit is never an approval:
    # the citizen hears what changed, sees the whole text, and is asked
    # whether it is right NOW.
    "edit_changed": {
        "en": "I changed {old} to {new}. Is the grievance correct now?",
        "ta": "{old} என்பதை {new} என்று மாற்றிவிட்டேன். இப்போது சரியா?",
    },
    "edit_removed": {
        "en": "I removed that. Is the grievance correct now?",
        "ta": "அதை நீக்கிவிட்டேன். இப்போது சரியா?",
    },
    "edit_added": {
        "en": "I added that. Is the grievance correct now?",
        "ta": "அதைச் சேர்த்துவிட்டேன். இப்போது சரியா?",
    },
    # The brief, word for word: Citizen "Change that." -> AI "Which part
    # would you like to change?" -> Do not guess.
    "edit_which_part": {
        "en": "Which part would you like to change?",
        "ta": "எந்த பகுதியை மாற்ற வேண்டும்?",
    },
    "edit_what_instead": {
        "en": "What should it say instead?",
        "ta": "அதற்குப் பதிலாக என்ன சொல்ல வேண்டும்?",
    },
    "edit_not_found": {
        "en": ("I could not find those words in your grievance. Which part "
               "would you like to change?"),
        "ta": ("அந்த வார்த்தைகள் உங்கள் குறையில் கிடைக்கவில்லை. "
               "எந்த பகுதியை மாற்ற வேண்டும்?"),
    },
    "edit_only_one": {
        "en": ("That is the whole grievance. Say 'again' to record it from "
               "the start, or tell me what to change."),
        "ta": ("அதுதான் முழு குறை. முதலிலிருந்து சொல்ல 'மீண்டும்' "
               "என்று சொல்லலாம், அல்லது மாற்ற வேண்டியதைச் சொல்லுங்கள்."),
    },
    "edit_too_long": {
        "en": ("There is not enough room left to add that. Everything you "
               "have said is saved."),
        "ta": ("அதைச் சேர்க்க இடம் போதாது. சொன்ன அனைத்தும் "
               "பதிவில் உள்ளது."),
    },
    "long_continue": {
        "en": "Please continue.",
        "ta": "தொடர்ந்து சொல்லுங்கள்.",
    },
    # The one place a hard limit is allowed to change the outcome, and the
    # citizen is told before anything is lost rather than after.
    "long_full": {
        "en": ("That is as much as this form can hold. Everything you have "
               "said so far is saved. Please review it on screen."),
        "ta": ("இந்தப் படிவத்தில் இடம்பிடிக்கக்கூடிய அளவு நிறைந்துவிட்டது. "
               "இதுவரை சொன்ன அனைத்தும் பதிவு செய்யப்பட்டுள்ளது. திரையில் "
               "சரிபார்க்கவும்."),
    },
    # Said ONCE per session, when the room has been measurably loud for
    # several seconds. Advisory: nothing is rejected for it, and the citizen
    # is given the one instruction that actually helps.
    "noisy_room": {
        "en": ("High background noise detected. Please speak a little closer "
               "to the microphone."),
        "ta": ("பின்னணி சத்தம் அதிகமாக உள்ளது. மைக்ரோஃபோனுக்கு அருகில் "
               "பேசுங்கள்."),
    },
    "not_understood": {
        "en": "I couldn't understand that. Please say it again.",
        "ta": "எனக்கு தெளிவாக புரியவில்லை. மீண்டும் சொல்லுங்கள்.",
    },
    "reading": {
        "en": "Here is your petition. Say stop at any time.",
        "ta": "உங்கள் மனு இதோ. எப்போது வேண்டுமானாலும் 'நிறுத்து' எனச் சொல்லலாம்.",
    },
    "read_done": {
        "en": "That is the whole petition. You can download it as PDF or Word.",
        "ta": "மனு முழுவதும் இதுதான். PDF அல்லது Word ஆக பதிவிறக்கம் செய்யலாம்.",
    },
    "read_stopped": {
        "en": "Stopped. The petition is ready to download whenever you are.",
        "ta": "நிறுத்தப்பட்டது. மனு பதிவிறக்கத்திற்குத் தயாராக உள்ளது.",
    },
    "ready_no_read": {
        "en": "Your petition is ready. You can download it as PDF or Word.",
        "ta": "உங்கள் மனு தயார். PDF அல்லது Word ஆக பதிவிறக்கம் செய்யலாம்.",
    },
}


def phrase(key: str, language: Language, **kwargs: Any) -> str:
    template = SPOKEN[key].get(language) or SPOKEN[key]["en"]
    return template.format(**kwargs)


# Section headings the letter itself uses, so reading aloud can stop between
# them. Matched against the start of a line only.
_SECTION_STARTS = (
    "From,", "To,", "Subject", "Respected", "Thanking you", "Thank you",
    "Yours faithfully",
    "Date", "Place", "Note", "Enclosures",
    "அனுப்புநர்", "பெறுநர்", "பொருள்", "மதிப்பிற்குரிய", "நன்றி",
    "இப்படிக்கு", "நாள்", "இடம்", "குறிப்பு", "இணைப்புகள்",
)


def readable_sections(letter_text: str, max_chars: int = 420) -> list[str]:
    """The petition broken into pieces short enough to read aloud and stop.

    Section by section rather than all at once, because a citizen who wants to
    interrupt after the subject line should not have to sit through the whole
    document to do it — and because a single synthesis request for a full
    petition is slow enough to feel broken.

    Every piece goes through `redact_for_speech`, so the identifiers printed in
    the document are not recited to the room. The DOCUMENT is unchanged; this
    is only what is said.
    """
    lines = str(letter_text or "").split("\n")
    sections: list[list[str]] = []
    current: list[str] = []

    for line in lines:
        stripped = line.strip()
        starts_section = any(stripped.startswith(h) for h in _SECTION_STARTS)
        too_long = sum(len(x) for x in current) > max_chars
        if current and (starts_section or too_long) and stripped:
            sections.append(current)
            current = []
        if stripped:
            current.append(stripped)
    if current:
        sections.append(current)

    out = []
    for block in sections:
        spoken = _drop_empty_labels(redact_for_speech(" ".join(block)))
        if spoken.strip():
            out.append(spoken.strip())
    return out


# "Mobile number:" with its value redacted away. Read aloud that is a label
# announcing nothing, and two of them in a row — "Mobile number: Aadhaar
# number:" — sounds like the service lost the data rather than withheld it.
_EMPTY_LABEL = re.compile(
    r"(?:[A-Z][A-Za-z ]{2,24}|[஀-௿][஀-௿ ]{2,24}?)\s*:\s*"
    r"(?=$|[A-Z஀-௿][A-Za-z஀-௿ ]{2,24}\s*:|[,.])"
)


def _drop_empty_labels(text: str) -> str:
    previous = None
    while previous != text:
        previous = text
        text = _EMPTY_LABEL.sub("", text)
    return re.sub(r"\s{2,}", " ", text).strip(" ,;")


def last_four(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[-4:] if len(digits) >= 4 else ""


def redact_for_speech(text: str) -> str:
    """Remove identifiers from something about to be spoken.

    The backstop rather than the mechanism. `speech_for` below builds spoken
    text deliberately; this catches anything that reached the speaker by
    another route — a validation message quoting a number back, a reply
    assembled somewhere this module does not know about.
    """
    # The shared boundary masker also catches email addresses and alphanumeric
    # IDs. A number-only backstop used to announce these in ordinary replies.
    masked = mask_pii(str(text or ""))
    masked = re.sub(r"\[[A-Z ]+ REDACTED\]", "", masked)
    return re.sub(r"[ \t]+", " ", _LONG_NUMBER.sub("", masked)).strip()


def should_type_instead(field_type: str, allow_spoken_identifiers: bool) -> bool:
    """True when this field should be typed rather than spoken.

    An Aadhaar number spoken aloud goes two places it need not go: the room,
    and whichever speech-to-text service is configured — which for a hosted
    provider means the audio of a citizen reciting their Aadhaar leaves the
    building. Typing it keeps it on the deterministic path it already has.

    Off by default, and configurable, because a citizen who cannot type is the
    person this service exists for; an operator can turn spoken identifiers on
    for an assisted counter where that trade is the right one.
    """
    return field_type in SPEAK_NEVER_TYPES and not allow_spoken_identifiers


def speech_for(
    *,
    display_text: str,
    view: dict[str, Any],
    template: LetterTemplate,
    language: Language,
    allow_spoken_identifiers: bool = False,
) -> str:
    """What to say, given what is being shown.

    Never contradicts the screen. It abbreviates, and for identifiers it
    describes rather than recites.
    """
    status = view.get("status")
    awaiting = view.get("awaiting")

    if status == "generating":
        return phrase("preparing", language)

    if status == "ready":
        if (view.get("editing") or {}).get("pending"):
            return redact_for_speech(display_text)
        return phrase("ready", language)

    # The read-back lists every value, identifiers included. Spoken, it becomes
    # a question — the screen beside it carries the detail, already masked.
    if status == "confirming" and not view.get("awaiting_correction"):
        return phrase("read_back", language)

    # About to ask for an identifier: say so, and ask for it to be typed.
    if awaiting:
        spec = next((f for f in template.fields if f.name == awaiting), None)
        if spec and should_type_instead(spec.type, allow_spoken_identifiers):
            return phrase("type_it", language, label=spec.label_for(language))

    return redact_for_speech(display_text)


def read_back_sentence(
    spec: Any,
    answer: str,
    language: Language,
    *,
    lengthy: bool = False,
) -> str:
    """How a captured answer is said back to the citizen.

    Names the field wherever one is known, because that is what lets someone
    catch an answer landing in the wrong place. "I heard Harish" is agreeable
    even when Harish was meant to be the town; "I have recorded your name as
    Harish" is not.

    An identifier is described by its last four digits rather than recited.
    The screen beside them carries the full value; the queue behind them does
    not need it.

    A long answer is summarised — two minutes of speech read back is two
    minutes nobody listens to, and the whole of it is on the screen.

    Lives here rather than inside the socket so it can be tested as the
    function it is. It was a closure, and a test that reproduced its logic
    instead of calling it passed happily while the real one was broken.
    """
    if lengthy:
        return phrase("long_captured", language)

    spoken = mask_for_display(str(answer))
    if spec is None:
        return phrase("heard", language, answer=spoken)

    label = spec.speech_label_for(language)
    if spec.type in SENSITIVE_TYPES:
        digits = re.sub(r"\D", "", str(answer))
        if len(digits) >= 4:
            return phrase("heard_last4", language, label=label, last4=digits[-4:])
    # A full stop inside the quotation collides with the sentence built
    # around it: "your grievance: no water came. is that correct?" reads as
    # two broken sentences when spoken.
    return phrase("heard_field", language, label=label,
                  answer=spoken.rstrip(" .।"))


def acknowledgement(
    *, name: str, value: Any, template: LetterTemplate, language: Language
) -> str | None:
    """How to confirm a value that has just been accepted, out loud.

    Returns None for ordinary fields — the next question is acknowledgement
    enough, and a service that repeats every answer is tiring to use. Only
    identifiers get one, because the citizen cannot see whether the digits went
    in correctly from the fact that the conversation moved on.
    """
    spec = next((f for f in template.fields if f.name == name), None)
    if spec is None or spec.type not in SENSITIVE_TYPES:
        return None
    label = spec.label_for(language)
    tail = last_four(value)
    if tail:
        return phrase("ending_in", language, label=label, last4=tail)
    return phrase("recorded_identifier", language, label=label)
