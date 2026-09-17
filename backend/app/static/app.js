/* ==========================================================================
   Citizen Petition Assistant — interface layer.

   Everything on this page is a rendering of the session the SERVER holds. The
   stepper, the lifecycle chip, the progress bar and the review state are all
   derived from `status`, `awaiting`, `collected` and `outstanding` as they come
   back from the API. Nothing here advances on a timer, and nothing here keeps
   a second copy of the record: if the two ever disagreed, the citizen would be
   shown one thing and the petition would be built from another.
   ========================================================================== */

const UI = {
  en: {
    title: "Citizen Petition Assistant",
    subtitle: "AI Assisted Petition Preparation",
    assistant: "Petition Assistant",
    details: "Petition Details",
    citizenSection: "Citizen Details",
    grievanceSection: "Grievance Details",
    corrections: "Corrections History",
    analysis: "AI Petition Analysis",
    attachRequiredHead: "An official document says these are required:",
    attachRemove: "Remove",
    attachTitle: "Attach a file",
    attachUploading: "Uploading…",
    attachDone: "Attached",
    attachConfirmHead: "Is this right?",
    attachConfirmYes: "Yes, that is correct",
    attachAcknowledge: "Understood, keep it attached",
    attachConfirmNo: "No, ignore this",
    attachUnreadable: "The text in this file could not be read.",
    attachLowConfidence: "This was read with low confidence \u2014 please check it.",
    attachFailed: "That file could not be attached.",
    attachField: {
      reference_number: "Acknowledgement number", petition_number: "Petition number",
      submitted_on: "Submitted on", department: "Department",
      authority: "Authority", subject: "Subject", status: "Status",
    },
    analysisSources: "Sources",
    analysisPage: "page",
    analysisOfficial: "Official",
    analysisDepartmental: "Departmental",
    analysisExternal: "External",
    analysisSuperseded: "Superseded",
    system: "System Status",
    langLabel: "Language",
    inputLabel: "Your response",
    refLabel: "Reference",
    newPetition: "New Petition",
    petitions: "Petitions",
    petitionsEmpty: "Petitions you prepare on this device will be listed here.",
    petitionsNote: "Saved on this device only. Clear the list before leaving a shared computer.",
    petitionsClear: "Clear this list",
    petitionsClearConfirm: "Remove all petitions from this list? The documents themselves are not deleted.",
    petitionsOpen: "Open",
    petitionsRemove: "Remove from list",
    petitionStatus: {
      collecting: "In progress", attachments: "In progress",
      confirming: "Awaiting confirmation", generating: "Preparing",
      ready: "Ready", cancelled: "Cancelled", failed: "Needs attention",
    },

    placeholder: "Type your response…",
    placeholderLong: "Describe your grievance in your own words…",
    send: "Send",
    confirm: "Confirm & Generate Petition",
    restart: "Start Over",
    cancel: "Cancel",
    edit: "Edit",
    save: "Save",
    dismiss: "Cancel",

    lifecycle: {
      collecting: "Collecting Information",
      attachments: "Adding Attachments",
      confirming: "Reviewing Details",
      generating: "Generating Petition",
      ready: "Petition Ready",
      cancelled: "Petition Cancelled",
      failed: "Action Required",
    },
    assistantStatus: {
      collecting: "Collecting citizen information",
      attachments: "Waiting for any supporting documents",
      confirming: "Waiting for your confirmation",
      generating: "Preparing your petition",
      ready: "Editing your saved petition · ask for a change",
      cancelled: "This petition was cancelled",
      failed: "Something needs your attention",
    },
    steps: ["Citizen Details", "Grievance", "Attachments", "Review", "Generate", "Petition Ready"],

    progress: (a, b) => `${a} of ${b} required details collected`,
    pending: "Pending",
    required: "Required",

    reviewTitle: "Review your petition details",
    reviewText: "Please check everything below before the petition is generated.",

    genTitle: "Preparing your petition",
    genHint: "This usually takes a few seconds.",
    genSteps: ["Citizen information verified", "Grievance recorded",
               "Drafting the petition", "Applying the official format",
               "Final verification"],
    draftHeading: "Draft Petition",
    fromTag: "From", toTag: "To",
    improve1: "Improved clarity", improve2: "Better wording",
    improve3: "Official format",
    // A change made after the petition exists is a DIFFERENT piece of work
    // from writing it, and the rail says so rather than claiming the details
    // are being verified again.
    translate: "Translate", translating: "Translating your petition",
    translateSteps: ["Reading the petition", "Translating the wording",
                     "Applying the official format", "Final verification"],
    translateFailed: "The petition could not be translated. It has not been changed.",
    reviseTitle: "Updating your petition",
    reviseSteps: ["Reading your request", "Updating the petition",
                  "Applying the official format", "Final verification"],

    readyTitle: "Petition Successfully Generated",
    readyText: "Check every detail before signing or submitting it.",
    verifyOk: (n) => `${n} required fields validated`,
    verifyBad: "Petition requires attention — review the verification warnings.",
    failedTitle: "Petition could not be completed",
    failedText: "Your information is safe. Please try again.",
    cancelledTitle: "Petition cancelled",
    cancelledText: "Start a new petition when you are ready.",

    pdf: "Download PDF", docx: "Download Word", noPdf: "PDF unavailable",
    print: "Print", copy: "Copy", copied: "Copied",
    revise: "Edit Petition", editSave: "Save Changes", editCancel: "Cancel",
    editHint: "Edit the petition directly below. Your changes are used exactly as you type them \u2014 nothing is reworded. To ask for a rewording instead, type what you want in the chat.",
    editEmpty: "The petition cannot be emptied. Press Cancel to keep it as it was.",
    reviseWorking: "Rewriting your petition…",

    voiceStart: "Start Voice", voiceStop: "End Voice", voiceEnd: "End",
    mute: "Mute", unmute: "Unmute",
    voiceState: {
      idle: "Voice off",
      connecting: "Connecting…",
      listening: "Listening",
      user_speaking: "Speaking…",
      transcribing: "Transcribing…",
      processing: "Thinking…",
      assistant_speaking: "Assistant speaking",
      reconnecting: "Reconnecting…",
      error: "Voice stopped",
      ended: "Voice off",
    },
    voiceRetry: "Retry Voice", voiceContinueText: "Continue with Text",
    voiceUnavailable: "Voice is not available on this service. Your petition is safe — please type instead.",
    voiceLost: "The voice connection was lost. Your petition progress is safe.",
    voiceIdleEnded: "Voice ended after a long silence. Your petition is saved — press Start Voice to continue.",
    micDenied: "Microphone access is required for voice conversation. Please allow it in your browser, or type your answer.",
    micMissing: "No microphone was found. Please connect one, or type your answer.",
    micBusy: "The microphone is being used by another application. Close it and try again, or type your answer.",
    micUnsupported: "This browser cannot record audio. Please use Chrome or Edge, or type your answer.",

    restartTitle: "Start a new petition?",
    restartText: "The details collected for the current petition will be cleared.",
    restartKeep: "Keep Current Petition", restartGo: "Start New Petition",
    cancelTitle: "Cancel this petition?",
    cancelText: "The details collected so far will be discarded.",
    cancelKeep: "Keep Working", cancelGo: "Cancel Petition",

    svcAI: "AI drafting service", svcDoc: "Document generation",
    svcVoice: "Voice input", svcSecure: "Secure processing",
    svcReady: "Ready", svcOff: "Not available",
    svcSecureNote: "Identifiers are masked before any text is sent for drafting.",

    none: "No corrections yet.",
    failedMsg: "We couldn't reach the service. Your details are safe — please try again.",
    reveal: "Show", hide: "Hide",
  },
  ta: {
    title: "குடிமகன் மனு உதவியாளர்",
    subtitle: "செயற்கை நுண்ணறிவு துணையுடன் மனு தயாரிப்பு",
    assistant: "மனு உதவியாளர்",
    details: "மனு விவரங்கள்",
    citizenSection: "குடிமகன் விவரங்கள்",
    grievanceSection: "குறை விவரங்கள்",
    corrections: "திருத்தங்கள் வரலாறு",
    analysis: "மனு தொடர்பான ஆவணப் பகுப்பாய்வு",
    attachRequiredHead: "அதிகாரப்பூர்வ ஆவணத்தின்படி இவை தேவை:",
    attachRemove: "நீக்கு",
    attachTitle: "கோப்பைச் சேர்க்கவும்",
    attachUploading: "பதிவேற்றப்படுகிறது…",
    attachDone: "இணைக்கப்பட்டது",
    attachConfirmHead: "இது சரியா?",
    attachConfirmYes: "ஆம், சரிதான்",
    attachAcknowledge: "சரி, இணைத்தே வைக்கவும்",
    attachConfirmNo: "இல்லை, இதைக் கணக்கில் கொள்ள வேண்டாம்",
    attachUnreadable: "இந்தக் கோப்பிலிருந்து உரையைப் படிக்க முடியவில்லை.",
    attachLowConfidence: "இது குறைந்த உறுதியுடன் படிக்கப்பட்டது \u2014 சரிபார்க்கவும்.",
    attachFailed: "அந்தக் கோப்பை இணைக்க முடியவில்லை.",
    attachField: {
      reference_number: "ஒப்புகை எண்", petition_number: "மனு எண்",
      submitted_on: "அளித்த தேதி", department: "துறை",
      authority: "அதிகாரி", subject: "பொருள்", status: "நிலை",
    },
    analysisSources: "ஆதாரங்கள்",
    analysisPage: "பக்கம்",
    analysisOfficial: "அதிகாரப்பூர்வம்",
    analysisDepartmental: "துறை சார்ந்தது",
    analysisExternal: "வெளி ஆதாரம்",
    analysisSuperseded: "காலாவதியானது",
    system: "சேவை நிலை",
    langLabel: "மொழி",
    inputLabel: "உங்கள் பதில்",
    refLabel: "தொடர்பு எண்",
    newPetition: "புதிய மனு",
    petitions: "மனுக்கள்",
    petitionsEmpty: "இந்தச் சாதனத்தில் நீங்கள் தயாரிக்கும் மனுக்கள் இங்கே பட்டியலிடப்படும்.",
    petitionsNote: "இந்தச் சாதனத்தில் மட்டுமே சேமிக்கப்படுகிறது. பொதுக் கணினியை விட்டுச் செல்லும் முன் பட்டியலை அழிக்கவும்.",
    petitionsClear: "பட்டியலை அழிக்கவும்",
    petitionsClearConfirm: "அனைத்து மனுக்களையும் பட்டியலிலிருந்து நீக்கவா? ஆவணங்கள் நீக்கப்படாது.",
    petitionsOpen: "திற",
    petitionsRemove: "பட்டியலிலிருந்து நீக்கு",
    petitionStatus: {
      collecting: "நடப்பில்", attachments: "நடப்பில்",
      confirming: "உறுதிப்படுத்தல் நிலுவையில்", generating: "தயாராகிறது",
      ready: "தயார்", cancelled: "ரத்து", failed: "கவனம் தேவை",
    },

    placeholder: "உங்கள் பதிலைத் தட்டச்சு செய்யவும்…",
    placeholderLong: "உங்கள் குறையை உங்கள் சொந்த வார்த்தைகளில் எழுதுங்கள்…",
    send: "அனுப்பு",
    confirm: "உறுதி செய்து மனு தயாரிக்கவும்",
    restart: "மீண்டும் தொடங்கு",
    cancel: "ரத்து செய்",
    edit: "திருத்து",
    save: "சேமி",
    dismiss: "வேண்டாம்",

    lifecycle: {
      collecting: "விவரங்கள் சேகரிக்கப்படுகின்றன",
      attachments: "இணைப்புகள் சேர்த்தல்",
      confirming: "விவரங்கள் சரிபார்ப்பு",
      generating: "மனு தயாராகிறது",
      ready: "மனு தயார்",
      cancelled: "மனு ரத்து செய்யப்பட்டது",
      failed: "கவனம் தேவை",
    },
    assistantStatus: {
      collecting: "குடிமகன் விவரங்கள் சேகரிக்கப்படுகின்றன",
      attachments: "துணை ஆவணங்களுக்காகக் காத்திருக்கிறோம்",
      confirming: "உங்கள் உறுதிப்படுத்தலுக்குக் காத்திருக்கிறேன்",
      generating: "உங்கள் மனு தயாராகிறது",
      ready: "சேமித்த மனுவில் மாற்றங்களைக் கோரலாம்",
      cancelled: "இந்த மனு ரத்து செய்யப்பட்டது",
      failed: "ஏதோ ஒன்றுக்கு உங்கள் கவனம் தேவை",
    },
    steps: ["குடிமகன் விவரம்", "குறை", "இணைப்புகள்", "சரிபார்ப்பு", "தயாரிப்பு", "மனு தயார்"],

    progress: (a, b) => `${b} விவரங்களில் ${a} சேகரிக்கப்பட்டது`,
    pending: "நிலுவையில்",
    required: "அவசியம்",

    reviewTitle: "உங்கள் மனு விவரங்களைச் சரிபார்க்கவும்",
    reviewText: "மனு தயாரிக்கப்படும் முன் கீழே உள்ள அனைத்தையும் சரிபார்க்கவும்.",

    genTitle: "உங்கள் மனு தயாராகிறது",
    genHint: "இதற்கு சில வினாடிகள் ஆகும்.",
    genSteps: ["குடிமகன் விவரங்கள் சரிபார்க்கப்பட்டன", "குறை பதிவு செய்யப்பட்டது",
               "மனு எழுதப்படுகிறது", "அரசு வடிவம் அமைக்கப்படுகிறது",
               "இறுதிச் சரிபார்ப்பு"],
    draftHeading: "மனு வரைவு",
    fromTag: "அனுப்புநர்", toTag: "பெறுநர்",
    improve1: "தெளிவு மேம்பாடு", improve2: "சிறந்த சொற்கள்",
    improve3: "அரசு வடிவம்",
    translate: "மொழிபெயர்",
    translating: "மனு மொழிபெயர்க்கப்படுகிறது",
    translateSteps: ["மனு படிக்கப்படுகிறது",
                     "சொற்கள் மொழிபெயர்க்கப்படுகிறன",
                     "அரசு வடிவம் அமைக்கப்படுகிறது",
                     "இறுதிச் சரிபார்ப்பு"],
    translateFailed: "மனுவை மொழிபெயர்க்க இயலவில்லை. மனு மாற்றப்படவில்லை.",
    reviseTitle: "உங்கள் மனு புதுப்பிக்கப்படுகிறது",
    reviseSteps: ["உங்கள் கோரிக்கை படிக்கப்படுகிறது", "மனு புதுப்பிக்கப்படுகிறது",
                  "அரசு வடிவம் அமைக்கப்படுகிறது", "இறுதிச் சரிபார்ப்பு"],

    readyTitle: "மனு வெற்றிகரமாகத் தயாரிக்கப்பட்டது",
    readyText: "கையொப்பமிடும் அல்லது சமர்ப்பிக்கும் முன் ஒவ்வொரு விவரத்தையும் சரிபார்க்கவும்.",
    verifyOk: (n) => `${n} அவசிய விவரங்கள் சரிபார்க்கப்பட்டன`,
    verifyBad: "மனுவுக்குக் கவனம் தேவை — சரிபார்ப்பு எச்சரிக்கைகளைப் பாருங்கள்.",
    failedTitle: "மனுவை முடிக்க முடியவில்லை",
    failedText: "உங்கள் விவரங்கள் பாதுகாப்பாக உள்ளன. மீண்டும் முயற்சிக்கவும்.",
    cancelledTitle: "மனு ரத்து செய்யப்பட்டது",
    cancelledText: "தயாரானதும் புதிய மனுவைத் தொடங்கவும்.",

    pdf: "PDF பதிவிறக்கம்", docx: "Word பதிவிறக்கம்", noPdf: "PDF இல்லை",
    print: "அச்சிடு", copy: "நகலெடு", copied: "நகலெடுக்கப்பட்டது",
    revise: "மனுவைத் திருத்து", editSave: "மாற்றங்களைச் சேமி", editCancel: "ரத்து",
    editHint: "கீழே உள்ள மனுவை நேரடியாகத் திருத்தலாம். நீங்கள் எழுதியபடியே அப்படியே பயன்படுத்தப்படும் \u2014 எதுவும் மாற்றி எழுதப்படாது. மாற்றி எழுதச் சொல்ல வேண்டுமானால், அரட்டையில் தட்டச்சு செய்யுங்கள்.",
    editEmpty: "மனுவை காலியாக்க முடியாது. முந்தையபடி வைத்திருக்க ரத்து அழுத்தவும்.",
    reviseWorking: "உங்கள் மனு மீண்டும் எழுதப்படுகிறது…",

    voiceStart: "குரல் தொடங்கு", voiceStop: "குரல் நிறுத்து", voiceEnd: "நிறுத்து",
    mute: "ஒலி நிறுத்து", unmute: "ஒலி தொடங்கு",
    voiceState: {
      idle: "குரல் நிறுத்தப்பட்டது",
      connecting: "இணைக்கப்படுகிறது…",
      listening: "கேட்கிறேன்…",
      user_speaking: "பேசுகிறீர்கள்…",
      transcribing: "புரிந்துகொள்கிறேன்…",
      processing: "புரிந்துகொள்கிறேன்…",
      assistant_speaking: "பதிலளிக்கிறேன்…",
      reconnecting: "மீண்டும் இணைக்கப்படுகிறது…",
      error: "குரல் நிறுத்தப்பட்டது",
      ended: "குரல் நிறுத்தப்பட்டது",
    },
    voiceRetry: "மீண்டும் முயற்சி", voiceContinueText: "தட்டச்சில் தொடர்",
    voiceUnavailable: "இந்தச் சேவையில் குரல் வசதி இல்லை. உங்கள் மனு பாதுகாப்பாக உள்ளது — தட்டச்சு செய்யவும்.",
    voiceLost: "குரல் இணைப்பு துண்டிக்கப்பட்டது. உங்கள் மனு பாதுகாப்பாக உள்ளது.",
    voiceIdleEnded: "நெடுநேரம் அமைதியாக இருந்ததால் குரல் நிறுத்தப்பட்டது. மனு சேமிக்கப்பட்டது.",
    micDenied: "குரல் உரையாடலுக்கு ஒலிவாங்கி அனுமதி தேவை. உலாவியில் அனுமதி அளிக்கவும் அல்லது தட்டச்சு செய்யவும்.",
    micMissing: "ஒலிவாங்கி கிடைக்கவில்லை. இணைக்கவும் அல்லது தட்டச்சு செய்யவும்.",
    micBusy: "ஒலிவாங்கியை வேறு ஒரு செயலி பயன்படுத்துகிறது. மீண்டும் முயற்சிக்கவும்.",
    micUnsupported: "இந்த உலாவியில் ஒலிப்பதிவு இயலாது. Chrome அல்லது Edge பயன்படுத்தவும்.",

    restartTitle: "புதிய மனுவைத் தொடங்கவா?",
    restartText: "தற்போதைய மனுவின் விவரங்கள் அழிக்கப்படும்.",
    restartKeep: "தற்போதையதை வைத்திரு", restartGo: "புதிய மனு தொடங்கு",
    cancelTitle: "இந்த மனுவை ரத்து செய்யவா?",
    cancelText: "இதுவரை சேகரித்த விவரங்கள் நீக்கப்படும்.",
    cancelKeep: "தொடர்ந்து செய்", cancelGo: "மனுவை ரத்து செய்",

    svcAI: "மனு எழுதும் சேவை", svcDoc: "ஆவணத் தயாரிப்பு",
    svcVoice: "குரல் உள்ளீடு", svcSecure: "பாதுகாப்பான செயலாக்கம்",
    svcReady: "தயார்", svcOff: "இல்லை",
    svcSecureNote: "எழுதுவதற்கு உரை அனுப்பும் முன் அடையாள எண்கள் மறைக்கப்படுகின்றன.",

    none: "இதுவரை திருத்தம் இல்லை.",
    failedMsg: "சேவையைத் தொடர்பு கொள்ள முடியவில்லை. உங்கள் விவரங்கள் பாதுகாப்பாக உள்ளன — மீண்டும் முயற்சிக்கவும்.",
    reveal: "காட்டு", hide: "மறை",
  },
};

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[<>&"]/g, c =>
  ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" })[c]);
const T = () => UI[lang];

const EXPERIENCE = {
  en: {
    eyebrow: "YOUR VOICE. A CLEARER PATH FORWARD.", title: "Let’s prepare your petition.",
    subtitle: "Share your details, tell us what happened, and leave with a document you can use.",
    detailsHint: "Your answers appear here as we go. You can edit any detail.",
    saved: "Progress saved", saving: "Saving…", restored: "Your saved petition has been restored.",
    offline: "Connection interrupted. Your last saved answers are kept. Reconnect before sending again.",
    expired: "This saved petition is no longer available. Start a new petition to continue.",
    retry: "Reconnect", help: "How it works", details: "View details", conversation: "Back to conversation",
    inputHint: "Enter to send · Shift + Enter for a new line", retryDraft: "Your answer is still in the box. Check your saved details before sending again.",
    sessionGone: "That petition is no longer on this service, so it has been removed from the list.",
    privateHint: "Type this number privately. Only the last four digits appear in the conversation.",
    longHint: "Include the location, what happened, and the action you are requesting. Your words are kept unchanged.",
    copiedError: "Copy is unavailable. Select the petition text to copy it, or download the Word document.",
    popupError: "Allow pop-ups for this page to print, or download the document.",
    helpTitle: "From your concern to a clear petition",
    helpText: "1. Answer the questions by typing or using voice.\n2. Review your details and select Edit to make corrections.\n3. Confirm to create your document, then download or print it.\n\nYour progress is restored on this browser. Your grievance is kept in your own words. Review the document before signing; this app does not submit it to an office.",
    close: "Got it", forget: "Forget on this browser", forgetText: "The saved link will be removed from this browser. Existing server records and downloaded files are kept.",
    readyTitle: "Your petition is ready.", readySubtitle: "Review the document, then download, print, or make a correction.",
    reviewTitle: "Everything ready for a final check.", reviewSubtitle: "Review the details beside your conversation. Confirm when everything is correct.",
    recoveryNeeded: "Checking your last saved progress…", genericError: "That request could not be completed. Please try again.",
    add: "Add", retryGeneration: "Retry document generation", reviewBeforeRetry: "Your details are saved. Review them and retry document generation.",
    voiceExternal: "Voice audio is processed by the configured speech service.", localProcessing: "External AI processing is disabled.",
  },
  ta: {
    eyebrow: "உங்கள் குரல். உங்கள் மனு.", title: "உங்கள் மனுவைத் தயாரிப்போம்.",
    subtitle: "உங்கள் விவரங்களையும் குறையையும் பகிருங்கள். பயன்படுத்தக்கூடிய மனுவைப் பெறுங்கள்.",
    detailsHint: "உங்கள் பதில்கள் இங்கே தோன்றும். எந்த விவரத்தையும் திருத்தலாம்.",
    saved: "விவரங்கள் சேமிக்கப்பட்டன", saving: "சேமிக்கப்படுகிறது…", restored: "சேமிக்கப்பட்ட மனு மீட்கப்பட்டது.",
    offline: "இணைப்பு துண்டிக்கப்பட்டது. சேமித்த பதில்கள் உள்ளன. மீண்டும் அனுப்பும் முன் இணைக்கவும்.",
    expired: "சேமித்த மனு கிடைக்கவில்லை. புதிய மனுவைத் தொடங்கவும்.",
    retry: "மீண்டும் இணை", help: "பயன்படுத்துவது எப்படி", details: "விவரங்களைக் காண்க", conversation: "உரையாடலுக்குத் திரும்பு",
    inputHint: "அனுப்ப Enter · புதிய வரிக்கு Shift + Enter", retryDraft: "உங்கள் பதில் பெட்டியில் உள்ளது. மீண்டும் அனுப்பும் முன் சேமித்த விவரங்களைப் பாருங்கள்.",
    sessionGone: "அந்த மனு இந்தச் சேவையில் இப்போது இல்லை; எனவே பட்டியலிலிருந்து நீக்கப்பட்டது.",
    privateHint: "இந்த எண்ணைத் தட்டச்சு செய்யவும். கடைசி நான்கு இலக்கங்கள் மட்டும் உரையாடலில் தெரியும்.",
    longHint: "இடம், நடந்தது, நீங்கள் கோரும் நடவடிக்கை ஆகியவற்றைக் குறிப்பிடவும். உங்கள் சொற்கள் மாற்றப்படாது.",
    copiedError: "நகலெடுக்க இயலவில்லை. மனு உரையைத் தேர்ந்தெடுத்து நகலெடுக்கவும் அல்லது Word ஆவணத்தைப் பதிவிறக்கவும்.",
    popupError: "அச்சிட இந்தப் பக்கத்திற்குப் பாப்-அப் அனுமதி அளிக்கவும் அல்லது ஆவணத்தைப் பதிவிறக்கவும்.",
    helpTitle: "உங்கள் குறையிலிருந்து தெளிவான மனு வரை",
    helpText: "1. தட்டச்சு அல்லது குரல் மூலம் கேள்விகளுக்குப் பதிலளிக்கவும்.\n2. விவரங்களைச் சரிபார்த்து தேவையான திருத்தங்களைச் செய்யவும்.\n3. உறுதிசெய்த பிறகு ஆவணத்தைப் பதிவிறக்கவும் அல்லது அச்சிடவும்.\n\nஇந்த உலாவியில் உங்கள் மனுவை மீண்டும் தொடரலாம். உங்கள் குறை மாற்றப்படாது. கையொப்பமிடும் முன் ஆவணத்தைச் சரிபார்க்கவும். இந்தச் செயலி மனுவை அலுவலகத்திற்குச் சமர்ப்பிக்காது.",
    close: "புரிந்தது", forget: "இந்த உலாவியில் மற", forgetText: "இந்த உலாவியிலிருந்து சேமித்த இணைப்பு நீக்கப்படும். சேவையகப் பதிவுகளும் பதிவிறக்கிய கோப்புகளும் இருக்கும்.",
    readyTitle: "உங்கள் மனு தயார்.", readySubtitle: "ஆவணத்தைச் சரிபார்த்து பதிவிறக்கவும், அச்சிடவும் அல்லது திருத்தவும்.",
    reviewTitle: "இறுதியாகச் சரிபார்ப்போம்.", reviewSubtitle: "உரையாடலுடன் உள்ள விவரங்களைச் சரிபார்க்கவும். அனைத்தும் சரியாக இருந்தால் உறுதிசெய்யவும்.",
    recoveryNeeded: "சேமித்த விவரங்கள் சரிபார்க்கப்படுகின்றன…", genericError: "கோரிக்கையை முடிக்க இயலவில்லை. மீண்டும் முயற்சிக்கவும்.",
    add: "சேர்", retryGeneration: "ஆவணத்தை மீண்டும் தயாரி", reviewBeforeRetry: "உங்கள் விவரங்கள் சேமிக்கப்பட்டுள்ளன. சரிபார்த்து ஆவணத்தை மீண்டும் தயாரிக்கவும்.",
    voiceExternal: "குரல் ஒலி இணைக்கப்பட்ட பேச்சுச் சேவையால் செயலாக்கப்படுகிறது.", localProcessing: "வெளிப்புற AI செயலாக்கம் முடக்கப்பட்டுள்ளது.",
  },
};
const X = () => EXPERIENCE[lang];

let lang = "en";
let sid = null;
let seen = 0;
let busy = false;
let view = null;
let socket = null;
let editing = null;         // field name currently being corrected inline
let revealed = new Set();   // identifiers the citizen asked to see, this render only
let lastValues = {};        // to animate only the row that actually changed
let closedNotice = false;   // a cancelled or failed session is announced once
let requestPending = false;
let lastApiMessage = "";
let connectionLost = false;
let lastApiStatus = 0;
let healthState = null;
let generationPoll = null;
// Whether the petition text itself is open for hand editing.
//
// Declared HERE, with the rest of the module state, and not beside the editor
// functions further down: `syncControls` reads it, `syncControls` runs during
// page initialisation, and a `let` declared after its first use throws
// "cannot access before initialization" — which killed the whole script, so
// the page loaded with a dead composer and no session at all.
//
// Named for the letter specifically, because `editing` already belongs to the
// inline field editor in the details panel.
let editingLetter = false;
let editBackup = "";
let editVersion = 0;
let editConflict = false;
const STORAGE_KEY = "petition.current.v1";

function rememberSession() {
  // Store only the recovery handle, never citizen answers or document text.
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ id: sid, language: lang })); } catch {}
}
function savedSession() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    return /^[\da-f-]{36}$/i.test(saved?.id || "") ? saved : null;
  } catch { return null; }
}
function forgetSession() { try { localStorage.removeItem(STORAGE_KEY); } catch {} }

function connectionNotice(message = "") {
  if ($("connectionBanner")) $("connectionBanner").hidden = !message;
  if ($("connectionText")) $("connectionText").textContent = message;
}

/* ------------------------------------------------------------------ masking
   Aadhaar and mobile are shown with only their last four digits. The full
   value stays in the record on the server and goes into the petition through
   the deterministic path; the screen does not need it, and a screen in a
   public office is the easiest place in the whole system to read one off. */
const SENSITIVE = new Set(["aadhaar", "mobile"]);

function maskDisplay(type, display) {
  const text = String(display ?? "");
  if (!SENSITIVE.has(type)) return text;
  const digits = (text.match(/\d/g) || []).join("");
  if (digits.length <= 4) return text;
  const last4 = digits.slice(-4);

  // Aadhaar is printed in three groups of four, so the last four are exactly
  // the last group and the grouping survives masking intact.
  if (type === "aadhaar") return "XXXX XXXX " + last4;

  // A mobile is grouped 5 + 5, so keeping the last four straddles the space
  // and produces "+91 XXXXX X3210", which reads like a typo. Collapse the
  // masked part into one run instead.
  const cc = text.startsWith("+91") ? "+91 " : "";
  const body = cc ? digits.slice(2) : digits;
  return cc + "X".repeat(Math.max(0, body.length - 4)) + last4;
}

/* The read-back the assistant speaks carries the full identifiers, because the
   server composed it for a citizen reading their own details. On screen the
   same masking applies — without touching the grievance, which is reproduced
   word for word by rule. */
function maskInText(text) {
  let out = String(text ?? "");
  for (const f of (view?.collected || [])) {
    if (!SENSITIVE.has(f.type)) continue;
    const shown = String(f.display ?? "");
    if (shown.length >= 6 && out.includes(shown)) {
      out = out.split(shown).join(maskDisplay(f.type, shown));
    }
  }
  return out;
}

/* The citizen's own turn is masked only when the WHOLE message is one
   identifier — which is what an answer to "say your Aadhaar number" is.
   Deliberately not a search-and-replace over their words: a twelve-digit
   figure quoted inside a grievance would be rewritten on screen, and the
   grievance is reproduced exactly as entered. */
function maskCitizenTurn(text) {
  const trimmed = String(text ?? "").trim();
  const digits = trimmed.replace(/\D/g, "");
  if (!digits || digits.length < 10 || /[A-Za-z஀-௿]/.test(trimmed)) return text;
  for (const f of (view?.collected || [])) {
    if (!SENSITIVE.has(f.type)) continue;
    const raw = String(f.value ?? "").replace(/\D/g, "");
    if (raw && raw === digits) return maskDisplay(f.type, f.display);
  }
  // Also protect rejected values and earlier answers after a correction.
  return maskDisplay(digits.length === 12 ? "aadhaar" : "mobile", digits);
}

/* --------------------------------------------------------------------- api */

async function api(path, options = {}) {
  const { quiet = false, timeout = 180000, ...fetchOptions } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  lastApiStatus = 0;
  lastApiMessage = "";
  try {
    const r = await fetch(path, { headers: { "Content-Type": "application/json" },
      cache: "no-store", ...fetchOptions, signal: controller.signal });
    lastApiStatus = r.status;
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      const message = typeof body.detail === "string" ? body.detail
        : Array.isArray(body.detail) ? body.detail.map(e => e.msg).join(". ") : X().genericError;
      // "Not Found" is what the framework says when a ROUTE is missing, and
      // it means nothing to a citizen. Anything else is a sentence this
      // service wrote on purpose and is worth showing.
      lastApiMessage = message === "Not Found" ? "" : message;
      if (!quiet) bubble("system", message, true);
      return null;
    }
    return await r.json();
  } catch {
    if (!quiet) {
      connectionLost = true;
      connectionNotice(X().offline);
    }
    return null;
  } finally {
    clearTimeout(timer);
  }
}

async function mutate(path, body) {
  if (requestPending || connectionLost) return null;
  requestPending = true;
  busy = true;
  syncControls();
  const result = await api(path, { method: "POST", ...(body ? { body: JSON.stringify(body) } : {}) });
  requestPending = false;
  busy = false;
  if (result) render(result);
  else {
    clearWorking();
    if (view) { drawLifecycle(view); drawStepper(view); }
    syncControls();
  }
  return result;
}

/* ---------------------------------------------------------------- messages */

function bubble(who, text, isError) {
  const row = document.createElement("div");
  row.className = "turn " + who + (isError ? " error" : "");
  if (who !== "citizen") {
    const av = document.createElement("div");
    av.className = "avatar";
    av.setAttribute("aria-hidden", "true");
    av.textContent = who === "system" ? "!" : "✦";
    row.appendChild(av);
  }
  const b = document.createElement("div");
  b.className = "bubble";
  b.textContent = who === "citizen" ? maskCitizenTurn(text) : maskInText(text);
  row.appendChild(b);
  $("log").appendChild(row);
  // The citizen's own message always brings the view with it — they just sent
  // it and expect to see it land. Anything else only follows if they were
  // already at the bottom, so reading back over the conversation is not
  // interrupted by the assistant answering.
  scrollLog(who === "citizen");
  return row;
}

/** An assistant question, with the field it is asking about named above it. */
function questionBubble(text, field) {
  const row = document.createElement("div");
  row.className = "turn assistant";
  const av = document.createElement("div");
  av.className = "avatar";
  av.setAttribute("aria-hidden", "true");
  av.textContent = "✦";
  const b = document.createElement("div");
  b.className = "bubble";
  if (field) {
    const head = document.createElement("div");
    head.className = "q-label";
    head.innerHTML = `${esc(field.label)}${field.required ? `<span class="req">${esc(T().required)}</span>` : ""}`;
    b.appendChild(head);
  }
  b.appendChild(document.createTextNode(maskInText(text)));
  row.appendChild(av); row.appendChild(b);
  $("log").appendChild(row);
  scrollLog();
  return row;
}

/* Scrolling the conversation.
 *
 * Two things were wrong. Setting scrollTop the instant a bubble is appended
 * measures it before the browser has wrapped its text, so the view stopped
 * about 27 pixels short and the last line of the read-back — "Is all of this
 * correct?" — sat under the composer where nobody saw it. And it scrolled
 * unconditionally, which yanked a citizen back to the bottom while they were
 * reading something further up.
 */
function nearBottom(el, slack = 90) {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= slack;
}

function scrollLog(force = false) {
  const log = $("log");
  if (!log) return;
  // Decide BEFORE the new content changes the measurement.
  const shouldFollow = force || nearBottom(log);
  if (!shouldFollow) return;
  const go = () => { log.scrollTop = log.scrollHeight; };
  go();                                  // never visibly behind
  requestAnimationFrame(() => { go(); requestAnimationFrame(go); });  // after layout
}

/* ------------------------------------------------- the drafting animation
   Opens the middle column while the petition is being made.

   The stage rail walks forward on elapsed time, and that is honest only
   because of where it stops: the first two stages describe work that has
   genuinely finished, the middle ones are what the service is doing now, and
   the LAST one never ticks until the server has actually returned a document.
   The panel cannot claim the petition is done before it is. */

let genTimer = null;
let genStage = 2;
// "create" the first time, "revise" for a change made afterwards. The panel
// and its animation are the same either way — only what it claims to be doing
// changes, because a petition that already exists is not being written again.
let genMode = "create";
let docWorkTimer = null;

function railSteps() {
  const t = T();
  if (genMode === "translate") return t.translateSteps;
  return genMode === "revise" ? t.reviseSteps : t.genSteps;
}

function drawRail() {
  const steps = railSteps();
  $("genRail").innerHTML = steps.map((label, i) => {
    const cls = i < genStage ? "done" : i === genStage ? "now" : "";
    const mark = i < genStage ? "✓" : "";
    return `<li class="${cls}"><span class="m" aria-hidden="true">${mark}</span>${esc(label)}</li>`;
  }).join("");
  $("genNow").textContent = steps[Math.min(genStage, steps.length - 1)];
}

function startGenerating(mode) {
  const t = T();
  genMode = ["revise", "translate"].includes(mode) ? mode : "create";
  $("ui-genTitle").textContent = genMode === "translate" ? t.translating
    : genMode === "revise" ? t.reviseTitle : t.genTitle;
  $("gp-title").textContent = t.draftHeading;
  $("gp-from").textContent = t.fromTag;
  $("gp-to").textContent = t.toTag;
  $("gp-c1").textContent = t.improve1;
  $("gp-c2").textContent = t.improve2;
  $("gp-c3").textContent = t.improve3;
  $("gp-date").textContent = new Date().toLocaleDateString(
    lang === "ta" ? "ta-IN" : "en-IN", { day: "2-digit", month: "long", year: "numeric" });

  // Writing the first draft, details and grievance are behind us before this
  // panel ever opens. Updating one, nothing is behind us yet: the request has
  // been sent, not read.
  genStage = genMode === "create" ? 2 : 0;
  drawRail();
  $("genPanel").hidden = false;
  document.querySelector("main.workspace").classList.add("generating");

  clearInterval(genTimer);
  // No timed stage completions: only the server can report work finished.
}

function stopGenerating(completed) {
  clearInterval(genTimer);
  genTimer = null;
  clearTimeout(docWorkTimer);
  docWorkTimer = null;
  if (completed) { genStage = railSteps().length; drawRail(); }
  $("genPanel").hidden = true;
  document.querySelector("main.workspace").classList.remove("generating");
}

/* Work on the document itself, whenever it happens.
 *
 * The first draft and every later change play in the same panel, in the same
 * place, because to the citizen they are the same event: the petition is being
 * worked on and they are waiting for it.
 *
 * The delay is only for changes. A question answered in a fifth of a second
 * ("what is my reference number?") must not blank the petition and put it
 * straight back — that reads as something having gone wrong. Work that
 * actually takes time still gets the panel, which is every real edit. */
const DOC_WORK_DELAY_MS = 450;

/* Saying yes in the conversation, rather than pressing the button.
 *
 * The button knows what it just asked for and opens the panel itself. A typed
 * or spoken "yes" does not: the page sends one message and waits, and the
 * reply only arrives once the petition has been written. That wait was two and
 * a half minutes in one report, with the review screen unchanged throughout
 * and no sign that anything had started.
 *
 * The workflow knows. It records `generating` the moment the confirm step
 * routes to composition, and /progress reports that one word without waiting
 * on the session lock. So the panel opens on the workflow's say-so, exactly as
 * it does for the button — and a turn that was a correction or a question
 * never reaches that status, so nothing opens and nothing is claimed.
 */
const PROGRESS_POLL_MS = 700;

async function watchForGeneration(session) {
  while (requestPending && sid === session) {
    await new Promise(resolve => setTimeout(resolve, PROGRESS_POLL_MS));
    if (!requestPending || sid !== session) return;
    let status;
    try {
      const response = await fetch(`/api/sessions/${session}/progress`,
                                   { cache: "no-store" });
      if (!response.ok) return;
      status = (await response.json()).status;
    } catch {
      return;  // A progress check that fails must never disturb the turn.
    }
    if (!requestPending || sid !== session) return;
    if (status === "generating") { startGenerating("create"); return; }
  }
}

function beginDocumentWork(mode) {
  clearTimeout(docWorkTimer);
  docWorkTimer = null;
  if (mode !== "revise") { startGenerating("create"); return; }
  docWorkTimer = setTimeout(() => {
    docWorkTimer = null;
    startGenerating("revise");
  }, DOC_WORK_DELAY_MS);
}

/** A plain working bubble, used by dictation. */
function workingBubble(text) {
  clearWorking();
  const row = document.createElement("div");
  row.className = "turn assistant";
  row.id = "working";
  row.innerHTML =
    `<div class="avatar" aria-hidden="true">✦</div>
     <div class="bubble" role="status" aria-live="polite">
       <span class="spin-dot" aria-hidden="true"></span>${esc(text)}
     </div>`;
  $("log").appendChild(row);
  scrollLog();
  return row;
}

function clearWorking() { $("working")?.remove(); }

/* ------------------------------------------------------------------ labels */

function labels() {
  const t = T();
  document.documentElement.lang = lang;
  $("ui-title").textContent = t.title;
  $("ui-subtitle").textContent = t.subtitle;
  $("ui-assistant").textContent = t.assistant;
  $("ui-details").textContent = t.details;
  $("ui-citizenSection").textContent = t.citizenSection;
  $("ui-grievanceSection").textContent = t.grievanceSection;
  $("ui-corrections").textContent = t.corrections;
  $("ui-analysis").textContent = t.analysis;
  $("ui-system").textContent = t.system;
  $("ui-langLabel").textContent = t.langLabel;
  $("ui-inputLabel").textContent = t.inputLabel;
  $("ui-refLabel").textContent = t.refLabel;
  $("newText").textContent = t.newPetition;
  $("sendText").textContent = t.send;
  $("confirm").textContent = t.confirm;
  $("restart").textContent = t.restart;
  $("cancel").textContent = t.cancel;
  $("printBtn").textContent = t.print;
  $("copyBtn").textContent = t.copy;
  $("reviseText").textContent = t.revise;
  $("editHint").textContent = t.editHint;
  $("editSave").textContent = t.editSave;
  $("editCancel").textContent = t.editCancel;
  const x = X();
  const extras = { "ui-workspaceEyebrow": x.eyebrow, workspaceTitle: x.title,
    workspaceSubtitle: x.subtitle, "ui-detailsHint": x.detailsHint,
    retryConnection: x.retry, helpText: x.help, detailsToggleText: x.details };
  for (const [id, value] of Object.entries(extras)) if ($(id)) $(id).textContent = value;
  $("lang").value = lang;
  $("stepper").setAttribute("aria-label", lang === "ta" ? "மனு முன்னேற்றம்" : "Petition progress");
  drawHealth();
  paintVoice({});
  if (typeof navigationLabels === "function") navigationLabels();
}

/* ----------------------------------------------------------------- stepper
   Derived from the session, never from a counter of our own. */

function stageOf(v) {
  if (!v) return 0;
  if (v.status === "ready") return 5;
  if (v.status === "generating") return 4;
  if (v.status === "confirming") return 3;
  if (v.status === "attachments") return 2;
  if (v.awaiting === "grievance") return 1;
  return 0;
}

function drawStepper(v) {
  const stage = stageOf(v);
  // "Completed" is itself complete once the petition exists — it is the only
  // step that is finished at the moment it becomes current.
  const finished = Boolean(v) && v.status === "ready";
  $("stepper").innerHTML = T().steps.map((label, i) => {
    const isDone = i < stage || (finished && i === T().steps.length - 1);
    const state = isDone ? "done" : i === stage ? "active" : "";
    const mark = isDone ? "✓" : String(i + 1).padStart(2, "0");
    const arrow = i < T().steps.length - 1 ? `<span class="step-arrow" aria-hidden="true">›</span>` : "";
    return `<span class="step ${state}"${i === stage ? ' aria-current="step"' : ""}>
              <span class="marker" aria-hidden="true">${mark}</span>${esc(label)}
            </span>${arrow}`;
  }).join("");
}

/* ------------------------------------------------------------------ render */

function render(v) {
  if (!v) { busy = false; syncControls(); return; }
  view = v;
  sid = v.session_id;
  if (v.language !== lang) { lang = v.language; lastLang = lang; labels(); }
  rememberSession();
  revealed.clear();

  clearWorking();

  // New transcript turns. An assistant question is labelled with the field it
  // is asking for, which the session tells us directly.
  const turns = v.transcript || [];
  if (turns.length < seen) { $("log").replaceChildren(); seen = 0; }
  const pendingField = [...(v.outstanding || []), ...(v.collected || [])].find(f => f.name === v.awaiting);
  turns.slice(seen).forEach((t, i, arr) => {
    const isLast = i === arr.length - 1;
    if (t.who === "assistant" && isLast && pendingField && v.status === "collecting") {
      questionBubble(t.text, pendingField);
    } else {
      bubble(t.who, t.text);
    }
  });
  seen = turns.length;

  if (pendingField && pendingField.error) bubble("system", pendingField.error, true);

  // A failure says so once, in the conversation, carrying the reason. There is
  // no banner for it: the document column only exists when a document does,
  // and a cancelled session already gets a plain sentence from the service, so
  // repeating it here would tell the citizen the same thing twice.
  if (!closedNotice && v.status === "failed") {
    closedNotice = true;
    bubble("system", `${T().failedTitle} — ${v.error || T().failedText}`, true);
  }

  // Also covers the paths that do not go through the Confirm button — a
  // reconnecting client, or a turn settled over the voice socket.
  if (v.status === "generating") {
    if ($("genPanel").hidden) startGenerating();
  } else if (!$("genPanel").hidden || docWorkTimer) {
    stopGenerating(v.status === "ready");
  }

  drawStepper(v);
  drawLifecycle(v);
  drawDetails(v);
  drawCorrections(v);
  drawAnalysis(v);
  drawAttachments(v);
  drawOutcome(v);

  busy = requestPending || v.status === "generating";
  if (["cancelled", "failed"].includes(v.status) && voice.wants) stopVoice();
  if ($("workspaceTitle")) $("workspaceTitle").textContent = v.status === "ready" ? X().readyTitle
    : v.status === "confirming" ? X().reviewTitle : X().title;
  if ($("workspaceSubtitle")) $("workspaceSubtitle").textContent = v.status === "ready" ? X().readySubtitle
    : v.status === "confirming" ? X().reviewSubtitle : X().subtitle;
  if ($("saveStatus")) {
    const updated = new Date(v.updated_at || v.started_at);
    $("saveStatus").textContent = X().saved + (Number.isNaN(updated.getTime()) ? "" : " · " +
      updated.toLocaleTimeString(lang === "ta" ? "ta-IN" : "en-IN", { hour: "2-digit", minute: "2-digit" }));
  }
  document.querySelector("main.workspace").dataset.status = v.status;
  clearTimeout(generationPoll);
  // The recovery poll is for a generation this page started and then lost
  // track of. NOT for one running on the voice socket: that socket delivers
  // the next state itself, and the session snapshot this would fetch is
  // blocked behind the very lock the turn is holding — so it could only time
  // out after fifteen seconds and report a connection that was never lost,
  // in the middle of a composition that is going perfectly well.
  const voiceTurn = Boolean(voice.socket && voice.socket.readyState === 1
    && voice.state === VOICE.PROCESSING);
  if (v.status === "generating" && !requestPending && !voiceTurn) {
    generationPoll = setTimeout(recover, 2500);
  }
  syncControls();
  if (typeof drawVersions === "function") drawVersions(v);
}

function drawLifecycle(v) {
  const t = T();
  const key = v.status in t.lifecycle ? v.status : "collecting";
  const map = { collecting: "is-collecting", confirming: "is-review", generating: "is-generating",
                ready: "is-ready", cancelled: "is-stopped", failed: "is-stopped" };
  $("lifecycle").className = "lifecycle " + (map[key] || "is-collecting");
  $("lifecycleText").textContent = t.lifecycle[key];
  $("assistantStatus").textContent = t.assistantStatus[key];
}

function drawDetails(v) {
  const t = T();
  const total = v.progress?.total ?? 6;
  const done = v.progress?.answered ?? 0;
  $("progressText").textContent = t.progress(done, total);
  const pct = total ? Math.round((done / total) * 100) : 0;
  $("progressPct").textContent = pct + "%";
  $("progressBar").style.width = pct + "%";
  const track = $("progressBar").parentElement;
  track.setAttribute("role", "progressbar");
  track.setAttribute("aria-label", t.details);
  track.setAttribute("aria-valuenow", String(done));
  track.setAttribute("aria-valuemin", "0");
  track.setAttribute("aria-valuemax", String(total));

  const byName = {};
  for (const f of v.collected) byName[f.name] = { ...f, filled: true };
  for (const f of v.outstanding) byName[f.name] = { ...f, filled: false };

  const order = [...v.collected.map(f => f.name), ...v.outstanding.map(f => f.name)];
  const canonical = ["applicant_name", "age", "mobile", "address", "aadhaar", "grievance"];
  const names = canonical.filter(n => byName[n]).concat(order.filter(n => !canonical.includes(n)));

  const citizen = [], grievance = [];
  for (const name of names) {
    (name === "grievance" ? grievance : citizen).push(rowFor(byName[name], v));
  }
  $("citizenFields").innerHTML = citizen.join("");
  $("grievanceFields").innerHTML = grievance.join("") ||
    `<div class="field-row"><span class="field-mark" aria-hidden="true"></span>
       <div class="field-main"><div class="field-value pending">${esc(t.pending)}</div></div></div>`;

  $("warnings").innerHTML = (v.warnings || [])
    .map(w => `<div class="notice">${esc(w)}</div>`).join("");

  // Animate only rows whose value actually changed since the last render.
  for (const f of v.collected) {
    if (lastValues[f.name] !== undefined && lastValues[f.name] !== f.display) {
      document.querySelector(`.field-row[data-field="${f.name}"]`)?.classList.add("changed");
    }
    lastValues[f.name] = f.display;
  }

  wireFieldButtons(v);
}

function rowFor(f, v) {
  const t = T();
  if (!f) return "";
  const editable = ["collecting", "confirming", "ready", "failed"].includes(v.status);
  const error = f.error || v.field_errors?.[f.name]?.message;
  const form = editing === f.name
    ? `<form class="edit-form" data-editform="${esc(f.name)}">
         ${f.type === "text" || f.name === "address" || f.name === "grievance"
            ? `<textarea name="v" required maxlength="6000" aria-label="${esc(f.label)}">${esc(f.value || "")}</textarea>`
            : `<input name="v" required maxlength="6000" value="${esc(f.value || "")}" autocomplete="off"
                inputmode="${["age", "aadhaar", "mobile"].includes(f.type) ? "numeric" : "text"}" aria-label="${esc(f.label)}">`}
         <button type="submit">${esc(t.save)}</button>
         <button type="button" class="ghost" data-canceledit="1">${esc(t.dismiss)}</button>
       </form>` : "";
  const awaiting = f.name === v.awaiting ? " awaiting" : "";
  if (!f.filled) {
    const err = error ? `<span class="field-err" role="alert">${esc(error)}</span>` : "";
    // No tick on a row that is not filled. It was there and merely transparent,
    // which reads as "done" to anything that takes text rather than pixels.
    return `<div class="field-row${awaiting}" data-field="${esc(f.name)}">
      <span class="field-mark" aria-hidden="true"></span>
      <div class="field-main">
        <div class="field-label">${esc(f.label)}</div>
        <div class="field-value pending">${esc(t.pending)}${editable ? `<button class="mini" data-edit="${esc(f.name)}" type="button" aria-label="${esc(X().add)} ${esc(f.label)}">+</button>` : ""}${err}</div>${form}
      </div></div>`;
  }

  const sensitive = SENSITIVE.has(f.type);
  const show = revealed.has(f.name);
  const shown = show ? f.display : maskDisplay(f.type, f.display);
  // An icon, not the word. `.mini` is a fixed 28px box, and "Show" inside it
  // wrapped to "Sh / o / w" and spilled over the value beside it. The word
  // stays as the accessible name, where it is read rather than drawn.
  const eyeIcon = show
    ? `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M3 3l18 18M10.6 10.7a2 2 0 0 0 2.8 2.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M6.8 6.9C4.6 8.3 3 10.5 2.5 12c1 2.6 4.6 6 9.5 6 1.7 0 3.2-.4 4.5-1.05M9.9 5.2A9.9 9.9 0 0 1 12 5c4.9 0 8.5 3.4 9.5 6-.4 1.1-1.3 2.5-2.7 3.7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`
    : `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M2.5 12C3.5 9.4 7.1 6 12 6s8.5 3.4 9.5 6c-1 2.6-4.6 6-9.5 6s-8.5-3.4-9.5-6Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><circle cx="12" cy="12" r="2.6" stroke="currentColor" stroke-width="1.8"/></svg>`;
  const eye = sensitive
    ? `<button class="mini" data-reveal="${esc(f.name)}" type="button"
         aria-label="${esc(show ? t.hide : t.reveal)} ${esc(f.label)}" title="${esc(show ? t.hide : t.reveal)}">${eyeIcon}</button>`
    : "";

  // Editing uses the existing /field correction endpoint, so the value passes
  // the same validators and lands in the same audit trail as a spoken change.
  const pencil = editable
    ? `<button class="mini" data-edit="${esc(f.name)}" type="button"
         aria-label="${esc(t.edit)} ${esc(f.label)}" title="${esc(t.edit)}"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m14.5 5.5 4 4M4 20l4.5-.9L20 7.6a2 2 0 0 0 0-2.8l-.8-.8a2 2 0 0 0-2.8 0 L4.9 15.5 4 20Z" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg></button>`
    : "";

  return `<div class="field-row filled" data-field="${esc(f.name)}">
    <span class="field-mark" aria-hidden="true">✓</span>
    <div class="field-main">
      <div class="field-label">${esc(f.label)}</div>
      <div class="field-value">${esc(shown)}${eye}${pencil}</div>
      ${error ? `<span class="field-err" role="alert">${esc(error)}</span>` : ""}
      ${form}
    </div></div>`;
}

function wireFieldButtons(v) {
  document.querySelectorAll("[data-reveal]").forEach(b => {
    b.onclick = () => {
      if (busy || requestPending) return;
      const name = b.dataset.reveal;
      revealed.has(name) ? revealed.delete(name) : revealed.add(name);
      drawDetails(view);
    };
  });
  document.querySelectorAll("[data-edit]").forEach(b => {
    b.onclick = () => {
      if (busy || requestPending) return;
      editing = b.dataset.edit;
      drawDetails(view);
      document.querySelector(`[data-editform="${editing}"] [name="v"]`)?.focus();
    };
  });
  document.querySelectorAll("[data-canceledit]").forEach(b => {
    b.onclick = () => { editing = null; drawDetails(view); };
  });
  document.querySelectorAll("[data-editform]").forEach(form => {
    form.onsubmit = async (e) => {
      e.preventDefault();
      if (busy || requestPending || connectionLost) return;
      const name = form.dataset.editform;
      const value = form.querySelector('[name="v"]').value.trim();
      if (!value) return;
      const result = await mutate(`/api/sessions/${sid}/field`, { name, value });
      if (result && !result.field_errors?.[name]) { editing = null; drawDetails(result); }
      syncControls();
    };
  });
}

// The government knowledge base's findings, for the officer.
//
// Three rules hold this panel together, and all three exist so that nothing on
// this screen can be mistaken for something the citizen said or for settled
// legal advice:
//
//   * it is absent unless the service sent findings — no empty shell, no
//     spinner, no "searching…" that never resolves;
//   * every line carries the number of the document it came from, and every
//     document is listed underneath with the passage it was read from;
//   * the caveat is printed in the panel, not hidden in a tooltip.
//
// When retrieval found nothing, the service sends one sentence and that
// sentence is all that is shown.
function drawAnalysis(v) {
  const t = T();
  const a = v.analysis;
  const drawer = $("analysisDrawer");
  if (!a || !a.available) { drawer.hidden = true; $("analysis").innerHTML = ""; return; }

  drawer.hidden = false;
  const count = (a.sections || []).reduce((n, s) => n + s.items.length, 0);
  $("analysisCount").hidden = count === 0;
  $("analysisCount").textContent = String(count);

  // Conflicts the corpus could not settle. Shown ABOVE the findings and in
  // warning colour, because everything below them is qualified by them: two
  // versions of one rule were retrieved and nothing establishes which is in
  // force. An officer must see that before they read the answer, not after.
  const warnings = (a.warnings || []).length
    ? `<div class="an-warnings">${a.warnings.map(w =>
        `<p>${esc(w)}</p>`).join("")}</div>`
    : "";

  if (a.unverified) {
    $("analysis").innerHTML = warnings +
      `<p class="an-empty">${esc(a.message)}</p>`;
    return;
  }

  const authorityLabel = {
    official: t.analysisOfficial, departmental: t.analysisDepartmental,
    external: t.analysisExternal,
  };

  const sections = (a.sections || []).map(section => {
    const items = section.items.map(item => {
      const cites = (item.cites || [])
        .map(n => `<sup class="an-cite">${n}</sup>`).join("");
      return `<li>${esc(item.value)}${cites}</li>`;
    }).join("");
    return `<div class="an-section"><h4>${esc(section.label)}</h4><ul>${items}</ul></div>`;
  }).join("");

  const sources = (a.sources || []).map(s => {
    const where = [
      s.section, s.page_number ? `${t.analysisPage} ${s.page_number}` : "",
    ].filter(Boolean).join(" · ");
    const tag = authorityLabel[s.authority]
      ? `<span class="an-tag an-${esc(s.authority)}">${esc(authorityLabel[s.authority])}</span>`
      : "";
    return `<li><span class="an-n">${s.index}</span>
      <div><b>${esc(s.document_title)}</b>${tag}
      ${where ? `<span class="an-where">${esc(where)}</span>` : ""}
      ${s.excerpt ? `<q>${esc(s.excerpt)}</q>` : ""}
      ${s.source_url ? `<a href="${esc(s.source_url)}" target="_blank" rel="noopener noreferrer">${esc(s.source_url)}</a>` : ""}
      </div></li>`;
  }).join("");

  $("analysis").innerHTML = `${warnings}${sections}
    ${sources ? `<div class="an-sources"><h4>${esc(t.analysisSources)}</h4><ol>${sources}</ol></div>` : ""}
    <p class="an-note">${esc(a.note || "")}</p>`;
}

/* What is attached, shown small.
 *
 * This used to be a panel: the question, a suggestion list, a drop zone, the
 * files, the buttons. It was the largest thing on the screen at the moment the
 * citizen was answering a one-line question, and it read as a form inside a
 * form. The question is now said in the conversation like every other question,
 * attaching is the paperclip beside the microphone, and what is left here is a
 * strip of chips — plus, when a file was read, the card asking whether what was
 * read is right. That card stays: nothing from a document may be used until the
 * citizen has looked at it.
 */
function drawAttachments(v) {
  const t = T();
  const a = v.attachments;
  const strip = $("attachStrip");
  const items = a?.items || [];

  const editable = ["collecting", "attachments", "confirming"].includes(v.status);
  $("attachBtn").hidden = !editable;
  $("attachBtn").title = t.attachTitle;
  $("attachBtn").setAttribute("aria-label", t.attachTitle);
  $("attachBtn").disabled = !canSend() || items.length >= (a?.max ?? 10);

  if (!items.length) { strip.hidden = true; return; }
  strip.hidden = false;

  $("attachChips").innerHTML = items.map(item => `
    <li class="as-chip${item.needs_confirmation ? " is-pending" : ""}">
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M18.4 11.3 12 17.7a4.5 4.5 0 0 1-6.4-6.4l7.1-7a3 3 0 0 1 4.3 4.2l-7.1 7.1a1.5 1.5 0 0 1-2.1-2.1l6.3-6.4"
              stroke="currentColor" stroke-width="1.8" stroke-linecap="round"
              stroke-linejoin="round"/>
      </svg>
      <span title="${esc(item.filename)}">${esc(item.label)}</span>
      <button type="button" data-remove="${esc(item.attachment_id)}"
              aria-label="${esc(t.attachRemove)}">&times;</button>
    </li>`).join("");

  // Only the files that still need an answer get a card. Everything else is a
  // chip and nothing more.
  const pending = items.filter(i => i.needs_confirmation);
  $("attachConfirmList").innerHTML = pending.map(item => {
    const rows = (item.fields || []).map(f => `
      <div class="ap-field">
        <label for="af-${esc(item.attachment_id)}-${esc(f.name)}">${esc(t.attachField[f.name] || f.name)}</label>
        <input id="af-${esc(item.attachment_id)}-${esc(f.name)}" name="${esc(f.name)}" value="${esc(f.value)}">
        ${f.evidence ? `<q>${esc(f.evidence)}</q>` : ""}
      </div>`).join("");
    const nothingToCheck = !rows;
    return `<form class="ap-confirm" data-confirm="${esc(item.attachment_id)}">
      <p class="ap-confirm-head">${esc(nothingToCheck ? item.label : t.attachConfirmHead)}</p>
      ${item.low_confidence && !nothingToCheck ? `<p class="ap-warn">${esc(t.attachLowConfidence)}</p>` : ""}
      ${item.readable ? "" : `<p class="ap-warn">${esc(item.reason || t.attachUnreadable)}</p>`}
      ${rows}
      <div class="ap-confirm-actions">
        <button class="btn primary" type="submit">${esc(nothingToCheck ? t.attachAcknowledge : t.attachConfirmYes)}</button>
        ${nothingToCheck ? "" : `<button class="btn" type="button" data-reject="${esc(item.attachment_id)}">${esc(t.attachConfirmNo)}</button>`}
      </div>
    </form>`;
  }).join("");

  // Documents an OFFICIAL source says are required. Almost always empty, and
  // never confused with the suggestions, which are no longer shown at all.
  const required = a?.required || [];
  $("attachNote").hidden = required.length === 0;
  if (required.length) {
    $("attachNote").textContent =
      `${t.attachRequiredHead} ${required.map(r => r.value).join("; ")}`;
  }

  strip.querySelectorAll("[data-remove]").forEach(b => {
    b.onclick = () => attachmentAction(
      `/api/sessions/${sid}/attachments/${b.dataset.remove}`, { method: "DELETE" });
  });
  strip.querySelectorAll("[data-reject]").forEach(b => {
    b.onclick = () => attachmentAction(
      `/api/sessions/${sid}/attachments/${b.dataset.reject}/confirm`,
      { method: "POST", body: JSON.stringify({ confirmed: false }) });
  });
  strip.querySelectorAll("[data-confirm]").forEach(form => {
    form.onsubmit = (e) => {
      e.preventDefault();
      const values = {};
      form.querySelectorAll("input[name]").forEach(i => { values[i.name] = i.value.trim(); });
      attachmentAction(
        `/api/sessions/${sid}/attachments/${form.dataset.confirm}/confirm`,
        { method: "POST", body: JSON.stringify({ confirmed: true, values }) });
    };
  });
}

async function attachmentAction(url, options) {
  if (busy || requestPending) return;
  busy = true; syncControls();
  const result = await api(url, options);
  busy = false;
  if (result) render(result); else syncControls();
}

async function uploadAttachments(files) {
  const chosen = Array.from(files || []);
  if (!chosen.length || busy) return;

  // One at a time, in order, with a line each. A citizen attaching six
  // photographs of a broken road should see six lines fill in rather than one
  // frozen panel — and a file the service refuses should say which one.
  busy = true;
  syncControls();
  const progress = $("attachProgress");
  progress.hidden = false;
  progress.innerHTML = chosen.map((f, i) =>
    `<li id="up-${i}"><span>${esc(f.name)}</span><b>${esc(T().attachUploading)}</b></li>`
  ).join("");

  let latest = null;
  for (const [index, file] of chosen.entries()) {
    const row = $(`up-${index}`);
    const form = new FormData();
    form.append("file", file);
    // No Content-Type header: the browser sets the multipart boundary.
    const response = await fetch(`/api/sessions/${sid}/attachments`, {
      method: "POST", body: form,
    }).catch(() => null);

    if (response && response.ok) {
      latest = await response.json();
      if (row) { row.className = "ok"; row.querySelector("b").textContent = T().attachDone; }
    } else {
      const detail = response ? (await response.json().catch(() => ({}))).detail : "";
      if (row) {
        row.className = "bad";
        row.querySelector("b").textContent = detail || T().attachFailed;
      }
    }
  }

  busy = false;
  if (latest) render(latest); else syncControls();
  // Successes clear; anything refused stays on screen with its reason.
  setTimeout(() => {
    progress.querySelectorAll("li.ok").forEach(li => li.remove());
    if (!progress.children.length) progress.hidden = true;
  }, 2500);
}


function drawCorrections(v) {
  const list = v.corrections || [];
  $("correctionsCount").hidden = list.length === 0;
  $("correctionsCount").textContent = String(list.length);
  $("corrections").innerHTML = list.length
    ? list.map(c => {
      const spec = [...v.collected, ...v.outstanding].find(f => f.name === c.field);
      const safe = value => maskDisplay(spec?.type, String(value ?? ""));
      return `<div class="correction"><b>${esc(spec?.label || c.field)}</b>
        <span class="from">${esc(safe(c.from))}</span> →
        ${c.to === null ? "…" : esc(safe(c.to))}</div>`;
    }).join("")
    : `<span>${esc(T().none)}</span>`;
}

function drawOutcome(v) {
  const t = T();
  const doc = v.document || {};
  const hasLetter = v.status === "ready" && Boolean(v.document && v.letter_text);

  // The document column exists only when there is a document. A session that
  // was cancelled or failed has nothing to put in it, and an empty column two
  // thirds of the screen wide reads as something having gone missing — so
  // those outcomes are said in the conversation, where the rest of what
  // happened is already written down.
  $("docColumn").hidden = !hasLetter;
  $("docCard").hidden = !hasLetter;
  document.querySelector("main.workspace").classList.toggle("done", hasLetter);

  if (hasLetter) {
    const ok = !v.verification || v.verification.ok;
    $("outcome").hidden = false;
    $("outcome").className = "banner" + (ok ? "" : " bad");
    $("outcomeIcon").textContent = ok ? "✓" : "!";
    $("outcomeTitle").textContent = ok ? t.readyTitle : t.verifyBad;
    $("outcomeText").textContent = ok
      ? (v.verification ? t.verifyOk(v.verification.checked) + " · " + t.readyText : t.readyText)
      : t.readyText;
    $("outcomeRef").hidden = !doc.reference;
    $("refValue").textContent = doc.reference || "";
    if (!editingLetter) drawLetter(v.letter_text);
    paintEmblem(v.emblem);
  } else {
    $("outcome").hidden = true;
  }

  setLink($("pdf"), doc.pdf_url, t.pdf, t.noPdf);
  setLink($("docx"), doc.docx_url, t.docx);
  $("printBtn").disabled = !hasLetter;
  $("copyBtn").disabled = !hasLetter;
  $("reviseBtn").disabled = !hasLetter || busy;
  $("translateBtn").disabled = !hasLetter || busy || requestPending || editing;
  $("translateMenu").hidden = !hasLetter;
  if (!hasLetter || busy || editing) closeTranslate(); else drawTranslate();
  if (!hasLetter && editingLetter) stopEditing(true);
}


/* Where the emblem sits on the preview.
 *
 * The same placement the document uses, so a citizen who asks for it to be
 * moved sees it move here rather than having to download the PDF to find out
 * whether it worked. "First page only" still draws it, because the preview is
 * one continuous sheet and hiding it would misrepresent page one.
 */
function paintEmblem(placement) {
  const paper = $("letter");
  if (!paper) return;
  const align = (placement && placement.align) || "center";
  const pages = (placement && placement.pages) || "none";
  paper.classList.toggle("has-emblem", pages !== "none");
  paper.style.setProperty("--emblem-x",
    align === "left" ? "46px" : align === "right" ? "calc(100% - 46px)" : "50%");
}

function setLink(el, url, label, offLabel) {
  el.textContent = url ? label : (offLabel || label);
  if (url) { el.href = url; el.classList.remove("off"); el.removeAttribute("aria-disabled"); }
  else { el.removeAttribute("href"); el.classList.add("off"); el.setAttribute("aria-disabled", "true"); }
}

/** Every control's enabled state comes from the session, in one place. */
function syncControls() {
  const status = view?.status || "collecting";
  const stopped = ["cancelled", "failed"].includes(status);
  const generating = status === "generating" || busy || requestPending;
  const unavailable = generating || connectionLost || !sid;
  const retryable = status === "failed" && !view?.missing?.length && !Object.keys(view?.field_errors || {}).length;

  // One primary button, and the step decides what it says and does. At the
  // attachment step it is "Continue with These Details", so a citizen with
  // nothing to attach moves on with the button that is already in front of
  // them instead of hunting for one inside a panel.
  const attaching = status === "attachments";
  $("confirm").hidden = !attaching && status !== "confirming" && !retryable;
  $("confirm").textContent = attaching
    ? (view?.attachments?.continue_label || T().confirm)
    : retryable ? X().retryGeneration : T().confirm;
  $("confirm").disabled =
    (!attaching && status !== "confirming" && !retryable) || unavailable;
  // Same predicate the handler uses, so the button never offers something the
  // handler will silently refuse.
  $("send").disabled = !canSend() || !$("text").value.trim();
  $("text").disabled = !canSend();
  $("micInline").disabled = !voice.wants && (stopped || unavailable || editingLetter);
  $("mic").disabled = !voice.wants && (stopped || unavailable || editingLetter);
  $("restart").disabled = generating;
  $("cancel").disabled = stopped || unavailable;
  $("cancel").hidden = stopped || status === "ready";
  $("text").placeholder = status === "ready" ? (lang === "ta" ? "மனுவில் என்ன மாற்றம் வேண்டும்?" : "What would you like to change in this petition?")
    : view?.awaiting === "grievance" ? T().placeholderLong : T().placeholder;
  $("text").maxLength = 6000;
  $("text").inputMode = ["age", "aadhaar", "mobile"].includes(view?.awaiting) ? "numeric" : "text";
  $("text").setAttribute("aria-describedby", "inputHint inputCount");
  if ($("inputHint")) $("inputHint").textContent = status === "ready" ? (lang === "ta" ? "உதாரணம்: பொருளை மாற்று, ஒரு வாக்கியத்தைச் சேர், அல்லது முகவரியைத் திருத்து." : "Try “Change the subject”, “Add a sentence”, or “Change my address”.")
    : ["aadhaar", "mobile"].includes(view?.awaiting) ? X().privateHint
    : view?.awaiting === "grievance" ? X().longHint : X().inputHint;
  if ($("inputCount")) $("inputCount").textContent = `${$("text").value.length.toLocaleString(lang)} / 6,000`;
  $("new").disabled = generating;
  $("lang").disabled = generating;
  $("restart").disabled = unavailable && Boolean(sid);
  document.querySelectorAll("[data-edit], [data-reveal], [data-editform] button, [data-editform] input, [data-editform] textarea")
    .forEach(el => { el.disabled = unavailable; });
  // Edit mode swaps the toolbar: the Edit button becomes Save and Cancel.
  $("reviseBtn").hidden = editingLetter;
  $("editSave").hidden = !editingLetter;
  $("editCancel").hidden = !editingLetter;
  $("editSave").disabled = busy || requestPending || editConflict || connectionLost;
  $("editCancel").disabled = busy || requestPending;
  $("reviseBtn").disabled = status !== "ready" || unavailable;
  for (const id of ["pdf", "docx", "printBtn", "copyBtn"]) $(id).hidden = editingLetter;
  if (typeof syncNavigation === "function") syncNavigation();

  $("chatCard").setAttribute("aria-busy", String(generating));
  if (requestPending && $("saveStatus")) $("saveStatus").textContent = X().saving;
}

/* --------------------------------------------------------------- lifecycle */

async function start() {
  if (requestPending) return;
  requestPending = true;
  busy = true;
  syncControls();
  const result = await api("/api/sessions", {
    method: "POST", body: JSON.stringify({ language: $("lang").value, text: "" }),
  });
  requestPending = false;
  busy = false;
  if (!result) {
    if (view) { lang = view.language; lastLang = lang; labels(); }
    syncControls(); return;
  }
  resetInterface();
  connectionLost = false;
  connectionNotice();
  render(result);
  if (typeof showGenerator === "function") showGenerator(sid);
  $("text").focus();
}

function resetInterface() {
  if (editingLetter) stopEditing(false);
  clearTimeout(generationPoll);
  $("log").innerHTML = "";
  seen = 0; busy = false; editing = null;
  revealed = new Set(); lastValues = {};
  view = null;
  sid = null;
  $("text").value = "";
  autoGrow();
  closedNotice = false;
  $("docColumn").hidden = true;
  $("docCard").hidden = true;
  $("outcome").hidden = true;
  document.querySelector("main.workspace").classList.remove("done");
  document.querySelector("main.workspace").classList.remove("details-open");
  $("detailsToggle").setAttribute("aria-expanded", "false");
  stopGenerating(false);
  stopVoice({ tell: false });
  $("voiceError").hidden = true;
  labels();
}

async function recover() {
  if (requestPending) return;
  const saved = savedSession();
  if (!sid && !saved) { connectionLost = false; await start(); return; }
  requestPending = true;
  syncControls();
  const result = await api(`/api/sessions/${sid || saved.id}`, { timeout: 15000, quiet: true });
  requestPending = false;
  if (result) {
    connectionLost = false;
    connectionNotice();
    render(result);
  } else if ([404, 410].includes(lastApiStatus)) {
    forgetSession();
    connectionLost = false;
    resetInterface();
    connectionNotice(X().expired);
    syncControls();
  } else {
    connectionLost = true;
    connectionNotice(X().offline);
    syncControls();
  }
}

/* Whether a typed turn can be sent right now.
 *
 * ONE predicate, used by both the submit handler and `syncControls`. They used
 * to decide separately — the handler against a hard list of statuses, the
 * button against a list of *stopped* ones — and when the attachment step was
 * added it reached the button's list but not the handler's. The Send button
 * looked enabled, the citizen typed "yes i want to add attachments", pressed
 * it, and the handler returned without sending anything. Nothing appeared, no
 * error, no bubble. Derive both from here and they cannot drift again. */
// `ready` is in the list because a finished petition is still a
// conversation: "make the closing request firmer" typed into the chat is
// how a citizen asks for a rewording. Editing the words THEMSELVES is the
// Edit button, which is a different thing and touches no model.
const SENDABLE_STATUSES = ["collecting", "attachments", "confirming", "ready"];

function canSend() {
  return Boolean(
    sid && !busy && !requestPending && !connectionLost && !editingLetter
    && SENDABLE_STATUSES.includes(view?.status ?? "collecting"),
  );
}

$("ask").onsubmit = async (e) => {
  e.preventDefault();
  const text = $("text").value.trim();
  if (!text || !canSend()) return;
  stopPlayback();
  send({ type: "voice.interrupt" });
  workingBubble(X().saving);
  // Asking for a change to a petition that already exists is work on the
  // document, so it is shown where work on the document is always shown.
  const changing = view?.status === "ready";
  const confirming = ["confirming", "attachments"].includes(view?.status);
  if (changing) beginDocumentWork("revise");
  // Started, not awaited. `mutate` marks the request in flight synchronously,
  // and that is the flag the watcher runs on — awaiting it first would mean
  // the turn had already finished before anything looked at it.
  const pending = mutate(`/api/sessions/${sid}/message`, { text });
  if (confirming) void watchForGeneration(sid);
  const result = await pending;
  if (changing || confirming) stopGenerating(Boolean(result));
  if (result) { $("text").value = ""; autoGrow(); }
  else if (connectionLost) bubble("system", X().retryDraft, true);
  syncControls();
  $("text").focus();
};

/* Enter sends, Shift+Enter starts a new line — a grievance is often several
   sentences and a citizen should not have to fight the box to write them. */
$("text").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) { e.preventDefault(); $("ask").requestSubmit(); }
});
$("text").addEventListener("input", () => { autoGrow(); syncControls(); });
function autoGrow() {
  const el = $("text");
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 148) + "px";
}

$("confirm").onclick = async () => {
  if (busy || requestPending || connectionLost) return;

  // At the attachment step the same button means "continue with these
  // details". A citizen with nothing to attach presses the button already in
  // front of them; the read-back follows, as it always has.
  if (view?.status === "attachments") {
    await attachmentAction(`/api/sessions/${sid}/attachments/done`, { method: "POST" });
    return;
  }

  if (!["confirming", "failed"].includes(view?.status)) return;
  stopVoice();
  drawLifecycle({ ...view, status: "generating" });
  drawStepper({ ...view, status: "generating" });
  beginDocumentWork("create");
  const result = await mutate(`/api/sessions/${sid}/confirm`);
  stopGenerating(Boolean(result && result.letter_text));
  busy = false;
  if (result) render(result);
  else { drawLifecycle(view); drawStepper(view); syncControls(); }
};

$("new").onclick = () => {
  if (busy || requestPending) return;
  if (typeof guardUnsaved === "function" && !guardUnsaved(() => $("new").click())) return;
  if (!view || ["ready", "cancelled"].includes(view.status) || (view.progress?.answered ?? 0) === 0) {
    start();
    return;
  }
  confirmThen(T().restartTitle, T().restartText, T().restartKeep, T().restartGo, start);
};

$("restart").onclick = () => {
  if (busy || requestPending) return;
  if (!view || (view.progress?.answered ?? 0) === 0) return start();
  confirmThen(T().restartTitle, T().restartText, T().restartKeep, T().restartGo, async () => {
    stopVoice();
    const result = await mutate(`/api/sessions/${sid}/restart`);
    if (result) { resetInterface(); render(result); $("text").focus(); }
  });
};

$("cancel").onclick = () => {
  if (busy || requestPending) return;
  confirmThen(T().cancelTitle, T().cancelText, T().cancelKeep, T().cancelGo, async () => {
    stopVoice();
    const result = await mutate(`/api/sessions/${sid}/cancel`);
    if (result) { $("text").value = ""; autoGrow(); }
  });
};

/* Changing language starts a fresh session in that language — the prompts, the
   record labels and the petition itself are all language-bound on the server,
   so a half-translated session is not a state worth having. The citizen is
   asked first when there is anything to lose. */
let lastLang = "en";
$("lang").onchange = () => {
  const next = $("lang").value;
  if (typeof currentRoute !== "undefined" && currentRoute !== "generator") {
    lang = next; lastLang = next; labels();
    if (currentRoute === "petitions") loadPetitions();
    return;
  }
  if (view && (view.progress?.answered ?? 0) > 0 && !["ready", "cancelled"].includes(view.status)) {
    confirmThen(T().restartTitle, T().restartText, T().restartKeep, T().restartGo,
      () => { lang = next; lastLang = next; start(); },
      () => { $("lang").value = lastLang; });
    return;
  }
  lang = next; lastLang = next;
  start();
};

/* ----------------------------------------------------------------- dialogs */

function confirmThen(title, text, keepLabel, goLabel, onGo, onKeep) {
  if (document.querySelector(".modal-backdrop")) return;
  const priorFocus = document.activeElement;
  const back = document.createElement("div");
  back.className = "modal-backdrop";
  back.innerHTML =
    `<div class="modal" role="dialog" aria-modal="true" aria-labelledby="mt">
       <h3 id="mt">${esc(title)}</h3>
       <p>${esc(text)}</p>
       <div class="modal-actions">
         <button class="btn" data-keep>${esc(keepLabel)}</button>
         <button class="btn primary" data-go>${esc(goLabel)}</button>
       </div>
     </div>`;
  document.body.appendChild(back);
  const close = () => { back.remove(); document.removeEventListener("keydown", onKey); priorFocus?.focus(); };
  const onKey = (e) => {
    if (e.key === "Escape") { close(); onKeep?.(); }
    if (e.key === "Tab") {
      const buttons = [...back.querySelectorAll("button")];
      const first = buttons[0], last = buttons[buttons.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  };
  back.querySelector("[data-keep]").onclick = () => { close(); onKeep?.(); };
  back.querySelector("[data-go]").onclick = () => { close(); onGo(); };
  back.onclick = (e) => { if (e.target === back) { close(); onKeep?.(); } };
  document.addEventListener("keydown", onKey);
  back.querySelector("[data-keep]").focus();
}

/* -------------------------------------------------------------- document */

$("printBtn").onclick = async () => {
  if (!view?.document || view.status !== "ready") return;
  const w = window.open("", "_blank");
  if (!w) { bubble("system", X().popupError, true); return; }
  w.opener = null;
  w.document.write(
    `<!doctype html><html lang="${lang}"><head><meta charset="utf-8">
     <title>${esc(view.document?.reference || T().title)}</title>
     <style>
       @font-face { font-family:"Noto Sans Tamil";
         src:url("${location.origin}/assets/fonts/NotoSansTamil-Regular.ttf") format("truetype"); }
       body { font: 12pt/1.8 "Noto Sans Tamil","Segoe UI",serif; margin: 22mm 20mm;
              white-space: pre-wrap; }
     </style></head><body></body></html>`);
  w.document.body.textContent = view.letter_text;
  w.document.close();
  w.focus();
  await w.document.fonts.ready;
  w.print();
};

$("copyBtn").onclick = async () => {
  if (!view?.document || view.status !== "ready") return;
  try {
    await navigator.clipboard.writeText(view.letter_text);
    const was = $("copyBtn").textContent;
    $("copyBtn").textContent = T().copied;
    setTimeout(() => { $("copyBtn").textContent = was; }, 1600);
  } catch { bubble("system", X().copiedError, true); }
};

/* ==========================================================================
   Live voice.

   One socket carries the whole conversation. The citizen presses Start Voice
   once and then talks; the server decides when they have finished and hands
   the transcript to the same workflow a typed answer goes to. Nothing about
   the petition is decided here — this file captures audio, plays audio, and
   draws what is happening.

   The state is ONE value, mirrored from the server. It was tempting to keep
   `isListening`, `isSpeaking` and `isProcessing` alongside each other, and
   that is exactly how a page ends up showing a microphone that is listening
   to a citizen the server stopped hearing two seconds ago.
   ========================================================================== */

const VOICE = {
  IDLE: "idle", CONNECTING: "connecting", LISTENING: "listening",
  USER_SPEAKING: "user_speaking", TRANSCRIBING: "transcribing",
  PROCESSING: "processing", ASSISTANT_SPEAKING: "assistant_speaking",
  RECONNECTING: "reconnecting", ERROR: "error", ENDED: "ended",
};

const voice = {
  state: VOICE.IDLE,
  socket: null,
  ctx: null,            // capture AudioContext
  stream: null,
  node: null,
  analyser: null,
  playCtx: null,        // playback AudioContext, separate so stopping is total
  playing: [],          // sources currently scheduled
  queue: Promise.resolve(),
  playToken: 0,         // bumped to invalidate audio decoded before an interrupt
  muted: false,
  wants: false,         // the citizen asked for voice and has not ended it
  attempts: 0,
  raf: null,
  partial: "",
  rms: 0,
  playRms: 0,
  playAnalyser: null,
  playBins: null,
  meterRaf: null,
  // Where speech starts being counted, in the same units the meter shows.
  // A starting estimate; the service does the authoritative detection.
  speechLine: 0.045,
  diagnostics: false,
  thresholds: null,
  lastDiscard: null,
};

function voiceState(next, extra) {
  if (voice.state === next && !extra) return;
  voice.state = next;
  paintVoice(extra || {});
}

function paintVoice(extra) {
  const t = T();
  const s = voice.state;
  const live = ![VOICE.IDLE, VOICE.ENDED, VOICE.ERROR].includes(s);

  // The panel is up whenever the citizen has asked for voice and has not
  // ended it. Tying it to the phase instead made it flicker away every time
  // the state passed through idle between turns.
  $("voiceBar").hidden = !(voice.wants || s === VOICE.CONNECTING);
  $("voiceStatus").textContent = t.voiceState[s] || "";

  if (extra.transcript !== undefined) {
    $("voiceTranscript").textContent = extra.transcript;
    $("voiceTranscript").classList.toggle("live", Boolean(extra.live));
  }

  // The header button says the same thing, so the state is legible with the
  // panel scrolled out of view.
  const btn = $("mic");
  btn.className = "hbtn" + (s === VOICE.IDLE || s === VOICE.ENDED ? "" : " voice-" + s);
  $("micText").textContent = live || s === VOICE.CONNECTING ? t.voiceStop : t.voiceStart;
  btn.setAttribute("aria-label", $("micText").textContent);
  $("micInline").classList.toggle("listening", s === VOICE.LISTENING || s === VOICE.USER_SPEAKING);

  const mute = $("voiceMute");
  mute.classList.toggle("muted", voice.muted);
  mute.classList.toggle("live", !voice.muted && (s === VOICE.LISTENING || s === VOICE.USER_SPEAKING));
  mute.setAttribute("aria-pressed", String(voice.muted));
  mute.setAttribute("aria-label", voice.muted ? t.unmute : t.mute);
  mute.title = voice.muted ? t.unmute : t.mute;
  $("voiceEnd").textContent = t.voiceEnd;
}

/* ----------------------------------------------------------------- errors */

function voiceFail(message, { recoverable = true } = {}) {
  $("voiceErrorText").textContent = message;
  $("voiceRetry").hidden = !recoverable;
  $("voiceRetry").textContent = T().voiceRetry;
  $("voiceDismiss").textContent = T().voiceContinueText;
  $("voiceError").hidden = false;
  voiceState(VOICE.ERROR);
}

$("voiceRetry").onclick = () => { $("voiceError").hidden = true; startVoice(); };
$("voiceDismiss").onclick = () => {
  $("voiceError").hidden = true;
  stopVoice({ tell: false });
  $("text").focus();
};

/* -------------------------------------------------------------- playback
   A queue of clips on their own AudioContext. Barge-in has to be total and
   instant: stopping every scheduled source AND invalidating anything still
   being decoded, because a clip that finishes decoding after the interrupt
   would otherwise start playing over the citizen. */

async function playClip(bytes, token) {
  if (token !== voice.playToken) return;
  if (!voice.playCtx) {
    voice.playCtx = new AudioContext();
    // Tapped on the way to the speaker, so the ribbon moves with the words the
    // citizen is actually hearing rather than to a timer of our own.
    voice.playAnalyser = voice.playCtx.createAnalyser();
    voice.playAnalyser.fftSize = 512;
    voice.playBins = new Uint8Array(voice.playAnalyser.frequencyBinCount);
    voice.playAnalyser.connect(voice.playCtx.destination);
  }
  if (voice.playCtx.state === "suspended") await voice.playCtx.resume();
  let buffer;
  try { buffer = await voice.playCtx.decodeAudioData(bytes); }
  catch { return; }
  if (token !== voice.playToken) return;          // interrupted while decoding
  await new Promise((done) => {
    const src = voice.playCtx.createBufferSource();
    src.buffer = buffer;
    src.connect(voice.playAnalyser);
    src.onended = () => {
      voice.playing = voice.playing.filter(s => s !== src);
      done();
    };
    voice.playing.push(src);
    src.start();
  });
}

function enqueueClip(bytes) {
  const token = voice.playToken;
  voice.queue = voice.queue.then(() => playClip(bytes, token)).catch(() => {});
}

function stopPlayback() {
  voice.playToken++;                    // anything mid-decode is now void
  for (const src of voice.playing) { try { src.stop(); } catch {} }
  voice.playing = [];
  voice.queue = Promise.resolve();
}

/* ------------------------------------------------------------------ capture */

const TARGET_RATE = 16000;   // what the service expects on the wire

/** Rate-convert one buffer, averaging rather than dropping samples.
 *
 *  Averaging across each source window is a crude low-pass, which is what
 *  keeps 48 kHz speech from aliasing into a metallic 16 kHz that the speech
 *  service mis-hears. Plain decimation is one line shorter and audibly worse.
 */
function resampleTo(input, inRate, outRate) {
  if (!inRate || inRate === outRate) return input;
  const ratio = inRate / outRate;
  const out = new Float32Array(Math.floor(input.length / ratio));
  for (let i = 0; i < out.length; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.min(Math.floor((i + 1) * ratio), input.length);
    let sum = 0, n = 0;
    for (let j = start; j < end; j++) { sum += input[j]; n++; }
    out[i] = n ? sum / n : input[start] || 0;
  }
  return out;
}

const BARGE_RMS = 0.055;    // local speech onset, for instant interruption
let bargeFrames = 0;

/* ---------------------------------------------------------- the voice field
   Five translucent bands, drawn every frame, their height driven by whatever
   audio is live at that moment: the microphone while the citizen speaks, the
   reply while the assistant speaks, and a slow idle motion in between.

   Additive blending is what makes the overlaps glow rather than muddy —
   `lighter` adds the colours where the bands cross, which is why cyan over
   pink gives white in the middle and why the whole thing needs a dark ground.

   No library and no image. A recorded animation would move while the service
   was doing nothing, which on a voice interface is a lie about whether it is
   listening. */

const WAVE_BANDS = [
  // `centre` shifts where each lobe is fattest. Without it every band peaks in
  // the middle, they all add up in the same place, and the additive blend
  // turns the whole centre white — which is what the first attempt looked
  // like. Spreading the peaks is what lets the cyan, the pink and the purple
  // each be seen while still overlapping into lighter colours where they
  // cross.
  { colour: "56, 232, 225", freq: 1.05, speed: 0.95, phase: 0.0, weight: 1.00, centre: 0.50, alpha: 0.50 },
  { colour: "60, 150, 255", freq: 1.45, speed: -0.72, phase: 1.1, weight: 0.90, centre: 0.38, alpha: 0.46 },
  { colour: "150, 105, 255", freq: 1.95, speed: 1.22, phase: 2.3, weight: 0.78, centre: 0.62, alpha: 0.44 },
  { colour: "255, 80, 160", freq: 2.55, speed: -1.05, phase: 3.7, weight: 0.64, centre: 0.30, alpha: 0.42 },
  { colour: "120, 255, 210", freq: 3.10, speed: 1.55, phase: 5.2, weight: 0.52, centre: 0.70, alpha: 0.40 },
];
const wave = {
  canvas: null, ctx: null, raf: null,
  t: 0, level: 0, target: 0, dpr: 1,
};

/** Tapered to a point at both ends, fattest at `centre`. */
function waveEnvelope(x, centre) {
  // Distance from this band's own peak, normalised so the taper still reaches
  // zero at both ends of the ribbon whichever side the peak sits on.
  const span = centre <= 0.5 ? Math.max(centre, 1 - centre) : Math.max(centre, 1 - centre);
  const d = Math.min(1, Math.abs(x - centre) / span);
  return Math.pow(Math.cos(d * Math.PI / 2), 2.4);
}

function resizeWave() {
  const canvas = wave.canvas;
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  if (!rect.width) return;
  wave.dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(rect.width * wave.dpr);
  canvas.height = Math.round(rect.height * wave.dpr);
}

/** How tall the bands should be right now, and how fast they move. */
function waveDrive() {
  const s = voice.state;
  if (s === VOICE.USER_SPEAKING) {
    // The citizen's own voice, straight off the microphone analyser.
    return { amp: Math.min(1, voice.rms / 0.16), speed: 1.6 };
  }
  if (s === VOICE.ASSISTANT_SPEAKING) {
    // The reply, off the playback analyser, so the ribbon moves with the
    // words the citizen is hearing rather than to a timer.
    return { amp: Math.min(1, voice.playRms / 0.30), speed: 1.25 };
  }
  if (s === VOICE.PROCESSING || s === VOICE.TRANSCRIBING) {
    // Nothing is being heard. A steady, unhurried pulse says the service is
    // working without pretending to hear anything.
    return { amp: 0.34 + 0.12 * Math.sin(wave.t * 2.2), speed: 0.85 };
  }
  if (s === VOICE.ERROR) return { amp: 0.06, speed: 0.12 };
  // Listening, connecting, idle: a small, patient motion. Never flat — a flat
  // line reads as a dead microphone.
  return { amp: 0.16 + 0.05 * Math.sin(wave.t * 1.1), speed: 0.55 };
}

function drawWave() {
  wave.raf = requestAnimationFrame(drawWave);
  const ctx = wave.ctx, canvas = wave.canvas;
  if (!ctx || !canvas || !canvas.width) return;

  const drive = waveDrive();
  // Ease towards the target so a sudden syllable swells the ribbon instead of
  // snapping it, and a pause lets it fall away rather than cutting out.
  wave.target = drive.amp;
  wave.level += (wave.target - wave.level) * (wave.target > wave.level ? 0.35 : 0.08);
  wave.t += 0.016 * drive.speed;

  const w = canvas.width, h = canvas.height, mid = h / 2;
  ctx.clearRect(0, 0, w, h);
  ctx.globalCompositeOperation = "lighter";

  const steps = 96;
  const reach = h * 0.42 * (0.22 + 0.78 * wave.level);

  for (const band of WAVE_BANDS) {
    ctx.beginPath();
    for (let i = 0; i <= steps; i++) {
      const x = i / steps;
      const y = mid - Math.sin(x * Math.PI * 2 * band.freq + wave.t * band.speed + band.phase)
                      * reach * band.weight * waveEnvelope(x, band.centre);
      i ? ctx.lineTo(x * w, y) : ctx.moveTo(x * w, y);
    }
    // Back along the mirrored curve, so each band is a closed lens rather than
    // a line — which is what gives the overlaps their colour.
    for (let i = steps; i >= 0; i--) {
      const x = i / steps;
      const y = mid + Math.sin(x * Math.PI * 2 * band.freq + wave.t * band.speed + band.phase)
                      * reach * band.weight * waveEnvelope(x, band.centre);
      ctx.lineTo(x * w, y);
    }
    ctx.closePath();
    const fill = ctx.createLinearGradient(0, 0, w, 0);
    fill.addColorStop(0.00, `rgba(${band.colour}, 0)`);
    fill.addColorStop(Math.max(0.05, band.centre - 0.30), `rgba(${band.colour}, ${band.alpha * 0.6})`);
    fill.addColorStop(band.centre, `rgba(${band.colour}, ${band.alpha})`);
    fill.addColorStop(Math.min(0.95, band.centre + 0.30), `rgba(${band.colour}, ${band.alpha * 0.6})`);
    fill.addColorStop(1.00, `rgba(${band.colour}, 0)`);
    ctx.fillStyle = fill;
    ctx.fill();
  }

  // A bright hairline through the middle, which is what stops the ribbon
  // looking like a smudge when everything is quiet.
  ctx.globalCompositeOperation = "source-over";
  const line = ctx.createLinearGradient(0, 0, w, 0);
  line.addColorStop(0, "rgba(180, 225, 255, 0)");
  line.addColorStop(0.5, `rgba(210, 240, 255, ${0.35 + 0.4 * wave.level})`);
  line.addColorStop(1, "rgba(180, 225, 255, 0)");
  ctx.strokeStyle = line;
  ctx.lineWidth = Math.max(1, wave.dpr);
  ctx.beginPath();
  ctx.moveTo(0, mid);
  ctx.lineTo(w, mid);
  ctx.stroke();
}

function startWave() {
  wave.canvas = $("voiceWave");
  wave.ctx = wave.canvas.getContext("2d");
  resizeWave();
  if (!wave.raf) drawWave();
}

function stopWave() {
  if (wave.raf) cancelAnimationFrame(wave.raf);
  wave.raf = null;
  wave.level = 0;
  if (wave.ctx && wave.canvas) wave.ctx.clearRect(0, 0, wave.canvas.width, wave.canvas.height);
}

window.addEventListener("resize", resizeWave);


/** Read the microphone level every frame; the field and the diagnostics use it. */
function startMeter() {
  const bins = new Uint8Array(voice.analyser.frequencyBinCount);
  const read = () => {
    voice.meterRaf = requestAnimationFrame(read);
    voice.analyser.getByteTimeDomainData(bins);
    let sum = 0;
    for (let i = 0; i < bins.length; i++) {
      const v = bins[i] / 128 - 1;
      sum += v * v;
    }
    voice.rms = Math.sqrt(sum / bins.length);

    if (voice.playAnalyser) {
      voice.playAnalyser.getByteTimeDomainData(voice.playBins);
      let p = 0;
      for (let i = 0; i < voice.playBins.length; i++) {
        const v = voice.playBins[i] / 128 - 1;
        p += v * v;
      }
      voice.playRms = Math.sqrt(p / voice.playBins.length);
    } else {
      voice.playRms = 0;
    }

    const meter = $("voiceMeter");
    if (!meter.hidden) {
      const pct = Math.min(100, Math.round((voice.rms / 0.25) * 100));
      meter.firstElementChild.style.width = pct + "%";
      meter.classList.toggle("over", voice.rms > voice.speechLine);
      meter.lastElementChild.style.left =
        Math.min(99, (voice.speechLine / 0.25) * 100) + "%";
    }
    if (voice.diagnostics) paintDiagnostics(voice.rms);
  };
  read();
  startWave();
}



/* Developer diagnostics. Enabled by the service, never by the page, and it
   carries measurements only — no transcript, no field value, nothing that
   could put a citizen's Aadhaar into a screenshot of a debug panel. */
function paintDiagnostics(rms) {
  const now = performance.now();
  if (now - (voice.diagPaintedAt || 0) < 120) return;   // 8 Hz is plenty
  voice.diagPaintedAt = now;
  const t = voice.thresholds || {};
  const d = voice.lastDiscard;
  $("voiceDiag").innerHTML =
    `<span>mic rms <b>${rms.toFixed(3)}</b></span>` +
    `<span>speech at <b>${voice.speechLine.toFixed(3)}</b></span>` +
    `<span>state <b>${voice.state}</b></span>` +
    `<span>lang <b>${lang === "ta" ? "ta-IN" : "en-IN"}</b></span>` +
    `<span>onset <b>${t.onset_ms ?? "-"}ms</b></span>` +
    `<span>silence <b>${t.silence_ms ?? "-"}ms</b></span>` +
    (d ? `<span class="bad">discarded <b>${esc(d.reason)}</b></span>` +
         `<span class="bad">voiced <b>${d.voiced_ms}ms</b></span>` +
         `<span class="bad">mod <b>${d.modulation}</b></span>` +
         `<span class="bad">snr <b>${d.peak_snr}</b></span>`
       : "");
}

/** Stop reading the microphone and drawing the field, and clear both. */
function stopMeter() {
  if (voice.meterRaf) cancelAnimationFrame(voice.meterRaf);
  voice.meterRaf = null;
  voice.rms = 0;
  voice.playRms = 0;
  stopWave();
  const meter = $("voiceMeter");
  if (meter && meter.firstElementChild) {
    meter.firstElementChild.style.width = "0%";
    meter.classList.remove("over");
  }
}

/** Microphone problems, said in words a citizen can act on. */
function micMessage(err) {
  const t = T();
  const name = (err && err.name) || "";
  if (name === "NotAllowedError" || name === "SecurityError") return t.micDenied;
  if (name === "NotFoundError" || name === "OverconstrainedError") return t.micMissing;
  if (name === "NotReadableError") return t.micBusy;
  if (!navigator.mediaDevices || !window.AudioContext) return t.micUnsupported;
  return t.micDenied;
}

async function openMicrophone() {
  voice.stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true,
             autoGainControl: true },
  });
  voice.ctx = new AudioContext({ sampleRate: 16000 });
  if (voice.ctx.state === "suspended") await voice.ctx.resume();

  const source = voice.ctx.createMediaStreamSource(voice.stream);
  voice.analyser = voice.ctx.createAnalyser();
  voice.analyser.fftSize = 512;
  source.connect(voice.analyser);

  // What the browser ACTUALLY gave us, which is often not what was asked for.
  // `new AudioContext({sampleRate: 16000})` is a hint, and plenty of devices
  // ignore it and hand back 48 kHz. Sending those samples as though they were
  // 16 kHz stretches the audio to three times its length, and the speech
  // service faithfully transcribes the stretch: "My name is Harish" came back
  // as "My My My Me Me Me Mess Mess Hara Hara". Resample here rather than
  // trusting the hint.
  voice.inputRate = voice.ctx.sampleRate;

  voice.node = voice.ctx.createScriptProcessor(2048, 1, 1);
  voice.node.onaudioprocess = (e) => {
    if (!voice.socket || voice.socket.readyState !== 1) return;
    const input = e.inputBuffer.getChannelData(0);

    // Local barge-in. The server decides turns, but it cannot stop audio that
    // is already in this browser, and a round trip is long enough to be heard
    // as the assistant talking over the citizen.
    if (voice.state === VOICE.ASSISTANT_SPEAKING) {
      let sum = 0;
      for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
      if (Math.sqrt(sum / input.length) > BARGE_RMS) {
        if (++bargeFrames >= 2) {
          bargeFrames = 0;
          stopPlayback();
          send({ type: "voice.interrupt" });
        }
      } else { bargeFrames = 0; }
    }

    if (voice.muted) return;
    const frames = resampleTo(input, voice.inputRate, TARGET_RATE);
    const pcm = new Int16Array(frames.length);
    for (let i = 0; i < frames.length; i++)
      pcm[i] = Math.max(-1, Math.min(1, frames[i])) * 0x7fff;
    voice.socket.send(pcm.buffer);
  };
  // Through a silent gain node: a ScriptProcessor needs a path to the
  // destination to run at all, and the obvious wiring plays the citizen's own
  // microphone back at them.
  const mute = voice.ctx.createGain();
  mute.gain.value = 0;
  source.connect(voice.node);
  voice.node.connect(mute);
  mute.connect(voice.ctx.destination);
  startMeter();
}

function releaseAudio() {
  stopMeter();
  if (voice.node) { try { voice.node.disconnect(); } catch {} voice.node = null; }
  if (voice.ctx) { try { voice.ctx.close(); } catch {} voice.ctx = null; }
  if (voice.stream) { voice.stream.getTracks().forEach(t => t.stop()); voice.stream = null; }
  voice.analyser = null;
}

/* ------------------------------------------------------------------ socket */

function send(payload) {
  if (voice.socket && voice.socket.readyState === 1) {
    voice.socket.send(JSON.stringify(payload));
  }
}

function openSocket() {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const sock = new WebSocket(`${scheme}://${location.host}/ws/voice/${sid}`);
  sock.binaryType = "arraybuffer";
  let expectAudio = false;

  sock.onmessage = (ev) => {
    if (voice.socket !== sock || !voice.wants) return;
    if (typeof ev.data !== "string") {
      if (expectAudio) { expectAudio = false; enqueueClip(ev.data); }
      return;
    }
    const m = JSON.parse(ev.data);
    switch (m.type) {
      case "voice.ready":
        voice.diagnostics = Boolean(m.diagnostics);
        voice.thresholds = m.thresholds || null;
        $("voiceDiag").hidden = !voice.diagnostics;
        $("voiceMeter").hidden = !voice.diagnostics;
        if (!m.enabled) {
          voiceFail(T().voiceUnavailable, { recoverable: false });
          stopVoice({ tell: false });
          return;
        }
        voice.attempts = 0;
        send({ type: "voice.start" });
        break;

      case "voice.state":
        if (m.state === VOICE.USER_SPEAKING) voiceState(m.state, { transcript: "", live: true });
        else if (m.state === VOICE.ASSISTANT_SPEAKING)
          voiceState(m.state, { transcript: m.text || "", live: false });
        else voiceState(m.state);
        break;

      case "stt.final":
        // Only a settled transcript becomes a conversation turn, and the
        // server's `state` message is what actually writes it — this is the
        // panel showing what was heard, not a second copy of the message.
        voiceState(VOICE.PROCESSING, { transcript: m.text, live: false });
        // Same as typing it: the transcript is settled and the server is now
        // running the turn. The `state` message that follows closes the panel.
        if (view?.status === "ready") beginDocumentWork("revise");
        break;

      case "state":
        render(m.state);
        break;

      case "tts.start":
        voiceState(VOICE.ASSISTANT_SPEAKING, { transcript: m.text || "", live: false });
        break;

      case "tts.audio":
        expectAudio = true;
        break;

      case "tts.end":
        break;

      case "voice.interrupted":
        stopPlayback();
        break;

      case "voice.discarded":
        // Something was heard and judged not to be an answer. The citizen is
        // told nothing — the assistant simply keeps listening, which is what
        // it looks like when a fan runs past a microphone.
        voice.lastDiscard = m;
        break;

      case "voice.ended":
        stopVoice({ tell: false });
        if (m.reason === "idle") bubble("system", T().voiceIdleEnded);
        break;

      case "error":
        stopGenerating(false);
        if (m.recoverable === false) {
          voiceFail(m.message || T().voiceUnavailable, { recoverable: false });
          stopVoice({ tell: false });
        } else {
          bubble("system", m.message, true);
        }
        break;
    }
  };

  sock.onclose = () => {
    if (voice.socket !== sock) return;
    stopPlayback();
    if (!voice.wants) { voiceState(VOICE.IDLE); return; }
    // Bounded reconnect against the SAME petition session. The petition is on
    // the server and untouched by any of this; only the audio path is lost.
    if (voice.attempts < 3) {
      voice.attempts++;
      voiceState(VOICE.RECONNECTING);
      setTimeout(() => { if (voice.wants) voice.socket = openSocket(); },
                 400 * voice.attempts);
    } else {
      releaseAudio();
      voice.wants = false;
      voiceFail(T().voiceLost);
    }
  };

  sock.onerror = () => { /* onclose does the work */ };
  return sock;
}

/* --------------------------------------------------------------- lifecycle */

async function startVoice() {
  if (!sid || voice.wants || busy || requestPending || connectionLost || editingLetter || !SENDABLE_STATUSES.includes(view?.status)) return;
  if (healthState && !healthState.dictation?.ok) {
    voiceFail(T().voiceUnavailable, { recoverable: false });
    return;
  }
  if (!navigator.mediaDevices || !window.AudioContext) {
    voiceFail(T().micUnsupported, { recoverable: false });
    return;
  }
  voice.wants = true;
  voice.muted = false;
  voice.attempts = 0;
  $("voiceError").hidden = true;
  voiceState(VOICE.CONNECTING);
  const voiceSession = sid;
  try {
    await openMicrophone();
  } catch (err) {
    voice.wants = false;
    releaseAudio();
    voiceFail(micMessage(err), { recoverable: err && err.name === "NotAllowedError" });
    return;
  }
  if (!voice.wants || sid !== voiceSession) { releaseAudio(); return; }
  voice.socket = openSocket();
}

function stopVoice({ tell = true } = {}) {
  const wanted = voice.wants;
  voice.wants = false;
  stopPlayback();
  releaseAudio();
  if (voice.socket) {
    if (tell && voice.socket.readyState === 1) send({ type: "voice.end" });
    try { voice.socket.close(); } catch {}
    voice.socket = null;
  }
  if (voice.playCtx) { try { voice.playCtx.close(); } catch {} voice.playCtx = null; }
  voice.partial = "";
  voiceState(wanted ? VOICE.ENDED : VOICE.IDLE, { transcript: "", live: false });
  $("voiceBar").hidden = true;
}

function toggleVoice() {
  if (voice.wants) stopVoice(); else startVoice();
}

$("mic").onclick = toggleVoice;
$("micInline").onclick = toggleVoice;
$("voiceEnd").onclick = () => stopVoice();
$("voiceMute").onclick = () => {
  voice.muted = !voice.muted;
  paintVoice({});
};


/* ------------------------------------------------------------ system panel
   User-facing statuses only. Which model answered, which PDF engine ran and
   where the binary lives are operator questions, and this panel is collapsed
   by default because a citizen at a counter has no use for any of it. */

function drawHealth() {
  const h = healthState;
  const t = T();
  if (h) {
    const line = (ok, label, detail) =>
      `<div class="status-line ${ok ? "ok" : "bad"}">
         <span class="ic" aria-hidden="true">${ok ? "✓" : "✕"}</span>
         <span>${esc(label)}: <b>${esc(ok ? t.svcReady : t.svcOff)}</b>${
           detail ? ` <span style="color:var(--muted)">· ${esc(detail)}</span>` : ""}</span>
       </div>`;
    $("health").innerHTML =
      line(h.language_model.available, t.svcAI) +
      line(h.documents.docx, t.svcDoc, h.documents.pdf ? "PDF + Word" : "Word") +
      line(h.dictation.ok, t.svcVoice, h.dictation.ok ? X().voiceExternal : "") +
      line(true, t.svcSecure, h.language_model.egress ? t.svcSecureNote : X().localProcessing);
  }
}

async function loadHealth() {
  // Health probing never delays the first question or session recovery.
  try {
    const response = await fetch("/api/health", { cache: "no-store", signal: AbortSignal.timeout(12000) });
    if (response.ok) { healthState = await response.json(); drawHealth(); }
  } catch { /* The conversation API is the source of connection status. */ }
}

$("retryConnection")?.addEventListener("click", recover);
$("detailsToggle")?.addEventListener("click", () => {
  const workspace = document.querySelector("main.workspace");
  const open = workspace.classList.toggle("details-open");
  $("detailsToggle").setAttribute("aria-expanded", String(open));
  $("detailsToggleText").textContent = open ? X().conversation : X().details;
  if (open) $("detailsPanel").scrollIntoView({ behavior: "smooth", block: "start" });
});
$("helpBtn")?.addEventListener("click", () => {
  confirmThen(X().helpTitle, X().helpText, X().close, X().forget, () => {
    confirmThen(X().forget, X().forgetText, T().dismiss, X().forget, () => {
      stopVoice(); forgetSession(); resetInterface(); connectionLost = false;
      connectionNotice(); syncControls();
    });
  });
});
window.addEventListener("offline", () => {
  connectionLost = true;
  connectionNotice(X().offline);
  syncControls();
});
window.addEventListener("online", recover);
window.addEventListener("pagehide", () => { stopVoice(); clearTimeout(generationPoll); });
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    revealed.clear();
    if (view && !editing) drawDetails(view);
  }
});

// Navigation initializes the app after both scripts are loaded.


/* ------------------------------------------------------------- edit wording
 *
 * A petition the citizen has read is the first moment they can judge how it
 * reads, so this is where changing the wording belongs. It is deliberately NOT
 * a way to change the record: the particulars were confirmed before anything
 * was drafted, and a detail that is simply wrong is a correction — named in
 * the conversation, revalidated, and logged as a correction.
 *
 * The same instruction can be spoken instead. Both paths reach the same
 * endpoint and the same drafting call.
 */
/* Editing the petition directly.
 *
 * The button used to open a box that asked what should be said differently and
 * then sent that to the drafting model. That is a REWORDING, and it now lives
 * where rewordings belong — the chat, where every other instruction is typed.
 *
 * The Edit button does the other thing, the one there was no way to do: it
 * makes the petition itself editable, and what the citizen types is used
 * exactly as typed. No model, no tidying. An editor that improves what it was
 * given is not an editor, and somebody who fixed one word and got a
 * differently-worded document back would be right to stop trusting it.
 */
/* The petition as it will be printed.
 *
 * The date and place go at the top right of a letter, and the preview has to
 * agree with the document — a citizen checks the preview and then downloads
 * the file, and two different layouts means one of them is lying.
 *
 * The opening block is found the same way the renderer finds it: a short run
 * of "label: value" lines before the first blank one. By SHAPE, not by the
 * words "Date" and "Place", so a petition translated into a third language
 * keeps them on the right. The rule is written twice, once here and once in
 * render.py, and a test holds the two to the same answers.
 *
 * Split into exactly two elements, never one per line: `innerText` joins
 * block children with a single newline, so two blocks reproduce the original
 * text character for character. That matters because it is what the manual
 * editor reads back and sends to the server. */
const LABELLED_LINE = /^[^:\n]{1,24}:\s*\S/;
const MAX_OPENING_LINES = 3;

function openingBlock(lines) {
  const head = [];
  for (const line of lines) {
    if (!line.trim()) break;
    head.push(line);
    if (head.length > MAX_OPENING_LINES) return 0;
  }
  if (!head.length) return 0;
  return head.every(line => LABELLED_LINE.test(line.trim())) ? head.length : 0;
}

function drawLetter(text) {
  const paper = $("letter");
  const value = String(text ?? "");
  // While editing it is one plain text node: the citizen is typing into it.
  if (editingLetter) { paper.textContent = value; return; }
  const lines = value.split("\n");
  const head = openingBlock(lines);
  paper.replaceChildren();
  if (head > 0) {
    const top = document.createElement("div");
    top.className = "paper-dateline";
    top.textContent = lines.slice(0, head).join("\n");
    paper.appendChild(top);
  }
  const body = document.createElement("div");
  body.className = "paper-body";
  body.textContent = lines.slice(head).join("\n");
  paper.appendChild(body);
}

function startEditing() {
  if (!view?.document || busy || requestPending) return;
  stopVoice();
  const paper = $("letter");
  editingLetter = true;
  editBackup = view.letter_text;
  editVersion = view.version || view.document?.version || 1;
  editConflict = false;
  // Flattened first: the citizen edits plain text, not a laid-out preview.
  paper.textContent = editBackup;
  paper.setAttribute("contenteditable", "plaintext-only");
  paper.setAttribute("role", "textbox");
  paper.setAttribute("aria-multiline", "true");
  paper.setAttribute("aria-label", T().revise);
  paper.classList.add("is-editing");
  paper.setAttribute("spellcheck", "false");
  $("editHint").hidden = false;
  $("reviseBtn").setAttribute("aria-expanded", "true");
  syncControls();
  paper.focus();
}

function stopEditing(restore) {
  const paper = $("letter");
  editingLetter = false;
  if (restore) drawLetter(editBackup);
  paper.removeAttribute("contenteditable");
  paper.removeAttribute("role");
  paper.removeAttribute("aria-multiline");
  paper.classList.remove("is-editing");
  $("editHint").hidden = true;
  $("reviseBtn").setAttribute("aria-expanded", "false");
  syncControls();
}

/* Reading the petition in another language.
 *
 * What gets translated is the letter the service wrote. What does NOT is the
 * citizen's own text: their name, their address and their grievance come
 * through exactly as entered. The server enforces that — the request cannot
 * ask for anything else — and it is the reason a translated petition still
 * passes verification.
 */
function closeTranslate() {
  $("translateList").hidden = true;
  $("translateBtn").setAttribute("aria-expanded", "false");
}

function drawTranslate() {
  const current = view?.document_language || view?.language || "en";
  for (const option of document.querySelectorAll(".translate-option")) {
    const mine = option.dataset.language === current;
    option.setAttribute("aria-current", String(mine));
    // The language it is already in is shown ticked and not offered again;
    // choosing it would remake the document for no change.
    option.disabled = mine || busy || requestPending;
  }
  $("translateText").textContent = T().translate;
}

$("translateBtn").onclick = (e) => {
  e.stopPropagation();
  if ($("translateBtn").disabled) return;
  const open = $("translateList").hidden;
  drawTranslate();
  $("translateList").hidden = !open;
  $("translateBtn").setAttribute("aria-expanded", String(open));
};

$("translateList").addEventListener("click", async (e) => {
  const option = e.target.closest(".translate-option");
  if (!option || option.disabled) return;
  closeTranslate();
  await translateDocument(option.dataset.language);
});

document.addEventListener("click", (e) => {
  if (!e.target.closest("#translateMenu")) closeTranslate();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("translateList").hidden) {
    closeTranslate();
    $("translateBtn").focus();
  }
});

async function translateDocument(language) {
  if (busy || requestPending || !sid) return;
  busy = true;
  syncControls();
  // The same panel every other change to the document uses, in the same place.
  startGenerating("translate");
  const result = await api(`/api/sessions/${sid}/translate`, {
    method: "POST", quiet: true,
    // The same version the manual editor pins to. `document_language` is a
    // field of the view; `document_version` is not, so this was sending null
    // and skipping the check that stops two changes landing on each other.
    body: JSON.stringify({
      language,
      expected_version: view?.version || view?.document?.version || null,
    }),
  });
  stopGenerating(Boolean(result));
  busy = false;
  if (result) render(result);
  else {
    // Exactly one message, and the service's own reason when it gave one —
    // "the translation service is unavailable, your petition has not been
    // changed" tells a citizen what happened and what did not.
    bubble("system", lastApiMessage || T().translateFailed, true);
    syncControls();
  }
}

$("reviseBtn").onclick = () => {
  if (!editingLetter) startEditing(); else stopEditing(true);
};

$("editCancel").onclick = async () => {
  const refresh = editConflict;
  stopEditing(true); editConflict = false;
  if (refresh) await recover();
  $("reviseBtn").focus();
};

$("editSave").onclick = async () => {
  if (busy || requestPending || connectionLost || editConflict || !editingLetter) return;
  const text = $("letter").innerText.replace(/\u00a0/g, " ").trimEnd();
  if (text.trim().length < 40) {
    bubble("system", T().editEmpty, true);
    return;
  }
  if (text === editBackup) { stopEditing(false); return; }
  if (text.length > 40000) {
    bubble("system", lang === "ta" ? "மனு 40,000 எழுத்துகளுக்குள் இருக்க வேண்டும்." : "Keep the petition within 40,000 characters.", true);
    return;
  }

  busy = true;
  requestPending = true;
  $("letter").setAttribute("contenteditable", "false");
  syncControls();
  drawLifecycle({ ...view, status: "generating" });
  drawStepper({ ...view, status: "generating" });
  beginDocumentWork("revise");
  const result = await api(`/api/sessions/${sid}/document/text`, {
    method: "POST", body: JSON.stringify({ text, expected_version: editVersion }),
  });
  stopGenerating(Boolean(result));
  busy = false;
  requestPending = false;
  if (result) { stopEditing(false); render(result); }
  else {
    // The save did not land. Put their words back rather than silently
    // showing them the old petition as though nothing had happened.
    $("letter").textContent = text;
    $("letter").setAttribute("contenteditable", "plaintext-only");
    editConflict = lastApiStatus === 409;
    if (editConflict) bubble("system", lang === "ta"
      ? "மனு வேறு இடத்தில் மாற்றப்பட்டுள்ளது. உங்கள் உரையை நகலெடுத்து, ரத்து செய்து புதிய பதிப்பைத் திறக்கவும்."
      : "This petition changed elsewhere. Your edits are still here. Copy them, then Cancel to load the latest version.", true);
    drawLifecycle(view); drawStepper(view); syncControls();
  }
};

$("letter").addEventListener("keydown", (e) => {
  if (!editingLetter) return;
  if (e.key === "Escape") { e.preventDefault(); $("editCancel").click(); }
  if (e.key === "s" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); $("editSave").click(); }
});

$("attachBtn").onclick = () => $("attachInput").click();

$("attachInput").addEventListener("change", (e) => {
  uploadAttachments(e.target.files);
  e.target.value = "";           // so the same file can be re-picked after a removal
});


