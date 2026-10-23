"""A second held-out set, written after the first was spent.

WHY A SECOND ONE EXISTS. `grievance_heldout.py` was scored once, cleanly, at
0.7174. I then read its failure list — which is a one-way door. Everything
measured on it afterwards is weaker evidence, because the design of the
semantic reader was informed by knowing how that set failed.

So this set was written before the semantic reader was scored on anything, and
is scored ONCE, at the end. It is the honest number.

THE LIMITATION THAT CANNOT BE ENGINEERED AWAY, stated rather than hidden: the
same author wrote the system and this set. That is weaker than a set written
by somebody who has never seen the exemplars, and the right fix is for a
Tamil Nadu officer who takes petitions at a counter to write the next one from
real intake patterns — not from imagination. Until then this is the best
available evidence and should be read as such.

WHAT IT IS MEANT TO BE: an ordinary week at a counter. Mostly plain
complaints, because most complaints are plain. A minority stated indirectly,
because that is the real rate. Two-subject and empty cases at roughly the
frequency a clerk meets them. Deliberately NOT a collection of hard cases —
a set made only of traps measures trap-handling.

EVERYTHING IS INVENTED. No citizen text, no real names, numbers or addresses.
"""

from __future__ import annotations

from .grievance_cases import Case

ENGLISH: tuple[Case, ...] = (
    Case("There has been no water in the public tap on our street since "
         "Monday and the tanker has not come either.", "en", "WATER"),
    Case("The pipeline laid last year has burst at the corner and water is "
         "running waste all day.", "en", "WATER"),
    Case("Half the lane was dug up for cable work and has not been closed up "
         "since. A scooter went into it last week.", "en", "ROAD"),
    Case("The tar on our stretch has come off completely and in the rain it "
         "is all slush.", "en", "ROAD"),
    Case("Three of the poles on our street have no bulbs and have not had any "
         "since the festival.", "en", "STREET_LIGHT"),
    Case("It is pitch black from the bus stop to our gate and my mother will "
         "not walk back alone after her shift.", "en", "STREET_LIGHT"),
    Case("The bins at the end of our road overflow by Tuesday and nobody "
         "empties them until the weekend.", "en", "SANITATION"),
    Case("The drain behind our houses has been choked for a month and the "
         "water has started backing up into the yard.", "en", "SANITATION"),
    Case("My father is eighty-one and the old age pension has not reached his "
         "account since April.", "en", "PENSION"),
    Case("I was sanctioned the widow pension two years ago and the payments "
         "simply stopped without any letter.", "en", "PENSION"),
    Case("Our family card still shows my late father as the head and the shop "
         "refuses to issue against it.", "en", "WELFARE"),
    Case("My son was selected for the scholarship and the amount has not been "
         "paid for two terms.", "en", "WELFARE"),
    Case("I run a tea stall and have been trying for eight months to get the "
         "licence renewed.", "en", "LICENCE"),
    Case("The plan approval for my house extension has been with the office "
         "since February with no decision.", "en", "LICENCE"),
    Case("I need the nativity certificate for my daughter's application and "
         "the taluk office keeps asking me to come back.", "en", "CERTIFICATE"),
    Case("The income certificate was applied for online in March and the "
         "status has not changed since.", "en", "CERTIFICATE"),
    Case("A compound wall has come up across the path we have used to reach "
         "our field for forty years.", "en", "PROPERTY"),
    Case("The patta has not been changed to my name though I submitted the "
         "legal heir papers last year.", "en", "PROPERTY"),
    Case("Our area has had a power cut every evening this month and the "
         "transformer hums loudly before it trips.", "en", "ELECTRICITY"),
    Case("My meter was replaced and since then the bill has tripled although "
         "nothing in the house has changed.", "en", "ELECTRICITY"),
    Case("The water supply is fine but the sewage line beside it has been "
         "leaking for weeks.", "en", "SANITATION",
         "contrast: the first clause is not the complaint"),
    Case("Both the street light and the drainage in our lane need attention.",
         "en", "UNKNOWN", "two subjects"),
    Case("The road is bad and the ration shop also refuses to serve us.",
         "en", "UNKNOWN", "two subjects"),
    Case("I have written three times and received no reply at all. Kindly "
         "look into my matter.", "en", "UNKNOWN", "no subject"),
    Case("Sir, please help.", "en", "UNKNOWN", "nothing"),
    Case("Stray cattle are being left on the main road at night and there "
         "have been two accidents.", "en", "OTHER"),
    Case("The primary school in our village has had no teacher for the "
         "fifth standard since June.", "en", "OTHER"),
)

TAMIL: tuple[Case, ...] = (
    Case("எங்கள் தெருவில் உள்ள பொதுக் குழாயில் திங்கள் முதல் தண்ணீர் வரவில்லை.",
         "ta", "WATER"),
    Case("குழாய் உடைந்து தண்ணீர் வீணாக ஓடுகிறது, யாரும் சரிசெய்யவில்லை.",
         "ta", "WATER"),
    Case("கேபிள் பணிக்காக தோண்டிய சாலை இன்னும் மூடப்படவில்லை.", "ta", "ROAD"),
    Case("மழை பெய்தால் எங்கள் தெரு முழுவதும் சேறு, நடக்கவே முடியவில்லை.",
         "ta", "ROAD"),
    Case("எங்கள் தெருவில் மூன்று கம்பங்களில் விளக்கு இல்லை.",
         "ta", "STREET_LIGHT"),
    Case("பேருந்து நிறுத்தத்திலிருந்து வீடு வரை இருட்டாக உள்ளது, அம்மா தனியாக "
         "வர பயப்படுகிறார்.", "ta", "STREET_LIGHT"),
    Case("குப்பைத் தொட்டி நிரம்பி வழிகிறது, வாரக்கடைசி வரை யாரும் எடுப்பதில்லை.",
         "ta", "SANITATION"),
    Case("வீட்டின் பின்புறம் உள்ள வடிகால் அடைத்து, நீர் முற்றத்தில் தேங்குகிறது.",
         "ta", "SANITATION"),
    Case("என் தந்தைக்கு எண்பத்தொரு வயது, ஏப்ரல் முதல் ஓய்வூதியம் வரவில்லை.",
         "ta", "PENSION"),
    Case("விதவை ஓய்வூதியம் எந்த அறிவிப்பும் இன்றி நிறுத்தப்பட்டுவிட்டது.",
         "ta", "PENSION"),
    Case("குடும்ப அட்டையில் இறந்த தந்தையின் பெயர் உள்ளது, கடையில் பொருள் "
         "தர மறுக்கிறார்கள்.", "ta", "WELFARE"),
    Case("எனது தேநீர் கடைக்கான உரிமம் எட்டு மாதமாக புதுப்பிக்கப்படவில்லை.",
         "ta", "LICENCE"),
    Case("மகளின் விண்ணப்பத்திற்கு பிறப்பிட சான்றிதழ் தேவை, அலுவலகம் மீண்டும் "
         "மீண்டும் வரச் சொல்கிறது.", "ta", "CERTIFICATE"),
    Case("வாரிசு ஆவணங்கள் கொடுத்தும் பட்டா என் பெயருக்கு மாற்றப்படவில்லை.",
         "ta", "PROPERTY"),
    Case("இந்த மாதம் தினமும் மாலையில் மின்வெட்டு, மின்மாற்றி சத்தம் போடுகிறது.",
         "ta", "ELECTRICITY"),
    Case("theru lightu eriyala, ratri romba iruttu.", "ta", "STREET_LIGHT",
         "romanised"),
    Case("kudineer varala, thinakkizhamai mudhal onnume illa.", "ta", "WATER",
         "romanised"),
    Case("சாலையும் சரியில்லை, குப்பையும் அகற்றப்படவில்லை.", "ta", "UNKNOWN",
         "two subjects"),
    Case("ஐயா, மூன்று முறை எழுதியும் பதில் இல்லை.", "ta", "UNKNOWN",
         "no subject"),
    Case("இரவில் சாலையில் கால்நடைகள் விடப்படுகின்றன, விபத்து நடந்தது.",
         "ta", "OTHER"),
)

MALAYALAM: tuple[Case, ...] = (
    Case("ഞങ്ങളുടെ തെരുവിലെ പൊതു ടാപ്പിൽ തിങ്കളാഴ്ച മുതൽ വെള്ളമില്ല.",
         "ml", "WATER"),
    Case("പൈപ്പ് പൊട്ടി വെള്ളം പാഴായി ഒഴുകുന്നു, ആരും ശരിയാക്കിയിട്ടില്ല.",
         "ml", "WATER"),
    Case("കേബിൾ ജോലിക്കായി കുഴിച്ച റോഡ് ഇതുവരെ മൂടിയിട്ടില്ല.", "ml", "ROAD"),
    Case("ഞങ്ങളുടെ തെരുവിലെ മൂന്ന് തൂണുകളിൽ വിളക്കില്ല.", "ml", "STREET_LIGHT"),
    Case("ബസ് സ്റ്റോപ്പ് മുതൽ വീട് വരെ ഇരുട്ടാണ്, അമ്മ ഒറ്റയ്ക്ക് വരാൻ ഭയക്കുന്നു.",
         "ml", "STREET_LIGHT"),
    Case("മാലിന്യ പെട്ടി നിറഞ്ഞൊഴുകുന്നു, ആഴ്ചാവസാനം വരെ ആരും എടുക്കാറില്ല.",
         "ml", "SANITATION"),
    Case("വീടിന് പിന്നിലെ ഓട അടഞ്ഞ് വെള്ളം മുറ്റത്തേക്ക് കയറുന്നു.",
         "ml", "SANITATION"),
    Case("അച്ഛന് എൺപത്തിയൊന്ന് വയസ്സുണ്ട്, ഏപ്രിൽ മുതൽ പെൻഷൻ ലഭിച്ചിട്ടില്ല.",
         "ml", "PENSION"),
    Case("വിധവാ പെൻഷൻ അറിയിപ്പില്ലാതെ നിർത്തി.", "ml", "PENSION"),
    Case("റേഷൻ കാർഡിൽ മരിച്ച അച്ഛന്റെ പേരാണ്, കടയിൽ സാധനം തരുന്നില്ല.",
         "ml", "WELFARE"),
    Case("എന്റെ ചായക്കടയുടെ ലൈസൻസ് എട്ട് മാസമായി പുതുക്കിയിട്ടില്ല.",
         "ml", "LICENCE"),
    Case("മകളുടെ അപേക്ഷയ്ക്ക് ജനന സർട്ടിഫിക്കറ്റ് വേണം, ഓഫീസ് വീണ്ടും വരാൻ പറയുന്നു.",
         "ml", "CERTIFICATE"),
    Case("അവകാശ രേഖകൾ നൽകിയിട്ടും പട്ടയം എന്റെ പേരിലേക്ക് മാറ്റിയിട്ടില്ല.",
         "ml", "PROPERTY"),
    Case("ഈ മാസം എല്ലാ വൈകുന്നേരവും വൈദ്യുതി പോകുന്നു, ട്രാൻസ്ഫോർമർ ശബ്ദമുണ്ടാക്കുന്നു.",
         "ml", "ELECTRICITY"),
    Case("റോഡും ശരിയല്ല, മാലിന്യവും നീക്കുന്നില്ല.", "ml", "UNKNOWN",
         "two subjects"),
    Case("സർ, മൂന്ന് തവണ എഴുതിയിട്ടും മറുപടിയില്ല.", "ml", "UNKNOWN"),
    Case("രാത്രി റോഡിൽ കന്നുകാലികളെ വിടുന്നു, അപകടം ഉണ്ടായി.", "ml", "OTHER"),
)

TELUGU: tuple[Case, ...] = (
    Case("మా వీధిలోని పబ్లిక్ నల్లాలో సోమవారం నుండి నీరు రావడం లేదు.",
         "te", "WATER"),
    Case("పైపు పగిలి నీరు వృథాగా పోతోంది, ఎవరూ బాగు చేయలేదు.", "te", "WATER"),
    Case("కేబుల్ పని కోసం తవ్విన రోడ్డును ఇంకా పూడ్చలేదు.", "te", "ROAD"),
    Case("మా వీధిలో మూడు స్తంభాలకు దీపాలు లేవు.", "te", "STREET_LIGHT"),
    Case("బస్ స్టాప్ నుండి ఇంటి వరకు చీకటిగా ఉంది, అమ్మ ఒంటరిగా రావడానికి "
         "భయపడుతోంది.", "te", "STREET_LIGHT"),
    Case("చెత్త డబ్బా నిండి పొర్లుతోంది, వారాంతం వరకు ఎవరూ తీయరు.",
         "te", "SANITATION"),
    Case("ఇంటి వెనుక కాలువ మూసుకుపోయి నీరు ముంగిట్లోకి వస్తోంది.",
         "te", "SANITATION"),
    Case("మా నాన్నకు ఎనభై ఒక్క ఏళ్లు, ఏప్రిల్ నుండి పింఛను రాలేదు.",
         "te", "PENSION"),
    Case("వితంతు పింఛను ఎలాంటి సమాచారం లేకుండా ఆపేశారు.", "te", "PENSION"),
    Case("రేషన్ కార్డులో చనిపోయిన నాన్న పేరు ఉంది, దుకాణంలో సరుకులు ఇవ్వడం లేదు.",
         "te", "WELFARE"),
    Case("నా టీ దుకాణం లైసెన్సు ఎనిమిది నెలలుగా పునరుద్ధరించలేదు.",
         "te", "LICENCE"),
    Case("కూతురి దరఖాస్తుకు జనన ధృవీకరణ పత్రం కావాలి, ఆఫీసు మళ్లీ రమ్మంటోంది.",
         "te", "CERTIFICATE"),
    Case("వారసత్వ పత్రాలు ఇచ్చినా పట్టా నా పేరుకు మార్చలేదు.", "te", "PROPERTY"),
    Case("ఈ నెల ప్రతి సాయంత్రం కరెంటు పోతోంది, ట్రాన్స్‌ఫార్మర్ శబ్దం చేస్తోంది.",
         "te", "ELECTRICITY"),
    Case("రోడ్డు కూడా బాగాలేదు, చెత్త కూడా తీయడం లేదు.", "te", "UNKNOWN",
         "two subjects"),
    Case("సార్, మూడుసార్లు రాసినా సమాధానం లేదు.", "te", "UNKNOWN"),
    Case("రాత్రి రోడ్డుపై పశువులను వదులుతున్నారు, ప్రమాదం జరిగింది.",
         "te", "OTHER"),
)

HINDI: tuple[Case, ...] = (
    Case("हमारी गली के सार्वजनिक नल में सोमवार से पानी नहीं आ रहा।",
         "hi", "WATER"),
    Case("पाइप फट गया है और पानी बर्बाद बह रहा है, किसी ने ठीक नहीं किया।",
         "hi", "WATER"),
    Case("केबल के काम के लिए खोदी गई सड़क अब तक नहीं भरी गई।", "hi", "ROAD"),
    Case("हमारी गली के तीन खंभों पर बत्ती नहीं है।", "hi", "STREET_LIGHT"),
    Case("बस स्टॉप से घर तक अंधेरा रहता है, माँ अकेले आने से डरती हैं।",
         "hi", "STREET_LIGHT"),
    Case("कूड़ेदान भरकर बह रहा है, सप्ताहांत तक कोई नहीं उठाता।",
         "hi", "SANITATION"),
    Case("घर के पीछे की नाली जाम है और पानी आँगन में आने लगा है।",
         "hi", "SANITATION"),
    Case("मेरे पिता इक्यासी वर्ष के हैं, अप्रैल से पेंशन नहीं आई।",
         "hi", "PENSION"),
    Case("विधवा पेंशन बिना किसी सूचना के बंद कर दी गई।", "hi", "PENSION"),
    Case("राशन कार्ड में स्वर्गीय पिता का नाम है, दुकान सामान नहीं देती।",
         "hi", "WELFARE"),
    Case("मेरी चाय की दुकान का लाइसेंस आठ महीने से नवीनीकृत नहीं हुआ।",
         "hi", "LICENCE"),
    Case("बेटी के आवेदन के लिए जन्म प्रमाण पत्र चाहिए, दफ्तर बार-बार बुलाता है।",
         "hi", "CERTIFICATE"),
    Case("वारिस के कागज देने पर भी पट्टा मेरे नाम नहीं हुआ।", "hi", "PROPERTY"),
    Case("इस महीने हर शाम बिजली जाती है, ट्रांसफार्मर आवाज करता है।",
         "hi", "ELECTRICITY"),
    Case("सड़क भी खराब है और कूड़ा भी नहीं उठता।", "hi", "UNKNOWN",
         "two subjects"),
    Case("सर, तीन बार लिखा पर कोई जवाब नहीं।", "hi", "UNKNOWN"),
    Case("रात में सड़क पर मवेशी छोड़ दिए जाते हैं, दुर्घटना हुई है।",
         "hi", "OTHER"),
)


def dataset() -> tuple[Case, ...]:
    return ENGLISH + TAMIL + MALAYALAM + TELUGU + HINDI
