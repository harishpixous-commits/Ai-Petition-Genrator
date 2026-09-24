"""THE FINAL HOLDOUT. Run once. Never tuned against. Do not edit to pass.

Three tiers now exist and they must not be confused with one another:

    system_one_cases          DEVELOPMENT / TUNING — changed freely
    system_one_holdout{,2,3}  VALIDATION — each one caused a fix and is spent
    system_one_final_tamil    THIS FILE — the honest figure

Every earlier set has, at some point, made the tables change. That is what
validation sets are for, and it is also what makes them useless as a final
measure: they agree with the code because the code was adjusted until they
did. This file exists so there is one number nobody has optimised against.

WHAT IT COVERS, because this is a Tamil Nadu service and the earlier sets were
written by somebody thinking in English:

    Tamil script            written as a literate citizen writes
    inflected Tamil         the virama trap, which cost three cases once
    spoken/colloquial Tamil what people actually say, not what is written
    romanised Tamil         how it is typed at a keyboard with no Tamil layout
    Tamil-English mixed     the ordinary register of speech here
    STT-style errors        what the recogniser hears, which is not what was said

THE RULE FOR THIS FILE. If a case here fails, the failure is reported. A fix
may be made, but it belongs in the tuning set with a note, and this file is
then spent and must be replaced by a new one. Editing a label here to make a
score look better destroys the only unbiased measurement in the project.
"""

from __future__ import annotations

from benchmarks.system_one_cases import Case

_GRIEVANCE: tuple[tuple[str, str, str, str], ...] = (
    # --- Romanised Tamil, as typed ------------------------------------
    ("thanni varala", "WATER", "mixed", "given as an example by the user"),
    ("road seri illa", "ROAD", "mixed", "given as an example by the user"),
    ("corporation complaint panniten", "UNKNOWN", "mixed",
     "names no subject at all — and 'corporation' must not read as 'ration'"),
    ("kudineer problem", "WATER", "mixed", "given as an example by the user"),
    ("kuppai eduka varala", "SANITATION", "mixed", ""),
    ("current romba neram illa", "ELECTRICITY", "mixed",
     "colloquial: 'current' IS the word for electricity here. Labelled UNKNOWN"
     " at first, which was a prediction about the code rather than ground"
     " truth — a labelling error, corrected before the set was scored."),
    ("street light eriyala neraya naal", "STREET_LIGHT", "mixed", ""),
    ("pension varala ippo rendu maasam", "PENSION", "mixed", ""),
    ("ration kadai la arisi illa", "WELFARE", "mixed", ""),
    ("saalai la kuzhi niraya iruku", "ROAD", "mixed", ""),

    # --- STT-style spelling, which is not how anyone writes -----------
    ("thaneer varala enga area la", "WATER", "mixed", "thanni heard as thaneer"),
    ("kudi neer connection kudukala", "WATER", "mixed", "split into two words"),
    ("kupai lorry varuvathillai", "SANITATION", "mixed", "kuppai with one p"),
    ("penshan money varala", "PENSION", "mixed", "pension as heard"),
    ("streetlight repair pannunga", "STREET_LIGHT", "mixed", "run together"),

    # --- Tamil script, written -----------------------------------------
    ("ரேஷன் கிடைக்கவில்லை", "WELFARE", "ta", "given as an example by the user"),
    ("குடிநீரும் வரவில்லை", "WATER", "ta",
     "given as an example by the user — உம் on ONE noun is not coordination"),
    ("சாலை மிகவும் மோசமாக உள்ளது", "ROAD", "ta", ""),
    ("குப்பை தொட்டி நிரம்பி வழிகிறது", "SANITATION", "ta", ""),
    ("மின்சாரம் அடிக்கடி போய்விடுகிறது", "ELECTRICITY", "ta", ""),
    ("தெருவிளக்கு பழுதாகி உள்ளது", "STREET_LIGHT", "ta", ""),
    ("பட்டா இன்னும் வழங்கப்படவில்லை", "PROPERTY", "ta", ""),

    # --- Inflected Tamil, on nouns no earlier set used ------------------
    ("குப்பையால் நோய் பரவுகிறது", "SANITATION", "ta", "குப்பை + ஆல்"),
    ("தண்ணீரின் தரம் மோசம்", "WATER", "ta", "தண்ணீர் + இன்"),
    ("சாலையை சரிசெய்யுங்கள்", "ROAD", "ta", "சாலை + ஐ"),
    ("ஓய்வூதியத்தில் குறைவு", "PENSION", "ta", "ஓய்வூதியம் → ஓய்வூதியத்தில்"),
    ("சான்றிதழுக்கு விண்ணப்பித்தேன்", "CERTIFICATE", "ta", "சான்றிதழ் + உக்கு"),

    # --- Spoken/colloquial Tamil ---------------------------------------
    ("தண்ணி வரல ஐயா", "WATER", "ta", "spoken form: தண்ணி not தண்ணீர்"),
    ("கரண்ட் போயிடுச்சு", "ELECTRICITY", "ta",
     "spoken form of 'current'. Same labelling error as above: what the code"
     " was expected to do is not what the answer is."),
    ("ரோடு ரொம்ப மோசம்", "ROAD", "ta", "ரோடு, the English word in Tamil script"),

    # --- Genuinely two subjects, in mixed register ----------------------
    ("thanni um varala kuppai um eduka la", "UNKNOWN", "mixed",
     "romanised உம் coordination — expected to be a gap"),
    ("குப்பையும் தண்ணீரும் பிரச்சினை", "UNKNOWN", "ta", "written உம் coordination"),

    # --- Nothing to classify -------------------------------------------
    ("ayya konjam help pannunga", "UNKNOWN", "mixed", ""),
    ("ஐயா உதவி வேண்டும்", "UNKNOWN", "ta", ""),
)

_RELATIONSHIP: tuple[tuple[dict, str, str, str], ...] = (
    # A Tamil petition naming somebody else: the reported bug, in the
    # language most of these petitions are actually written in.
    ({"kind": "previous_petition", "citizen_name": "ஹரிஷ்",
      "document_name": "சேதுபாலா",
      "text": "மதிப்பிற்குரிய ஐயா, பொருள்: குடிநீர் வசதி கோரி மனு. "
              "நடவடிக்கை எடுக்குமாறு கேட்டுக்கொள்கிறேன்."},
     "THIRD_PARTY_SUPPORTING_DOCUMENT", "ta", ""),
    ({"kind": "previous_petition", "citizen_name": "ஹரிஷ்",
      "document_name": "ஹரிஷ்",
      "text": "மதிப்பிற்குரிய ஐயா, பொருள்: குடிநீர் வசதி கோரி மனு. "
              "நடவடிக்கை எடுக்குமாறு கேட்டுக்கொள்கிறேன்."},
     "OWN_PREVIOUS_PETITION", "ta", ""),
    # A Tamil petition that carries its own acknowledgement number. The
    # English version of this was misread as a receipt.
    ({"kind": "previous_petition", "citizen_name": "Murugan",
      "document_name": "Murugan",
      "text": "மதிப்பிற்குரிய ஐயா, பொருள்: சாலை பழுது. ஒப்புகை எண் 7781. "
              "கேட்டுக்கொள்கிறேன்."},
     "OWN_PREVIOUS_PETITION", "ta", "a petition that quotes its own receipt number"),
    ({"kind": "acknowledgement", "citizen_name": "Murugan", "document_name": "",
      "text": "ரசீது எண் 7781. உங்கள் மனு பெறப்பட்டது."},
     "ACKNOWLEDGEMENT", "ta", "a real receipt, with no salutation"),
    ({"kind": "pdf", "citizen_name": "Murugan", "document_name": "",
      "text": "உங்கள் மனுவிற்கு பதிலளிக்கிறேன். அலுவலக குறிப்பு படி "
              "அனுமதிக்கப்பட்டது."},
     "GOVERNMENT_RESPONSE", "ta", ""),
    # Mixed-script names: the citizen typed Tamil, the document is in Latin.
    ({"kind": "previous_petition", "citizen_name": "ஹரிஷ்",
      "document_name": "Sethubala",
      "text": "Respected Sir, Subject: water supply. I humbly request action."},
     "THIRD_PARTY_SUPPORTING_DOCUMENT", "mixed",
     "two scripts, two different people — must not be read as a match"),
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
