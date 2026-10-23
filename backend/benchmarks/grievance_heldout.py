"""The held-out test set. Written first, read last.

WHAT "HELD OUT" MEANS HERE, operationally, because the phrase is often used
loosely. This file was written BEFORE any tuning of the classifier and was not
consulted while the taxonomy was being extended or the matcher changed. The
development set in `grievance_dev.py` is what was looked at, repeatedly. This
one is scored once, at the end, and the number it gives is the only number
anybody should quote about this classifier.

If a case here fails, the honest response is to fix the CAUSE in a way that is
justified by the development set too — not to add the failing phrase to a word
list. Doing the latter converts this file into a development set and destroys
the only unbiased measurement the project has. If that ever happens it must be
recorded in the report, and a fresh held-out set written.

EVERYTHING IS INVENTED. No case came from a citizen, a petition, a log or a
support ticket. No real names, telephone numbers, Aadhaar numbers or addresses
appear. This file is safe to publish with the repository.

WHAT IT IS MEANT TO REPRESENT: an ordinary day at a counter. The difficulty is
meant to come from how people actually speak — burying the subject in
backstory, naming the consequence rather than the cause, being polite for three
sentences before saying what is wrong — rather than from puzzles. A test set
made entirely of hard tricks measures trick-handling, not service quality.
"""

from __future__ import annotations

from .grievance_cases import Case

# --------------------------------------------------------------------------- #
# English
# --------------------------------------------------------------------------- #

ENGLISH: tuple[Case, ...] = (
    Case("Respected sir, I am a resident of the fourth ward. I do not wish to "
         "trouble you but we have had no supply in the public tap since the "
         "pump failed and the women are walking to the next ward.",
         "en", "WATER", "polite preamble before the subject"),
    Case("My children cannot study after seven in the evening because the lane "
         "is pitch dark and nothing has been repaired since Deepavali.",
         "en", "STREET_LIGHT", "stated only by its consequence"),
    Case("The lorry that collects from our area stopped coming in the second "
         "week of last month and the corner has become a dump.",
         "en", "SANITATION"),
    Case("I retired as a weaver and the amount that used to come every month "
         "has not been credited since June. I have shown the passbook twice.",
         "en", "PENSION", "never uses the word pension"),
    Case("The surface has broken up so badly after the rains that autos refuse "
         "to come down our lane at night.", "en", "ROAD"),
    Case("I applied in January for the paper the college needs to prove my "
         "daughter's community and the taluk office still has not issued it.",
         "en", "CERTIFICATE", "describes the document rather than naming it"),
    Case("The shop has been in my husband's name and after his death I have "
         "been trying to get the trade permission transferred to mine.",
         "en", "LICENCE"),
    Case("Supply trips every evening between six and nine and the repair van "
         "has been to the pole three times without fixing it.",
         "en", "ELECTRICITY"),
    Case("My neighbour has put up a wall two feet inside my boundary and the "
         "survey stone has been moved.", "en", "PROPERTY"),
    Case("My card was cancelled when we shifted and the fair price shop will "
         "not give provisions without it.", "en", "WELFARE"),
    Case("I have been to the office four times about this and each time I am "
         "told to come again next week. Kindly do something.",
         "en", "UNKNOWN", "distress, no subject stated"),
    Case("The drain outside is blocked and the pension has also not arrived "
         "for two months.", "en", "UNKNOWN", "two complaints"),
    Case("There is a stray dog problem in our street and nobody has come "
         "despite several complaints.", "en", "OTHER",
         "a real grievance that none of the ten categories covers"),
    Case("Sir, kindly help.", "en", "UNKNOWN", "nothing to classify"),
    Case("Water stagnates outside my gate every time it rains because the "
         "channel was never cleared, and the mosquitoes are unbearable.",
         "en", "SANITATION",
         "mentions water, but the subject is the uncleared drain"),
    Case("I am told the transformer serving our hamlet is undersized but the "
         "board says it is not their work.", "en", "ELECTRICITY"),
    Case("We were promised a connection when the new line was laid past our "
         "house two years ago and it has still not been given.",
         "en", "WATER", "vague unless read carefully"),
    Case("The light in front of the temple works but the one at the turning "
         "where the accident happened does not.", "en", "STREET_LIGHT",
         "contrast within one category"),
    Case("My application for the housing assistance was returned saying the "
         "income paper was old, and the office that issues it says the "
         "application must come first.", "en", "UNKNOWN",
         "genuinely circular, two offices, two subjects"),
    Case("The patta is in my father's name and he died in 2019. I have the "
         "death certificate and the legal heir paper.", "en", "PROPERTY",
         "names two certificates, but the request is the patta transfer"),
)

# --------------------------------------------------------------------------- #
# Tamil
# --------------------------------------------------------------------------- #

TAMIL: tuple[Case, ...] = (
    Case("எங்கள் தெருவில் உள்ள பொதுக் குழாயில் ஒரு வாரமாக தண்ணீர் வரவில்லை.",
         "ta", "WATER"),
    Case("மழைக்குப் பிறகு சாலை முழுவதும் பள்ளமாகி விட்டது, இரவில் நடக்க முடியவில்லை.",
         "ta", "ROAD"),
    Case("தெருவிளக்கு எரியாததால் இரவில் பெண்கள் வெளியே செல்ல அஞ்சுகிறார்கள்.",
         "ta", "STREET_LIGHT", "consequence first"),
    Case("குப்பை வண்டி இரண்டு வாரமாக வரவில்லை, துர்நாற்றம் தாங்க முடியவில்லை.",
         "ta", "SANITATION"),
    Case("எனது முதியோர் ஓய்வூதியம் மூன்று மாதமாக வரவில்லை.", "ta", "PENSION"),
    Case("ரேஷன் அட்டை புதுப்பிக்கப்படவில்லை, பொருட்கள் வாங்க முடியவில்லை.",
         "ta", "WELFARE"),
    Case("எனது கடைக்கான உரிமம் ஆறு மாதமாக நிலுவையில் உள்ளது.", "ta", "LICENCE"),
    Case("மகளின் கல்லூரி சேர்க்கைக்கு சாதிச் சான்றிதழ் தேவை, இன்னும் கிடைக்கவில்லை.",
         "ta", "CERTIFICATE"),
    Case("அண்டை வீட்டார் எனது நிலத்தை ஆக்கிரமித்து சுவர் கட்டியுள்ளனர்.",
         "ta", "PROPERTY"),
    Case("தினமும் மாலையில் மின்வெட்டு, மின்மாற்றி பழுதடைந்துள்ளது.",
         "ta", "ELECTRICITY"),
    Case("சாக்கடை அடைத்துள்ளது, தெருவிளக்கும் எரியவில்லை.", "ta", "UNKNOWN",
         "two complaints"),
    Case("ஐயா, பல முறை அலுவலகம் வந்தேன், ஒன்றும் நடக்கவில்லை.",
         "ta", "UNKNOWN", "no subject"),
    Case("kudineer varala oru vaaramaa, pothu kuzhaayil onnume illa.",
         "ta", "WATER", "romanised Tamil"),
    Case("theruvilakku eriyala, ratri romba iruttaa irukku.",
         "ta", "STREET_LIGHT", "romanised Tamil"),
    Case("kuppai vandi varaama rendu vaaram aachu.", "ta", "SANITATION",
         "romanised Tamil"),
    Case("road la kuzhi romba irukku, vandi ponga mudiyala.", "ta", "ROAD",
         "romanised Tamil with an English noun"),
    Case("எனது வீட்டின் முன் street light மாதக்கணக்கில் எரியவில்லை.",
         "ta", "STREET_LIGHT", "code-switched, English noun in Latin script"),
    Case("நீர்த்தொட்டி அருகே உள்ள மின் கம்பம் சாய்ந்து உள்ளது.",
         "ta", "ELECTRICITY", "water tank is the landmark, the pole is the subject"),
    Case("வீட்டு வரி செலுத்தியும் பெயர் மாற்றம் செய்யப்படவில்லை.",
         "ta", "PROPERTY"),
    Case("அரசு மருத்துவமனையில் மருந்து கிடைக்கவில்லை.", "ta", "OTHER",
         "a real grievance outside the ten categories"),
)

# --------------------------------------------------------------------------- #
# Malayalam
# --------------------------------------------------------------------------- #

MALAYALAM: tuple[Case, ...] = (
    Case("ഞങ്ങളുടെ തെരുവിലെ പൊതു ടാപ്പിൽ ഒരാഴ്ചയായി വെള്ളം വരുന്നില്ല.",
         "ml", "WATER"),
    Case("മഴയ്ക്ക് ശേഷം റോഡ് നിറയെ കുഴികളായി, വാഹനം ഓടിക്കാൻ കഴിയുന്നില്ല.",
         "ml", "ROAD"),
    Case("തെരുവുവിളക്ക് കത്താത്തതിനാൽ രാത്രി പുറത്തിറങ്ങാൻ പേടിയാണ്.",
         "ml", "STREET_LIGHT"),
    Case("മാലിന്യം രണ്ടാഴ്ചയായി നീക്കം ചെയ്തിട്ടില്ല, ദുർഗന്ധം സഹിക്കാനാവുന്നില്ല.",
         "ml", "SANITATION"),
    Case("എന്റെ വാർദ്ധക്യ പെൻഷൻ മൂന്ന് മാസമായി ലഭിച്ചിട്ടില്ല.", "ml", "PENSION"),
    Case("റേഷൻ കാർഡ് പുതുക്കിയിട്ടില്ല, സാധനങ്ങൾ വാങ്ങാൻ കഴിയുന്നില്ല.",
         "ml", "WELFARE"),
    Case("എന്റെ കടയുടെ ലൈസൻസ് ആറ് മാസമായി തീർപ്പാക്കിയിട്ടില്ല.", "ml", "LICENCE"),
    Case("മകളുടെ പ്രവേശനത്തിന് ജാതി സർട്ടിഫിക്കറ്റ് ഇതുവരെ ലഭിച്ചിട്ടില്ല.",
         "ml", "CERTIFICATE"),
    Case("അയൽവാസി എന്റെ ഭൂമി കൈയേറി മതിൽ കെട്ടിയിരിക്കുന്നു.", "ml", "PROPERTY"),
    Case("എല്ലാ വൈകുന്നേരവും വൈദ്യുതി പോകുന്നു, ട്രാൻസ്ഫോർമർ തകരാറിലാണ്.",
         "ml", "ELECTRICITY"),
    Case("ഓട അടഞ്ഞിരിക്കുന്നു, തെരുവുവിളക്കും കത്തുന്നില്ല.", "ml", "UNKNOWN",
         "two complaints"),
    Case("സർ, പലതവണ ഓഫീസിൽ വന്നു, ഒന്നും നടന്നില്ല.", "ml", "UNKNOWN",
         "no subject"),
    Case("കുട്ടികൾക്ക് വൈകുന്നേരം പഠിക്കാൻ കഴിയുന്നില്ല, വഴി ഇരുട്ടാണ്.",
         "ml", "STREET_LIGHT", "consequence only"),
    Case("പൊതു കിണറിന് അടുത്തുള്ള വൈദ്യുതി തൂൺ ചരിഞ്ഞിരിക്കുന്നു.",
         "ml", "ELECTRICITY", "the well is the landmark"),
    Case("സർക്കാർ ആശുപത്രിയിൽ മരുന്ന് ലഭിക്കുന്നില്ല.", "ml", "OTHER"),
)

# --------------------------------------------------------------------------- #
# Telugu
# --------------------------------------------------------------------------- #

TELUGU: tuple[Case, ...] = (
    Case("మా వీధిలోని పబ్లిక్ నల్లాలో వారం రోజులుగా నీరు రావడం లేదు.",
         "te", "WATER"),
    Case("వర్షాల తర్వాత రోడ్డు పూర్తిగా గుంతలమయమైంది, నడవడం కష్టంగా ఉంది.",
         "te", "ROAD"),
    Case("వీధి దీపం వెలగకపోవడంతో రాత్రి బయటకు వెళ్లడానికి భయంగా ఉంది.",
         "te", "STREET_LIGHT"),
    Case("చెత్త రెండు వారాలుగా తీసుకెళ్లడం లేదు, దుర్వాసన భరించలేకపోతున్నాం.",
         "te", "SANITATION"),
    Case("నా వృద్ధాప్య పింఛను మూడు నెలలుగా రావడం లేదు.", "te", "PENSION"),
    Case("రేషన్ కార్డు పునరుద్ధరించలేదు, సరుకులు తీసుకోలేకపోతున్నాను.",
         "te", "WELFARE"),
    Case("నా దుకాణం లైసెన్సు ఆరు నెలలుగా పెండింగ్‌లో ఉంది.", "te", "LICENCE"),
    Case("కూతురి ప్రవేశానికి కుల ధృవీకరణ పత్రం ఇంకా ఇవ్వలేదు.",
         "te", "CERTIFICATE"),
    Case("పొరుగువారు నా భూమిని ఆక్రమించి గోడ కట్టారు.", "te", "PROPERTY"),
    Case("ప్రతి సాయంత్రం కరెంటు పోతోంది, ట్రాన్స్‌ఫార్మర్ పాడైంది.",
         "te", "ELECTRICITY"),
    Case("కాలువ మూసుకుపోయింది, వీధి దీపం కూడా వెలగడం లేదు.", "te", "UNKNOWN",
         "two complaints"),
    Case("సార్, చాలాసార్లు ఆఫీసుకు వచ్చాను, ఏమీ జరగలేదు.", "te", "UNKNOWN",
         "no subject"),
    Case("పిల్లలు సాయంత్రం చదువుకోలేకపోతున్నారు, దారి చీకటిగా ఉంది.",
         "te", "STREET_LIGHT", "consequence only"),
    Case("ప్రభుత్వ ఆసుపత్రిలో మందులు దొరకడం లేదు.", "te", "OTHER"),
    Case("నీటి ట్యాంకు దగ్గర ఉన్న విద్యుత్ స్తంభం వంగిపోయింది.",
         "te", "ELECTRICITY", "the tank is the landmark"),
)

# --------------------------------------------------------------------------- #
# Hindi
# --------------------------------------------------------------------------- #

HINDI: tuple[Case, ...] = (
    Case("हमारी गली के सार्वजनिक नल में एक सप्ताह से पानी नहीं आ रहा है।",
         "hi", "WATER"),
    Case("बारिश के बाद सड़क पूरी तरह गड्ढों से भर गई है, चलना मुश्किल है।",
         "hi", "ROAD"),
    Case("स्ट्रीट लाइट न जलने के कारण रात में बाहर निकलने में डर लगता है।",
         "hi", "STREET_LIGHT"),
    Case("दो हफ्ते से कूड़ा नहीं उठाया गया, बदबू असहनीय हो गई है।",
         "hi", "SANITATION"),
    Case("मेरी वृद्धावस्था पेंशन तीन महीने से नहीं आई है।", "hi", "PENSION"),
    Case("राशन कार्ड नवीनीकृत नहीं हुआ, सामान नहीं मिल पा रहा।",
         "hi", "WELFARE"),
    Case("मेरी दुकान का लाइसेंस छह महीने से लंबित है।", "hi", "LICENCE"),
    Case("बेटी के दाखिले के लिए जाति प्रमाण पत्र अब तक नहीं मिला।",
         "hi", "CERTIFICATE"),
    Case("पड़ोसी ने मेरी जमीन पर अतिक्रमण कर दीवार बना दी है।",
         "hi", "PROPERTY"),
    Case("हर शाम बिजली चली जाती है, ट्रांसफार्मर खराब है।",
         "hi", "ELECTRICITY"),
    Case("नाली बंद है और स्ट्रीट लाइट भी नहीं जल रही।", "hi", "UNKNOWN",
         "two complaints"),
    Case("सर, कई बार दफ्तर आया, कुछ नहीं हुआ।", "hi", "UNKNOWN", "no subject"),
    Case("बच्चे शाम को पढ़ नहीं पाते, रास्ता अंधेरा रहता है।",
         "hi", "STREET_LIGHT", "consequence only"),
    Case("सरकारी अस्पताल में दवा नहीं मिलती।", "hi", "OTHER"),
    Case("पानी की टंकी के पास वाला बिजली का खंभा झुक गया है।",
         "hi", "ELECTRICITY", "the tank is the landmark"),
)


def dataset() -> tuple[Case, ...]:
    """The whole held-out set."""
    return ENGLISH + TAMIL + MALAYALAM + TELUGU + HINDI
