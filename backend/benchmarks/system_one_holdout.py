"""Cases written AFTER the word tables were tuned, and never tuned against.

WHY THIS FILE IS SEPARATE. `system_one_cases.py` scored 56/61, five failures
were diagnosed, the tables were changed, and it then scored 61/61. That second
number is close to meaningless on its own: the rules were edited until the
labels matched. It measures agreement with itself.

So these cases were written afterwards, from the same four tasks, and run
once. Whatever they say is the reported figure. Nothing here may be used to
tune the tables — if a case fails and the rule is genuinely wrong, the fix
belongs in the tuning set with a note, and this file gets fresh cases.

Same rules as the tuning set: every line synthetic, no real citizen data, no
Aadhaar, no mobile number, no address that exists.
"""

from __future__ import annotations

from benchmarks.system_one_cases import Case

_GRIEVANCE: tuple[tuple[str, str, str, str], ...] = (
    # Plain single-subject complaints, both scripts.
    ("My old age pension has not been credited for three months.", "PENSION", "en", ""),
    ("Garbage has not been collected from our area for ten days.", "SANITATION", "en", ""),
    ("The transformer near our school is sparking dangerously.", "ELECTRICITY", "en", ""),
    ("I applied for a community certificate two months ago and there is no reply.",
     "CERTIFICATE", "en", ""),
    ("Please renew the licence for my provision shop.", "LICENCE", "en", ""),
    ("There is encroachment on the government land behind our house.", "PROPERTY", "en", ""),
    ("The public toilet near the market is never cleaned.", "SANITATION", "en", ""),
    ("ரேஷன் கடையில் இந்த மாதம் அரிசி தரவில்லை.", "WELFARE", "ta", ""),
    ("மின்சாரம் அடிக்கடி துண்டிக்கப்படுகிறது.", "ELECTRICITY", "ta", ""),
    ("பட்டா மாற்றம் செய்ய விண்ணப்பித்தேன், இன்னும் நடவடிக்கை இல்லை.", "PROPERTY", "ta", ""),
    ("தெருவிளக்கு ஒரு மாதமாக எரியவில்லை.", "STREET_LIGHT", "ta", ""),
    ("சாலையில் பெரிய குழி உள்ளது, விபத்து நடக்கிறது.", "ROAD", "ta", ""),
    ("குடிநீர் குழாய் உடைந்து தண்ணீர் வீணாகிறது.", "WATER", "ta", ""),

    # The locational-word trap again, on sentences it has not seen.
    ("There is no water in our street since Monday.", "WATER", "en",
     "street is where they live, not the subject"),
    ("எங்கள் தெருவில் குப்பை அள்ளப்படவில்லை.", "SANITATION", "ta",
     "தெரு is locational; the subject is the rubbish"),
    ("street la light eriyala", "STREET_LIGHT", "mixed", ""),
    ("enga area la drainage block aagiduchu", "SANITATION", "mixed", ""),

    # No subject at all: UNKNOWN is the right answer.
    ("I would like to submit a complaint.", "UNKNOWN", "en", ""),
    ("நான் ஒரு புகார் கொடுக்க விரும்புகிறேன்.", "UNKNOWN", "ta", ""),
    ("Thank you for your help.", "UNKNOWN", "en", ""),

    # Genuinely two subjects: UNKNOWN is also right.
    ("The drain is blocked and the road above it has collapsed.", "UNKNOWN", "en",
     "two subjects, honestly ambiguous"),

    # HARD. A human officer answers these without hesitating; they carry a
    # second subject as circumstance, not as a second complaint.
    ("Sewage is overflowing onto the main road near the bus stand.", "SANITATION", "en",
     "the road is where it overflows; the complaint is the sewage"),
    ("My widow pension allowance has been stopped without notice.", "PENSION", "en",
     "widow pension is one thing, not pension plus welfare"),
    ("Drinking water is coming mixed with sewage from the tap.", "WATER", "en",
     "contaminated supply is a water complaint"),
    ("The borewell motor has burnt and the whole colony is without water.",
     "WATER", "en", ""),
)

_RELATIONSHIP: tuple[tuple[dict, str, str, str], ...] = (
    ({"kind": "pdf", "citizen_name": "Meena", "document_name": "Meena",
      "text": "Respected Sir, I request action on the drainage in my street. Petition dated 4 March."},
     "OWN_PREVIOUS_PETITION", "en", ""),
    ({"kind": "pdf", "citizen_name": "Meena", "document_name": "Rajendran",
      "text": "Respected Sir, I request action on the drainage in my street. Petition dated 4 March."},
     "THIRD_PARTY_SUPPORTING_DOCUMENT", "en", "the reported bug, on a new name pair"),
    ({"kind": "pdf", "citizen_name": "Meena", "document_name": "",
      "text": "Respected Sir, I humbly request that the street light be repaired."},
     "UNKNOWN", "en", "no petitioner legible — never assume it is theirs"),
    ({"kind": "pdf", "citizen_name": "Arun", "document_name": "Arun Prakash",
      "text": "மதிப்பிற்குரிய ஐயா, எங்கள் பகுதியில் சாலை பழுது பார்க்க கேட்டுக்கொள்கிறேன்."},
     "OWN_PREVIOUS_PETITION", "ta", "short name against long is the same person"),
    ({"kind": "pdf", "citizen_name": "Arun", "document_name": "Kalaiselvi",
      "text": "மதிப்பிற்குரிய ஐயா, எங்கள் பகுதியில் சாலை பழுது பார்க்க கேட்டுக்கொள்கிறேன்."},
     "THIRD_PARTY_SUPPORTING_DOCUMENT", "ta", ""),
    ({"kind": "pdf", "citizen_name": "Meena", "document_name": "Meena",
      "text": "With reference to your petition dated 4 March, this office has sanctioned the work."},
     "GOVERNMENT_RESPONSE", "en", "a reply quotes the petition it answers"),
    ({"kind": "pdf", "citizen_name": "Meena", "document_name": "",
      "text": "Acknowledgement: we have received your petition. Token number 4412."},
     "ACKNOWLEDGEMENT", "en", ""),
    ({"kind": "pdf", "citizen_name": "Meena", "document_name": "",
      "text": "This is to certify that the applicant belongs to the said community."},
     "CERTIFICATE", "en", ""),
    ({"kind": "photo", "citizen_name": "Meena", "document_name": "", "text": ""},
     "PHOTO_EVIDENCE", "en", ""),
    ({"kind": "pdf", "citizen_name": "Meena", "document_name": "", "text": ""},
     "UNKNOWN", "en", "nothing readable"),
    ({"kind": "pdf", "citizen_name": "Meena", "document_name": "",
      "text": "Statement of account for the period ending 31 March. Closing balance carried forward."},
     "GENERAL_SUPPORTING_DOCUMENT", "en", ""),
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
