/* Page navigation and saved-petition browsing. The existing generator remains
   the only editor; every card opens its persisted server session. */
const NAV = {
  en: {
    home: "Home", create: "Create Petition", view: "View", edit: "Edit",
    search: "Search reference, petitioner or subject", all: "All", language: "Language",
    department: "Department", category: "Category", status: "Status", from: "From date", to: "To date",
    newest: "Newest", oldest: "Oldest", updated: "Recently updated", clear: "Clear filters",
    generated: "Generated", updatedStatus: "Updated", draft: "Draft", failed: "Requires attention",
    cancelled: "Cancelled", generating: "Preparing", current: "Current", version: "Version",
    history: "Version history",
    noResultsText: "Try a different reference, name, date, or filter.",
    empty: "Petitions will appear here.", emptyText: "Create a petition and generate its document to save it here.",
    error: "We couldn’t load the petitions. Check the connection and try again.", retry: "Try again",
    previous: "Previous", next: "Next", page: "Page", of: "of", count: "petitions",
    created: "Created", edited: "Updated", attention: "Verification needs attention", verified: "Verification passed",
    leaveTitle: "Leave these unsaved changes?", leaveText: "Your saved petition is kept. The changes you have not saved will be discarded.",
    keepEditing: "Keep editing", discard: "Discard changes", openError: "This petition could not be opened. Try again.",
    savedVersion: "Saved version", preview: "View version", historyError: "Version history could not be loaded.",
    close: "Close", manual: "Manual edit", ai: "Chat edit", initial: "Initial generation",
    versionNote: "This is a previous saved version. Your current petition has not changed.",
    dateError: "The end date must be on or after the start date.",
    // The home page, word for word as it appears. These were missing
    // entirely — the page had been redesigned and this table still carried
    // the copy from before it, so the landing page stayed in English no
    // matter what the language selector said.
    homeEyebrow: "A SIMPLE WAY TO BE HEARD",
    homeTitleLineOne: "Your concerns.",
    homeTitleLineTwo: "A well-prepared petition.",
    homeDescription: "Turn the details of your concern into a clear petition. Get guided help in your own language, review every detail, and keep your documents in one place.",
    homeLanguage: "Five languages",
    homeReview: "Review before downloading",
    homeCaption: "From your words to a clear document",
    homeCreateEyebrow: "START SOMETHING NEW",
    homeCreateTitle: "Create a petition",
    homeCreateDescription: "A guided conversation, a complete draft, and a document ready for your review.",
    kiosk: "Kiosk",
    ready: "Ready", allDepartments: "All departments",

    homeGuideEyebrow: "THREE SIMPLE STEPS",
    homeGuideTitle: "A little guidance, all the way.",
    homeStepOneTitle: "Share your concern",
    homeStepOneText: "Answer a few questions and add supporting documents if you have them.",
    homeStepTwoTitle: "Make it yours",
    homeStepTwoText: "Check your details, review the draft, and make any changes you need.",
    homeStepThreeTitle: "Download & keep",
    homeStepThreeText: "Save your document and return to All Petitions whenever you need it.", loading: "Loading saved petitions…", sort: "Sort by",
    pickLabel: "Select petition {ref}",
    skipToContent: "Skip to content",
    officerLogin: "Officer Login",
    builtBy: "Developed by",
  },
  ta: {
    home: "முகப்பு", create: "மனு உருவாக்கு", view: "காண்க", edit: "திருத்து",
    search: "தொடர்பு எண், பெயர் அல்லது பொருள் தேடவும்", all: "அனைத்தும்", language: "மொழி",
    department: "துறை", category: "வகை", status: "நிலை", from: "தொடக்கத் தேதி", to: "முடிவுத் தேதி",
    newest: "புதியவை முதலில்", oldest: "பழையவை முதலில்", updated: "சமீபத்திய திருத்தம்", clear: "வடிகட்டிகளை நீக்கு",
    generated: "தயாரிக்கப்பட்டது", updatedStatus: "புதுப்பிக்கப்பட்டது", draft: "வரைவு", failed: "கவனம் தேவை",
    cancelled: "ரத்து", generating: "தயாராகிறது", current: "தற்போதையது", version: "பதிப்பு",
    history: "பதிப்பு வரலாறு",
    noResultsText: "வேறு எண், பெயர், தேதி அல்லது வடிகட்டியை முயற்சிக்கவும்.",
    empty: "மனுக்கள் இங்கே தோன்றும்.", emptyText: "மனுவை உருவாக்கி ஆவணத்தைத் தயாரித்ததும் இங்கே சேமிக்கப்படும்.",
    error: "மனுக்களைப் பெற இயலவில்லை. இணைப்பைச் சரிபார்த்து மீண்டும் முயற்சிக்கவும்.", retry: "மீண்டும் முயற்சி",
    previous: "முந்தைய", next: "அடுத்த", page: "பக்கம்", of: "/", count: "மனுக்கள்",
    created: "உருவாக்கியது", edited: "திருத்தியது", attention: "சரிபார்ப்பில் கவனம் தேவை", verified: "சரிபார்க்கப்பட்டது",
    leaveTitle: "சேமிக்காத மாற்றங்களை விட்டு வெளியேறவா?", leaveText: "சேமித்த மனு இருக்கும். சேமிக்காத மாற்றங்கள் கைவிடப்படும்.",
    keepEditing: "திருத்துவதைத் தொடர்", discard: "மாற்றங்களைக் கைவிடு", openError: "இந்த மனுவைத் திறக்க இயலவில்லை. மீண்டும் முயற்சிக்கவும்.",
    savedVersion: "சேமித்த பதிப்பு", preview: "பதிப்பைக் காண்க", historyError: "பதிப்பு வரலாற்றைப் பெற இயலவில்லை.",
    close: "மூடு", manual: "நேரடித் திருத்தம்", ai: "உரையாடல் திருத்தம்", initial: "முதல் தயாரிப்பு",
    versionNote: "இது முந்தைய சேமித்த பதிப்பு. தற்போதைய மனு மாற்றப்படவில்லை.",
    dateError: "முடிவுத் தேதி தொடக்கத் தேதிக்குப் பிறகு இருக்க வேண்டும்.",
    // Written as a citizen service speaks, not as a translation of the
    // English reads. The English says "Turn the details of your concern
    // into a clear petition"; the Tamil says the same thing the way it
    // would be said at a counter.
    homeEyebrow: "உங்கள் குரலைப் பதிவு செய்ய ஓர் எளிய வழி",
    homeTitleLineOne: "உங்கள் குறைகள்.",
    homeTitleLineTwo: "நன்கு தயாரிக்கப்பட்ட மனு.",
    homeDescription: "உங்கள் குறையின் விவரங்களைத் தெளிவான மனுவாக மாற்றுங்கள். தமிழிலோ ஆங்கிலத்திலோ வழிகாட்டுதலுடன் உதவி பெறலாம்; ஒவ்வொரு விவரத்தையும் சரிபார்த்து, ஆவணங்களை ஒரே இடத்தில் வைத்துக்கொள்ளலாம்.",
    homeLanguage: "தமிழ் மற்றும் ஆங்கிலம்",
    homeReview: "பதிவிறக்கும் முன் சரிபார்க்கலாம்",
    homeCaption: "உங்கள் வார்த்தைகளிலிருந்து தெளிவான ஆவணம்",
    homeCreateEyebrow: "புதிதாகத் தொடங்குங்கள்",
    homeCreateTitle: "மனு உருவாக்கு",
    homeCreateDescription: "வழிகாட்டும் உரையாடல், முழுமையான வரைவு, உங்கள் சரிபார்ப்புக்குத் தயாரான ஆவணம்.",
    kiosk: "கியோஸ்க்",
    ready: "தயார்", allDepartments: "அனைத்து துறைகளும்",

    homeGuideEyebrow: "மூன்று எளிய படிகள்",
    homeGuideTitle: "ஒவ்வொரு படியிலும் வழிகாட்டுதல்.",
    homeStepOneTitle: "உங்கள் குறையைச் சொல்லுங்கள்",
    homeStepOneText: "சில கேள்விகளுக்குப் பதிலளியுங்கள்; ஆதார ஆவணங்கள் இருந்தால் இணைக்கலாம்.",
    homeStepTwoTitle: "உங்களுக்கேற்ப மாற்றுங்கள்",
    homeStepTwoText: "உங்கள் விவரங்களைச் சரிபாருங்கள், வரைவைப் படித்து, தேவையான மாற்றங்களைச் செய்யுங்கள்.",
    homeStepThreeTitle: "பதிவிறக்கிப் பாதுகாக்கவும்",
    homeStepThreeText: "ஆவணத்தைச் சேமித்து, தேவைப்படும்போது அனைத்து மனுக்கள் பகுதிக்குத் திரும்பலாம்.", loading: "மனுக்கள் ஏற்றப்படுகின்றன…", sort: "வரிசை",
    pickLabel: "{ref} மனுவைத் தேர்வு செய்",
    skipToContent: "உள்ளடக்கத்திற்குச் செல்",
    officerLogin: "அதிகாரி நுழைவு",
    builtBy: "உருவாக்கம்",
  },
  ml: {
    home: "ഹോം",
    create: "പരാതി തയ്യാറാക്കുക",
    view: "കാണുക",
    edit: "തിരുത്തുക",
    search: "റഫറൻസ്, പരാതിക്കാരൻ അല്ലെങ്കിൽ വിഷയം തിരയുക",
    all: "എല്ലാം",
    language: "ഭാഷ",
    department: "വകുപ്പ്",
    category: "വിഭാഗം",
    status: "സ്ഥിതി",
    from: "തുടങ്ങുന്ന തീയതി",
    to: "അവസാനിക്കുന്ന തീയതി",
    newest: "ഏറ്റവും പുതിയത്",
    oldest: "ഏറ്റവും പഴയത്",
    updated: "അടുത്തിടെ പുതുക്കിയത്",
    clear: "ഫിൽട്ടറുകൾ മായ്ക്കുക",
    generated: "തയ്യാറാക്കി",
    updatedStatus: "പുതുക്കി",
    draft: "കരട്",
    failed: "ശ്രദ്ധ ആവശ്യമാണ്",
    cancelled: "റദ്ദാക്കി",
    generating: "തയ്യാറാക്കുന്നു",
    current: "നിലവിലുള്ളത്",
    version: "പതിപ്പ്",
    history: "പതിപ്പുകളുടെ ചരിത്രം",
    noResultsText: "മറ്റൊരു റഫറൻസ്, പേര്, തീയതി അല്ലെങ്കിൽ ഫിൽട്ടർ ഉപയോഗിച്ച് നോക്കുക.",
    empty: "പരാതികൾ ഇവിടെ കാണാം.",
    emptyText: "ഒരു പരാതി തയ്യാറാക്കി രേഖ സൃഷ്ടിച്ചാൽ അത് ഇവിടെ സൂക്ഷിക്കപ്പെടും.",
    error: "പരാതികൾ എടുക്കാൻ കഴിഞ്ഞില്ല. ബന്ധം പരിശോധിച്ച് വീണ്ടും ശ്രമിക്കുക.",
    retry: "വീണ്ടും ശ്രമിക്കുക",
    previous: "മുമ്പത്തേത്",
    next: "അടുത്തത്",
    page: "പേജ്",
    of: "ൽ",
    count: "പരാതികൾ",
    created: "തയ്യാറാക്കിയത്",
    edited: "പുതുക്കിയത്",
    attention: "പരിശോധനയ്ക്ക് ശ്രദ്ധ ആവശ്യമാണ്",
    verified: "പരിശോധന പൂർത്തിയായി",
    leaveTitle: "സൂക്ഷിക്കാത്ത മാറ്റങ്ങൾ ഉപേക്ഷിക്കണോ?",
    leaveText: "സൂക്ഷിച്ച പരാതി നിലനിൽക്കും. സൂക്ഷിക്കാത്ത മാറ്റങ്ങൾ നഷ്ടപ്പെടും.",
    keepEditing: "തിരുത്തൽ തുടരുക",
    discard: "മാറ്റങ്ങൾ ഉപേക്ഷിക്കുക",
    openError: "ഈ പരാതി തുറക്കാൻ കഴിഞ്ഞില്ല. വീണ്ടും ശ്രമിക്കുക.",
    savedVersion: "സൂക്ഷിച്ച പതിപ്പ്",
    preview: "പതിപ്പ് കാണുക",
    historyError: "പതിപ്പുകളുടെ ചരിത്രം എടുക്കാൻ കഴിഞ്ഞില്ല.",
    close: "അടയ്ക്കുക",
    manual: "നേരിട്ടുള്ള തിരുത്തൽ",
    ai: "സംഭാഷണത്തിലൂടെ തിരുത്തൽ",
    initial: "ആദ്യ രേഖ",
    versionNote: "ഇത് മുമ്പ് സൂക്ഷിച്ച ഒരു പതിപ്പാണ്. താങ്കളുടെ നിലവിലുള്ള പരാതിയിൽ മാറ്റമില്ല.",
    dateError: "അവസാന തീയതി ആരംഭ തീയതിയിലോ അതിനു ശേഷമോ ആയിരിക്കണം.",
    homeEyebrow: "താങ്കളുടെ പരാതി അറിയിക്കാൻ ലളിതമായ വഴി",
    homeTitleLineOne: "താങ്കളുടെ പരാതി.",
    homeTitleLineTwo: "നന്നായി തയ്യാറാക്കിയ ഒരു നിവേദനം.",
    homeDescription: "താങ്കളുടെ പരാതിയുടെ വിവരങ്ങൾ വ്യക്തമായ ഒരു നിവേദനമാക്കി മാറ്റുക. സ്വന്തം ഭാഷയിൽ സഹായം സ്വീകരിക്കുക, ഓരോ വിവരവും പരിശോധിക്കുക, രേഖകൾ ഒരിടത്ത് സൂക്ഷിക്കുക.",
    homeLanguage: "അഞ്ച് ഭാഷകൾ",
    homeReview: "ഡൗൺലോഡ് ചെയ്യുന്നതിന് മുമ്പ് പരിശോധിക്കുക",
    homeCaption: "താങ്കളുടെ വാക്കുകളിൽ നിന്ന് വ്യക്തമായ ഒരു രേഖയിലേക്ക്",
    homeCreateEyebrow: "പുതിയതായി തുടങ്ങുക",
    homeCreateTitle: "ഒരു പരാതി തയ്യാറാക്കുക",
    homeCreateDescription: "വഴികാട്ടുന്ന ഒരു സംഭാഷണം, പൂർണ്ണമായ ഒരു കരട്, പരിശോധനയ്ക്ക് തയ്യാറായ രേഖ.",
    kiosk: "കിയോസ്ക്",
    ready: "തയ്യാർ",
    allDepartments: "എല്ലാ വകുപ്പുകളും",
    homeGuideEyebrow: "മൂന്ന് ലളിതമായ ഘട്ടങ്ങൾ",
    homeGuideTitle: "ഒപ്പം നിൽക്കുന്ന ചെറിയ വഴികാട്ടൽ.",
    homeStepOneTitle: "പരാതി പറയുക",
    homeStepOneText: "ഏതാനും ചോദ്യങ്ങൾക്ക് ഉത്തരം നൽകുക; രേഖകൾ ഉണ്ടെങ്കിൽ ചേർക്കുക.",
    homeStepTwoTitle: "താങ്കളുടേതാക്കുക",
    homeStepTwoText: "വിവരങ്ങൾ പരിശോധിക്കുക, കരട് വായിക്കുക, വേണ്ട മാറ്റങ്ങൾ വരുത്തുക.",
    homeStepThreeTitle: "ഡൗൺലോഡ് ചെയ്ത് സൂക്ഷിക്കുക",
    homeStepThreeText: "രേഖ സൂക്ഷിക്കുക; ആവശ്യമുള്ളപ്പോൾ എല്ലാ പരാതികളിലേക്കും മടങ്ങുക.",
    loading: "സൂക്ഷിച്ച പരാതികൾ എടുക്കുന്നു…",
    sort: "ക്രമീകരിക്കുക",
    pickLabel: "പരാതി {ref} തിരഞ്ഞെടുക്കുക",
    skipToContent: "ഉള്ളടക്കത്തിലേക്ക് പോകുക",
    officerLogin: "ഉദ്യോഗസ്ഥ ലൌഗിൻ",
    builtBy: "വികസിപ്പിച്ചത്",
  },
  te: {
    home: "హోమ్",
    create: "విన్నపం తయారు చేయండి",
    view: "చూడండి",
    edit: "సవరించండి",
    search: "రిఫరెన్స్, విన్నపదారు లేదా విషయం వెతకండి",
    all: "అన్నీ",
    language: "భాష",
    department: "శాఖ",
    category: "విభాగం",
    status: "స్థితి",
    from: "ప్రారంభ తేదీ",
    to: "ముగింపు తేదీ",
    newest: "సరికొత్తవి",
    oldest: "పాతవి",
    updated: "ఇటీవల నవీకరించినవి",
    clear: "ఫిల్టర్లు తొలగించండి",
    generated: "తయారైంది",
    updatedStatus: "నవీకరించబడింది",
    draft: "ముసాయిదా",
    failed: "శ్రద్ధ అవసరం",
    cancelled: "రద్దు చేయబడింది",
    generating: "తయారవుతోంది",
    current: "ప్రస్తుతం",
    version: "ప్రతి",
    history: "ప్రతుల చరిత్ర",
    noResultsText: "వేరే రిఫరెన్స్, పేరు, తేదీ లేదా ఫిల్టర్‌తో ప్రయత్నించండి.",
    empty: "విన్నపాలు ఇక్కడ కనిపిస్తాయి.",
    emptyText: "ఒక విన్నపం తయారు చేసి పత్రం సృష్టించిన తర్వాత అది ఇక్కడ భద్రపరచబడుతుంది.",
    error: "విన్నపాలను తీసుకురాలేకపోయాం. కనెక్షన్ చూసి మళ్ళీ ప్రయత్నించండి.",
    retry: "మళ్ళీ ప్రయత్నించండి",
    previous: "మునుపటి",
    next: "తదుపరి",
    page: "పేజీ",
    of: "లో",
    count: "విన్నపాలు",
    created: "తయారైన తేదీ",
    edited: "నవీకరించిన తేదీ",
    attention: "ధ్రువీకరణకు శ్రద్ధ అవసరం",
    verified: "ధ్రువీకరణ పూర్తయింది",
    leaveTitle: "భద్రపరచని మార్పులను వదిలేయాలా?",
    leaveText: "భద్రపరచిన విన్నపం అలాగే ఉంటుంది. భద్రపరచని మార్పులు పోతాయి.",
    keepEditing: "సవరణ కొనసాగించండి",
    discard: "మార్పులను వదిలేయండి",
    openError: "ఈ విన్నపాన్ని తెరవలేకపోయాం. మళ్ళీ ప్రయత్నించండి.",
    savedVersion: "భద్రపరచిన ప్రతి",
    preview: "ప్రతిని చూడండి",
    historyError: "ప్రతుల చరిత్రను తీసుకురాలేకపోయాం.",
    close: "మూసివేయండి",
    manual: "నేరుగా చేసిన సవరణ",
    ai: "సంభాషణ ద్వారా సవరణ",
    initial: "మొదటి పత్రం",
    versionNote: "ఇది గతంలో భద్రపరచిన ప్రతి. మీ ప్రస్తుత విన్నపంలో మార్పు లేదు.",
    dateError: "ముగింపు తేదీ ప్రారంభ తేదీ నాడు లేదా ఆ తర్వాత ఉండాలి.",
    homeEyebrow: "మీ మాట వినిపించడానికి ఒక సులభమైన మార్గం",
    homeTitleLineOne: "మీ సమస్య.",
    homeTitleLineTwo: "చక్కగా తయారైన ఒక విన్నపం.",
    homeDescription: "మీ సమస్య వివరాలను స్పష్టమైన విన్నపంగా మార్చండి. మీ స్వంత భాషలో సహాయం పొందండి, ప్రతి వివరాన్ని పరిశీలించండి, పత్రాలను ఒకే చోట ఉంచండి.",
    homeLanguage: "ఐదు భాషలు",
    homeReview: "డౌన్‌లోడ్ చేసే ముందు పరిశీలించండి",
    homeCaption: "మీ మాటల నుండి ఒక స్పష్టమైన పత్రం వరకు",
    homeCreateEyebrow: "కొత్తగా మొదలుపెట్టండి",
    homeCreateTitle: "ఒక విన్నపం తయారు చేయండి",
    homeCreateDescription: "దారి చూపే సంభాషణ, పూర్తి ముసాయిదా, పరిశీలనకు సిద్ధమైన పత్రం.",
    kiosk: "కియోస్క్",
    ready: "సిద్ధం",
    allDepartments: "అన్ని శాఖలు",
    homeGuideEyebrow: "మూడు సులభమైన అడుగులు",
    homeGuideTitle: "చివరి వరకు చిన్న దారి చూపు.",
    homeStepOneTitle: "మీ సమస్య చెప్పండి",
    homeStepOneText: "కొన్ని ప్రశ్నలకు సమాధానం ఇవ్వండి; పత్రాలు ఉంటే జత చేయండి.",
    homeStepTwoTitle: "మీదిగా చేసుకోండి",
    homeStepTwoText: "మీ వివరాలు చూడండి, ముసాయిదా చదవండి, కావలసిన మార్పులు చేయండి.",
    homeStepThreeTitle: "డౌన్‌లోడ్ చేసి భద్రపరచండి",
    homeStepThreeText: "పత్రాన్ని భద్రపరచండి; అవసరమైనప్పుడు అన్ని విన్నపాలకు తిరిగి రండి.",
    loading: "భద్రపరచిన విన్నపాలను తీసుకువస్తోంది…",
    sort: "క్రమం",
    pickLabel: "విన్నపం {ref} ఎంచుకోండి",
    skipToContent: "విషయానికి వెళ్ళండి",
    officerLogin: "అధికారి లాగిన్",
    builtBy: "రూపొందించినవారు",
  },
  hi: {
    home: "मुख्य पृष्ठ",
    create: "आवेदन तैयार करें",
    view: "देखें",
    edit: "संशोधित करें",
    search: "संदर्भ, आवेदक या विषय खोजें",
    all: "सभी",
    language: "भाषा",
    department: "विभाग",
    category: "श्रेणी",
    status: "स्थिति",
    from: "आरंभ तिथि",
    to: "अंतिम तिथि",
    newest: "नवीनतम",
    oldest: "पुराने",
    updated: "हाल में अद्यतन",
    clear: "फ़िल्टर हटाएँ",
    generated: "तैयार",
    updatedStatus: "अद्यतन",
    draft: "प्रारूप",
    failed: "ध्यान देना आवश्यक",
    cancelled: "निरस्त",
    generating: "तैयार हो रहा है",
    current: "वर्तमान",
    version: "संस्करण",
    history: "संस्करण इतिहास",
    noResultsText: "कोई दूसरा संदर्भ, नाम, तिथि या फ़िल्टर आज़माएँ।",
    empty: "आवेदन यहाँ दिखाई देंगे।",
    emptyText: "आवेदन तैयार कर दस्तावेज़ बनाने पर वह यहाँ सुरक्षित रहेगा।",
    error: "आवेदन नहीं आ सके। संपर्क जाँचकर पुनः प्रयास करें।",
    retry: "पुनः प्रयास करें",
    previous: "पिछला",
    next: "अगला",
    page: "पृष्ठ",
    of: "में से",
    count: "आवेदन",
    created: "बनाया गया",
    edited: "अद्यतन",
    attention: "सत्यापन पर ध्यान देना आवश्यक",
    verified: "सत्यापन पूर्ण",
    leaveTitle: "असुरक्षित परिवर्तन छोड़ दें?",
    leaveText: "आपका सुरक्षित आवेदन बना रहेगा। जो परिवर्तन सुरक्षित नहीं हुए, वे चले जाएँगे।",
    keepEditing: "संशोधन जारी रखें",
    discard: "परिवर्तन छोड़ें",
    openError: "यह आवेदन खुल नहीं सका। पुनः प्रयास करें।",
    savedVersion: "सुरक्षित संस्करण",
    preview: "संस्करण देखें",
    historyError: "संस्करण इतिहास नहीं आ सका।",
    close: "बंद करें",
    manual: "स्वयं किया संशोधन",
    ai: "संवाद द्वारा संशोधन",
    initial: "पहला दस्तावेज़",
    versionNote: "यह पहले सुरक्षित किया गया संस्करण है। आपके वर्तमान आवेदन में कोई परिवर्तन नहीं हुआ है।",
    dateError: "अंतिम तिथि आरंभ तिथि को या उसके बाद होनी चाहिए।",
    homeEyebrow: "अपनी बात रखने का एक सरल तरीका",
    homeTitleLineOne: "आपकी समस्या।",
    homeTitleLineTwo: "भली-भाँति तैयार एक आवेदन।",
    homeDescription: "अपनी समस्या के विवरण को एक स्पष्ट आवेदन में बदलें। अपनी भाषा में सहायता लें, हर विवरण जाँचें, और अपने दस्तावेज़ एक ही जगह रखें।",
    homeLanguage: "पाँच भाषाएँ",
    homeReview: "डाउनलोड से पहले जाँचें",
    homeCaption: "आपके शब्दों से एक स्पष्ट दस्तावेज़ तक",
    homeCreateEyebrow: "कुछ नया आरंभ करें",
    homeCreateTitle: "आवेदन तैयार करें",
    homeCreateDescription: "मार्गदर्शन करता संवाद, पूरा प्रारूप, और जाँच के लिए तैयार दस्तावेज़।",
    kiosk: "कियोस्क",
    ready: "तैयार",
    allDepartments: "सभी विभाग",
    homeGuideEyebrow: "तीन सरल चरण",
    homeGuideTitle: "थोड़ा मार्गदर्शन, आरंभ से अंत तक।",
    homeStepOneTitle: "अपनी समस्या बताएँ",
    homeStepOneText: "कुछ प्रश्नों के उत्तर दें; दस्तावेज़ हों तो जोड़ें।",
    homeStepTwoTitle: "इसे अपना बनाएँ",
    homeStepTwoText: "अपने विवरण जाँचें, प्रारूप पढ़ें, और आवश्यक परिवर्तन करें।",
    homeStepThreeTitle: "डाउनलोड कर सुरक्षित रखें",
    homeStepThreeText: "दस्तावेज़ सुरक्षित रखें; आवश्यकता होने पर सभी आवेदनों पर लौटें।",
    loading: "सुरक्षित आवेदन आ रहे हैं…",
    sort: "क्रम",
    pickLabel: "आवेदन {ref} चुनें",
    skipToContent: "सीधे सामग्री पर जाएँ",
    officerLogin: "अधिकारी लॉगिन",
    builtBy: "विकसित",
  },
};
const N = () => NAV[lang] || NAV.en;
let currentRoute = "home";
let versionRequest = 0;
let routeHash = "#home";
/* Which petitions are ticked, by session id.
 *
 * Kept across pages on purpose: with twelve rows to a page and two hundred
 * petitions saved, a selection that emptied every time somebody turned the
 * page would make "select all" useless for the one job it exists for.
 *
 * It is emptied when the SEARCH or FILTERS change, because that is a different
 * question being asked and the rows that answered the old one are no longer on
 * screen to be unticked. */

function navigationLabels() {
  const n = N();
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.dataset.i18n;
    if (n[key]) el.textContent = n[key];
  });
  // The saved-petitions screen and its filters, sorting, selection and
  // paging labels were removed with it. What remains is the navigation and
  // the version history, which belongs to the generator.
  for (const [id, text] of Object.entries({ navHome: n.home, navCreate: n.create,
    versionTitle: n.history })) {
    if ($(id)) $(id).textContent = text;
  }
  if (view) drawVersions(view);
}

function syncNavigation() {
  document.querySelectorAll("[data-route]").forEach(el => {
    const active = el.dataset.route === (currentRoute === "generator" ? "create" : currentRoute);
    if (active) el.setAttribute("aria-current", "page"); else el.removeAttribute("aria-current");
    el.setAttribute("aria-disabled", String(requestPending || busy));
  });
  $("new").hidden = currentRoute !== "generator";
  // The spoken-replies toggle lives on the assistant panel now, which only
  // exists on the generator page, so its container governs when it shows.
  // Inside a kiosk session the whole navigation is hidden by CSS; this keeps
  // the link out of the tab order as well, so a keyboard cannot reach a
  // destination the terminal is not meant to leave for.
  // The Kiosk link was removed from the navigation. The MODE remains: a
  // terminal is put into it by its deployment, and #kiosk still works, so a
  // machine standing in an office with a printer attached is unaffected.
  // What has gone is the invitation to enter it from an ordinary browser.
}

function editorText() { return $("letter").innerText.replace(/\u00a0/g, " ").trimEnd(); }

function guardUnsaved(proceed) {
  const changedLetter = editingLetter && editorText() !== editBackup.trimEnd();
  const changedInput = Boolean($("text").value.trim());
  const changedField = Boolean(editing && document.querySelector("[data-editform]"));
  if (!changedLetter && !changedInput && !changedField) return true;
  confirmThen(N().leaveTitle, N().leaveText, N().keepEditing, N().discard, () => {
    if (editingLetter) stopEditing(true);
    $("text").value = ""; autoGrow(); editing = null;
    if (view) drawDetails(view);
    proceed();
  });
  return false;
}

function setPage(route, hash, replace = false) {
  currentRoute = route;
  $("homePage").hidden = route !== "home";

  $("generatorPage").hidden = route !== "generator";
  routeHash = hash;
  if (location.hash !== hash) window.history[replace ? "replaceState" : "pushState"](null, "", hash);
  document.title = `${route === "home" ? N().home : (view?.document?.reference || N().create)} · ${T().title}`;
  syncNavigation();
  window.scrollTo({ top: 0, behavior: "instant" });
}

function showGenerator(id, replace = false) { setPage("generator", `#petition/${id}`, replace); }

async function navigate(route, options = {}) {
  if (requestPending || busy) return;
  if (!options.checked && !guardUnsaved(() => navigate(route, { ...options, checked: true }))) return;
  if (editingLetter) stopEditing(true);
  stopVoice();
  // Kiosk is the create flow with the terminal behaviour switched on. One
  // page, one graph, one set of questions — the flag is the only difference.
  if (route === "kiosk" || route === "create") {
    setKioskMode(route === "kiosk");
    await start();
    if (route === "kiosk") setPage("generator", "#kiosk", options.replace);
    return;
  }
  if (route === "generator") { await openPetition(options.id, options.edit, options.replace); return; }
  setKioskMode(false);
  // "All petitions" was removed from the citizen UI. An old link or a
  // bookmark to #petitions lands on the home page rather than on a screen
  // that no longer exists.
  setPage("home", "#home", options.replace);
}

async function openPetition(id, edit = false, replace = false) {
  if (requestPending || !/^[\da-f-]{36}$/i.test(id || "")) return;
  requestPending = true; syncControls();
  const result = await api(`/api/sessions/${id}`, { timeout: 30000, quiet: true });
  requestPending = false;
  if (!result) {
    setPage("generator", `#petition/${id}`, replace);
    connectionNotice([404, 410].includes(lastApiStatus) ? X().expired : X().offline);
    syncControls(); return;
  }
  resetInterface(); connectionLost = false; connectionNotice();
  render(result); showGenerator(result.session_id, replace);
  if (edit && result.document) startEditing();
  else $("text").focus({ preventScroll: true });
}

const FILTER_PARAMS = {
  petitionSearch: "q", filterDateFrom: "date_from", filterDateTo: "date_to",
  filterDepartment: "department", filterCategory: "category", filterStatus: "status",
  filterLanguage: "language", petitionSort: "sort",
};

function dateLabel(value, time = false) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(lang === "ta" ? "ta-IN" : "en-IN", {
    day: "numeric", month: "short", year: "numeric", ...(time ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(date);
}

/** Every tick box currently drawn, page by page. */

/** Collect the ids of everything the current filter matches, not just this
    page. Asked for explicitly, and sent to the server explicitly — the delete
    endpoint takes ids and never a filter, so what is deleted is exactly what
    was listed here and nothing the filter might match a moment later. */

function drawVersions(v) {
  if (!$("versionPanel")) return;
  const version = v.version || v.document?.version || 0;
  $("versionPanel").hidden = !version;
  $("versionCurrent").textContent = `${N().version} ${version}`;
  $("versionStatus").textContent = `${v.verification?.ok ? N().verified : N().attention} · ${dateLabel(v.document?.generated_at || v.updated_at, true)}`;
  const versions = v.versions || v.version_history || [];
  $("versionList").innerHTML = versions.slice().reverse().map(entry => `<div class="version-item${entry.version === version ? " current" : ""}">
    <div class="version-info"><b>${esc(N().version)} ${entry.version} ${entry.version === version ? `· ${esc(N().current)}` : ""}</b>
      <span>${esc(dateLabel(entry.updated_at, true))} · ${esc(entry.source === "Manual" ? N().manual : entry.version === 1 ? N().initial : N().ai)}</span>
      <p class="version-note">${esc(entry.summary || "")}</p></div>
    <div class="version-actions"><button class="btn" type="button" data-version="${entry.version}">${esc(N().preview)}</button></div></div>`).join("");
}

async function previewVersion(version) {
  const request = ++versionRequest, session = sid;
  const data = await api(`/api/sessions/${sid}/versions`, { quiet: true, timeout: 15000 });
  if (request !== versionRequest || sid !== session) return;
  const snapshot = data?.versions?.find(entry => entry.version === version);
  if (!snapshot) { bubble("system", N().historyError, true); return; }
  const dialog = document.createElement("dialog");
  dialog.className = "version-preview";
  dialog.innerHTML = `<div class="version-preview-head"><div><h2>${esc(N().version)} ${version}</h2><p>${esc(N().versionNote)}</p></div>
    <button class="btn" type="button">${esc(N().close)}</button></div><article class="paper"></article>`;
  dialog.querySelector("article").textContent = snapshot.letter_text;
  dialog.querySelector("button").onclick = () => dialog.close();
  dialog.addEventListener("close", () => dialog.remove());
  document.body.appendChild(dialog); dialog.showModal();
}

document.addEventListener("keydown", e => {
  if (e.key !== "Enter" && e.key !== " ") return;
  const row = e.target.closest?.(".petition-item-main[data-open-petition]");
  if (!row) return;
  e.preventDefault();
  navigate("generator", { id: row.dataset.openPetition });
});

document.addEventListener("click", e => {
  const route = e.target.closest("[data-route]");
  if (route) { e.preventDefault(); navigate(route.dataset.route); return; }
  const version = e.target.closest("[data-version]");
  if (version) previewVersion(Number(version.dataset.version));
});

// The saved-petitions screen was removed from the citizen UI, and the
// controls it wired up went with it. These registrations ran at load, so
// leaving them behind meant `null.onclick` throwing before the rest of
// this file had run — the same failure shape as reaching for a painter's
// scoped `t` from module scope. The list, filter, paging and bulk-delete
// functions above are now unreferenced; they are left in place so the
// screen can be restored by putting its markup back.

window.addEventListener("beforeunload", e => {
  if (editingLetter && editorText() !== editBackup.trimEnd()) { e.preventDefault(); e.returnValue = ""; }
});

async function routeFromHash(initial = false) {
  const hash = location.hash;
  if (!initial && (busy || requestPending)) { window.history.replaceState(null, "", routeHash); return; }
  const match = /^#petition\/([\da-f-]{36})$/i.exec(hash);
  const route = match ? "generator"
    : hash === "#kiosk" ? "kiosk"
    : hash === "#petitions" ? "petitions"
    : hash === "#create" ? "create" : "home";
  if (!initial && !guardUnsaved(() => navigate(route, { id: match?.[1], checked: true, replace: true }))) {
    window.history.replaceState(null, "", routeHash); return;
  }
  await navigate(route, { id: match?.[1], checked: true, replace: true });
}
window.addEventListener("hashchange", () => routeFromHash());

(async () => {
  const saved = savedSession();
  // Checked against the tables rather than against a list of codes. This
  // used to read `=== "ta" ? "ta" : "en"`, which quietly threw away every
  // language added after it — and is the first line somebody edits when
  // adding one, which is how it would have been widened past what the
  // string tables could actually serve.
  if (saved) { lang = NAV[saved.language] ? saved.language : "en"; lastLang = lang; }
  labels(); syncControls();
  void loadHealth();
  await routeFromHash(true);
})();
