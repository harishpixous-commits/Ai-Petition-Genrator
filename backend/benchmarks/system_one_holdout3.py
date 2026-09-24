"""The third held-out set, and the one the reported figure comes from.

Held-out #1 caused the near-tie rule to be removed. Held-out #2 caused
romanised Tamil to be added and the coordination rule to be written. Both are
therefore spent: a set that has changed the code can only confirm the change,
never measure it.

This set was written last, run once, and nothing was altered afterwards. It
covers all four tasks — the earlier two held out only the first two — and it
over-samples the places the engine has already been shown to be weak:
romanised Tamil, coordinated complaints, inflected Tamil nouns, and names that
resemble one another.
"""

from __future__ import annotations

from benchmarks.system_one_cases import Case

_G = "Our street has had no drinking water for a week and the tank is empty."

_GRIEVANCE: tuple[tuple[str, str, str, str], ...] = (
    ("The corporation has not lifted the rubbish since Deepavali.", "SANITATION", "en", ""),
    ("My pension book was not updated at the office.", "PENSION", "en", ""),
    ("The bore well has run dry in our colony.", "WATER", "en", ""),
    ("Please issue an income certificate for the school admission.", "CERTIFICATE", "en", ""),
    ("The lamp post at the corner has been broken for weeks.", "STREET_LIGHT", "en", ""),
    ("A private party has encroached the common pathway.", "PROPERTY", "en", ""),
    ("Voltage fluctuation is damaging our appliances.", "ELECTRICITY", "en",
     "no table word matches — UNKNOWN would also be defensible"),
    ("The tar has come off the whole stretch near the school.", "ROAD", "en", ""),

    # Inflected Tamil: the virama trap, on nouns not used before.
    ("குப்பையை அகற்றவில்லை.", "SANITATION", "ta", "குப்பை inflected"),
    ("தண்ணீரை வழங்கவில்லை.", "WATER", "ta", "தண்ணீர் inflected"),
    ("சாலையில் விபத்து அதிகம், குழிகள் நிறைந்துள்ளன.", "ROAD", "ta", ""),
    ("ஓய்வூதியத்தை நிறுத்திவிட்டார்கள்.", "PENSION", "ta", "ஓய்வூதிய inflected"),
    ("மின்சாரத்தை துண்டித்துவிட்டனர்.", "ELECTRICITY", "ta", "மின்சாரம் inflected"),
    ("சான்றிதழை வழங்கக் கோருகிறேன்.", "CERTIFICATE", "ta", ""),
    ("தெருவிளக்குகள் எரியவில்லை.", "STREET_LIGHT", "ta", "plural inflection"),

    # Romanised Tamil, forms not in the tuning set.
    ("kudineer connection kedaikala", "WATER", "mixed", ""),
    ("saalai la kuzhi romba iruku", "ROAD", "mixed", ""),
    ("pension apply pannen reply illa", "PENSION", "mixed", ""),

    # Coordination, on markers not used before.
    ("We need both the drainage cleared and the water pipeline repaired.",
     "UNKNOWN", "en", "explicit both/and"),
    ("The pothole is dangerous and the street light is also dead.",
     "UNKNOWN", "en", "explicit also"),
    ("குப்பையும் சேரவில்லை, தண்ணீரும் வரவில்லை.", "UNKNOWN", "ta", "உம் on two nouns"),

    # NOT coordination: one department, two symptoms.
    ("The drain is blocked and the sewage is standing in the lane.", "SANITATION", "en",
     "both nouns are sanitation — not two complaints"),
    ("Water supply is irregular and the tank is never full.", "WATER", "en", ""),

    # Locational nouns, fourth variation.
    ("The transformer on our road keeps failing.", "ELECTRICITY", "en", "road is the setting"),
    ("சாலையில் குடிநீர் குழாய் உடைந்துள்ளது.", "WATER", "ta", "சாலை is the setting"),

    # Nothing to classify.
    ("Kindly do the needful at the earliest.", "UNKNOWN", "en", ""),
    ("உதவி செய்யுங்கள்.", "UNKNOWN", "ta", ""),
)

_RELATIONSHIP: tuple[tuple[dict, str, str, str], ...] = (
    ({"kind": "pdf", "citizen_name": "Murugan", "document_name": "Murugan",
      "text": "Respected Sir, Subject: request for a new water connection."},
     "OWN_PREVIOUS_PETITION", "en", ""),
    ({"kind": "pdf", "citizen_name": "Murugan", "document_name": "Muruganantham",
      "text": "Respected Sir, Subject: request for a new water connection."},
     "THIRD_PARTY_SUPPORTING_DOCUMENT", "en",
     "a prefix is NOT a short form — different person"),
    ({"kind": "pdf", "citizen_name": "Murugan Selvam", "document_name": "Murugan",
      "text": "Respected Sir, Subject: request for a new water connection."},
     "OWN_PREVIOUS_PETITION", "en", "long against short, the other way round"),
    ({"kind": "pdf", "citizen_name": "", "document_name": "Kavitha",
      "text": "Respected Sir, I humbly request repair of the road."},
     "UNKNOWN", "en", "no citizen name to compare against — must not guess"),
    ({"kind": "pdf", "citizen_name": "Kavitha", "document_name": "Kavitha",
      "text": "In reply to your petition, the work has been sanctioned by this office."},
     "GOVERNMENT_RESPONSE", "en", "a reply naming the citizen is still a reply"),
    ({"kind": "pdf", "citizen_name": "Kavitha", "document_name": "",
      "text": "Received your petition. Acknowledgement number 5567."},
     "ACKNOWLEDGEMENT", "en", ""),
    ({"kind": "photo", "citizen_name": "Kavitha", "document_name": "",
      "text": "some caption text"},
     "PHOTO_EVIDENCE", "en", "a photo stays a photo even with a caption"),
    ({"kind": "pdf", "citizen_name": "Kavitha", "document_name": "Devi",
      "text": "இந்த சான்றிதழ் வழங்கப்படுகிறது."},
     "CERTIFICATE", "ta", "a certificate is not a third-party petition"),
    ({"kind": "pdf", "citizen_name": "Kavitha", "document_name": "",
      "text": "Electricity bill. Consumer number 44/2. Amount 610."},
     "GENERAL_SUPPORTING_DOCUMENT", "en", ""),
)

_RELEVANCE: tuple[tuple[dict, str, str, str], ...] = (
    ({"kind": "previous_petition",
      "text": "Respected Sir, the drinking water supply to our street stopped "
              "and the overhead tank is empty. I request immediate repair.",
      "grievance": _G},
     "HIGHLY_RELEVANT", "en", ""),
    ({"kind": "other", "text": "Driving licence renewal receipt. Valid to 2030.",
      "grievance": _G},
     "UNRELATED", "en", ""),
    ({"kind": "other", "text": "", "grievance": _G, "readable": False},
     "UNKNOWN", "en", "unreadable is not unrelated"),
)

_REVIEW: tuple[tuple[dict, str, str, str], ...] = (
    ({"relationship": "THIRD_PARTY_SUPPORTING_DOCUMENT", "relevance": "UNRELATED",
      "category": "WATER", "attention": False},
     "YES", "en", "somebody else's document, always"),
    ({"relationship": "OWN_PREVIOUS_PETITION", "relevance": "HIGHLY_RELEVANT",
      "category": "SANITATION", "attention": False},
     "NO", "en", "clean"),
    ({"relationship": "UNKNOWN", "relevance": "HIGHLY_RELEVANT",
      "category": "WATER", "attention": False},
     "YES", "en", "an unidentified document needs a human"),
    ({"relationship": "GOVERNMENT_RESPONSE", "relevance": "PARTIALLY_RELEVANT",
      "category": "UNKNOWN", "attention": False},
     "YES", "en", "no category could be read"),
)


def dataset() -> list[Case]:
    cases: list[Case] = []
    for text, want, language, note in _GRIEVANCE:
        cases.append(Case("grievance", want, language, note,
                          {"grievance": text, "language": language}))
    for payload, want, language, note in _RELATIONSHIP:
        cases.append(Case("relationship", want, language, note,
                          dict(payload, language=language)))
    for payload, want, language, note in _RELEVANCE:
        cases.append(Case("relevance", want, language, note,
                          dict(payload, language=language)))
    for payload, want, language, note in _REVIEW:
        cases.append(Case("review", want, language, note, dict(payload)))
    return cases
