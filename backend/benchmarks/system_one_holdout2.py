"""A second held-out set, written after the weighting fix and never tuned on.

Held-out #1 informed a change — the near-tie rule was removed because of it —
so it is spent as evidence: it can only confirm a fix now, not measure one.
This set is fresh, run once, and its number is the reported one.

It deliberately over-samples the one weakness both earlier sets exposed:
complaints that name two subjects. Four cases below are genuinely two-subject
and expect UNKNOWN, so that the size of that gap is measured rather than
asserted.
"""

from __future__ import annotations

from benchmarks.system_one_cases import Case

_GRIEVANCE: tuple[tuple[str, str, str, str], ...] = (
    # Single subject, the ordinary case.
    ("The overhead tank has not been cleaned in a year.", "WATER", "en", ""),
    ("Our ration card has not been renewed despite three visits.", "WELFARE", "en", ""),
    ("The birth certificate for my daughter has not been issued.", "CERTIFICATE", "en", ""),
    ("Street lights on the temple lane stay off all night.", "STREET_LIGHT", "en", ""),
    ("There are potholes everywhere after the rain.", "ROAD", "en", ""),
    ("The sewage line behind the school is leaking.", "SANITATION", "en", ""),
    ("Power cut happens every evening for two hours.", "ELECTRICITY", "en", ""),
    ("My application for a trade permit is pending since January.", "LICENCE", "en", ""),
    ("Someone has put a fence on my survey number.", "PROPERTY", "en", ""),
    ("The old age pension amount was reduced without any notice.", "PENSION", "en", ""),
    ("குடிநீர் தொட்டி பழுதடைந்துள்ளது.", "WATER", "ta", ""),
    ("எங்கள் பகுதியில் சாக்கடை நிரம்பி வழிகிறது.", "SANITATION", "ta", ""),
    ("மின்மாற்றி பழுதாகி உள்ளது.", "ELECTRICITY", "ta", ""),
    ("முதியோர் ஓய்வூதியம் வரவில்லை.", "PENSION", "ta", ""),
    ("சான்றிதழ் வழங்கப்படவில்லை.", "CERTIFICATE", "ta", ""),
    ("நடைபாதை முழுவதும் சேதமடைந்துள்ளது.", "ROAD", "ta", ""),
    ("விளக்கு எரியவில்லை எங்கள் தெருவில்.", "STREET_LIGHT", "ta", ""),
    ("ஆக்கிரமிப்பு நீக்க கோரிக்கை.", "PROPERTY", "ta", ""),

    # Tanglish, which is how a great many citizens actually speak.
    ("thanni varala two weeks aachu", "WATER", "mixed", "தண்ணீர் romanised — likely a gap"),
    ("pension money credit aagala", "PENSION", "mixed", ""),
    ("kuppai collect panna varala", "SANITATION", "mixed", "குப்பை romanised"),

    # The locational trap, third variation.
    ("There is no light in our street at night.", "STREET_LIGHT", "en", ""),
    ("The garbage bin on our road is overflowing.", "SANITATION", "en",
     "road is the setting"),
    ("தெருவில் தண்ணீர் தேங்கி நிற்கிறது.", "WATER", "ta", ""),

    # Genuinely two subjects. This is the measured weakness.
    ("The road is damaged and the street lights are also not working.",
     "UNKNOWN", "en", "two subjects"),
    ("Both the drainage and the drinking water pipeline need repair.",
     "UNKNOWN", "en", "two subjects"),
    ("சாலையும் சேதம், குடிநீரும் வரவில்லை.", "UNKNOWN", "ta", "two subjects"),
    ("Garbage is not collected and the toilet is broken.", "SANITATION", "en",
     "two complaints but ONE department — not a tie"),

    # Nothing classifiable.
    ("I want to meet the officer regarding my issue.", "UNKNOWN", "en", ""),
    ("வணக்கம் ஐயா.", "UNKNOWN", "ta", ""),
)

_RELATIONSHIP: tuple[tuple[dict, str, str, str], ...] = (
    ({"kind": "pdf", "citizen_name": "Lakshmi Priya", "document_name": "Lakshmi Priya",
      "text": "Respected Madam, Subject: request for repair of the overhead tank."},
     "OWN_PREVIOUS_PETITION", "en", ""),
    ({"kind": "pdf", "citizen_name": "Lakshmi Priya", "document_name": "Lakshmi",
      "text": "Respected Madam, Subject: request for repair of the overhead tank."},
     "OWN_PREVIOUS_PETITION", "en", "short form of the same name"),
    ({"kind": "pdf", "citizen_name": "Lakshmi Priya", "document_name": "Lakshmi Narayanan",
      "text": "Respected Madam, Subject: request for repair of the overhead tank."},
     "THIRD_PARTY_SUPPORTING_DOCUMENT", "en",
     "shares a first word and is NOT the same person"),
    ({"kind": "pdf", "citizen_name": "Senthil", "document_name": "Senthil",
      "text": "Your petition dated 12 January has been disposed. This office regrets."},
     "GOVERNMENT_RESPONSE", "en", ""),
    ({"kind": "image", "citizen_name": "Senthil", "document_name": "", "text": ""},
     "UNKNOWN", "en", "an image with no text read is not automatically photo evidence"),
    ({"kind": "pdf", "citizen_name": "Senthil", "document_name": "",
      "text": "ரசீது எண் 8821. உங்கள் மனு பெறப்பட்டது.", },
     "ACKNOWLEDGEMENT", "ta", ""),
    ({"kind": "pdf", "citizen_name": "Senthil", "document_name": "",
      "text": "சான்றளிக்கப்படுகிறது இவர் இந்த ஊரில் வசிக்கிறார்."},
     "CERTIFICATE", "ta", ""),
    ({"kind": "pdf", "citizen_name": "Senthil", "document_name": "Devi",
      "text": "மதிப்பிற்குரிய ஐயா, பொருள்: குடிநீர் வசதி கோரி மனு."},
     "THIRD_PARTY_SUPPORTING_DOCUMENT", "ta", ""),
)


def dataset() -> list[Case]:
    cases: list[Case] = []
    for text, want, language, note in _GRIEVANCE:
        cases.append(Case("grievance", want, language, note,
                          {"grievance": text, "language": language}))
    for payload, want, language, note in _RELATIONSHIP:
        cases.append(Case("relationship", want, language, note,
                          dict(payload, language=language)))
    return cases
