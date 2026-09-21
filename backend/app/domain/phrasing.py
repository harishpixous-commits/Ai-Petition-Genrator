"""Every sentence the system says to a citizen, written in advance.

This module is the reason `ask` is not a model call. A field to collect plus a
reason for asking is enough to select a sentence, and selecting a sentence costs
nothing measurable — where a model call costs a round trip that the citizen
spends listening to silence.

It is also a safety property, carried over from the Node intake flow: a free
hosted model was measured producing fluent, confident and WRONG guidance to a
citizen (it directed a state government pensioner to EPFO). A model may help
read an answer. It never decides what a citizen is asked.

`rephrase.py` handles the one case where a fresh sentence genuinely helps: the
citizen has now failed the same field twice and repeating the same words a third
time is not going to work.
"""

from __future__ import annotations

import re
from typing import Literal

Language = Literal["en", "ta"]

# --------------------------------------------------------------------------- #
# Validation failures
#
# Keyed by the `code` a validator returns. Each says what is wrong and what to do
# about it, because "Invalid Aadhaar number" tells a citizen nothing they can act
# on. `{got}` and friends are filled from the validator's `detail`.
# --------------------------------------------------------------------------- #

ERRORS: dict[str, dict[Language, str]] = {
    "aadhaar.empty": {
        "en": "I did not catch any number. Please say your 12-digit Aadhaar number.",
        "ta": "எண் எதுவும் கிடைக்கவில்லை. உங்கள் 12 இலக்க ஆதார் எண்ணைச் சொல்லுங்கள்.",
    },
    "aadhaar.length": {
        "en": "The Aadhaar number must contain exactly 12 digits. I heard {got}. Please say it again.",
        "ta": "ஆதார் எண்ணில் சரியாக 12 இலக்கங்கள் இருக்க வேண்டும். {got} இலக்கங்கள் கிடைத்தன. மீண்டும் சொல்லுங்கள்.",
    },
    "aadhaar.leading": {
        "en": "An Aadhaar number never begins with 0 or 1. Please check the number and say it again.",
        "ta": "ஆதார் எண் 0 அல்லது 1 இல் தொடங்காது. எண்ணைச் சரிபார்த்து மீண்டும் சொல்லுங்கள்.",
    },
    "aadhaar.checksum": {
        "en": "That Aadhaar number did not pass the check digit, so one digit is likely wrong. Please read it once more.",
        "ta": "அந்த ஆதார் எண் சரிபார்ப்பில் தேறவில்லை; ஒரு இலக்கம் தவறாக இருக்கலாம். மீண்டும் ஒருமுறை படியுங்கள்.",
    },
    "mobile.empty": {
        "en": "I did not catch any number. Please say your 10-digit mobile number.",
        "ta": "எண் கிடைக்கவில்லை. உங்கள் 10 இலக்க கைபேசி எண்ணைச் சொல்லுங்கள்.",
    },
    "mobile.length": {
        "en": "The mobile number must contain 10 digits. I heard {got}. Please say it again.",
        "ta": "கைபேசி எண்ணில் 10 இலக்கங்கள் இருக்க வேண்டும். {got} கிடைத்தன. மீண்டும் சொல்லுங்கள்.",
    },
    "mobile.series": {
        "en": "An Indian mobile number begins with 6, 7, 8 or 9. Please check and say it again.",
        "ta": "இந்திய கைபேசி எண் 6, 7, 8 அல்லது 9 இல் தொடங்கும். சரிபார்த்து மீண்டும் சொல்லுங்கள்.",
    },
    "mobile.repeated": {
        "en": "That does not look like a real mobile number. Please say it again.",
        "ta": "அது சரியான கைபேசி எண்ணாகத் தெரியவில்லை. மீண்டும் சொல்லுங்கள்.",
    },
    "pincode.empty": {
        "en": "Please say the 6-digit PIN code.",
        "ta": "6 இலக்க அஞ்சல் குறியீட்டைச் சொல்லுங்கள்.",
    },
    "pincode.length": {
        "en": "The PIN code must contain 6 digits. I heard {got}. Please say it again.",
        "ta": "அஞ்சல் குறியீட்டில் 6 இலக்கங்கள் இருக்க வேண்டும். {got} கிடைத்தன. மீண்டும் சொல்லுங்கள்.",
    },
    "pincode.leading": {
        "en": "An Indian PIN code does not begin with 0. Please check and say it again.",
        "ta": "இந்திய அஞ்சல் குறியீடு 0 இல் தொடங்காது. சரிபார்த்து மீண்டும் சொல்லுங்கள்.",
    },
    "age.empty": {
        "en": "Please tell me your age in years.",
        "ta": "உங்கள் வயதை ஆண்டுகளில் சொல்லுங்கள்.",
    },
    "age.format": {
        "en": "Please tell me your age as a number of years, for example 45.",
        "ta": "உங்கள் வயதை எண்ணாகச் சொல்லுங்கள், எடுத்துக்காட்டாக 45.",
    },
    "age.range": {
        "en": "An age of {got} does not look right. Please tell me your age in years.",
        "ta": "{got} வயது சரியாகத் தெரியவில்லை. உங்கள் வயதை ஆண்டுகளில் சொல்லுங்கள்.",
    },
    "date.format": {
        "en": "I could not read that as a date. Please give the date as day, month and year, for example 15-03-2020.",
        "ta": "அதைத் தேதியாகப் படிக்க முடியவில்லை. நாள், மாதம், ஆண்டு வரிசையில் சொல்லுங்கள், எடுத்துக்காட்டாக 15-03-2020.",
    },
    "date.range": {
        "en": "That date is outside the range this form accepts. Please check the year.",
        "ta": "அந்தத் தேதி இந்தப் படிவம் ஏற்கும் வரம்பிற்கு வெளியே உள்ளது. ஆண்டைச் சரிபார்க்கவும்.",
    },
    "date.future": {
        "en": "That date is in the future. Please give the date on which it actually happened.",
        "ta": "அந்தத் தேதி எதிர்காலத்தில் உள்ளது. உண்மையில் நடந்த தேதியைச் சொல்லுங்கள்.",
    },
    "dob.range": {
        "en": "That date of birth gives an age above 120 years. Please check the year.",
        "ta": "அந்தப் பிறந்த தேதி 120 ஆண்டுகளுக்கு மேல் வயதைத் தருகிறது. ஆண்டைச் சரிபார்க்கவும்.",
    },
    "email.empty": {
        "en": "Please say your email address, or say skip if you do not have one.",
        "ta": "உங்கள் மின்னஞ்சல் முகவரியைச் சொல்லுங்கள், இல்லையெனில் 'தவிர்' எனச் சொல்லுங்கள்.",
    },
    "email.format": {
        "en": "That does not look like a complete email address. Please say it again, including the part after the @ sign.",
        "ta": "அது முழுமையான மின்னஞ்சல் முகவரியாகத் தெரியவில்லை. @ குறிக்குப் பின் உள்ள பகுதியுடன் மீண்டும் சொல்லுங்கள்.",
    },
    "email.length": {
        "en": "That email address is too long. Please check it and say it again.",
        "ta": "அந்த மின்னஞ்சல் முகவரி மிக நீளமாக உள்ளது. சரிபார்த்து மீண்டும் சொல்லுங்கள்.",
    },
    "name.empty": {
        "en": "I did not catch the name. Please say it again.",
        "ta": "பெயர் கிடைக்கவில்லை. மீண்டும் சொல்லுங்கள்.",
    },
    "name.short": {
        "en": "That name seems too short. Please say the full name.",
        "ta": "அந்தப் பெயர் மிகச் சிறியதாக உள்ளது. முழுப் பெயரைச் சொல்லுங்கள்.",
    },
    "name.long": {
        "en": "That name is longer than this form allows. Please give the name as it appears on your identity document.",
        "ta": "அந்தப் பெயர் இந்தப் படிவம் அனுமதிப்பதை விட நீளமானது. அடையாள ஆவணத்தில் உள்ளபடி பெயரைச் சொல்லுங்கள்.",
    },
    "name.digits": {
        "en": "A name cannot contain numbers. Please say the name again.",
        "ta": "பெயரில் எண்கள் இருக்க முடியாது. பெயரை மீண்டும் சொல்லுங்கள்.",
    },
    "name.characters": {
        "en": "I could not read that as a name. Please say it again, or spell it.",
        "ta": "அதைப் பெயராகப் படிக்க முடியவில்லை. மீண்டும் சொல்லுங்கள் அல்லது எழுத்துக்கூட்டிச் சொல்லுங்கள்.",
    },
    "address.empty": {
        "en": "Please give your full address.",
        "ta": "உங்கள் முழு முகவரியைச் சொல்லுங்கள்.",
    },
    "address.short": {
        "en": "Please give the full address, including the street and the town or village.",
        "ta": "தெரு மற்றும் ஊர் உட்பட முழு முகவரியைச் சொல்லுங்கள்.",
    },
    "address.long": {
        "en": "That address is longer than the form allows. Please give the postal address only.",
        "ta": "அந்த முகவரி படிவம் அனுமதிப்பதை விட நீளமானது. அஞ்சல் முகவரியை மட்டும் சொல்லுங்கள்.",
    },
    "boolean.unclear": {
        "en": "Please answer yes or no.",
        "ta": "ஆம் அல்லது இல்லை என்று பதிலளிக்கவும்.",
    },
    "amount.empty": {"en": "Please tell me the amount in rupees.", "ta": "தொகையை ரூபாயில் சொல்லுங்கள்."},
    "amount.format": {
        "en": "I could not read that as an amount. Please say the amount in rupees, for example 50,000.",
        "ta": "அதைத் தொகையாகப் படிக்க முடியவில்லை. ரூபாயில் சொல்லுங்கள், எடுத்துக்காட்டாக 50,000.",
    },
    "amount.range": {
        "en": "That amount is outside the range this form accepts. Please check the figure.",
        "ta": "அந்தத் தொகை இந்தப் படிவம் ஏற்கும் வரம்பிற்கு வெளியே உள்ளது. எண்ணிக்கையைச் சரிபார்க்கவும்.",
    },
    "pan.empty": {"en": "Please say your PAN.", "ta": "உங்கள் PAN எண்ணைச் சொல்லுங்கள்."},
    "pan.format": {
        "en": "A PAN has five letters, four digits and one letter, for example ABCDE1234F. Please say it again.",
        "ta": "PAN இல் ஐந்து எழுத்துகள், நான்கு இலக்கங்கள், ஒரு எழுத்து இருக்கும் — ABCDE1234F. மீண்டும் சொல்லுங்கள்.",
    },
    "voter_id.empty": {"en": "Please say your voter ID number.", "ta": "உங்கள் வாக்காளர் அடையாள எண்ணைச் சொல்லுங்கள்."},
    "voter_id.format": {
        "en": "A voter ID has three letters followed by seven digits, for example ABC1234567. Please say it again.",
        "ta": "வாக்காளர் அடையாள எண்ணில் மூன்று எழுத்துகள், ஏழு இலக்கங்கள் இருக்கும் — ABC1234567. மீண்டும் சொல்லுங்கள்.",
    },
    "ifsc.empty": {"en": "Please say the bank IFSC code.", "ta": "வங்கியின் IFSC குறியீட்டைச் சொல்லுங்கள்."},
    "ifsc.format": {
        "en": "An IFSC has four letters, a zero, then six characters, for example SBIN0001234. Please say it again.",
        "ta": "IFSC இல் நான்கு எழுத்துகள், ஒரு பூஜ்ஜியம், பின் ஆறு எழுத்துகள் இருக்கும் — SBIN0001234. மீண்டும் சொல்லுங்கள்.",
    },
    "bank_account.empty": {"en": "Please say your bank account number.", "ta": "உங்கள் வங்கிக் கணக்கு எண்ணைச் சொல்லுங்கள்."},
    "bank_account.length": {
        "en": "A bank account number has between 9 and 18 digits. I heard {got}. Please say it again.",
        "ta": "வங்கிக் கணக்கு எண்ணில் 9 முதல் 18 இலக்கங்கள் இருக்கும். {got} கிடைத்தன. மீண்டும் சொல்லுங்கள்.",
    },
    "ration_card.empty": {"en": "Please say your ration card number.", "ta": "உங்கள் ரேஷன் அட்டை எண்ணைச் சொல்லுங்கள்."},
    "ration_card.format": {
        "en": "I could not read that as a ration card number. Please say it again.",
        "ta": "அதை ரேஷன் அட்டை எண்ணாகப் படிக்க முடியவில்லை. மீண்டும் சொல்லுங்கள்.",
    },
    "district.empty": {"en": "Please tell me the district.", "ta": "மாவட்டத்தைச் சொல்லுங்கள்."},
    "district.format": {
        "en": "I could not read that as a district name. Please say the district again.",
        "ta": "அதை மாவட்டப் பெயராகப் படிக்க முடியவில்லை. மீண்டும் சொல்லுங்கள்.",
    },
    "text.empty": {"en": "I did not catch that. Please say it again.", "ta": "புரியவில்லை. மீண்டும் சொல்லுங்கள்."},
    "text.short": {"en": "Please give a little more detail.", "ta": "சற்று மேலும் விவரமாகச் சொல்லுங்கள்."},
    "text.long": {
        # Says the limit, because the alternative is a citizen guessing how much
        # to cut. Nothing they said is discarded on their behalf.
        "en": "That is longer than this petition can carry ({got} characters; the limit is {limit}). Please shorten it and tell me again.",
        "ta": "இது இந்த மனுவில் இடம்பெற முடியாத அளவு நீளமாக உள்ளது ({got} எழுத்துகள்; வரம்பு {limit}). சுருக்கி மீண்டும் சொல்லுங்கள்.",
    },
}

_ERROR_FALLBACK: dict[Language, str] = {
    "en": "That answer could not be accepted. Please say it again.",
    "ta": "அந்தப் பதிலை ஏற்க முடியவில்லை. மீண்டும் சொல்லுங்கள்.",
}

# --------------------------------------------------------------------------- #
# Conversation furniture
# --------------------------------------------------------------------------- #

PHRASES: dict[str, dict[Language, str]] = {
    "not_understood": {
        "en": "I did not catch that. Please say it again.",
        "ta": "புரியவில்லை. மீண்டும் சொல்லுங்கள்.",
    },
    "confirm_intro": {
        "en": "Here is what I have recorded. Please check it.",
        "ta": "நான் பதிவு செய்தவை இங்கே உள்ளன. சரிபார்க்கவும்.",
    },
    "confirm_ask": {
        "en": "Is all of this correct? Say yes to prepare the letter, or tell me what to change.",
        "ta": "இவை அனைத்தும் சரியா? கடிதத்தைத் தயாரிக்க 'ஆம்' எனச் சொல்லுங்கள், அல்லது என்ன மாற்ற வேண்டும் எனச் சொல்லுங்கள்.",
    },
    "confirm_unclear": {
        "en": "Please say yes to prepare the letter, or tell me which detail to change.",
        "ta": "கடிதத்தைத் தயாரிக்க 'ஆம்' எனச் சொல்லுங்கள், அல்லது எந்த விவரத்தை மாற்ற வேண்டும் எனச் சொல்லுங்கள்.",
    },
    "generated": {
        "en": "Your letter is ready. You can review it and download it as a document.",
        "ta": "உங்கள் கடிதம் தயாராக உள்ளது. அதைப் பார்வையிட்டு ஆவணமாகப் பதிவிறக்கலாம்.",
    },
    "revising": {
        "en": "I am rewriting your petition with that change. Your details stay as they are.",
        "ta": "அந்த மாற்றத்துடன் உங்கள் மனுவை மீண்டும் எழுதுகிறேன். உங்கள் விவரங்கள் அப்படியே இருக்கும்.",
    },
    "restarted": {
        "en": "I have cleared everything. Tell me what letter you need.",
        "ta": "அனைத்தையும் அழித்துவிட்டேன். உங்களுக்கு என்ன கடிதம் தேவை எனச் சொல்லுங்கள்.",
    },
    "edited_saved": {
        "en": "Your changes have been saved and the document has been remade.",
        "ta": "உங்கள் மாற்றங்கள் சேமிக்கப்பட்டு ஆவணம் மீண்டும் தயாரிக்கப்பட்டது.",
    },
    "edited_missing": {
        # Said when a hand edit removed a detail the form recorded. It is the
        # citizen's document, so this is a warning and not a refusal.
        "en": ("These details are no longer in the petition after your edit: "
               "{fields}. The document has been saved as you wrote it."),
        "ta": ("உங்கள் திருத்தத்திற்குப் பிறகு இந்த விவரங்கள் மனுவில் இல்லை: "
               "{fields}. நீங்கள் எழுதியபடியே ஆவணம் சேமிக்கப்பட்டுள்ளது."),
    },
    "attach_waiting": {
        # Said after "yes, I have something". The citizen has agreed to attach
        # but has not attached yet, so the session waits rather than advancing.
        "en": ("Please add the file using the attach button. Tell me when you "
               "are done, or say continue to prepare the petition as it is."),
        "ta": ("இணைப்பு பொத்தானைப் பயன்படுத்தி கோப்பைச் சேர்க்கவும். முடிந்ததும் "
               "சொல்லுங்கள், அல்லது இப்படியே மனுவைத் தயாரிக்க 'தொடரவும்' "
               "எனச் சொல்லுங்கள்."),
    },
    "attachment_unreadable": {
        # An honest sentence for a photograph with no OCR engine behind it.
        "en": ("I could not read the text in that file, so I will attach it "
               "without reading it. If it has a reference number, please tell "
               "me the number."),
        "ta": ("அந்தக் கோப்பிலிருந்து உரையைப் படிக்க முடியவில்லை; அதை அப்படியே "
               "இணைக்கிறேன். அதில் ஒப்புகை எண் இருந்தால், அந்த எண்ணைச் "
               "சொல்லுங்கள்."),
    },
    "cancelled": {
        "en": "This request has been cancelled. Nothing has been saved.",
        "ta": "இந்தக் கோரிக்கை ரத்து செய்யப்பட்டது. எதுவும் சேமிக்கப்படவில்லை.",
    },
    "which_field": {
        # Asked after "no" at the read-back. Naming the fields matters: a citizen
        # who is told only "what should I change?" has to invent the vocabulary.
        "en": "Which detail should I change? You can say: {fields}.",
        "ta": "எந்த விவரத்தை மாற்ற வேண்டும்? நீங்கள் சொல்லலாம்: {fields}.",
    },
    "translation_unavailable": {
        "en": "The petition is shown in the language it was drafted in: no translation service was available.",
        "ta": "மொழிபெயர்ப்புச் சேவை கிடைக்காததால், மனு அது தயாரிக்கப்பட்ட மொழியிலேயே காட்டப்படுகிறது.",
    },
    "pdf_unavailable": {
        "en": "Only the Word document could be produced. The PDF converter is not available on this server.",
        "ta": "Word ஆவணம் மட்டுமே தயாரிக்க முடிந்தது. இந்தச் சேவையகத்தில் PDF மாற்றி கிடைக்கவில்லை.",
    },
    "turn_failed": {
        "en": "That could not be processed. Your details are saved. Please try again.",
        "ta": "அதைச் செயலாக்க முடியவில்லை. உங்கள் விவரங்கள் சேமிக்கப்பட்டுள்ளன. மீண்டும் முயற்சிக்கவும்.",
    },
    # Two different things, and they were being reported with one sentence.
    # A single utterance that could not be transcribed leaves the microphone
    # open and the session running: telling that citizen dictation has stopped
    # is false, and it sends them to the keyboard when saying it again would
    # have worked. `dictation_stopped` is kept for when it really has.
    "dictation_failed": {
        "en": "Voice recognition is temporarily unavailable. "
              "Please say that again, or type instead.",
        "ta": "குரல் அடையாளம் "
              "தற்காலிகமாக "
              "இயங்கவில்லை. "
              "மீண்டும் சொல்லுங்கள், "
              "அல்லது தட்டச்சு "
              "செய்யவும்.",
    },
    "dictation_stopped": {
        "en": "Dictation has stopped. You can type instead.",
        "ta": "ஒலிவாங்கி நிறுத்தப்பட்டது. நீங்கள் தட்டச்சு செய்யலாம்.",
    },
    "render_failed": {
        "en": "The letter could not be produced just now. Your details are saved, so please try again in a moment.",
        "ta": "கடிதத்தைத் தயாரிக்க இப்போது முடியவில்லை. உங்கள் விவரங்கள் சேமிக்கப்பட்டுள்ளன; சிறிது நேரம் கழித்து முயற்சிக்கவும்.",
    },
    "verify_failed": {
        "en": "The letter was produced but a check found a missing detail, so it has been held back. Please try again.",
        "ta": "கடிதம் தயாரிக்கப்பட்டது, ஆனால் ஒரு விவரம் விடுபட்டிருப்பதைச் சரிபார்ப்பு கண்டறிந்ததால் அது நிறுத்தி வைக்கப்பட்டுள்ளது. மீண்டும் முயற்சிக்கவும்.",
    },
}

DISCLAIMER: dict[Language, str] = {
    "en": (
        "This letter was prepared from what you told the assistant. Check every "
        "detail before signing or submitting it. It is not legal advice and it "
        "does not decide your eligibility."
    ),
    "ta": (
        "இந்தக் கடிதம் நீங்கள் உதவியாளரிடம் சொன்னதிலிருந்து தயாரிக்கப்பட்டது. "
        "கையொப்பமிடுவதற்கு அல்லது சமர்ப்பிப்பதற்கு முன் ஒவ்வொரு விவரத்தையும் சரிபார்க்கவும். "
        "இது சட்ட ஆலோசனை அல்ல; உங்கள் தகுதியை இது தீர்மானிக்காது."
    ),
}


def phrase(key: str, language: Language = "en") -> str:
    entry = PHRASES.get(key)
    if not entry:
        return ""
    return entry.get(language) or entry["en"]


def error_text(code: str, language: Language = "en", detail: dict | None = None) -> str:
    """The citizen-facing sentence for a validator failure code."""
    entry = ERRORS.get(code)
    template = (entry.get(language) or entry["en"]) if entry else _ERROR_FALLBACK[language]
    try:
        return template.format(**(detail or {}))
    except (KeyError, IndexError):
        # A template referencing a detail the validator did not supply must not
        # take down the turn; the un-substituted sentence is still useful.
        return re.sub(r"\{\w+\}", "", template).replace("  ", " ").strip()
