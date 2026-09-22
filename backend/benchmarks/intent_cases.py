"""A labelled evaluation set for voice control intents, in Tamil and English.

WHY IT EXISTS. Any proposal to replace the intent classifier — Laya, an LLM,
a different table — has to be measured against the one in service rather than
against an impression of it. This is the measuring stick, and it is
deliberately written as DATA so that a candidate can be scored without
touching the application.

NO REAL CITIZEN DATA. Every line is synthetic. The names are common Tamil
Nadu names used as decoys, the addresses are invented, and no Aadhaar, mobile
number or real grievance appears anywhere. Nothing here came from a session.

WHAT MAKES IT HONEST. Roughly a third of the cases are things that must NOT
be classified as a control intent: a person's name, a house number, a
sentence of a complaint, and the short acknowledgements a transcription
service invents out of silence. A confirmation classifier that scores well
only on confirmations is a classifier that says yes to everything, and that
one commits wrong answers to a government form.

THE LABEL SET is the one the brief asks for, which is wider than the
application's own three-way reading. The adapter in `run_intent_benchmark.py`
maps between them, so a candidate classifier can be scored on this vocabulary
without the application having to adopt it.

    CONFIRM    the answer just read back is right
    RETRY      it is wrong, and no replacement was offered
    CORRECT    it is wrong, and the replacement is in the same sentence
    ADD_MORE   the citizen has more to say; keep what is already captured
    FINISHED   a long answer is complete
    UNKNOWN    none of the above — hand it to the workflow as content

`context` says what the workflow was doing, because the same word means
different things in different places: "ஆம்" answering "is that correct?" is a
confirmation, and "ஆம்" answering "what is your name?" is not a name.
"""

from __future__ import annotations

from dataclasses import dataclass

# The three places an utterance can arrive, because the same words mean
# different things in each. These are the contexts the socket actually
# distinguishes — a benchmark that invented its own would be scoring a
# classifier the application does not run.
CONFIRMING = "WAITING_CONFIRMATION"           # a short answer read back
LONG_CONFIRMING = "WAITING_CONFIRMATION_LONG"  # a grievance read back
DICTATING = "LONG_GRIEVANCE_LISTENING"         # mid-narration
ASKING = "ASKING_FIELD"


@dataclass(frozen=True)
class Case:
    text: str
    want: str
    language: str          # en | ta | mixed
    context: str
    note: str = ""


def _cases(rows, want, language, context) -> list[Case]:
    return [Case(text, want, language, context) for text in rows]


# --------------------------------------------------------------------------- #
# CONFIRM — every ordinary way of agreeing
# --------------------------------------------------------------------------- #

CONFIRM_EN = [
    "yes", "yeah", "yep", "yup", "ya", "yes please", "yes it is",
    "correct", "that's correct", "thats correct", "that is correct",
    "right", "that's right", "thats right", "quite right",
    "okay", "ok", "OK", "okay then", "okay continue", "ok fine",
    "fine", "that's fine", "sure", "alright", "all right",
    "continue", "please continue", "you can continue", "proceed",
    "go ahead", "carry on", "move ahead", "next", "next one",
    "confirm", "confirmed", "please confirm", "good", "perfect",
    "exactly", "done", "save it", "keep it", "yes thank you",
    "yes that's it", "correct, thank you", "ok sir", "yes madam",
]

CONFIRM_TA = [
    "ஆம்", "ஆமாம்", "ஆமா", "சரி", "சரிதான்", "சரி சரி",
    "ஓகே", "ஓகே சரி", "உறுதி", "உறுதி செய்",
    "தொடரலாம்", "சரி தொடருங்கள்", "அடுத்தது போகலாம்", "அடுத்தது",
    "இதுதான்", "இதுதான் சரி", "பரவாயில்லை", "ஆமாம் சரி",
    "சரி நன்றி", "ஆம் சரிதான்",
]

CONFIRM_MIXED = [
    "yes சரி", "ok தொடரலாம்", "correct ஆமாம்", "சரி ok",
    "ஆமாம் continue", "yes அடுத்தது",
]

# --------------------------------------------------------------------------- #
# RETRY — wrong, with no replacement offered
# --------------------------------------------------------------------------- #

RETRY_EN = [
    "no", "nope", "nah", "no no", "wrong", "that's wrong", "thats wrong",
    "that is wrong", "it's wrong", "incorrect", "not correct",
    "that's not correct", "not right", "that's not right",
    "retry", "try again", "say again", "please say again",
    "let me say it again", "let me repeat", "let me try again",
    "I'll say it again", "I want to say it again", "repeat", "repeat it",
    "again", "again please", "change it", "I want to change it",
    "redo", "start over", "that's a mistake", "you got it wrong",
]

RETRY_TA = [
    "இல்லை", "இல்ல", "தவறு", "தவறான", "சரியில்லை", "சரியில்ல",
    "மீண்டும்", "மீண்டும் சொல்கிறேன்", "மறுபடியும்", "மறுபடி சொல்லுங்கள்",
    "திரும்ப சொல்லுகிறேன்", "நான் மீண்டும் சொல்கிறேன்",
    "மாற்ற வேண்டும்", "வேண்டாம்", "இல்லை மீண்டும்",
    "மறுபடியும் ஆரம்பிக்கலாம்",
]

RETRY_MIXED = [
    "no மீண்டும்", "தவறு try again", "இல்லை retry",
]

# --------------------------------------------------------------------------- #
# CORRECT — wrong, and the new answer is in the same breath
# --------------------------------------------------------------------------- #

CORRECT_EN = [
    "no, 36",
    "No, 36.",
    "no it's 36",
    "no, it is thirty six",
    "no, my name is Anbu Selvan",
    "wrong, it's 24 Gandhi Street",
    "that's wrong, Madurai",
    "no, Tiruchirappalli",
    "actually 42",
    "actually it's Salem",
    "change it to 15 Bharathi Road",
    "I said Coimbatore",
    "I meant Erode",
    "no, water has not come for six days",
    "not correct, the date was the fifteenth",
]

CORRECT_TA = [
    "இல்லை, மதுரை",
    "இல்லை மதுரை",
    "தவறு, சேலம்",
    "இல்லை, முப்பத்தி ஆறு",
    "இல்லை, என் பெயர் அன்பு செல்வன்",
    "சரியில்லை, திருச்சி",
]

CORRECT_MIXED = [
    "no, மதுரை",
    "இல்லை, Coimbatore",
]

# --------------------------------------------------------------------------- #
# ADD_MORE — at the confirmation prompt, but not finished
# --------------------------------------------------------------------------- #

ADD_MORE_EN = [
    "I have one more thing",
    "one more thing",
    "there is one more thing",
    "there's more",
    "I want to add something",
    "I would like to add one more point",
    "add one more",
    "another issue",
    "there is another problem",
    "also the drain is blocked",
    "also, the road is damaged",
    "and also the pole is leaning",
    "I forgot to mention the date",
    "I forgot one point",
    "additionally the bill was not given",
]

ADD_MORE_TA = [
    "இன்னும் ஒன்று இருக்கு",
    "இன்னும் ஒன்று சொல்ல வேண்டும்",
    "மேலும் சொல்ல வேண்டும்",
    "மேலும் சேர்க்க வேண்டும்",
    "இன்னும் விவரம் இருக்கிறது",
    "இன்னொரு பிரச்சனை இருக்கிறது",
    "ஒரு விஷயம் மறந்துவிட்டேன்",
]

ADD_MORE_MIXED = [
    "இன்னும் one more thing",
    "also இன்னும் ஒரு விஷயம்",
]

# --------------------------------------------------------------------------- #
# FINISHED — a long answer is complete
# --------------------------------------------------------------------------- #

FINISHED_EN = [
    "finished", "I am finished", "I'm finished", "I have finished",
    "done", "I am done", "I'm done",
    "that's all", "thats all", "that is all",
    "that's it", "that's everything", "that is everything",
    "nothing more", "nothing else", "no more",
    "that's my complaint", "okay finished", "yes that's all",
]

FINISHED_TA = [
    "முடிந்தது", "முடிஞ்சது", "சொல்லி முடித்துவிட்டேன்",
    "அவ்வளவுதான்", "இவ்வளவுதான்", "இதுதான்", "போதும்",
    "சரி முடிந்தது",
]

FINISHED_MIXED = [
    "ok முடிந்தது", "finished அவ்வளவுதான்",
]

# --------------------------------------------------------------------------- #
# UNKNOWN — the hard third of the set
#
# Everything here is ordinary petition content or transcription noise. Any of
# it read as CONFIRM commits a wrong value; any of it read as FINISHED cuts a
# complaint short. These are the cases that separate a classifier from a
# machine that agrees with everything.
# --------------------------------------------------------------------------- #

NOT_CONTROL_EN = [
    # Names. "Ya" and "Okay" are real fragments of real names.
    "Harish Kumar", "Anbu Selvan", "Meenakshi Sundaram", "Ravi",
    "Yashodha", "Okilan", "Rightson",
    # Addresses and numbers.
    "12 Kumar Street, Peelamedu", "45 Gandhi Road", "Coimbatore 641004",
    "door number 14 A", "near the bus stand",
    "thirty six", "forty five", "six hundred and four",
    # Grievance sentences, including ones containing control words.
    "The street light has not worked for three months.",
    "That's all the water we get in a week.",
    "The officer said it was correct but nothing happened.",
    "I was told to come again next month.",
    "They did not change it even after my complaint.",
    "No water has come since Monday.",
    "The road is right outside my house and it is broken.",
    "I have finished paying the tax but the receipt was not given.",
    "Water supply stopped and the drain is also blocked.",
]

NOT_CONTROL_TA = [
    "ஹரிஷ் குமார்", "அன்பு செல்வன்", "மீனாட்சி சுந்தரம்",
    "12 காந்தி தெரு, கோயம்புத்தூர்",
    "கோயம்புத்தூர் 641004",
    "எங்கள் தெருவில் மூன்று மாதமாக மின் விளக்கு எரியவில்லை.",
    "தண்ணீர் வரவில்லை என்று பலமுறை சொன்னோம்.",
    "அலுவலகத்தில் சரி என்று சொன்னார்கள் ஆனால் நடவடிக்கை இல்லை.",
    "சாலை முழுவதும் பள்ளம் இருக்கிறது.",
]

# What a transcription service returns when it was given no speech. These
# already have their own defence in `commit_guard.py` and never reach a
# classifier in service — they are here because a REPLACEMENT classifier
# would be asked about them if that defence ever changed.
STT_NOISE = [
    "...", "uh", "um", "hmm", "mm", "eh",
    "ம்", "ம்ம்",
]


def dataset() -> list[Case]:
    rows: list[Case] = []
    rows += _cases(CONFIRM_EN, "CONFIRM", "en", CONFIRMING)
    rows += _cases(CONFIRM_TA, "CONFIRM", "ta", CONFIRMING)
    rows += _cases(CONFIRM_MIXED, "CONFIRM", "mixed", CONFIRMING)

    rows += _cases(RETRY_EN, "RETRY", "en", CONFIRMING)
    rows += _cases(RETRY_TA, "RETRY", "ta", CONFIRMING)
    rows += _cases(RETRY_MIXED, "RETRY", "mixed", CONFIRMING)

    rows += _cases(CORRECT_EN, "CORRECT", "en", CONFIRMING)
    rows += _cases(CORRECT_TA, "CORRECT", "ta", CONFIRMING)
    rows += _cases(CORRECT_MIXED, "CORRECT", "mixed", CONFIRMING)

    # "Add more" only exists where there is something to add to, which is a
    # grievance. Asked at a short field, "also..." is not a control word.
    rows += _cases(ADD_MORE_EN, "ADD_MORE", "en", LONG_CONFIRMING)
    rows += _cases(ADD_MORE_TA, "ADD_MORE", "ta", LONG_CONFIRMING)
    rows += _cases(ADD_MORE_MIXED, "ADD_MORE", "mixed", LONG_CONFIRMING)

    rows += _cases(FINISHED_EN, "FINISHED", "en", DICTATING)
    rows += _cases(FINISHED_TA, "FINISHED", "ta", DICTATING)
    rows += _cases(FINISHED_MIXED, "FINISHED", "mixed", DICTATING)

    # The same content, asked about in the two places it can arrive.
    rows += _cases(NOT_CONTROL_EN, "UNKNOWN", "en", DICTATING)
    rows += _cases(NOT_CONTROL_TA, "UNKNOWN", "ta", DICTATING)
    rows += _cases(STT_NOISE, "UNKNOWN", "en", DICTATING)
    return rows


LABELS = ("CONFIRM", "RETRY", "CORRECT", "ADD_MORE", "FINISHED", "UNKNOWN")
