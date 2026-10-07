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
    
        "ml": "നമ്പർ കേട്ടില്ല. താങ്കളുടെ 12 അക്ക ആധാർ നമ്പർ പറയുക.",
        "te": "సంఖ్య వినిపించలేదు. మీ 12 అంకెల ఆధార్ సంఖ్య చెప్పండి.",
        "hi": "कोई संख्या सुनाई नहीं दी। कृपया अपना 12 अंकों का आधार नंबर बताएँ।",
    },
    "aadhaar.length": {
        "en": "The Aadhaar number must contain exactly 12 digits. I heard {got}. Please say it again.",
        "ta": "ஆதார் எண்ணில் சரியாக 12 இலக்கங்கள் இருக்க வேண்டும். {got} இலக்கங்கள் கிடைத்தன. மீண்டும் சொல்லுங்கள்.",
    
        "ml": "ആധാർ നമ്പറിൽ കൃത്യം 12 അക്കങ്ങൾ വേണം. ഞാൻ കേട്ടത് {got}. ദയവായി വീണ്ടും പറയുക.",
        "te": "ఆధార్ సంఖ్యలో సరిగ్గా 12 అంకెలు ఉండాలి. నేను విన్నది {got}. దయచేసి మళ్ళీ చెప్పండి.",
        "hi": "आधार नंबर में ठीक 12 अंक होने चाहिए। मैंने {got} सुना। कृपया दोबारा बताएँ।",
    },
    "aadhaar.leading": {
        "en": "An Aadhaar number never begins with 0 or 1. Please check the number and say it again.",
        "ta": "ஆதார் எண் 0 அல்லது 1 இல் தொடங்காது. எண்ணைச் சரிபார்த்து மீண்டும் சொல்லுங்கள்.",
    
        "ml": "ആധാർ നമ്പർ 0 അല്ലെങ്കിൽ 1 കൊണ്ട് തുടങ്ങാറില്ല. നമ്പർ പരിശോധിച്ച് വീണ്ടും പറയുക.",
        "te": "ఆధార్ సంఖ్య 0 లేదా 1తో మొదలవదు. సంఖ్యను చూసి మళ్ళీ చెప్పండి.",
        "hi": "आधार नंबर 0 या 1 से आरंभ नहीं होता। संख्या जाँचकर दोबारा बताएँ।",
    },
    "aadhaar.checksum": {
        "en": "That Aadhaar number did not pass the check digit, so one digit is likely wrong. Please read it once more.",
        "ta": "அந்த ஆதார் எண் சரிபார்ப்பில் தேறவில்லை; ஒரு இலக்கம் தவறாக இருக்கலாம். மீண்டும் ஒருமுறை படியுங்கள்.",
    
        "ml": "ആ ആധാർ നമ്പർ പരിശോധനയിൽ ശരിയായില്ല; ഒരു അക്കം തെറ്റിയിരിക്കാം. ഒന്നുകൂടി വായിക്കുക.",
        "te": "ఆ ఆధార్ సంఖ్య తనిఖీలో సరిపోలేదు; ఒక అంకె తప్పు కావచ్చు. మరోసారి చదవండి.",
        "hi": "वह आधार नंबर जाँच अंक पर खरा नहीं उतरा, इसलिए कोई एक अंक ग़लत लगता है। कृपया एक बार और पढ़ें।",
    },
    "mobile.empty": {
        "en": "I did not catch any number. Please say your 10-digit mobile number.",
        "ta": "எண் கிடைக்கவில்லை. உங்கள் 10 இலக்க கைபேசி எண்ணைச் சொல்லுங்கள்.",
    
        "ml": "നമ്പർ കേട്ടില്ല. താങ്കളുടെ 10 അക്ക മൊബൈൽ നമ്പർ പറയുക.",
        "te": "సంఖ్య వినిపించలేదు. మీ 10 అంకెల మొబైల్ సంఖ్య చెప్పండి.",
        "hi": "कोई संख्या सुनाई नहीं दी। कृपया अपना 10 अंकों का मोबाइल नंबर बताएँ।",
    },
    "mobile.length": {
        "en": "The mobile number must contain 10 digits. I heard {got}. Please say it again.",
        "ta": "கைபேசி எண்ணில் 10 இலக்கங்கள் இருக்க வேண்டும். {got} கிடைத்தன. மீண்டும் சொல்லுங்கள்.",
    
        "ml": "മൊബൈൽ നമ്പറിൽ 10 അക്കങ്ങൾ വേണം. ഞാൻ കേട്ടത് {got}. ദയവായി വീണ്ടും പറയുക.",
        "te": "మొబైల్ సంఖ్యలో 10 అంకెలు ఉండాలి. నేను విన్నది {got}. దయచేసి మళ్ళీ చెప్పండి.",
        "hi": "मोबाइल नंबर में 10 अंक होने चाहिए। मैंने {got} सुना। कृपया दोबारा बताएँ।",
    },
    "mobile.series": {
        "en": "An Indian mobile number begins with 6, 7, 8 or 9. Please check and say it again.",
        "ta": "இந்திய கைபேசி எண் 6, 7, 8 அல்லது 9 இல் தொடங்கும். சரிபார்த்து மீண்டும் சொல்லுங்கள்.",
    
        "ml": "ഇന്ത്യൻ മൊബൈൽ നമ്പർ 6, 7, 8 അല്ലെങ്കിൽ 9 കൊണ്ടാണ് തുടങ്ങുക. പരിശോധിച്ച് വീണ്ടും പറയുക.",
        "te": "భారతీయ మొబైల్ సంఖ్య 6, 7, 8 లేదా 9తో మొదలవుతుంది. చూసి మళ్ళీ చెప్పండి.",
        "hi": "भारतीय मोबाइल नंबर 6, 7, 8 या 9 से आरंभ होता है। जाँचकर दोबारा बताएँ।",
    },
    "mobile.repeated": {
        "en": "That does not look like a real mobile number. Please say it again.",
        "ta": "அது சரியான கைபேசி எண்ணாகத் தெரியவில்லை. மீண்டும் சொல்லுங்கள்.",
    
        "ml": "അത് ശരിയായ മൊബൈൽ നമ്പറായി തോന്നുന്നില്ല. ദയവായി വീണ്ടും പറയുക.",
        "te": "అది నిజమైన మొబైల్ సంఖ్యలా అనిపించడం లేదు. దయచేసి మళ్ళీ చెప్పండి.",
        "hi": "यह वास्तविक मोबाइल नंबर नहीं लगता। कृपया दोबारा बताएँ।",
    },
    "pincode.empty": {
        "en": "Please say the 6-digit PIN code.",
        "ta": "6 இலக்க அஞ்சல் குறியீட்டைச் சொல்லுங்கள்.",
    
        "ml": "6 അക്ക പിൻ കോഡ് പറയുക.",
        "te": "6 అంకెల పిన్ కోడ్ చెప్పండి.",
        "hi": "कृपया 6 अंकों का पिन कोड बताएँ।",
    },
    "pincode.length": {
        "en": "The PIN code must contain 6 digits. I heard {got}. Please say it again.",
        "ta": "அஞ்சல் குறியீட்டில் 6 இலக்கங்கள் இருக்க வேண்டும். {got} கிடைத்தன. மீண்டும் சொல்லுங்கள்.",
    
        "ml": "പിൻ കോഡിൽ 6 അക്കങ്ങൾ വേണം. ഞാൻ കേട്ടത് {got}. ദയവായി വീണ്ടും പറയുക.",
        "te": "పిన్ కోడ్‌లో 6 అంకెలు ఉండాలి. నేను విన్నది {got}. దయచేసి మళ్ళీ చెప్పండి.",
        "hi": "पिन कोड में 6 अंक होने चाहिए। मैंने {got} सुना। कृपया दोबारा बताएँ।",
    },
    "pincode.leading": {
        "en": "An Indian PIN code does not begin with 0. Please check and say it again.",
        "ta": "இந்திய அஞ்சல் குறியீடு 0 இல் தொடங்காது. சரிபார்த்து மீண்டும் சொல்லுங்கள்.",
    
        "ml": "ഇന്ത്യൻ പിൻ കോഡ് 0 കൊണ്ട് തുടങ്ങാറില്ല. പരിശോധിച്ച് വീണ്ടും പറയുക.",
        "te": "భారతీయ పిన్ కోడ్ 0తో మొదలవదు. చూసి మళ్ళీ చెప్పండి.",
        "hi": "भारतीय पिन कोड 0 से आरंभ नहीं होता। जाँचकर दोबारा बताएँ।",
    },
    "age.empty": {
        "en": "Please tell me your age in years.",
        "ta": "உங்கள் வயதை ஆண்டுகளில் சொல்லுங்கள்.",
    
        "ml": "താങ്കളുടെ വയസ്സ് വർഷത്തിൽ പറയുക.",
        "te": "మీ వయస్సును సంవత్సరాలలో చెప్పండి.",
        "hi": "कृपया अपनी आयु वर्षों में बताएँ।",
    },
    "age.format": {
        "en": "Please tell me your age as a number of years, for example 45.",
        "ta": "உங்கள் வயதை எண்ணாகச் சொல்லுங்கள், எடுத்துக்காட்டாக 45.",
    
        "ml": "വയസ്സ് ഒരു സംഖ്യയായി പറയുക, ഉദാഹരണത്തിന് 45.",
        "te": "వయస్సును సంఖ్యగా చెప్పండి, ఉదాహరణకు 45.",
        "hi": "कृपया आयु संख्या में बताएँ, जैसे 45।",
    },
    "age.range": {
        "en": "An age of {got} does not look right. Please tell me your age in years.",
        "ta": "{got} வயது சரியாகத் தெரியவில்லை. உங்கள் வயதை ஆண்டுகளில் சொல்லுங்கள்.",
    
        "ml": "{got} വയസ്സ് ശരിയായി തോന്നുന്നില്ല. താങ്കളുടെ വയസ്സ് വർഷത്തിൽ പറയുക.",
        "te": "{got} సంవత్సరాల వయస్సు సరైనదిగా అనిపించడం లేదు. మీ వయస్సును సంవత్సరాలలో చెప్పండి.",
        "hi": "{got} वर्ष की आयु सही नहीं लगती। कृपया अपनी आयु वर्षों में बताएँ।",
    },
    "date.format": {
        "en": "I could not read that as a date. Please give the date as day, month and year, for example 15-03-2020.",
        "ta": "அதைத் தேதியாகப் படிக்க முடியவில்லை. நாள், மாதம், ஆண்டு வரிசையில் சொல்லுங்கள், எடுத்துக்காட்டாக 15-03-2020.",
    
        "ml": "അത് ഒരു തീയതിയായി വായിക്കാൻ കഴിഞ്ഞില്ല. ദിവസം, മാസം, വർഷം എന്ന ക്രമത്തിൽ പറയുക, ഉദാഹരണത്തിന് 15-03-2020.",
        "te": "దాన్ని తేదీగా చదవలేకపోయాం. రోజు, నెల, సంవత్సరం క్రమంలో చెప్పండి, ఉదాహరణకు 15-03-2020.",
        "hi": "इसे तिथि के रूप में नहीं पढ़ा जा सका। कृपया दिन, माह और वर्ष बताएँ, जैसे 15-03-2020।",
    },
    "date.range": {
        "en": "That date is outside the range this form accepts. Please check the year.",
        "ta": "அந்தத் தேதி இந்தப் படிவம் ஏற்கும் வரம்பிற்கு வெளியே உள்ளது. ஆண்டைச் சரிபார்க்கவும்.",
    
        "ml": "ആ തീയതി ഈ ഫോം സ്വീകരിക്കുന്ന പരിധിക്ക് പുറത്താണ്. വർഷം പരിശോധിക്കുക.",
        "te": "ఆ తేదీ ఈ ఫారం అంగీకరించే పరిధికి వెలుపల ఉంది. సంవత్సరాన్ని చూడండి.",
        "hi": "वह तिथि इस फ़ॉर्म की स्वीकार्य सीमा से बाहर है। कृपया वर्ष जाँचें।",
    },
    "date.future": {
        "en": "That date is in the future. Please give the date on which it actually happened.",
        "ta": "அந்தத் தேதி எதிர்காலத்தில் உள்ளது. உண்மையில் நடந்த தேதியைச் சொல்லுங்கள்.",
    
        "ml": "ആ തീയതി ഭാവിയിലാണ്. സംഭവം നടന്ന തീയതി പറയുക.",
        "te": "ఆ తేదీ భవిష్యత్తులో ఉంది. సంఘటన జరిగిన తేదీని చెప్పండి.",
        "hi": "वह तिथि भविष्य की है। कृपया वह तिथि बताएँ जब यह वास्तव में हुआ।",
    },
    "dob.range": {
        "en": "That date of birth gives an age above 120 years. Please check the year.",
        "ta": "அந்தப் பிறந்த தேதி 120 ஆண்டுகளுக்கு மேல் வயதைத் தருகிறது. ஆண்டைச் சரிபார்க்கவும்.",
    
        "ml": "ആ ജനനത്തീയതി പ്രകാരം വയസ്സ് 120-ൽ കൂടുതലാകുന്നു. വർഷം പരിശോധിക്കുക.",
        "te": "ఆ పుట్టిన తేదీ ప్రకారం వయస్సు 120 సంవత్సరాలకు మించుతోంది. సంవత్సరాన్ని చూడండి.",
        "hi": "उस जन्मतिथि से आयु 120 वर्ष से अधिक होती है। कृपया वर्ष जाँचें।",
    },
    "email.empty": {
        "en": "Please say your email address, or say skip if you do not have one.",
        "ta": "உங்கள் மின்னஞ்சல் முகவரியைச் சொல்லுங்கள், இல்லையெனில் 'தவிர்' எனச் சொல்லுங்கள்.",
    
        "ml": "താങ്കളുടെ ഇമെയിൽ വിലാസം പറയുക, ഇല്ലെങ്കിൽ 'ഒഴിവാക്കുക' എന്ന് പറയുക.",
        "te": "మీ ఇమెయిల్ చిరునామా చెప్పండి, లేకపోతే 'వదిలేయండి' అనండి.",
        "hi": "कृपया अपना ईमेल पता बताएँ, या न हो तो 'छोड़ें' कहें।",
    },
    "email.format": {
        "en": "That does not look like a complete email address. Please say it again, including the part after the @ sign.",
        "ta": "அது முழுமையான மின்னஞ்சல் முகவரியாகத் தெரியவில்லை. @ குறிக்குப் பின் உள்ள பகுதியுடன் மீண்டும் சொல்லுங்கள்.",
    
        "ml": "അത് പൂർണ്ണമായ ഇമെയിൽ വിലാസമായി തോന്നുന്നില്ല. @ ചിഹ്നത്തിന് ശേഷമുള്ള ഭാഗം ഉൾപ്പെടെ വീണ്ടും പറയുക.",
        "te": "అది పూర్తి ఇమెయిల్ చిరునామాలా అనిపించడం లేదు. @ గుర్తు తర్వాతి భాగంతో సహా మళ్ళీ చెప్పండి.",
        "hi": "यह पूरा ईमेल पता नहीं लगता। @ चिह्न के बाद का भाग सहित दोबारा बताएँ।",
    },
    "email.length": {
        "en": "That email address is too long. Please check it and say it again.",
        "ta": "அந்த மின்னஞ்சல் முகவரி மிக நீளமாக உள்ளது. சரிபார்த்து மீண்டும் சொல்லுங்கள்.",
    
        "ml": "ആ ഇമെയിൽ വിലാസം വളരെ നീളമുള്ളതാണ്. പരിശോധിച്ച് വീണ്ടും പറയുക.",
        "te": "ఆ ఇమెయిల్ చిరునామా చాలా పొడవుగా ఉంది. చూసి మళ్ళీ చెప్పండి.",
        "hi": "वह ईमेल पता बहुत लंबा है। जाँचकर दोबारा बताएँ।",
    },
    "name.empty": {
        "en": "I did not catch the name. Please say it again.",
        "ta": "பெயர் கிடைக்கவில்லை. மீண்டும் சொல்லுங்கள்.",
    
        "ml": "പേര് കേട്ടില്ല. ദയവായി വീണ്ടും പറയുക.",
        "te": "పేరు వినిపించలేదు. దయచేసి మళ్ళీ చెప్పండి.",
        "hi": "नाम सुनाई नहीं दिया। कृपया दोबारा बताएँ।",
    },
    "name.short": {
        "en": "That name seems too short. Please say the full name.",
        "ta": "அந்தப் பெயர் மிகச் சிறியதாக உள்ளது. முழுப் பெயரைச் சொல்லுங்கள்.",
    
        "ml": "ആ പേര് വളരെ ചെറുതായി തോന്നുന്നു. പൂർണ്ണമായ പേര് പറയുക.",
        "te": "ఆ పేరు చాలా చిన్నదిగా అనిపిస్తోంది. పూర్తి పేరు చెప్పండి.",
        "hi": "वह नाम बहुत छोटा लगता है। कृपया पूरा नाम बताएँ।",
    },
    "name.long": {
        "en": "That name is longer than this form allows. Please give the name as it appears on your identity document.",
        "ta": "அந்தப் பெயர் இந்தப் படிவம் அனுமதிப்பதை விட நீளமானது. அடையாள ஆவணத்தில் உள்ளபடி பெயரைச் சொல்லுங்கள்.",
    
        "ml": "ആ പേര് ഈ ഫോം അനുവദിക്കുന്നതിലും നീളമുള്ളതാണ്. തിരിച്ചറിയൽ രേഖയിലുള്ളതുപോലെ പേര് നൽകുക.",
        "te": "ఆ పేరు ఈ ఫారం అనుమతించే దాని కంటే పొడవుగా ఉంది. గుర్తింపు పత్రంలో ఉన్నట్లు పేరు ఇవ్వండి.",
        "hi": "वह नाम इस फ़ॉर्म की सीमा से लंबा है। कृपया पहचान पत्र में दर्ज नाम बताएँ।",
    },
    "name.digits": {
        "en": "A name cannot contain numbers. Please say the name again.",
        "ta": "பெயரில் எண்கள் இருக்க முடியாது. பெயரை மீண்டும் சொல்லுங்கள்.",
    
        "ml": "പേരിൽ അക്കങ്ങൾ ഉണ്ടാകാൻ പാടില്ല. പേര് വീണ്ടും പറയുക.",
        "te": "పేరులో అంకెలు ఉండకూడదు. పేరు మళ్ళీ చెప్పండి.",
        "hi": "नाम में अंक नहीं हो सकते। कृपया नाम दोबारा बताएँ।",
    },
    "name.characters": {
        "en": "I could not read that as a name. Please say it again, or spell it.",
        "ta": "அதைப் பெயராகப் படிக்க முடியவில்லை. மீண்டும் சொல்லுங்கள் அல்லது எழுத்துக்கூட்டிச் சொல்லுங்கள்.",
    
        "ml": "അത് ഒരു പേരായി വായിക്കാൻ കഴിഞ്ഞില്ല. വീണ്ടും പറയുക, അല്ലെങ്കിൽ അക്ഷരം അക്ഷരമായി പറയുക.",
        "te": "దాన్ని పేరుగా చదవలేకపోయాం. మళ్ళీ చెప్పండి, లేదా అక్షరం అక్షరంగా చెప్పండి.",
        "hi": "इसे नाम के रूप में नहीं पढ़ा जा सका। दोबारा बताएँ, या अक्षर-अक्षर बोलें।",
    },
    "address.empty": {
        "en": "Please give your full address.",
        "ta": "உங்கள் முழு முகவரியைச் சொல்லுங்கள்.",
    
        "ml": "താങ്കളുടെ പൂർണ്ണ വിലാസം നൽകുക.",
        "te": "మీ పూర్తి చిరునామా ఇవ్వండి.",
        "hi": "कृपया अपना पूरा पता बताएँ।",
    },
    "address.short": {
        "en": "Please give the full address, including the street and the town or village.",
        "ta": "தெரு மற்றும் ஊர் உட்பட முழு முகவரியைச் சொல்லுங்கள்.",
    
        "ml": "തെരുവ്, പട്ടണം അല്ലെങ്കിൽ ഗ്രാമം ഉൾപ്പെടെ പൂർണ്ണ വിലാസം നൽകുക.",
        "te": "వీధి, పట్టణం లేదా గ్రామంతో సహా పూర్తి చిరునామా ఇవ్వండి.",
        "hi": "कृपया गली और नगर या गाँव सहित पूरा पता बताएँ।",
    },
    "address.long": {
        "en": "That address is longer than the form allows. Please give the postal address only.",
        "ta": "அந்த முகவரி படிவம் அனுமதிப்பதை விட நீளமானது. அஞ்சல் முகவரியை மட்டும் சொல்லுங்கள்.",
    
        "ml": "ആ വിലാസം ഫോം അനുവദിക്കുന്നതിലും നീളമുള്ളതാണ്. തപാൽ വിലാസം മാത്രം നൽകുക.",
        "te": "ఆ చిరునామా ఫారం అనుమతించే దాని కంటే పొడవుగా ఉంది. తపాలా చిరునామా మాత్రమే ఇవ్వండి.",
        "hi": "वह पता फ़ॉर्म की सीमा से लंबा है। कृपया केवल डाक पता बताएँ।",
    },
    "boolean.unclear": {
        "en": "Please answer yes or no.",
        "ta": "ஆம் அல்லது இல்லை என்று பதிலளிக்கவும்.",
    
        "ml": "അതെ അല്ലെങ്കിൽ അല്ല എന്ന് പറയുക.",
        "te": "అవును లేదా కాదు అని చెప్పండి.",
        "hi": "कृपया हाँ या नहीं में उत्तर दें।",
    },
    "amount.empty": {"en": "Please tell me the amount in rupees.", "ta": "தொகையை ரூபாயில் சொல்லுங்கள்.",
        "ml": "തുക രൂപയിൽ പറയുക.",
        "te": "మొత్తాన్ని రూపాయలలో చెప్పండి.",
        "hi": "कृपया राशि रुपयों में बताएँ।",
    },
    "amount.format": {
        "en": "I could not read that as an amount. Please say the amount in rupees, for example 50,000.",
        "ta": "அதைத் தொகையாகப் படிக்க முடியவில்லை. ரூபாயில் சொல்லுங்கள், எடுத்துக்காட்டாக 50,000.",
    
        "ml": "അത് ഒരു തുകയായി വായിക്കാൻ കഴിഞ്ഞില്ല. തുക രൂപയിൽ പറയുക, ഉദാഹരണത്തിന് 50,000.",
        "te": "దాన్ని మొత్తంగా చదవలేకపోయాం. మొత్తాన్ని రూపాయలలో చెప్పండి, ఉదాహరణకు 50,000.",
        "hi": "इसे राशि के रूप में नहीं पढ़ा जा सका। कृपया राशि रुपयों में बताएँ, जैसे 50,000।",
    },
    "amount.range": {
        "en": "That amount is outside the range this form accepts. Please check the figure.",
        "ta": "அந்தத் தொகை இந்தப் படிவம் ஏற்கும் வரம்பிற்கு வெளியே உள்ளது. எண்ணிக்கையைச் சரிபார்க்கவும்.",
    
        "ml": "ആ തുക ഈ ഫോം സ്വീകരിക്കുന്ന പരിധിക്ക് പുറത്താണ്. സംഖ്യ പരിശോധിക്കുക.",
        "te": "ఆ మొత్తం ఈ ఫారం అంగీకరించే పరిధికి వెలుపల ఉంది. సంఖ్యను చూడండి.",
        "hi": "वह राशि इस फ़ॉर्म की स्वीकार्य सीमा से बाहर है। कृपया अंक जाँचें।",
    },
    "pan.empty": {"en": "Please say your PAN.", "ta": "உங்கள் PAN எண்ணைச் சொல்லுங்கள்.",
        "ml": "താങ്കളുടെ പാൻ നമ്പർ പറയുക.",
        "te": "మీ పాన్ సంఖ్య చెప్పండి.",
        "hi": "कृपया अपना पैन बताएँ।",
    },
    "pan.format": {
        "en": "A PAN has five letters, four digits and one letter, for example ABCDE1234F. Please say it again.",
        "ta": "PAN இல் ஐந்து எழுத்துகள், நான்கு இலக்கங்கள், ஒரு எழுத்து இருக்கும் — ABCDE1234F. மீண்டும் சொல்லுங்கள்.",
    
        "ml": "പാനിൽ അഞ്ച് അക്ഷരങ്ങൾ, നാല് അക്കങ്ങൾ, ഒരു അക്ഷരം എന്നിവയുണ്ട്, ഉദാഹരണത്തിന് ABCDE1234F. വീണ്ടും പറയുക.",
        "te": "పాన్‌లో ఐదు అక్షరాలు, నాలుగు అంకెలు, ఒక అక్షరం ఉంటాయి, ఉదాహరణకు ABCDE1234F. మళ్ళీ చెప్పండి.",
        "hi": "पैन में पाँच अक्षर, चार अंक और एक अक्षर होते हैं, जैसे ABCDE1234F। कृपया दोबारा बताएँ।",
    },
    "voter_id.empty": {"en": "Please say your voter ID number.", "ta": "உங்கள் வாக்காளர் அடையாள எண்ணைச் சொல்லுங்கள்.",
        "ml": "താങ്കളുടെ വോട്ടർ ഐഡി നമ്പർ പറയുക.",
        "te": "మీ ఓటరు గుర్తింపు సంఖ్య చెప్పండి.",
        "hi": "कृपया अपना मतदाता पहचान संख्या बताएँ।",
    },
    "voter_id.format": {
        "en": "A voter ID has three letters followed by seven digits, for example ABC1234567. Please say it again.",
        "ta": "வாக்காளர் அடையாள எண்ணில் மூன்று எழுத்துகள், ஏழு இலக்கங்கள் இருக்கும் — ABC1234567. மீண்டும் சொல்லுங்கள்.",
    
        "ml": "വോട്ടർ ഐഡിയിൽ മൂന്ന് അക്ഷരങ്ങൾക്ക് ശേഷം ഏഴ് അക്കങ്ങളുണ്ട്, ഉദാഹരണത്തിന് ABC1234567. വീണ്ടും പറയുക.",
        "te": "ఓటరు గుర్తింపులో మూడు అక్షరాల తర్వాత ఏడు అంకెలు ఉంటాయి, ఉదాహరణకు ABC1234567. మళ్ళీ చెప్పండి.",
        "hi": "मतदाता पहचान में तीन अक्षरों के बाद सात अंक होते हैं, जैसे ABC1234567। कृपया दोबारा बताएँ।",
    },
    "ifsc.empty": {"en": "Please say the bank IFSC code.", "ta": "வங்கியின் IFSC குறியீட்டைச் சொல்லுங்கள்.",
        "ml": "ബാങ്കിന്റെ IFSC കോഡ് പറയുക.",
        "te": "బ్యాంకు IFSC కోడ్ చెప్పండి.",
        "hi": "कृपया बैंक का IFSC कोड बताएँ।",
    },
    "ifsc.format": {
        "en": "An IFSC has four letters, a zero, then six characters, for example SBIN0001234. Please say it again.",
        "ta": "IFSC இல் நான்கு எழுத்துகள், ஒரு பூஜ்ஜியம், பின் ஆறு எழுத்துகள் இருக்கும் — SBIN0001234. மீண்டும் சொல்லுங்கள்.",
    
        "ml": "IFSC-യിൽ നാല് അക്ഷരങ്ങൾ, ഒരു പൂജ്യം, പിന്നെ ആറ് അക്ഷരങ്ങളുണ്ട്, ഉദാഹരണത്തിന് SBIN0001234. വീണ്ടും പറയുക.",
        "te": "IFSCలో నాలుగు అక్షరాలు, ఒక సున్నా, ఆ తర్వాత ఆరు అక్షరాలు ఉంటాయి, ఉదాహరణకు SBIN0001234. మళ్ళీ చెప్పండి.",
        "hi": "IFSC में चार अक्षर, एक शून्य, फिर छह अक्षर होते हैं, जैसे SBIN0001234। कृपया दोबारा बताएँ।",
    },
    "bank_account.empty": {"en": "Please say your bank account number.", "ta": "உங்கள் வங்கிக் கணக்கு எண்ணைச் சொல்லுங்கள்.",
        "ml": "താങ്കളുടെ ബാങ്ക് അക്കൗണ്ട് നമ്പർ പറയുക.",
        "te": "మీ బ్యాంకు ఖాతా సంఖ్య చెప్పండి.",
        "hi": "कृपया अपना बैंक खाता संख्या बताएँ।",
    },
    "bank_account.length": {
        "en": "A bank account number has between 9 and 18 digits. I heard {got}. Please say it again.",
        "ta": "வங்கிக் கணக்கு எண்ணில் 9 முதல் 18 இலக்கங்கள் இருக்கும். {got} கிடைத்தன. மீண்டும் சொல்லுங்கள்.",
    
        "ml": "ബാങ്ക് അക്കൗണ്ട് നമ്പറിൽ 9 മുതൽ 18 വരെ അക്കങ്ങളുണ്ടാകും. ഞാൻ കേട്ടത് {got}. വീണ്ടും പറയുക.",
        "te": "బ్యాంకు ఖాతా సంఖ్యలో 9 నుండి 18 అంకెలు ఉంటాయి. నేను విన్నది {got}. మళ్ళీ చెప్పండి.",
        "hi": "बैंक खाता संख्या में 9 से 18 अंक होते हैं। मैंने {got} सुना। कृपया दोबारा बताएँ।",
    },
    "ration_card.empty": {"en": "Please say your ration card number.", "ta": "உங்கள் ரேஷன் அட்டை எண்ணைச் சொல்லுங்கள்.",
        "ml": "താങ്കളുടെ റേഷൻ കാർഡ് നമ്പർ പറയുക.",
        "te": "మీ రేషన్ కార్డు సంఖ్య చెప్పండి.",
        "hi": "कृपया अपना राशन कार्ड संख्या बताएँ।",
    },
    "ration_card.format": {
        "en": "I could not read that as a ration card number. Please say it again.",
        "ta": "அதை ரேஷன் அட்டை எண்ணாகப் படிக்க முடியவில்லை. மீண்டும் சொல்லுங்கள்.",
    
        "ml": "അത് ഒരു റേഷൻ കാർഡ് നമ്പറായി വായിക്കാൻ കഴിഞ്ഞില്ല. വീണ്ടും പറയുക.",
        "te": "దాన్ని రేషన్ కార్డు సంఖ్యగా చదవలేకపోయాం. మళ్ళీ చెప్పండి.",
        "hi": "इसे राशन कार्ड संख्या के रूप में नहीं पढ़ा जा सका। कृपया दोबारा बताएँ।",
    },
    "district.empty": {"en": "Please tell me the district.", "ta": "மாவட்டத்தைச் சொல்லுங்கள்.",
        "ml": "ജില്ല ഏതാണെന്ന് പറയുക.",
        "te": "జిల్లా ఏదో చెప్పండి.",
        "hi": "कृपया ज़िला बताएँ।",
    },
    "district.format": {
        "en": "I could not read that as a district name. Please say the district again.",
        "ta": "அதை மாவட்டப் பெயராகப் படிக்க முடியவில்லை. மீண்டும் சொல்லுங்கள்.",
    
        "ml": "അത് ഒരു ജില്ലയുടെ പേരായി വായിക്കാൻ കഴിഞ്ഞില്ല. ജില്ല വീണ്ടും പറയുക.",
        "te": "దాన్ని జిల్లా పేరుగా చదవలేకపోయాం. జిల్లా మళ్ళీ చెప్పండి.",
        "hi": "इसे ज़िले के नाम के रूप में नहीं पढ़ा जा सका। कृपया ज़िला दोबारा बताएँ।",
    },
    "text.empty": {"en": "I did not catch that. Please say it again.", "ta": "புரியவில்லை. மீண்டும் சொல்லுங்கள்.",
        "ml": "അത് കേട്ടില്ല. ദയവായി വീണ്ടും പറയുക.",
        "te": "అది వినిపించలేదు. దయచేసి మళ్ళీ చెప్పండి.",
        "hi": "वह सुनाई नहीं दिया। कृपया दोबारा बताएँ।",
    },
    "text.short": {"en": "Please give a little more detail.", "ta": "சற்று மேலும் விவரமாகச் சொல்லுங்கள்.",
        "ml": "ഒന്നുകൂടി വിശദമായി പറയുക.",
        "te": "కొంచెం ఎక్కువ వివరంగా చెప్పండి.",
        "hi": "कृपया कुछ और विस्तार से बताएँ।",
    },
    "text.long": {
        # Says the limit, because the alternative is a citizen guessing how much
        # to cut. Nothing they said is discarded on their behalf.
        "en": "That is longer than this petition can carry ({got} characters; the limit is {limit}). Please shorten it and tell me again.",
        "ta": "இது இந்த மனுவில் இடம்பெற முடியாத அளவு நீளமாக உள்ளது ({got} எழுத்துகள்; வரம்பு {limit}). சுருக்கி மீண்டும் சொல்லுங்கள்.",
    
        "ml": "ഈ പരാതിയിൽ ഉൾക്കൊള്ളാവുന്നതിലും നീളമുണ്ട് ({got} അക്ഷരങ്ങൾ; പരിധി {limit}). ചുരുക്കി വീണ്ടും പറയുക.",
        "te": "ఈ విన్నపం మోయగలిగే దాని కంటే ఇది పొడవుగా ఉంది ({got} అక్షరాలు; పరిమితి {limit}). కుదించి మళ్ళీ చెప్పండి.",
        "hi": "यह इस आवेदन की क्षमता से लंबा है ({got} अक्षर; सीमा {limit})। कृपया छोटा करके दोबारा बताएँ।",
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
    
        "ml": "അത് കേട്ടില്ല. ദയവായി വീണ്ടും പറയുക.",
        "te": "అది వినిపించలేదు. దయచేసి మళ్ళీ చెప్పండి.",
        "hi": "वह सुनाई नहीं दिया। कृपया दोबारा बताएँ।",
    },
    "confirm_intro": {
        "en": "Here is what I have recorded. Please check it.",
        "ta": "நான் பதிவு செய்தவை இங்கே உள்ளன. சரிபார்க்கவும்.",
    
        "ml": "ഞാൻ രേഖപ്പെടുത്തിയത് ഇതാണ്. ദയവായി പരിശോധിക്കുക.",
        "te": "నేను నమోదు చేసినది ఇదే. దయచేసి చూడండి.",
        "hi": "मैंने जो दर्ज किया है वह यह है। कृपया जाँच लें।",
    },
    "confirm_ask": {
        "en": "Is all of this correct? Say yes to prepare the letter, or tell me what to change.",
        "ta": "இவை அனைத்தும் சரியா? கடிதத்தைத் தயாரிக்க 'ஆம்' எனச் சொல்லுங்கள், அல்லது என்ன மாற்ற வேண்டும் எனச் சொல்லுங்கள்.",
    
        "ml": "ഇതെല്ലാം ശരിയാണോ? കത്ത് തയ്യാറാക്കാൻ 'അതെ' എന്ന് പറയുക, അല്ലെങ്കിൽ എന്ത് മാറ്റണമെന്ന് പറയുക.",
        "te": "ఇదంతా సరైనదేనా? లేఖ తయారు చేయడానికి 'అవును' అనండి, లేదా ఏం మార్చాలో చెప్పండి.",
        "hi": "क्या यह सब सही है? पत्र तैयार करने के लिए 'हाँ' कहें, या बताएँ कि क्या बदलना है।",
    },
    "confirm_unclear": {
        "en": "Please say yes to prepare the letter, or tell me which detail to change.",
        "ta": "கடிதத்தைத் தயாரிக்க 'ஆம்' எனச் சொல்லுங்கள், அல்லது எந்த விவரத்தை மாற்ற வேண்டும் எனச் சொல்லுங்கள்.",
    
        "ml": "കത്ത് തയ്യാറാക്കാൻ 'അതെ' എന്ന് പറയുക, അല്ലെങ്കിൽ ഏത് വിവരം മാറ്റണമെന്ന് പറയുക.",
        "te": "లేఖ తయారు చేయడానికి 'అవును' అనండి, లేదా ఏ వివరం మార్చాలో చెప్పండి.",
        "hi": "पत्र तैयार करने के लिए 'हाँ' कहें, या बताएँ कि कौन-सा विवरण बदलना है।",
    },
    "generated": {
        "en": "Your letter is ready. You can review it and download it as a document.",
        "ta": "உங்கள் கடிதம் தயாராக உள்ளது. அதைப் பார்வையிட்டு ஆவணமாகப் பதிவிறக்கலாம்.",
    
        "ml": "താങ്കളുടെ കത്ത് തയ്യാറാണ്. അത് പരിശോധിച്ച് രേഖയായി ഡൗൺലോഡ് ചെയ്യാം.",
        "te": "మీ లేఖ సిద్ధంగా ఉంది. దాన్ని చూసి పత్రంగా డౌన్‌లోడ్ చేసుకోవచ్చు.",
        "hi": "आपका पत्र तैयार है। आप इसे देखकर दस्तावेज़ के रूप में डाउनलोड कर सकते हैं।",
    },
    "revising": {
        "en": "I am rewriting your petition with that change. Your details stay as they are.",
        "ta": "அந்த மாற்றத்துடன் உங்கள் மனுவை மீண்டும் எழுதுகிறேன். உங்கள் விவரங்கள் அப்படியே இருக்கும்.",
    
        "ml": "ആ മാറ്റത്തോടെ പരാതി മാറ്റിയെഴുതുന്നു. താങ്കളുടെ വിവരങ്ങളിൽ മാറ്റമില്ല.",
        "te": "ఆ మార్పుతో మీ విన్నపాన్ని తిరిగి రాస్తున్నాను. మీ వివరాలు అలాగే ఉంటాయి.",
        "hi": "उस परिवर्तन के साथ आपका आवेदन दोबारा लिखा जा रहा है। आपके विवरण वैसे ही रहेंगे।",
    },
    "restarted": {
        "en": "I have cleared everything. Tell me what letter you need.",
        "ta": "அனைத்தையும் அழித்துவிட்டேன். உங்களுக்கு என்ன கடிதம் தேவை எனச் சொல்லுங்கள்.",
    
        "ml": "എല്ലാം മായ്ച്ചു. ഏത് കത്താണ് വേണ്ടതെന്ന് പറയുക.",
        "te": "అంతా తొలగించాను. ఏ లేఖ కావాలో చెప్పండి.",
        "hi": "मैंने सब कुछ साफ़ कर दिया है। बताएँ आपको कौन-सा पत्र चाहिए।",
    },
    "edited_saved": {
        "en": "Your changes have been saved and the document has been remade.",
        "ta": "உங்கள் மாற்றங்கள் சேமிக்கப்பட்டு ஆவணம் மீண்டும் தயாரிக்கப்பட்டது.",
    
        "ml": "താങ്കളുടെ മാറ്റങ്ങൾ സൂക്ഷിച്ച് രേഖ വീണ്ടും തയ്യാറാക്കി.",
        "te": "మీ మార్పులు భద్రపరచి పత్రాన్ని తిరిగి తయారు చేశాం.",
        "hi": "आपके परिवर्तन सुरक्षित कर दस्तावेज़ दोबारा बना दिया गया है।",
    },
    "edited_missing": {
        # Said when a hand edit removed a detail the form recorded. It is the
        # citizen's document, so this is a warning and not a refusal.
        "en": ("These details are no longer in the petition after your edit: "
               "{fields}. The document has been saved as you wrote it."),
        "ta": ("உங்கள் திருத்தத்திற்குப் பிறகு இந்த விவரங்கள் மனுவில் இல்லை: "
               "{fields}. நீங்கள் எழுதியபடியே ஆவணம் சேமிக்கப்பட்டுள்ளது."),
    
        "ml": "താങ്കളുടെ തിരുത്തലിന് ശേഷം ഈ വിവരങ്ങൾ പരാതിയിൽ ഇല്ല: {fields}. രേഖ താങ്കൾ എഴുതിയതുപോലെ സൂക്ഷിച്ചിട്ടുണ്ട്.",
        "te": "మీ సవరణ తర్వాత ఈ వివరాలు విన్నపంలో లేవు: {fields}. పత్రం మీరు రాసినట్లే భద్రపరచబడింది.",
        "hi": "आपके संशोधन के बाद ये विवरण आवेदन में नहीं रहे: {fields}। दस्तावेज़ वैसे ही सुरक्षित है जैसा आपने लिखा।",
    },
    "attach_waiting": {
        # Said after "yes, I have something". The citizen has agreed to attach
        # but has not attached yet, so the session waits rather than advancing.
        "en": ("Please add the file using the attach button. Tell me when you "
               "are done, or say continue to prepare the petition as it is."),
        "ta": ("இணைப்பு பொத்தானைப் பயன்படுத்தி கோப்பைச் சேர்க்கவும். முடிந்ததும் "
               "சொல்லுங்கள், அல்லது இப்படியே மனுவைத் தயாரிக்க 'தொடரவும்' "
               "எனச் சொல்லுங்கள்."),
    
        "ml": "ചേർക്കുക ബട്ടൺ ഉപയോഗിച്ച് രേഖ ചേർക്കുക. പൂർത്തിയായാൽ പറയുക, അല്ലെങ്കിൽ ഇതുപോലെ തന്നെ പരാതി തയ്യാറാക്കാൻ 'തുടരുക' എന്ന് പറയുക.",
        "te": "జత చేయు బటన్‌తో పత్రాన్ని జత చేయండి. పూర్తయితే చెప్పండి, లేదా ఇలాగే విన్నపం తయారు చేయడానికి 'కొనసాగించండి' అనండి.",
        "hi": "कृपया जोड़ें बटन से दस्तावेज़ जोड़ें। पूरा होने पर बताएँ, या इसी रूप में आवेदन तैयार करने के लिए 'जारी रखें' कहें।",
    },
    "attachment_unreadable": {
        # An honest sentence for a photograph with no OCR engine behind it.
        "en": ("I could not read the text in that file, so I will attach it "
               "without reading it. If it has a reference number, please tell "
               "me the number."),
        "ta": ("அந்தக் கோப்பிலிருந்து உரையைப் படிக்க முடியவில்லை; அதை அப்படியே "
               "இணைக்கிறேன். அதில் ஒப்புகை எண் இருந்தால், அந்த எண்ணைச் "
               "சொல்லுங்கள்."),
    
        "ml": "ആ രേഖയിലെ വാചകം വായിക്കാൻ കഴിഞ്ഞില്ല, അതിനാൽ വായിക്കാതെ ചേർക്കുന്നു. അതിൽ ഒരു റഫറൻസ് നമ്പറുണ്ടെങ്കിൽ അത് പറയുക.",
        "te": "ఆ పత్రంలోని వచనాన్ని చదవలేకపోయాం, కాబట్టి చదవకుండానే జత చేస్తాను. అందులో రిఫరెన్స్ సంఖ్య ఉంటే చెప్పండి.",
        "hi": "उस दस्तावेज़ का पाठ पढ़ा नहीं जा सका, इसलिए उसे बिना पढ़े जोड़ रहा हूँ। यदि उस पर कोई संदर्भ संख्या है तो कृपया बताएँ।",
    },
    "cancelled": {
        "en": "This request has been cancelled. Nothing has been saved.",
        "ta": "இந்தக் கோரிக்கை ரத்து செய்யப்பட்டது. எதுவும் சேமிக்கப்படவில்லை.",
    
        "ml": "ഈ അപേക്ഷ റദ്ദാക്കി. ഒന്നും സൂക്ഷിച്ചിട്ടില്ല.",
        "te": "ఈ అభ్యర్థన రద్దు చేయబడింది. ఏమీ భద్రపరచలేదు.",
        "hi": "यह अनुरोध निरस्त कर दिया गया है। कुछ भी सुरक्षित नहीं हुआ।",
    },
    "which_field": {
        # Asked after "no" at the read-back. Naming the fields matters: a citizen
        # who is told only "what should I change?" has to invent the vocabulary.
        "en": "Which detail should I change? You can say: {fields}.",
        "ta": "எந்த விவரத்தை மாற்ற வேண்டும்? நீங்கள் சொல்லலாம்: {fields}.",
    
        "ml": "ഏത് വിവരമാണ് മാറ്റേണ്ടത്? ഇവയിൽ ഒന്ന് പറയാം: {fields}.",
        "te": "ఏ వివరం మార్చాలి? వీటిలో ఒకటి చెప్పవచ్చు: {fields}.",
        "hi": "कौन-सा विवरण बदलूँ? आप कह सकते हैं: {fields}।",
    },
    "translation_unavailable": {
        "en": "The petition is shown in the language it was drafted in: no translation service was available.",
        "ta": "மொழிபெயர்ப்புச் சேவை கிடைக்காததால், மனு அது தயாரிக்கப்பட்ட மொழியிலேயே காட்டப்படுகிறது.",
    
        "ml": "പരാതി എഴുതിയ ഭാഷയിൽ തന്നെ കാണിക്കുന്നു: പരിഭാഷാ സേവനം ലഭ്യമായിരുന്നില്ല.",
        "te": "విన్నపాన్ని రాసిన భాషలోనే చూపుతున్నాం: అనువాద సేవ అందుబాటులో లేదు.",
        "hi": "आवेदन उसी भाषा में दिखाया जा रहा है जिसमें वह लिखा गया: अनुवाद सेवा उपलब्ध नहीं थी।",
    },
    "pdf_unavailable": {
        "en": "Only the Word document could be produced. The PDF converter is not available on this server.",
        "ta": "Word ஆவணம் மட்டுமே தயாரிக்க முடிந்தது. இந்தச் சேவையகத்தில் PDF மாற்றி கிடைக்கவில்லை.",
    
        "ml": "വേഡ് രേഖ മാത്രമേ തയ്യാറാക്കാൻ കഴിഞ്ഞുള്ളൂ. ഈ സെർവറിൽ PDF പരിവർത്തനം ലഭ്യമല്ല.",
        "te": "వర్డ్ పత్రం మాత్రమే తయారు చేయగలిగాం. ఈ సర్వర్‌లో PDF మార్పిడి అందుబాటులో లేదు.",
        "hi": "केवल वर्ड दस्तावेज़ बन सका। इस सर्वर पर PDF रूपांतरण उपलब्ध नहीं है।",
    },
    "turn_failed": {
        "en": "That could not be processed. Your details are saved. Please try again.",
        "ta": "அதைச் செயலாக்க முடியவில்லை. உங்கள் விவரங்கள் சேமிக்கப்பட்டுள்ளன. மீண்டும் முயற்சிக்கவும்.",
    
        "ml": "അത് കൈകാര്യം ചെയ്യാൻ കഴിഞ്ഞില്ല. താങ്കളുടെ വിവരങ്ങൾ സൂക്ഷിച്ചിട്ടുണ്ട്. വീണ്ടും ശ്രമിക്കുക.",
        "te": "దాన్ని నిర్వహించలేకపోయాం. మీ వివరాలు భద్రంగా ఉన్నాయి. మళ్ళీ ప్రయత్నించండి.",
        "hi": "वह पूरा नहीं हो सका। आपके विवरण सुरक्षित हैं। कृपया दोबारा प्रयास करें।",
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
    
        "ml": "ശബ്ദ തിരിച്ചറിയൽ താൽക്കാലികമായി ലഭ്യമല്ല. ഒന്നുകൂടി പറയുക, അല്ലെങ്കിൽ എഴുതുക.",
        "te": "గొంతు గుర్తింపు తాత్కాలికంగా అందుబాటులో లేదు. మరోసారి చెప్పండి, లేదా రాయండి.",
        "hi": "वाक् पहचान अभी उपलब्ध नहीं है। कृपया दोबारा बोलें, या लिखें।",
    },
    "dictation_stopped": {
        "en": "Dictation has stopped. You can type instead.",
        "ta": "ஒலிவாங்கி நிறுத்தப்பட்டது. நீங்கள் தட்டச்சு செய்யலாம்.",
    
        "ml": "ശബ്ദം രേഖപ്പെടുത്തൽ നിന്നു. താങ്കൾക്ക് എഴുതാം.",
        "te": "గొంతు నమోదు ఆగింది. మీరు రాయవచ్చు.",
        "hi": "श्रुतलेखन रुक गया है। आप लिख सकते हैं।",
    },
    "render_failed": {
        "en": "The letter could not be produced just now. Your details are saved, so please try again in a moment.",
        "ta": "கடிதத்தைத் தயாரிக்க இப்போது முடியவில்லை. உங்கள் விவரங்கள் சேமிக்கப்பட்டுள்ளன; சிறிது நேரம் கழித்து முயற்சிக்கவும்.",
    
        "ml": "കത്ത് ഇപ്പോൾ തയ്യാറാക്കാൻ കഴിഞ്ഞില്ല. വിവരങ്ങൾ സൂക്ഷിച്ചിട്ടുണ്ട്; അൽപ്പം കഴിഞ്ഞ് വീണ്ടും ശ്രമിക്കുക.",
        "te": "లేఖను ఇప్పుడు తయారు చేయలేకపోయాం. మీ వివరాలు భద్రంగా ఉన్నాయి; కొద్దిసేపటి తర్వాత మళ్ళీ ప్రయత్నించండి.",
        "hi": "पत्र अभी तैयार नहीं हो सका। आपके विवरण सुरक्षित हैं, कृपया थोड़ी देर बाद प्रयास करें।",
    },
    "verify_failed": {
        "en": "The letter was produced but a check found a missing detail, so it has been held back. Please try again.",
        "ta": "கடிதம் தயாரிக்கப்பட்டது, ஆனால் ஒரு விவரம் விடுபட்டிருப்பதைச் சரிபார்ப்பு கண்டறிந்ததால் அது நிறுத்தி வைக்கப்பட்டுள்ளது. மீண்டும் முயற்சிக்கவும்.",
    
        "ml": "കത്ത് തയ്യാറായെങ്കിലും ഒരു വിവരം ഇല്ലെന്ന് പരിശോധനയിൽ കണ്ടതിനാൽ അത് തടഞ്ഞുവച്ചു. വീണ്ടും ശ്രമിക്കുക.",
        "te": "లేఖ తయారైనా ఒక వివరం లేదని తనిఖీలో తేలడంతో దాన్ని ఆపాం. మళ్ళీ ప్రయత్నించండి.",
        "hi": "पत्र बन गया था पर जाँच में एक विवरण कम मिला, इसलिए उसे रोक लिया गया। कृपया दोबारा प्रयास करें।",
    },
}

# The note printed at the foot of every petition, in both languages.
#
# ONE definition. `letter.py` appends it to the document and `views.py`
# exposes it to any client, so changing it here changes the preview, the
# DOCX, the PDF and both languages at once — including petitions written by
# a model, because the model never writes this line.
#
# The "Note:" / "குறிப்பு:" label is NOT part of the text. `letter.py`
# prefixes it from the same table that names every other block on the page,
# so a department translating the document does not have to find this
# sentence to change one word of it.
#
# TWO SENTENCES, and the department has removed the third twice.
#
# The eligibility clause went first. "It does not decide your eligibility"
# reads as though eligibility were something this service had considered and
# declined to rule on — which invites exactly the question it means to
# deflect.
#
# The legal-advice clause followed. Asked for directly: the note should say
# where the petition came from and what to do before signing it, and stop.
# The remaining two sentences do that. Nothing else in the document carries
# a legal-advice disclaimer, which is the department's decision to make and
# is recorded here so it is not restored by somebody assuming it was lost.
DISCLAIMER: dict[Language, str] = {
    "en": (
        "This petition was prepared based on the information provided by the "
        "petitioner. Please verify all details before signing or submitting it."
    ),
    "ta": (
        "மனுதாரர் வழங்கிய தகவல்களின் அடிப்படையில் இந்த மனு தயாரிக்கப்பட்டுள்ளது. "
        "கையொப்பமிட்டு சமர்ப்பிப்பதற்கு முன் அனைத்து விவரங்களையும் சரிபார்க்கவும்."
    ),

    "ml": "പരാതിക്കാരൻ നൽകിയ വിവരങ്ങളുടെ അടിസ്ഥാനത്തിലാണ് ഈ പരാതി തയ്യാറാക്കിയത്. ഒപ്പിടുന്നതിനോ സമർപ്പിക്കുന്നതിനോ മുമ്പ് എല്ലാ വിവരങ്ങളും പരിശോധിക്കുക.",
    "te": "విన్నపదారు ఇచ్చిన సమాచారం ఆధారంగా ఈ విన్నపం తయారు చేయబడింది. సంతకం చేసే లేదా సమర్పించే ముందు అన్ని వివరాలను ధ్రువీకరించుకోండి.",
    "hi": "यह आवेदन आवेदक द्वारा दी गई जानकारी के आधार पर तैयार किया गया है। हस्ताक्षर या प्रस्तुत करने से पहले कृपया सभी विवरण सत्यापित कर लें।",
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
