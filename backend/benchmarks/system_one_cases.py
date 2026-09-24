"""A labelled evaluation set for the four System-1 tasks, Tamil and English.

WHY IT EXISTS. The same reason as `intent_cases.py` beside it: a proposal to
answer these questions with a model has to be measured against whatever is
answering them now, on cases written down in advance. Tuning a word table
against whichever sentence was last typed into a terminal is how a classifier
comes to score well on nothing in particular.

NO REAL CITIZEN DATA. Every line is synthetic. The names are common Tamil
Nadu names used as labels and decoys, the addresses and reference numbers are
invented, and no Aadhaar, mobile number or real grievance appears. Nothing
here came from a session.

WHAT MAKES IT HONEST. Three deliberate traps, each one a mistake that was
actually made:

    LOCATIONAL WORDS. Almost every Tamil grievance contains "தெரு" — street —
    because that is where people live, not because the complaint is about the
    road. A table that reads it as ROAD classifies half the water complaints
    in the state as road complaints. Several cases below exist only to catch
    that.

    A PETITION IS NOT AUTOMATICALLY THEIRS. A citizen called Harish attached
    a previous petition belonging to Sethubala, and the details from it were
    offered as replacements for his own. A petition naming somebody else is a
    THIRD PARTY's document; a petition naming nobody legible is UNKNOWN, not
    OWN.

    A REPLY QUOTES THE PETITION IT ANSWERS. A government response carries
    every marker a petition does. Read in the wrong order it is a petition.

UNKNOWN IS A CORRECT ANSWER and several cases expect it. Forcing an uncertain
input into the nearest label is the failure mode these tasks are exposed to.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Case:
    task: str                     # grievance | relationship | relevance | review
    want: str                     # the expected label
    language: str                 # en | ta | mixed
    note: str = ""                # why this case is here, when it is not obvious
    payload: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Grievance category
# --------------------------------------------------------------------------- #

_GRIEVANCE: tuple[tuple[str, str, str, str], ...] = (
    # (text, want, language, note)
    ("There is no drinking water supply for five days in our street.", "WATER", "en", ""),
    ("The water tank in our area has not been filled this month.", "WATER", "en", ""),
    ("Drinking water pipeline is broken near the temple.", "WATER", "en", ""),
    ("எங்கள் தெருவில் மூன்று நாட்களாக குடிநீர் வரவில்லை.", "WATER", "ta",
     "the word for street is in it and the complaint is not about the road"),
    ("குடிநீர் குழாய் உடைந்து கிடக்கிறது.", "WATER", "ta", ""),
    ("தண்ணீர் தொட்டி நிரப்பப்படவில்லை.", "WATER", "ta", ""),
    ("water supply சரியா வரலை எங்க தெருவுல", "WATER", "mixed", ""),

    ("The road outside my house is full of potholes.", "ROAD", "en", ""),
    ("The tar road was dug up and never repaired.", "ROAD", "en", ""),
    ("சாலையில் பெரிய குழி விழுந்துள்ளது.", "ROAD", "ta", ""),
    ("எங்கள் பகுதி சாலை மிகவும் சேதமடைந்துள்ளது.", "ROAD", "ta", ""),
    ("road ரொம்ப மோசமா இருக்கு, குழி நிறைய", "ROAD", "mixed", ""),

    ("The street light outside my house has not worked for three months.",
     "STREET_LIGHT", "en", ""),
    ("தெருவிளக்கு எரியவில்லை.", "STREET_LIGHT", "ta", ""),
    ("street light போடலை எங்க area la", "STREET_LIGHT", "mixed", ""),

    ("Garbage has not been collected from our lane for two weeks.",
     "SANITATION", "en", ""),
    ("The drainage is overflowing near the school.", "SANITATION", "en", ""),
    ("கழிவுநீர் வடிகால் அடைத்துக்கொண்டது.", "SANITATION", "ta", ""),
    ("குப்பை அள்ளப்படவில்லை.", "SANITATION", "ta", ""),

    ("My old age pension has not been credited for four months.", "PENSION", "en", ""),
    ("ஓய்வூதியம் வரவில்லை.", "PENSION", "ta", ""),

    ("I have not received the Magalir Urimai Thogai amount.", "WELFARE", "en", ""),
    ("ரேஷன் அட்டையில் பொருட்கள் வழங்கப்படவில்லை.", "WELFARE", "ta", ""),

    ("My trade licence renewal has been pending for six months.", "LICENCE", "en", ""),
    ("உரிமம் புதுப்பிக்கப்படவில்லை.", "LICENCE", "ta", ""),

    ("I applied for an income certificate and it has not been issued.",
     "CERTIFICATE", "en", ""),
    ("சாதிச் சான்றிதழ் இன்னும் வழங்கப்படவில்லை.", "CERTIFICATE", "ta", ""),

    ("There is an encroachment on my patta land.", "PROPERTY", "en", ""),
    ("பட்டா நிலத்தில் ஆக்கிரமிப்பு உள்ளது.", "PROPERTY", "ta", ""),

    ("There are frequent power cuts in our area.", "ELECTRICITY", "en", ""),
    ("மின்சாரம் அடிக்கடி தடைபடுகிறது.", "ELECTRICITY", "ta", ""),

    # --- UNKNOWN is the right answer -------------------------------------- #
    ("", "UNKNOWN", "en", "nothing said"),
    ("Please help me.", "UNKNOWN", "en", "no subject at all"),
    ("உதவி செய்யுங்கள்.", "UNKNOWN", "ta", "no subject at all"),
    ("I am writing about a matter in my locality.", "UNKNOWN", "en",
     "a complaint that names no subject"),
    ("The road was dug up to lay a water pipeline and neither was finished.",
     "UNKNOWN", "en",
     "genuinely two subjects; picking one silently is worse than saying so"),
)


# --------------------------------------------------------------------------- #
# Attachment relationship
# --------------------------------------------------------------------------- #
#
# `citizen` is who is filing THIS petition. `named` is the petitioner the
# document itself names. The gap between them is the whole task.

_PETITION_EN = ("Respected Sir, Subject: repair of the street light. "
                "I request that the light outside my house be repaired.")
_PETITION_TA = ("மதிப்பிற்குரிய ஐயா, பொருள்: தெருவிளக்கு சரிசெய்தல். "
                "எனது வீட்டின் முன் உள்ள விளக்கை சரிசெய்யுமாறு கேட்டுக்கொள்கிறேன்.")

_RELATIONSHIP: tuple[tuple[dict, str, str, str], ...] = (
    ({"kind": "previous_petition", "text": _PETITION_EN,
      "citizen_name": "Harish", "document_name": "Harish"},
     "OWN_PREVIOUS_PETITION", "en", ""),
    ({"kind": "previous_petition", "text": _PETITION_EN,
      "citizen_name": "Harish", "document_name": "Harish Kumar"},
     "OWN_PREVIOUS_PETITION", "en", "the same person, written short and long"),
    ({"kind": "previous_petition", "text": _PETITION_TA,
      "citizen_name": "ஹரிஷ்", "document_name": "ஹரிஷ்"},
     "OWN_PREVIOUS_PETITION", "ta", ""),

    # THE REPORTED CASE.
    ({"kind": "previous_petition", "text": _PETITION_EN,
      "citizen_name": "Harish", "document_name": "Sethubala"},
     "THIRD_PARTY_SUPPORTING_DOCUMENT", "en",
     "the bug: a petition naming somebody else was treated as the citizen's own"),
    ({"kind": "previous_petition", "text": _PETITION_TA,
      "citizen_name": "ஹரிஷ்", "document_name": "சேதுபாலா"},
     "THIRD_PARTY_SUPPORTING_DOCUMENT", "ta", "the same, in Tamil"),
    ({"kind": "previous_petition", "text": _PETITION_EN,
      "citizen_name": "Harish Kumar", "document_name": "Harish Kumaresan"},
     "THIRD_PARTY_SUPPORTING_DOCUMENT", "en",
     "two different people whose names begin the same way"),

    ({"kind": "previous_petition", "text": _PETITION_EN,
      "citizen_name": "Harish", "document_name": ""},
     "UNKNOWN", "en",
     "a petition with no legible petitioner is not assumed to be theirs"),

    ({"kind": "acknowledgement",
      "text": "Acknowledgement receipt. Your petition has been received. Token AP/2026/34A7E7.",
      "citizen_name": "Harish", "document_name": ""},
     "ACKNOWLEDGEMENT", "en", ""),
    ({"kind": "other", "text": "ஒப்புகைச் சீட்டு. உங்கள் மனு பெறப்பட்டது.",
      "citizen_name": "ஹரிஷ்", "document_name": ""},
     "ACKNOWLEDGEMENT", "ta", ""),

    ({"kind": "other",
      "text": ("With reference to your petition dated 16-09-2026, this office "
               "informs you that the matter has been disposed."),
      "citizen_name": "Harish", "document_name": "Harish"},
     "GOVERNMENT_RESPONSE", "en",
     "a reply quotes the petition it answers, so it carries every petition marker"),
    ({"kind": "other",
      "text": "உங்கள் மனுவிற்கு பதிலளிக்கிறேன். அலுவலக குறிப்பு படி நடவடிக்கை எடுக்கப்பட்டது.",
      "citizen_name": "ஹரிஷ்", "document_name": ""},
     "GOVERNMENT_RESPONSE", "ta", ""),

    ({"kind": "other",
      "text": "This is to certify that the applicant is a resident of this village.",
      "citizen_name": "Harish", "document_name": ""},
     "CERTIFICATE", "en", ""),

    ({"kind": "photo", "text": "", "citizen_name": "Harish", "document_name": ""},
     "PHOTO_EVIDENCE", "en", ""),

    ({"kind": "other", "text": "", "citizen_name": "Harish", "document_name": ""},
     "UNKNOWN", "en", "nothing could be read from it"),

    ({"kind": "other",
      "text": "Electricity bill for the period June to August. Amount due 420 rupees.",
      "citizen_name": "Harish", "document_name": ""},
     "GENERAL_SUPPORTING_DOCUMENT", "en", "a real document that is none of the named kinds"),
)


# --------------------------------------------------------------------------- #
# Attachment relevance
# --------------------------------------------------------------------------- #

_WATER_GRIEVANCE = ("There has been no drinking water supply in our street "
                    "for five days and the pipeline is broken.")

_RELEVANCE: tuple[tuple[dict, str, str, str], ...] = (
    ({"kind": "previous_petition",
      "text": ("Respected Sir, the drinking water supply in our street has "
               "stopped and the pipeline near the tank is broken. I request repair."),
      "grievance": _WATER_GRIEVANCE},
     "HIGHLY_RELEVANT", "en", ""),
    ({"kind": "other",
      "text": "Electricity bill for the period June to August. Amount due 420 rupees.",
      "grievance": _WATER_GRIEVANCE},
     "UNRELATED", "en", ""),
    ({"kind": "other", "text": "", "grievance": _WATER_GRIEVANCE,
      "readable": False},
     "UNKNOWN", "en", "unreadable is not unrelated"),
    ({"kind": "other", "text": "Anything at all.", "grievance": ""},
     "UNKNOWN", "en", "nothing to compare it against yet"),
)


# --------------------------------------------------------------------------- #
# Officer review
# --------------------------------------------------------------------------- #

_REVIEW: tuple[tuple[dict, str, str, str], ...] = (
    ({"relationship": "THIRD_PARTY_SUPPORTING_DOCUMENT", "relevance": "HIGHLY_RELEVANT",
      "category": "WATER", "attention": False},
     "YES", "en", "somebody else's document is always worth a look"),
    ({"relationship": "OWN_PREVIOUS_PETITION", "relevance": "HIGHLY_RELEVANT",
      "category": "WATER", "attention": False},
     "NO", "en", "everything placed and nothing odd"),
    ({"relationship": "OWN_PREVIOUS_PETITION", "relevance": "HIGHLY_RELEVANT",
      "category": "WATER", "attention": True},
     "YES", "en", "the record is already flagged"),
    ({"relationship": "UNKNOWN", "relevance": "HIGHLY_RELEVANT",
      "category": "WATER", "attention": False},
     "YES", "en", "an attachment that could not be placed"),
    ({"relationship": "OWN_PREVIOUS_PETITION", "relevance": "UNRELATED",
      "category": "WATER", "attention": False},
     "YES", "en", "evidence that does not appear to bear on the complaint"),
    ({"relationship": "OWN_PREVIOUS_PETITION", "relevance": "HIGHLY_RELEVANT",
      "category": "UNKNOWN", "attention": False},
     "YES", "en", "a complaint nothing could categorise"),
)


def dataset() -> list[Case]:
    """Every case, in one list."""
    cases: list[Case] = []
    for text, want, language, note in _GRIEVANCE:
        cases.append(Case("grievance", want, language, note, {"grievance": text}))
    for payload, want, language, note in _RELATIONSHIP:
        cases.append(Case("relationship", want, language, note, dict(payload)))
    for payload, want, language, note in _RELEVANCE:
        cases.append(Case("relevance", want, language, note, dict(payload)))
    for payload, want, language, note in _REVIEW:
        cases.append(Case("review", want, language, note, dict(payload)))
    return cases
