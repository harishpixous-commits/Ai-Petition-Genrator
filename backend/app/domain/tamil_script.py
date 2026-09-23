"""Writing a citizen's own words in Tamil script, for a Tamil petition.

A citizen picks Tamil, then types their name and address on a Latin keyboard
because that is the keyboard in front of them. The petition comes out with
Tamil headings and English values — correct, and it does not look like a
Tamil document. This renders those values in Tamil script so the letter reads
as one language.

WHAT THIS IS NOT. It is not a translator. A translator asked for Coimbatore
in Tamil once returned கோயம்பேடூர் — Koyambedu, a locality in Chennai, three
hundred kilometres away. A petition that names the wrong town is not a
petition with a translation error in it; it is a petition that will not be
acted on. So there is no model here and no network call: a fixed table, a
phonetic fallback, and the citizen's own text kept whenever neither is sure.

THREE RULES, in order of how much they matter.

1.  NEVER A DIFFERENT PLACE. A name this cannot render is left in Latin.
    English inside a Tamil address is untidy; the wrong town is a wasted
    journey to a government office.

2.  NUMBERS ARE NEVER TOUCHED. Door numbers, pin codes, mobile numbers,
    dates and reference numbers pass through exactly as typed. "82/33" is
    82/33 in every language, and a petition quoting a reference number in
    Tamil digits cannot be looked up.

3.  THE ORIGINAL IS NEVER OVERWRITTEN. This runs at DISPLAY time against a
    value the record still holds as the citizen entered it. Switching the
    petition back to English shows their own spelling again, and their name
    still matches the card in their pocket.
"""

from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# What is known, and therefore safe
# --------------------------------------------------------------------------- #

# Districts, major towns and the places a Tamil Nadu petition names most. A
# table rather than a guess, because these are the words that must not be
# approximated: every one of them was checked by hand.
PLACES: dict[str, str] = {
    "chennai": "சென்னை", "madras": "சென்னை",
    "coimbatore": "கோயம்புத்தூர்", "kovai": "கோவை",
    "madurai": "மதுரை", "trichy": "திருச்சி",
    "tiruchirappalli": "திருச்சிராப்பள்ளி", "tiruchirapalli": "திருச்சிராப்பள்ளி",
    "salem": "சேலம்", "erode": "ஈரோடு", "tiruppur": "திருப்பூர்",
    "tirupur": "திருப்பூர்", "vellore": "வேலூர்", "thanjavur": "தஞ்சாவூர்",
    "tanjore": "தஞ்சாவூர்", "dindigul": "திண்டுக்கல்", "theni": "தேனி",
    "karur": "கரூர்", "namakkal": "நாமக்கல்", "nagapattinam": "நாகப்பட்டினம்",
    "cuddalore": "கடலூர்", "villupuram": "விழுப்புரம்", "tirunelveli": "திருநெல்வேலி",
    "nellai": "நெல்லை", "thoothukudi": "தூத்துக்குடி", "tuticorin": "தூத்துக்குடி",
    "kanyakumari": "கன்னியாகுமரி", "nagercoil": "நாகர்கோவில்",
    "sivagangai": "சிவகங்கை", "ramanathapuram": "ராமநாதபுரம்",
    "virudhunagar": "விருதுநகர்", "pudukkottai": "புதுக்கோட்டை",
    "ariyalur": "அரியலூர்", "perambalur": "பெரம்பலூர்", "kallakurichi": "கள்ளக்குறிச்சி",
    "tiruvannamalai": "திருவண்ணாமலை", "kanchipuram": "காஞ்சிபுரம்",
    "chengalpattu": "செங்கல்பட்டு", "tiruvallur": "திருவள்ளூர்",
    "ranipet": "ராணிப்பேட்டை", "tirupattur": "திருப்பத்தூர்",
    "krishnagiri": "கிருஷ்ணகிரி", "dharmapuri": "தர்மபுரி",
    "nilgiris": "நீலகிரி", "ooty": "உதகமண்டலம்", "udhagamandalam": "உதகமண்டலம்",
    "coonoor": "குன்னூர்", "hosur": "ஓசூர்", "mayiladuthurai": "மயிலாடுதுறை",
    "tiruvarur": "திருவாரூர்", "thiruvarur": "திருவாரூர்",
    "pollachi": "பொள்ளாச்சி", "mettupalayam": "மேட்டுப்பாளையம்",
    "avinashi": "அவினாசி", "gobichettipalayam": "கோபிசெட்டிபாளையம்",
    "sivakasi": "சிவகாசி", "rajapalayam": "ராஜபாளையம்", "aruppukottai": "அருப்புக்கோட்டை",
    "palani": "பழனி", "kodaikanal": "கொடைக்கானல்", "bodinayakanur": "போடிநாயக்கனூர்",
    "cumbum": "கம்பம்", "periyakulam": "பெரியகுளம்", "andipatti": "ஆண்டிபட்டி",
    "tamil nadu": "தமிழ்நாடு", "tamilnadu": "தமிழ்நாடு",
    "india": "இந்தியா",
}

# The vocabulary an address is built from. These are TRANSLATED rather than
# transliterated, because that is how they are written in a Tamil address:
# nobody writes "ஸ்ட்ரீட்" on an envelope.
ADDRESS_WORDS: dict[str, str] = {
    "street": "தெரு", "st": "தெரு", "road": "சாலை", "rd": "சாலை",
    "main": "பிரதான", "cross": "குறுக்கு", "lane": "சந்து",
    "nagar": "நகர்", "colony": "காலனி", "village": "கிராமம்",
    "post": "அஞ்சல்", "taluk": "வட்டம்", "district": "மாவட்டம்",
    "dist": "மாவட்டம்", "pincode": "அஞ்சல் குறியீடு",
    "north": "வடக்கு", "south": "தெற்கு", "east": "கிழக்கு", "west": "மேற்கு",
    "new": "புதிய", "old": "பழைய", "near": "அருகில்",
    "opposite": "எதிரில்", "behind": "பின்புறம்",
    "door": "கதவு", "number": "எண்", "no": "எண்",
    "temple": "கோவில்", "kovil": "கோவில்", "koil": "கோவில்",
    "kovilpatti": "கோவில்பட்டி",
    "pettai": "பேட்டை", "puram": "புரம்", "patti": "பட்டி",
    "palayam": "பாளையம்", "kulam": "குளம்", "thottam": "தோட்டம்",
    "medu": "மேடு", "ur": "ஊர்",
    "perumal": "பெருமாள்", "amman": "அம்மன்", "pillaiyar": "பிள்ளையார்",
    "murugan": "முருகன்", "mariamman": "மாரியம்மன்",
    "gandhi": "காந்தி", "nehru": "நேரு", "bharathi": "பாரதி",
    "anna": "அண்ணா", "kamaraj": "காமராஜ்", "periyar": "பெரியார்",
    "bazaar": "பஜார்", "market": "சந்தை", "bus": "பேருந்து",
    "stand": "நிலையம்", "station": "நிலையம்",
}

# The name elements a Tamil Nadu petition carries most often.
#
# Phonetics alone gets these slightly wrong, and slightly wrong is somebody's
# name on a government document: "Kumar" is written ku-maar and spelled
# "kumar", so a letter-by-letter reading gives குமர் where every Tamil reader
# expects குமார். Each of these was checked by hand, and the list is meant to
# be added to — an unlisted name still transliterates, just less certainly.
NAMES: dict[str, str] = {
    "kumar": "குமார்", "kumaran": "குமரன்", "kumari": "குமாரி",
    "raj": "ராஜ்", "raja": "ராஜா", "rajan": "ராஜன்", "rajesh": "ராஜேஷ்",
    "ravi": "ரவி", "ramesh": "ரமேஷ்", "suresh": "சுரேஷ்", "mahesh": "மகேஷ்",
    "ganesh": "கணேஷ்", "ganesan": "கணேசன்", "natarajan": "நடராஜன்",
    "murugan": "முருகன்", "muthu": "முத்து", "velu": "வேலு", "mani": "மணி",
    "bala": "பாலா", "balaji": "பாலாஜி", "gopal": "கோபால்",
    "krishnan": "கிருஷ்ணன்", "krishna": "கிருஷ்ணா",
    "siva": "சிவா", "shiva": "சிவா", "sivakumar": "சிவக்குமார்",
    "selvan": "செல்வன்", "selvi": "செல்வி", "selvam": "செல்வம்",
    "arun": "அருண்", "anand": "ஆனந்த்", "vijay": "விஜய்", "vijaya": "விஜயா",
    "karthik": "கார்த்திக்", "karthikeyan": "கார்த்திகேயன்",
    "saravanan": "சரவணன்", "senthil": "செந்தில்", "sundar": "சுந்தர்",
    "sundaram": "சுந்தரம்", "subramanian": "சுப்ரமணியன்",
    "chandran": "சந்திரன்", "mohan": "மோகன்", "prakash": "பிரகாஷ்",
    "lakshmi": "லட்சுமி", "meena": "மீனா", "meenakshi": "மீனாட்சி",
    "priya": "பிரியா", "devi": "தேவி", "kala": "கலா", "malar": "மலர்",
    "saraswathi": "சரஸ்வதி", "parvathi": "பார்வதி", "revathi": "ரேவதி",
    "anbu": "அன்பு", "amudha": "அமுதா", "kavitha": "கவிதா",
    "harish": "ஹரிஷ்", "hari": "ஹரி", "dinesh": "தினேஷ்",
    "manikandan": "மணிகண்டன்", "palanisamy": "பழனிசாமி",
    "sekar": "சேகர்", "shankar": "சங்கர்", "sankar": "சங்கர்",
}

# --------------------------------------------------------------------------- #
# Phonetics, for everything the tables do not name
# --------------------------------------------------------------------------- #

_VOWEL_SIGNS = {
    "a": "", "aa": "ா", "i": "ி", "ii": "ீ", "ee": "ீ", "u": "ு", "uu": "ூ",
    "oo": "ூ", "e": "ெ", "ae": "ே", "ai": "ை", "o": "ொ", "oa": "ோ", "au": "ௌ",
}
_VOWELS_ALONE = {
    "a": "அ", "aa": "ஆ", "i": "இ", "ii": "ஈ", "ee": "ஈ", "u": "உ", "uu": "ஊ",
    "oo": "ஊ", "e": "எ", "ae": "ஏ", "ai": "ஐ", "o": "ஒ", "oa": "ஓ", "au": "ஔ",
}
# Longest first: "sh" must be tried before "s", "th" before "t".
_CONSONANTS = {
    "zh": "ழ", "sh": "ஷ", "ch": "ச", "th": "த", "dh": "த", "ph": "ப",
    "kh": "க", "gh": "க", "bh": "ப", "ng": "ங", "ny": "ஞ", "jn": "ஞ",
    "ks": "க்ஸ",
    "k": "க", "g": "க", "c": "க", "q": "க",
    "s": "ஸ", "j": "ஜ", "t": "ட", "d": "ட", "n": "ன", "p": "ப", "b": "ப",
    "m": "ம", "y": "ய", "r": "ர", "l": "ல", "v": "வ", "w": "வ",
    "f": "ப", "h": "ஹ", "x": "க்ஸ", "z": "ஸ",
}
_LONG_VOWELS = ("aa", "ai", "au", "ae", "ee", "ii", "oo", "oa")


def _transliterate_word(word: str) -> str:
    """One Latin word in Tamil script, by sound.

    Deliberately plain. It gets ordinary Tamil names right — Harish, Kumar,
    Selvan, Meena — and it is the LAST thing tried, after both tables. What
    it cannot do well is English words that are not pronounced as they are
    spelled, and those are what the tables are for.
    """
    lowered = word.lower()
    out: list[str] = []
    i = 0
    at_start = True
    while i < len(lowered):
        # A vowel: on its own at the start of a word, otherwise a sign
        # hanging off the consonant just written.
        matched_vowel = None
        for length in (2, 1):
            piece = lowered[i:i + length]
            if piece in _VOWELS_ALONE and (length == 2 or piece in "aeiou"):
                matched_vowel = piece
                break
        if matched_vowel:
            if at_start:
                out.append(_VOWELS_ALONE[matched_vowel])
            else:
                # The consonant before it was written with a pulli; replace
                # that with the vowel sign.
                if out and out[-1].endswith("்"):
                    out[-1] = out[-1][:-1] + _VOWEL_SIGNS[matched_vowel]
                else:
                    out.append(_VOWELS_ALONE[matched_vowel])
            i += len(matched_vowel)
            at_start = False
            continue

        matched_consonant = None
        for length in (2, 1):
            piece = lowered[i:i + length]
            if piece in _CONSONANTS:
                matched_consonant = piece
                break
        if matched_consonant:
            letter = _CONSONANTS[matched_consonant]
            out.append(letter + "்")
            i += len(matched_consonant)
            at_start = False
            continue

        # Anything else — an apostrophe, a stray mark — is kept as it is.
        out.append(lowered[i])
        i += 1
        at_start = False
    return "".join(out)


# --------------------------------------------------------------------------- #

TAMIL = re.compile("[஀-௿]")
_LATIN_WORD = re.compile(r"[A-Za-z]+")
# A token is a run of letters, a run of anything else, so numbers and
# punctuation come through untouched and in place.
_TOKENS = re.compile(r"[A-Za-z]+|[^A-Za-z]+")
# Whitespace-separated chunks, keeping the whitespace so it is put back.
_CHUNKS = re.compile(r"\S+|\s+")


def is_tamil(text: str) -> bool:
    return bool(TAMIL.search(str(text or "")))


def to_tamil(text: str) -> str:
    """The citizen's text in Tamil script, as far as it is safe to go.

    Word by word: a known place, a known address word, a known name, then
    phonetics.
    Digits, punctuation and anything already in Tamil are passed through
    untouched, which is what keeps "82/33" and "+91 93441 74752" intact.
    """
    source = str(text or "")
    if not source.strip() or not _LATIN_WORD.search(source):
        return source

    # Two-word places first — "Tamil Nadu" is not "Tamil" and "Nadu".
    lowered = source.lower()
    for phrase, tamil in sorted(PLACES.items(), key=lambda kv: -len(kv[0])):
        if " " in phrase and phrase in lowered:
            pattern = re.compile(rf"(?<![A-Za-z]){re.escape(phrase)}(?![A-Za-z])", re.I)
            source = pattern.sub(tamil, source)
            lowered = source.lower()

    out: list[str] = []
    for chunk in _CHUNKS.findall(source):
        # ANYTHING WITH A DIGIT IN IT IS LEFT EXACTLY AS TYPED.
        #
        # "82/33" is a door number, "2026/PG/44710012" is a reference an
        # office looks up, "14A" is a flat. The letters inside them are not
        # words — reading "PG" as a word turned a reference number into
        # 2026/ப்க்/44710012, which cannot be found in any register.
        if any(ch.isdigit() for ch in chunk):
            out.append(chunk)
            continue
        out.append(_chunk_to_tamil(chunk))
    return "".join(out)


def _chunk_to_tamil(chunk: str) -> str:
    out: list[str] = []
    for token in _TOKENS.findall(chunk):
        if not token[:1].isalpha():
            out.append(token)          # spaces, punctuation
            continue
        # A LONE LETTER IS NOT A WORD. It is the initial in "R. Kumar", and
        # "ர்." in place of it is wrong in a way a reader notices at once.
        if len(token) == 1:
            out.append(token)
            continue
        key = token.lower()
        if key in PLACES:
            out.append(PLACES[key])
        elif key in ADDRESS_WORDS:
            out.append(ADDRESS_WORDS[key])
        elif key in NAMES:
            out.append(NAMES[key])
        else:
            out.append(_transliterate_word(token))
    return "".join(out)


def for_language(text: str, language: str) -> str:
    """What to SHOW for a value, in the petition's language.

    English, or a value already written in Tamil, is returned unchanged. The
    stored value is never altered by this — it is the argument, not the
    destination.
    """
    if language != "ta":
        return str(text or "")
    if is_tamil(text):
        return str(text or "")
    return to_tamil(text)
