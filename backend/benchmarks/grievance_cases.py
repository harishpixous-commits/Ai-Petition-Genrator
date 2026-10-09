"""What a citizen is complaining about, as cases that can be scored.

WHY THIS EXISTS. `system_one.DeterministicProvider.classify_grievance` reads a
grievance and names one of eleven subjects, or UNKNOWN. Nothing measured it.
The category is a HINT — it never routes a petition, and an AST test in
`tests/test_attachment_relationship_flow.py` fails if `suggested_category` is
referenced anywhere outside `system_one.py` — but a hint that is wrong half the
time is worse than no hint, and until there is a set like this nobody can say
which it is.

It is also the measuring stick for anything proposed to replace that reader.
`docs/laya-decision.md` records an assessment of Laya as an intent classifier
and names grievance triage as the one place it might genuinely help; that claim
is not checkable without this file.

THERE IS ALREADY A SYSTEM-1 SET NEXT DOOR, and the reason this one exists
anyway is worth stating. `system_one_cases.py` holds 61 cases across four
tasks, 36 of them grievance classification — in English, Tamil and
code-switched input, and nothing else. The classifier it measures had words
for English and Tamil and nothing else either.

So the benchmark shared the implementation's blind spot exactly, and agreed
with it. Malayalam, Telugu and Hindi were added to the interview, the document
and the analysis panel while this classifier returned UNKNOWN for every
grievance written in any of them, and both the tests and the benchmark stayed
green throughout, because neither contained a word of those languages.

That is the argument for this file being organised by LANGUAGE as well as by
category: a set that covers only what the code already handles can only ever
confirm it.

EVERYTHING HERE IS INVENTED. Not one line came from a citizen, a petition, a
log or a support ticket. The complaints are the ordinary ones a Tamil Nadu
counter sees, written from the subject matter rather than copied from anybody,
and the suite may be published with the repository.

WHAT IS DELIBERATELY IN IT

  Five languages, because the service offers five. A classifier that reads
  English and guesses at the rest is not usable here, and measuring only
  English is how that goes unnoticed.

  Romanised Tamil, because citizens type it. "thanni varala" is how the
  complaint arrives on a Latin keyboard, and the incumbent has a fold table
  for exactly this.

  TWO-SUBJECT cases, expecting UNKNOWN. A citizen who complains about the road
  AND the street light has made two complaints, and picking one of them is a
  worse answer than admitting there are two.

  DECOYS. A category word appearing as scenery rather than as the subject:
  "opposite the water tank" is not a water complaint. These are where a
  keyword scorer is most likely to be wrong, and where a model that reads the
  sentence should win if it is going to win anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The vocabulary, mirrored from `app.services.system_one.CATEGORIES`. Kept as
#: a literal rather than imported so that a change to the application's list is
#: a visible failure here rather than a silently re-scored benchmark.
CATEGORIES = ("WATER", "ROAD", "STREET_LIGHT", "SANITATION", "PENSION",
              "WELFARE", "LICENCE", "CERTIFICATE", "PROPERTY", "ELECTRICITY",
              "OTHER", "UNKNOWN")


@dataclass(frozen=True)
class Case:
    """One grievance and the subject a human would file it under."""

    text: str
    language: str
    expected: str
    #: Why this case is in the set. Read when it fails.
    note: str = ""


# --------------------------------------------------------------------------- #
# Plain cases: one subject, stated directly
# --------------------------------------------------------------------------- #

PLAIN: tuple[Case, ...] = (
    # --- WATER ---------------------------------------------------------- #
    Case("There has been no drinking water supply in our street for ten days.",
         "en", "WATER"),
    Case("The public tap near our house has been dry since last month and we "
         "are carrying water from the next street.", "en", "WATER"),
    Case("எங்கள் தெருவில் குடிநீர் விநியோகம் பல நாட்களாக தடைபட்டுள்ளது.",
         "ta", "WATER"),
    Case("ഞങ്ങളുടെ തെരുവിൽ കുടിവെള്ള വിതരണം ഒരാഴ്ചയായി മുടങ്ങിയിരിക്കുന്നു.",
         "ml", "WATER"),
    Case("మా వీధిలో తాగునీటి సరఫరా పది రోజులుగా నిలిచిపోయింది.",
         "te", "WATER"),
    Case("हमारी गली में पेयजल आपूर्ति कई दिनों से बाधित है।", "hi", "WATER"),
    Case("engal theruvil thanni varala pathu naala.", "ta", "WATER",
         "romanised Tamil, which is how it arrives on a Latin keyboard"),

    # --- ROAD ----------------------------------------------------------- #
    Case("The road in front of our colony is full of potholes and two "
         "two-wheeler riders have fallen this month.", "en", "ROAD"),
    Case("The approach road to our village has not been laid since the "
         "pipeline work and is now impassable.", "en", "ROAD"),
    Case("எங்கள் பகுதியில் உள்ள சாலை முழுவதும் பள்ளங்களாக உள்ளது.",
         "ta", "ROAD"),
    Case("ഞങ്ങളുടെ പ്രദേശത്തെ റോഡ് നിറയെ കുഴികളാണ്.", "ml", "ROAD"),
    Case("మా ప్రాంతంలోని రహదారి గుంతలతో నిండిపోయింది.", "te", "ROAD"),
    Case("हमारे इलाके की सड़क गड्ढों से भरी हुई है।", "hi", "ROAD"),

    # --- STREET_LIGHT --------------------------------------------------- #
    Case("The street light outside my house has not worked for three months "
         "and the road is completely dark at night.", "en", "STREET_LIGHT"),
    Case("None of the lamps on our lane have been replaced since the storm.",
         "en", "STREET_LIGHT"),
    Case("எனது வீட்டின் முன் உள்ள தெருவிளக்கு மூன்று மாதங்களாக எரியவில்லை.",
         "ta", "STREET_LIGHT"),
    Case("എന്റെ വീടിന് മുന്നിലെ തെരുവുവിളക്ക് മാസങ്ങളായി കത്തുന്നില്ല.",
         "ml", "STREET_LIGHT"),
    Case("మా ఇంటి ముందు వీధి దీపం చాలా నెలలుగా వెలగడం లేదు.",
         "te", "STREET_LIGHT"),
    Case("मेरे घर के सामने की स्ट्रीट लाइट तीन महीने से नहीं जल रही है।",
         "hi", "STREET_LIGHT"),

    # --- SANITATION ----------------------------------------------------- #
    Case("Garbage has not been collected from our street for two weeks and "
         "the smell is unbearable.", "en", "SANITATION"),
    Case("The sewage line near our house is overflowing onto the footpath.",
         "en", "SANITATION"),
    Case("எங்கள் தெருவில் குப்பை இரண்டு வாரங்களாக அகற்றப்படவில்லை.",
         "ta", "SANITATION"),
    Case("ഞങ്ങളുടെ തെരുവിൽ മാലിന്യം രണ്ടാഴ്ചയായി നീക്കം ചെയ്തിട്ടില്ല.",
         "ml", "SANITATION"),
    Case("మా వీధిలో చెత్తను రెండు వారాలుగా తొలగించలేదు.", "te", "SANITATION"),
    Case("हमारी गली से दो हफ्ते से कूड़ा नहीं उठाया गया है।", "hi", "SANITATION"),

    # --- PENSION -------------------------------------------------------- #
    Case("My old age pension has not been credited for the last four months.",
         "en", "PENSION"),
    Case("I am a widow and my widow pension was stopped without any notice.",
         "en", "PENSION"),
    Case("எனது முதியோர் ஓய்வூதியம் நான்கு மாதங்களாக வரவில்லை.", "ta", "PENSION"),
    Case("എന്റെ വാർദ്ധക്യ പെൻഷൻ നാല് മാസമായി ലഭിച്ചിട്ടില്ല.", "ml", "PENSION"),
    Case("నా వృద్ధాప్య పింఛను నాలుగు నెలలుగా రాలేదు.", "te", "PENSION"),
    Case("मेरी वृद्धावस्था पेंशन चार महीने से नहीं आई है।", "hi", "PENSION"),

    # --- WELFARE -------------------------------------------------------- #
    Case("My ration card has not been issued even after applying one year ago "
         "and I cannot draw my monthly provisions.", "en", "WELFARE"),
    Case("I applied for the housing scheme for the poor and my application "
         "has not been considered.", "en", "WELFARE"),
    Case("ஒரு வருடமாக விண்ணப்பித்தும் எனக்கு ரேஷன் அட்டை வழங்கப்படவில்லை.",
         "ta", "WELFARE"),
    Case("मैंने गरीबों की आवास योजना के लिए आवेदन किया था, उस पर विचार नहीं हुआ।",
         "hi", "WELFARE"),

    # --- LICENCE -------------------------------------------------------- #
    Case("My application for a trade licence for my small shop has been "
         "pending at the municipal office for six months.", "en", "LICENCE"),
    Case("I applied for building plan approval and the licence has not been "
         "granted despite paying the fee.", "en", "LICENCE"),
    Case("எனது சிறிய கடைக்கான வர்த்தக உரிமம் ஆறு மாதங்களாக நிலுவையில் உள்ளது.",
         "ta", "LICENCE"),

    # --- CERTIFICATE ---------------------------------------------------- #
    Case("I applied for a community certificate for my daughter's admission "
         "and it has not been issued.", "en", "CERTIFICATE"),
    Case("The income certificate I need for my son's scholarship has been "
         "pending at the taluk office.", "en", "CERTIFICATE"),
    Case("எனது மகளின் சேர்க்கைக்கான சாதிச் சான்றிதழ் இன்னும் வழங்கப்படவில்லை.",
         "ta", "CERTIFICATE"),
    Case("എന്റെ മകളുടെ പ്രവേശനത്തിനുള്ള ജാതി സർട്ടിഫിക്കറ്റ് ഇതുവരെ ലഭിച്ചിട്ടില്ല.",
         "ml", "CERTIFICATE"),

    # --- PROPERTY ------------------------------------------------------- #
    Case("My neighbour has encroached on my patta land and built a compound "
         "wall over the boundary.", "en", "PROPERTY"),
    Case("The patta for my land has not been transferred to my name after my "
         "father's death.", "en", "PROPERTY"),
    Case("எனது பட்டா நிலத்தை அண்டை வீட்டார் ஆக்கிரமித்து சுவர் கட்டியுள்ளனர்.",
         "ta", "PROPERTY"),

    # --- ELECTRICITY ---------------------------------------------------- #
    Case("There is a power cut in our area every evening for four hours and "
         "the transformer has not been repaired.", "en", "ELECTRICITY"),
    Case("My electricity bill shows a reading three times higher than my "
         "actual usage and no one has inspected the meter.", "en", "ELECTRICITY"),
    Case("எங்கள் பகுதியில் தினமும் மாலையில் மின்வெட்டு ஏற்படுகிறது.",
         "ta", "ELECTRICITY"),
    Case("हमारे क्षेत्र में हर शाम चार घंटे बिजली कटौती होती है।",
         "hi", "ELECTRICITY"),
)


# --------------------------------------------------------------------------- #
# Two subjects: the honest answer is UNKNOWN
# --------------------------------------------------------------------------- #

TWO_SUBJECTS: tuple[Case, ...] = (
    Case("The road near our house is damaged and the street light has also "
         "not been working for two months.", "en", "UNKNOWN",
         "two complaints, explicitly coordinated"),
    Case("There is no water supply and the garbage is also not collected in "
         "our area.", "en", "UNKNOWN", "two complaints"),
    Case("My pension has stopped and my ration card has also not been "
         "renewed.", "en", "UNKNOWN", "two complaints"),
    Case("எங்கள் சாலையும் சரியில்லை, தெருவிளக்கும் எரியவில்லை.",
         "ta", "UNKNOWN", "Tamil coordination"),
    Case("Both the drinking water line and the sewage line in our street need "
         "attention.", "en", "UNKNOWN", "'both' is the citizen saying two"),
)


# --------------------------------------------------------------------------- #
# Decoys: a category word that is scenery, not the subject
# --------------------------------------------------------------------------- #

DECOYS: tuple[Case, ...] = (
    Case("The street light opposite the water tank has not been repaired for "
         "two months.", "en", "STREET_LIGHT",
         "'water tank' is the landmark; the complaint is the light"),
    Case("Garbage is dumped on the road in front of my house and has not been "
         "cleared.", "en", "SANITATION",
         "'road' is where the rubbish is, not the complaint"),
    Case("I am unable to collect my pension because the road to the bank "
         "branch is washed out and no bus runs.", "en", "ROAD",
         "the pension is the consequence; the road is the complaint"),
    Case("The water board office near the bus stand did not accept my "
         "application for a new sewage connection.", "en", "SANITATION",
         "'water board' is the office; the request is a sewage connection"),
    Case("My electricity connection was cut because the meter reader could "
         "not reach my house on the damaged road.", "en", "UNKNOWN",
         "genuinely two-sided; UNKNOWN is a defensible answer and a confident "
         "single answer is not"),
)


# --------------------------------------------------------------------------- #
# Nothing to classify
# --------------------------------------------------------------------------- #

NO_SUBJECT: tuple[Case, ...] = (
    Case("", "en", "UNKNOWN", "empty"),
    Case("hello", "en", "UNKNOWN", "too short to classify"),
    Case("I want to submit a petition.", "en", "UNKNOWN",
         "a request to petition names no subject"),
    Case("Please help me sir, I have been to the office many times.",
         "en", "UNKNOWN", "distress with no subject stated"),
    Case("ஐயா, எனக்கு உதவி செய்யுங்கள்.", "ta", "UNKNOWN",
         "Tamil, distress with no subject"),
)


def dataset() -> tuple[Case, ...]:
    """Every case, in one tuple."""
    return PLAIN + TWO_SUBJECTS + DECOYS + NO_SUBJECT


def by_language() -> dict[str, list[Case]]:
    grouped: dict[str, list[Case]] = {}
    for case in dataset():
        grouped.setdefault(case.language, []).append(case)
    return grouped
