"""The letters, places, address words and names for each script.

DATA ONLY. The walk that uses it is in `indic_script.py` and is the Tamil one,
generalised — proved to reproduce `tamil_script.to_tamil` exactly across every
input tried, including four hundred random words.

ON BEING CONSERVATIVE. The tables here are smaller than they could be, on
purpose. A name this cannot render is left in Latin, which is untidy; a name it
renders as a DIFFERENT PLACE sends somebody to the wrong office. Where a
spelling was not certain it was left out, and the phonetic fallback or the
citizen's own Latin text handles it.

The places are Tamil Nadu's, because that is where this service runs and that
is what a citizen types into it — written here in Malayalam, Telugu and
Devanagari because the petition is in one of those. The phonetic fallback
renders most of them acceptably on its own; the entries below are the ones
where it does not, or where the town has a settled spelling of its own.
"""

from __future__ import annotations

from .indic_script import PATTERNS, Script, register


# TWO KINDS OF ENTRY ARE DELIBERATELY ABSENT, and both were here once.
#
# "ny" as a single letter. ഞ / ఞ / ञ carry one sound, so the y was swallowed
# and "dhanya" came out with a letter missing. Left out, n and y form the
# conjunct they should.
#
# "st" as street. In an Indian address St is Saint at least as often —
# St Thomas Church, St Mary's School — and one token cannot tell them apart.
# Rule 1 gives the tie to leaving it alone: "St" in Latin is untidy, "Street
# Thomas Church" is wrong.
# --------------------------------------------------------------------------- #
# Malayalam
# --------------------------------------------------------------------------- #

_ML_CONSONANTS = {
    "kh": "ഖ", "gh": "ഘ", "ng": "ങ", "ch": "ച", "jn": "ഞ",
    "th": "ത", "dh": "ധ", "ph": "ഫ", "bh": "ഭ", "sh": "ഷ", "zh": "ഴ",
    "ks": "ക്ഷ",
    "k": "ക", "g": "ഗ", "c": "ച", "j": "ജ", "t": "ട", "d": "ദ", "n": "ന",
    "p": "പ", "f": "ഫ", "b": "ബ", "m": "മ", "y": "യ", "r": "ര", "l": "ല",
    "v": "വ", "w": "വ", "s": "സ", "h": "ഹ", "z": "സ", "q": "ക", "x": "ക്സ",
}
_ML_VOWELS = {
    "a": "അ", "aa": "ആ", "i": "ഇ", "ii": "ഈ", "ee": "ഈ", "u": "ഉ",
    "uu": "ഊ", "oo": "ഊ", "e": "എ", "ae": "ഏ", "ai": "ഐ", "o": "ഒ",
    "oa": "ഓ", "au": "ഔ",
}
_ML_SIGNS = {
    "a": "", "aa": "ാ", "i": "ി", "ii": "ീ", "ee": "ീ", "u": "ു",
    "uu": "ൂ", "oo": "ൂ", "e": "െ", "ae": "േ", "ai": "ൈ", "o": "ൊ",
    "oa": "ോ", "au": "ൗ",
}
# A consonant that ends a word is written as a chillu. കുമാര് reads as an
# unfinished syllable; കുമാർ is the name.
_ML_FINALS = {"ന്": "ൻ", "ര്": "ർ", "ല്": "ൽ", "ള്": "ൾ", "ണ്": "ൺ"}

_ML_PLACES = {
    "chennai": "ചെന്നൈ", "madras": "ചെന്നൈ",
    "coimbatore": "കോയമ്പത്തൂർ", "kovai": "കോവൈ",
    "madurai": "മധുര", "trichy": "തിരുച്ചി",
    "tiruchirappalli": "തിരുച്ചിറപ്പള്ളി",
    "salem": "സേലം", "erode": "ഈറോഡ്", "theni": "തേനി",
    "tirunelveli": "തിരുനെൽവേലി", "vellore": "വെല്ലൂർ",
    "thanjavur": "തഞ്ചാവൂർ", "tanjore": "തഞ്ചാവൂർ",
    "karur": "കരൂർ", "namakkal": "നാമക്കൽ",
    "tiruppur": "തിരുപ്പൂർ", "cuddalore": "കടലൂർ",
    "kanyakumari": "കന്യാകുമാരി", "nagercoil": "നാഗർകോവിൽ",
    "tamil nadu": "തമിഴ്നാട്", "tamilnadu": "തമിഴ്നാട്",
    "kerala": "കേരളം", "india": "ഇന്ത്യ",
}
_ML_ADDRESS = {
    "street": "തെരുവ്", "road": "റോഡ്", "rd": "റോഡ്",
    "main": "മെയിൻ", "cross": "ക്രോസ്", "nagar": "നഗർ", "colony": "കോളനി",
    "village": "ഗ്രാമം", "town": "പട്ടണം", "district": "ജില്ല",
    "taluk": "താലൂക്ക്", "post": "പോസ്റ്റ്", "near": "അടുത്ത്",
    "opposite": "എതിർവശം", "house": "വീട്", "door": "വാതിൽ",
    "floor": "നില", "temple": "ക്ഷേത്രം", "kovil": "കോവിൽ",
    "koil": "കോവിൽ", "church": "പള്ളി", "mosque": "പള്ളി",
    "school": "സ്കൂൾ", "hospital": "ആശുപത്രി", "market": "ചന്ത",
    "north": "വടക്ക്", "south": "തെക്ക്", "east": "കിഴക്ക്",
    "west": "പടിഞ്ഞാറ്", "new": "പുതിയ", "old": "പഴയ",
}
_ML_NAMES = {
    "harish": "ഹരിഷ്", "kumar": "കുമാർ", "kumari": "കുമാരി",
    "ravi": "രവി", "raja": "രാജ", "rajan": "രാജൻ", "raj": "രാജ്",
    "suresh": "സുരേഷ്", "ramesh": "രമേഷ്", "mahesh": "മഹേഷ്",
    "rajesh": "രാജേഷ്", "ganesh": "ഗണേഷ്", "dinesh": "ദിനേഷ്",
    "lakshmi": "ലക്ഷ്മി", "priya": "പ്രിയ", "devi": "ദേവി",
    "krishna": "കൃഷ്ണ", "murugan": "മുരുകൻ", "selvam": "ചെൽവം",
    "anitha": "അനിത", "kavitha": "കവിത", "sunitha": "സുനിത",
    "meena": "മീന", "latha": "ലത", "geetha": "ഗീത",
    "mohan": "മോഹൻ", "arun": "അരുൺ", "vijay": "വിജയ്",
    "sanjay": "സഞ്ജയ്", "ajay": "അജയ്", "nair": "നായർ",
    "menon": "മേനോൻ", "pillai": "പിള്ള", "kumaran": "കുമരൻ",
}

# --------------------------------------------------------------------------- #
# Telugu
# --------------------------------------------------------------------------- #

_TE_CONSONANTS = {
    "kh": "ఖ", "gh": "ఘ", "ng": "ఙ", "ch": "చ", "jn": "ఞ",
    "th": "త", "dh": "ధ", "ph": "ఫ", "bh": "భ", "sh": "ష", "zh": "ళ",
    "ks": "క్ష",
    "k": "క", "g": "గ", "c": "చ", "j": "జ", "t": "ట", "d": "ద", "n": "న",
    "p": "ప", "f": "ఫ", "b": "బ", "m": "మ", "y": "య", "r": "ర", "l": "ల",
    "v": "వ", "w": "వ", "s": "స", "h": "హ", "z": "స", "q": "క", "x": "క్స",
}
_TE_VOWELS = {
    "a": "అ", "aa": "ఆ", "i": "ఇ", "ii": "ఈ", "ee": "ఈ", "u": "ఉ",
    "uu": "ఊ", "oo": "ఊ", "e": "ఎ", "ae": "ఏ", "ai": "ఐ", "o": "ఒ",
    "oa": "ఓ", "au": "ఔ",
}
_TE_SIGNS = {
    "a": "", "aa": "ా", "i": "ి", "ii": "ీ", "ee": "ీ", "u": "ు",
    "uu": "ూ", "oo": "ూ", "e": "ె", "ae": "ే", "ai": "ై", "o": "ొ",
    "oa": "ో", "au": "ౌ",
}
_TE_PLACES = {
    "chennai": "చెన్నై", "madras": "చెన్నై",
    "coimbatore": "కోయంబత్తూరు", "madurai": "మధురై",
    "trichy": "తిరుచ్చి", "salem": "సేలం", "erode": "ఈరోడ్",
    "theni": "తేని", "tirunelveli": "తిరునెల్వేలి",
    "vellore": "వెల్లూరు", "thanjavur": "తంజావూరు",
    "karur": "కరూరు", "namakkal": "నామక్కల్",
    "tiruppur": "తిరుప్పూరు", "cuddalore": "కడలూరు",
    "kanyakumari": "కన్యాకుమారి", "nagercoil": "నాగర్‌కోవిల్",
    "tamil nadu": "తమిళనాడు", "tamilnadu": "తమిళనాడు",
    "andhra pradesh": "ఆంధ్రప్రదేశ్", "telangana": "తెలంగాణ",
    "hyderabad": "హైదరాబాద్", "india": "భారతదేశం",
}
_TE_ADDRESS = {
    "street": "వీధి", "road": "రోడ్డు", "rd": "రోడ్డు",
    "main": "ప్రధాన", "cross": "క్రాస్", "nagar": "నగర్",
    "colony": "కాలనీ", "village": "గ్రామం", "town": "పట్టణం",
    "district": "జిల్లా", "taluk": "తాలూకా", "post": "పోస్ట్",
    "near": "దగ్గర", "opposite": "ఎదురుగా", "house": "ఇల్లు",
    "door": "తలుపు", "floor": "అంతస్తు", "temple": "ఆలయం",
    "kovil": "కోవెల", "koil": "కోవెల", "church": "చర్చి",
    "mosque": "మసీదు", "school": "పాఠశాల", "hospital": "ఆసుపత్రి",
    "market": "మార్కెట్", "north": "ఉత్తర", "south": "దక్షిణ",
    "east": "తూర్పు", "west": "పడమర", "new": "కొత్త", "old": "పాత",
}
_TE_NAMES = {
    "harish": "హరీష్", "kumar": "కుమార్", "kumari": "కుమారి",
    "ravi": "రవి", "raja": "రాజా", "rajan": "రాజన్", "raj": "రాజ్",
    "suresh": "సురేష్", "ramesh": "రమేష్", "mahesh": "మహేష్",
    "rajesh": "రాజేష్", "ganesh": "గణేష్", "dinesh": "దినేష్",
    "lakshmi": "లక్ష్మి", "priya": "ప్రియ", "devi": "దేవి",
    "krishna": "కృష్ణ", "murugan": "మురుగన్", "selvam": "చెల్వం",
    "anitha": "అనిత", "kavitha": "కవిత", "sunitha": "సునీత",
    "meena": "మీన", "latha": "లత", "geetha": "గీత",
    "mohan": "మోహన్", "arun": "అరుణ్", "vijay": "విజయ్",
    "sanjay": "సంజయ్", "ajay": "అజయ్", "reddy": "రెడ్డి",
    "naidu": "నాయుడు", "rao": "రావు", "sharma": "శర్మ",
}

# --------------------------------------------------------------------------- #
# Devanagari (Hindi)
# --------------------------------------------------------------------------- #
#
# "th" is the PLAIN dental त, not the aspirated थ. Indian-English spells the
# dental with an h — Theni, Thanjavur, Kamath — and a citizen typing "theni"
# means तेनी. Reading it as थेनी produces a different word, which is the one
# thing rule 1 forbids.

_HI_CONSONANTS = {
    "kh": "ख", "gh": "घ", "ng": "ङ", "ch": "च", "jn": "ज्ञ",
    "th": "त", "dh": "ध", "ph": "फ", "bh": "भ", "sh": "श", "zh": "झ",
    "ks": "क्ष",
    "k": "क", "g": "ग", "c": "च", "j": "ज", "t": "ट", "d": "द", "n": "न",
    "p": "प", "f": "फ", "b": "ब", "m": "म", "y": "य", "r": "र", "l": "ल",
    "v": "व", "w": "व", "s": "स", "h": "ह", "z": "ज", "q": "क", "x": "क्स",
}
_HI_VOWELS = {
    "a": "अ", "aa": "आ", "i": "इ", "ii": "ई", "ee": "ई", "u": "उ",
    "uu": "ऊ", "oo": "ऊ", "e": "ए", "ae": "ए", "ai": "ऐ", "o": "ओ",
    "oa": "ओ", "au": "औ",
}
_HI_SIGNS = {
    "a": "", "aa": "ा", "i": "ि", "ii": "ी", "ee": "ी", "u": "ु",
    "uu": "ू", "oo": "ू", "e": "े", "ae": "े", "ai": "ै", "o": "ो",
    "oa": "ो", "au": "ौ",
}
_HI_PLACES = {
    "chennai": "चेन्नई", "madras": "चेन्नई",
    "coimbatore": "कोयंबटूर", "madurai": "मदुरै",
    "trichy": "त्रिची", "salem": "सेलम", "erode": "ईरोड",
    "theni": "तेनी", "tirunelveli": "तिरुनेलवेली",
    "vellore": "वेल्लोर", "thanjavur": "तंजावुर",
    "karur": "करूर", "namakkal": "नामक्कल",
    "tiruppur": "तिरुप्पुर", "cuddalore": "कडलूर",
    "kanyakumari": "कन्याकुमारी", "nagercoil": "नागरकोइल",
    "tamil nadu": "तमिलनाडु", "tamilnadu": "तमिलनाडु",
    "delhi": "दिल्ली", "india": "भारत",
}
_HI_ADDRESS = {
    "street": "गली", "road": "रोड", "rd": "रोड",
    "main": "मुख्य", "cross": "क्रॉस", "nagar": "नगर",
    "colony": "कॉलोनी", "village": "गाँव", "town": "कस्बा",
    "district": "जिला", "taluk": "तालुका", "post": "पोस्ट",
    "near": "पास", "opposite": "सामने", "house": "मकान",
    "door": "द्वार", "floor": "मंजिल", "temple": "मंदिर",
    "kovil": "मंदिर", "koil": "मंदिर", "church": "चर्च",
    "mosque": "मस्जिद", "school": "विद्यालय", "hospital": "अस्पताल",
    "market": "बाजार", "north": "उत्तर", "south": "दक्षिण",
    "east": "पूर्व", "west": "पश्चिम", "new": "नया", "old": "पुराना",
}
_HI_NAMES = {
    "harish": "हरीश", "kumar": "कुमार", "kumari": "कुमारी",
    "ravi": "रवि", "raja": "राजा", "rajan": "राजन", "raj": "राज",
    "suresh": "सुरेश", "ramesh": "रमेश", "mahesh": "महेश",
    "rajesh": "राजेश", "ganesh": "गणेश", "dinesh": "दिनेश",
    "lakshmi": "लक्ष्मी", "priya": "प्रिया", "devi": "देवी",
    "krishna": "कृष्ण", "murugan": "मुरुगन", "selvam": "सेल्वम",
    "anitha": "अनीता", "kavitha": "कविता", "sunitha": "सुनीता",
    "meena": "मीना", "latha": "लता", "geetha": "गीता",
    "mohan": "मोहन", "arun": "अरुण", "vijay": "विजय",
    "sanjay": "संजय", "ajay": "अजय", "sharma": "शर्मा",
    "verma": "वर्मा", "singh": "सिंह", "gupta": "गुप्ता",
}

# --------------------------------------------------------------------------- #

for _script in (
    Script(code="ml", pattern=PATTERNS["ml"], consonants=_ML_CONSONANTS,
           vowels_alone=_ML_VOWELS, vowel_signs=_ML_SIGNS, virama="്",
           places=_ML_PLACES, address_words=_ML_ADDRESS, names=_ML_NAMES,
           final_forms=_ML_FINALS),
    Script(code="te", pattern=PATTERNS["te"], consonants=_TE_CONSONANTS,
           vowels_alone=_TE_VOWELS, vowel_signs=_TE_SIGNS, virama="్",
           places=_TE_PLACES, address_words=_TE_ADDRESS, names=_TE_NAMES),
    Script(code="hi", pattern=PATTERNS["hi"], consonants=_HI_CONSONANTS,
           vowels_alone=_HI_VOWELS, vowel_signs=_HI_SIGNS, virama="्",
           places=_HI_PLACES, address_words=_HI_ADDRESS, names=_HI_NAMES,
           drop_final_virama=True),
):
    register(_script)
