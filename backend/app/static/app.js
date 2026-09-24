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
      petitioner_name: "Name on the document", address: "Address on the document",
      submitted_on: "Submitted on", department: "Department",
      authority: "Authority", subject: "Subject", status: "Status",
    },
    includeAttachments: "Include the attached files",
    attachConflictHead: "This document says something different",
    attachConflictAsk: "Which should the petition use?",
    attachConflictCurrent: "What you told me",
    attachConflictDocument: "What the document says",
    attachConflictKeep: "Keep mine",
    attachConflictUse: "Use the document's",
    attachConflictNameOnly: "The petition keeps the name you gave. A name read from a scan is not reliable enough to replace it — if yours is wrong, edit it in Petition Details.",
    attachConflictField: {
      applicant_name: "Name", address: "Address",
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

    pdf: "Download PDF", packagePdf: "Full Package (with attachments)", docx: "Download Word", noPdf: "PDF unavailable",
    enclosuresHeading: "Documents attached to this petition",
    onePage: "1 page", manyPages: "{n} pages",
    enclosureIncluded: "Included in the Full Package download, after the letter.",
    enclosureView: "View", enclosureDownload: "Download",
    modeLetter: "Petition Only", modePackage: "Full Package",
    pageOf: "Page {n} of {total}",
    packagePageLoading: "Loading page…",
    packagePageAlt: "Page {n}",
    packagePageFailed: "Unable to preview this page.",
    packageOpenOriginal: "Open Original",
    packageBuilding: "Preparing the combined document…",
    packageUnavailable: "The combined preview could not be prepared on this server. The petition and the attachments are still available.",
    packageNotMerged: "This document remains attached but cannot be previewed inline.",
    attachmentWord: "Attachment",
    enclosureUnreadable: "This file could not be read, but it is still attached.",
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
      listening: "Listening…",
      long_listening: "Listening to your grievance…",
      long_paused: "Paused",
      long_editing: "Updating your grievance…",
      long_confirmed: "Grievance confirmed",
      user_speaking: "You're speaking…",
      transcribing: "Transcribing…",
      reading_back: "Reading back…",
      waiting_confirmation: "Waiting for confirmation",
      processing: "Thinking…",
      generating: "Writing your petition…",
      assistant_speaking: "Assistant speaking",
      reconnecting: "Reconnecting…",
      error: "Voice stopped",
      ended: "Voice off",
    },
    answerHeading: "Your answer",
    answerAsk: "Is that correct?",
    answerConfirm: "Confirm",
    answerRetryBtn: "Retry",
    answerSaved: "Confirmed ✓",
    answerRetrying: "Retrying — please say it again",
    answerReadOut: "Read it to me",
    noiseOn: "✓ Noise reduction active",
    noiseHigh: "High background noise — please speak a little closer to the microphone.",
    dictationTitle: "Listening to your grievance…",
    dictationPaused: "Grievance captured",
    dictationHeld: "Paused",
    dictationSub: "You can continue speaking",
    dictationSubHeld: "Press Resume when you are ready",
    dictationSubDone: "Check it below, then confirm it",
    dictationEmpty: "Your words will appear here as you speak.",
    dictationFinish: "Finish",
    dictationPause: "Pause",
    dictationResume: "Resume",
    dictationRestart: "Start over",
    answerEdit: "Edit",
    answerGrievanceHeading: "Your grievance",
    answerGrievanceAsk: "Say yes, retry, or tell me what to change.",
    grievanceDoneTitle: "Grievance confirmed",
    grievanceDoneText: "Your grievance has been saved.",
    dictationCount: (n) => n === 1 ? "1 part" : `${n} parts`,
    dictationSafe: "Connection interrupted. Your recorded grievance is safe. Please continue.",
    dictationFull: "The box is full. Please send what is there before saying more.",
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
      petitioner_name: "ஆவணத்தில் உள்ள பெயர்", address: "ஆவணத்தில் உள்ள முகவரி",
      reference_number: "ஒப்புகை எண்", petition_number: "மனு எண்",
      submitted_on: "அளித்த தேதி", department: "துறை",
      authority: "அதிகாரி", subject: "பொருள்", status: "நிலை",
    },
    includeAttachments: "இணைக்கப்பட்ட ஆவணங்களையும் சேர்க்கவும்",
    attachConflictHead: "இந்த ஆவணம் வேறு விவரம் கூறுகிறது",
    attachConflictAsk: "மனுவில் எதைப் பயன்படுத்த வேண்டும்?",
    attachConflictCurrent: "நீங்கள் கூறியது",
    attachConflictDocument: "ஆவணம் கூறுவது",
    attachConflictKeep: "என்னுடையதைப் பயன்படுத்து",
    attachConflictUse: "ஆவணத்தில் உள்ளதைப் பயன்படுத்து",
    attachConflictNameOnly: "நீங்கள் கூறிய பெயரே மனுவில் இருக்கும். ஆவணச் சிதறலில் படிக்கப்பட்ட பெயரை நம்ப முடியாது — உங்கள் பெயர் தவறாக இருந்தால், மனு விவரங்களில் திருத்தவும்.",
    attachConflictField: {
      applicant_name: "பெயர்", address: "முகவரி",
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

    pdf: "PDF பதிவிறக்கம்",
    packagePdf: "முழு தொகுப்பு (இணைப்புகளுடன்)", docx: "Word பதிவிறக்கம்", noPdf: "PDF இல்லை",
    enclosuresHeading: "இந்த மனுவுடன் இணைக்கப்பட்ட ஆவணங்கள்",
    onePage: "1 பக்கம்", manyPages: "{n} பக்கங்கள்",
    enclosureIncluded: "முழு தொகுப்பில், கடிதத்திற்குப் பின் இணைக்கப்பட்டுள்ளது.",
    enclosureView: "பார்", enclosureDownload: "பதிவிறக்கு",
    modeLetter: "மனு மட்டும்", modePackage: "முழு தொகுப்பு",
    pageOf: "பக்கம் {n} / {total}",
    packagePageLoading: "பக்கம் ஏற்றப்படுகிறது…",
    packagePageAlt: "பக்கம் {n}",
    packagePageFailed: "இந்தப் பக்கத்தை முன்னோட்டமிட முடியவில்லை.",
    packageOpenOriginal: "அசலைத் திற",
    packageBuilding: "இணைந்த ஆவணம் தயாராகிறது…",
    packageUnavailable: "இணைந்த முன்னோட்டத்தை இந்த சேவையகத்தில் தயாரிக்க முடியவில்லை. மனுவும் இணைப்புகளும் கிடைக்கின்றன.",
    packageNotMerged: "இந்த ஆவணம் இணைக்கப்பட்டுள்ளது, ஆனால் இங்கே காட்ட முடியாது.",
    attachmentWord: "இணைப்பு",
    enclosureUnreadable: "இந்தக் கோப்பைப் படிக்க முடியவில்லை, ஆனால் அது இணைக்கப்பட்டுள்ளது.",
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
      long_listening: "உங்கள் குறையை கேட்கிறேன்…",
      long_paused: "நிறுத்தப்பட்டது",
      long_editing: "குறை மாற்றப்படுகிறது…",
      long_confirmed: "குறை உறுதி செய்யப்பட்டது",
      user_speaking: "நீங்கள் பேசுகிறீர்கள்…",
      transcribing: "புரிந்துகொள்கிறேன்…",
      reading_back: "மீண்டும் வாசிக்கிறேன்…",
      waiting_confirmation: "உறுதிப்படுத்தலுக்குக் காத்திருக்கிறேன்",
      processing: "புரிந்துகொள்கிறேன்…",
      generating: "மனுவை எழுதுகிறேன்…",
      assistant_speaking: "பதிலளிக்கிறேன்…",
      reconnecting: "மீண்டும் இணைக்கப்படுகிறது…",
      error: "குரல் நிறுத்தப்பட்டது",
      ended: "குரல் நிறுத்தப்பட்டது",
    },
    answerHeading: "உங்கள் பதில்",
    answerAsk: "இது சரியா?",
    answerConfirm: "சரி",
    answerRetryBtn: "மீண்டும்",
    answerSaved: "உறுதி செய்யப்பட்டது ✓",
    answerRetrying: "மீண்டும் சொல்லுங்கள்",
    answerReadOut: "படித்துக் காட்டு",
    noiseOn: "✓ பின்னணி சத்தம் குறைக்கப்படுகிறது",
    noiseHigh: "பின்னணி சத்தம் அதிகமாக உள்ளது. மைக்ரோஃபோனுக்கு அருகில் பேசுங்கள்.",
    dictationTitle: "உங்கள் குறையை கேட்கிறேன்…",
    dictationPaused: "குறை பதிவு செய்யப்பட்டது",
    dictationHeld: "நிறுத்தப்பட்டது",
    dictationSub: "தொடர்ந்து பேசலாம்",
    dictationSubHeld: "தயாரானதும் தொடர் என்பதை அழுத்தவும்",
    dictationSubDone: "கீழே பார்த்து உறுதி செய்யவும்",
    dictationEmpty: "நீங்கள் பேசும்போது உங்கள் வார்த்தைகள் இங்கே தோன்றும்.",
    dictationFinish: "முடிந்தது",
    dictationPause: "நிறுத்து",
    dictationResume: "தொடர்",
    dictationRestart: "மீண்டும் தொடங்கு",
    answerEdit: "மாற்று",
    answerGrievanceHeading: "உங்கள் குறை",
    answerGrievanceAsk: "ஆம், மீண்டும், அல்லது மாற்ற வேண்டியதைச் சொல்லுங்கள்.",
    grievanceDoneTitle: "குறை உறுதி செய்யப்பட்டது",
    grievanceDoneText: "உங்கள் குறை சேமிக்கப்பட்டது.",
    dictationCount: (n) => n === 1 ? "1 பகுதி" : `${n} பகுதிகள்`,
    dictationSafe: "இணைப்பு தற்காலிகமாக துண்டிக்கப்பட்டது. இதுவரை பதிவு செய்யப்பட்ட குறை பாதுகாப்பாக உள்ளது. தொடர்ந்து சொல்லுங்கள்.",
    dictationFull: "பெட்டி நிரம்பிவிட்டது. மேலும் சொல்வதற்கு முன் உள்ளதை அனுப்பவும்.",
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
    retryDraft: "Your answer is still in the box. Check your saved details before sending again.",
    sessionGone: "That petition is no longer on this service, so it has been removed from the list.",
    privateHint: "Type this number privately. Only the last four digits appear in the conversation.",
    longHint: "Include the location, what happened, and the action you are requesting. Your words are kept unchanged.",
    copiedError: "Copy is unavailable. Select the petition text to copy it, or download the Word document.",
    popupError: "Allow pop-ups for this page to print, or download the document.",
    kiosk: "Kiosk",
    kioskWelcomeTitle: "Welcome",
    kioskWelcomeText: "This service will help you prepare your citizen petition. "
                      + "Tap below to begin.",
    kioskStart: "Start Petition",
    kioskPrinting: "Sending your petition to the printer…",
    // NOTHING here says "printed successfully". A browser cannot tell whether
    // paper came out of a printer, and a screen that claims it did sends a
    // citizen away from an empty tray.
    kioskDialogTitle: "The print window is open",
    kioskDialogText: "Press Print in the window to print your petition, then "
                     + "collect it from the printer.",
    kioskSentTitle: "Your petition has been sent to the printer",
    kioskSentText: "Please collect it from the printer and check every detail "
                   + "before signing it.",
    kioskFailedTitle: "Unable to print the petition",
    kioskFailedText: "Your petition is safe and is still on the screen. Try again, "
                     + "or ask the staff at the counter for help.",
    kioskRetryPrint: "Try printing again",
    kioskPrintAgain: "Print another copy",
    kioskFinish: "Finish",
    kioskClearing: (n) => `This screen clears in ${n} seconds.`,
    kioskStillThere: "Are you still there? This screen will clear shortly so the "
                     + "next person cannot see your details.",
    helpTitle: "From your concern to a clear petition",
    helpSteps: ["Answer the questions by typing or using voice.",
                "Review your details and select Edit to make corrections.",
                "Confirm to create your document, then download or print it."],
    helpNote: "Your progress is restored on this browser. Your grievance is kept in your own words. Review the document before signing; this app does not submit it to an office.",
    close: "Got it",
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
    retryDraft: "உங்கள் பதில் பெட்டியில் உள்ளது. மீண்டும் அனுப்பும் முன் சேமித்த விவரங்களைப் பாருங்கள்.",
    sessionGone: "அந்த மனு இந்தச் சேவையில் இப்போது இல்லை; எனவே பட்டியலிலிருந்து நீக்கப்பட்டது.",
    privateHint: "இந்த எண்ணைத் தட்டச்சு செய்யவும். கடைசி நான்கு இலக்கங்கள் மட்டும் உரையாடலில் தெரியும்.",
    longHint: "இடம், நடந்தது, நீங்கள் கோரும் நடவடிக்கை ஆகியவற்றைக் குறிப்பிடவும். உங்கள் சொற்கள் மாற்றப்படாது.",
    copiedError: "நகலெடுக்க இயலவில்லை. மனு உரையைத் தேர்ந்தெடுத்து நகலெடுக்கவும் அல்லது Word ஆவணத்தைப் பதிவிறக்கவும்.",
    popupError: "அச்சிட இந்தப் பக்கத்திற்குப் பாப்-அப் அனுமதி அளிக்கவும் அல்லது ஆவணத்தைப் பதிவிறக்கவும்.",
    kiosk: "கியோஸ்க்",
    kioskWelcomeTitle: "வணக்கம்",
    kioskWelcomeText: "உங்கள் மனுவை எளிதாக தயாரிக்க இந்த சேவை உதவும். "
                      + "தொடங்க கீழே உள்ள பொத்தானை அழுத்தவும்.",
    kioskStart: "மனுவை தொடங்கவும்",
    kioskPrinting: "உங்கள் மனு அச்சுப்பொறிக்கு அனுப்பப்படுகிறது…",
    kioskDialogTitle: "அச்சிடும் சாளரம் திறந்துள்ளது",
    kioskDialogText: "சாளரத்தில் 'Print' அழுத்தி உங்கள் மனுவை அச்சிடுங்கள், பிறகு "
                     + "அச்சுப்பொறியில் இருந்து பெற்றுக்கொள்ளுங்கள்.",
    kioskSentTitle: "உங்கள் மனு அச்சுப்பொறிக்கு அனுப்பப்பட்டுள்ளது",
    kioskSentText: "அச்சுப்பொறியில் இருந்து பெற்றுக்கொண்டு, கையொப்பமிடும் முன் "
                   + "ஒவ்வொரு விவரத்தையும் சரிபார்க்கவும்.",
    kioskFailedTitle: "மனுவை அச்சிட முடியவில்லை",
    kioskFailedText: "உங்கள் மனு பாதுகாப்பாக திரையில் உள்ளது. மீண்டும் முயற்சிக்கவும் "
                     + "அல்லது உதவியாளரை தொடர்பு கொள்ளவும்.",
    kioskRetryPrint: "மீண்டும் அச்சிட முயற்சிக்கவும்",
    kioskPrintAgain: "மற்றொரு நகல் அச்சிடு",
    kioskFinish: "முடிந்தது",
    kioskClearing: (n) => `இந்தத் திரை ${n} வினாடிகளில் அழிக்கப்படும்.`,
    kioskStillThere: "நீங்கள் இருக்கிறீர்களா? அடுத்தவர் உங்கள் விவரங்களைப் பார்க்காதபடி "
                     + "இந்தத் திரை விரைவில் அழிக்கப்படும்.",
    helpTitle: "உங்கள் குறையிலிருந்து தெளிவான மனு வரை",
    helpSteps: ["தட்டச்சு அல்லது குரல் மூலம் கேள்விகளுக்குப் பதிலளிக்கவும்.",
                "விவரங்களைச் சரிபார்த்து தேவையான திருத்தங்களைச் செய்யவும்.",
                "உறுதிசெய்த பிறகு ஆவணத்தைப் பதிவிறக்கவும் அல்லது அச்சிடவும்."],
    helpNote: "இந்த உலாவியில் உங்கள் மனுவை மீண்டும் தொடரலாம். உங்கள் குறை மாற்றப்படாது. கையொப்பமிடும் முன் ஆவணத்தைச் சரிபார்க்கவும். இந்தச் செயலி மனுவை அலுவலகத்திற்குச் சமர்ப்பிக்காது.",
    close: "புரிந்தது",
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
   An identifier is shown with only its last four digits. The full value stays
   in the record on the server and goes into the petition through the
   deterministic path; the screen does not need it, and a screen in a public
   office is the easiest place in the whole system to read one off.

   THE FORM NO LONGER ASKS FOR AN AADHAAR. `aadhaar` stays in this set
   because one can still arrive: typed into the box by a citizen who assumes
   it is wanted, or read off an attached card. Masking a number nobody asked
   for costs nothing; failing to mask one that turns up costs a great deal. */
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
   identifier — somebody typing a bare twelve-digit number into the box.
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

function bubble(who, text, isError, turn) {
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
  // Only what the assistant said. A citizen's own answer read back aloud at
  // a counter is heard by the queue behind them, and the server refuses it
  // either way — this is the half of that rule the page is responsible for.
  if (who === "assistant" && turn !== undefined) b.appendChild(speakerButton(turn));
  row.appendChild(b);
  $("log").appendChild(row);
  // The citizen's own message always brings the view with it — they just sent
  // it and expect to see it land. Anything else only follows if they were
  // already at the bottom, so reading back over the conversation is not
  // interrupted by the assistant answering.
  scrollLog(who === "citizen");
  return row;
}

/* A SPEAKER BESIDE WHAT THE ASSISTANT SAID.
   Press once and it reads that message; press again and it reads it again.
   It addresses the turn by its number rather than posting the text back, so
   the words spoken are the ones the session holds — the page cannot ask the
   service to say something the conversation never contained. */
function speakerButton(turn) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "say-again";
  button.dataset.turn = String(turn);
  button.title = button.ariaLabel = voiceWords().hear;
  button.innerHTML = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    + '<path d="M4 9v6h3.5L12 19V5L7.5 9H4Z" stroke="currentColor" stroke-width="1.7" '
    + 'stroke-linejoin="round"/><path d="M16 9.2a4 4 0 0 1 0 5.6M18.5 6.5a8 8 0 0 1 0 11" '
    + 'stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>';
  button.onclick = () => {
    void speakOnce(`/api/sessions/${encodeURIComponent(sid)}/speech?turn=${turn}`);
  };
  return button;
}

/** An assistant question, with the field it is asking about named above it. */
function questionBubble(text, field, turn) {
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
  if (turn !== undefined) b.appendChild(speakerButton(turn));
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
  for (const say of document.querySelectorAll(".bubble .say-again")) {
    say.title = say.ariaLabel = voiceWords().hear;
  }
  $("readText").textContent = typing.reading ? voiceWords().readStop : voiceWords().readDoc;
  $("readBtn").title = $("readBtn").ariaLabel =
    typing.reading ? voiceWords().readStop : voiceWords().readDoc;
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
  let spokenSoFar = turns.slice(0, seen).filter(t => t.who === "assistant").length;
  turns.slice(seen).forEach((t, i, arr) => {
    const isLast = i === arr.length - 1;
    const turn = t.who === "assistant" ? spokenSoFar++ : undefined;
    if (t.who === "assistant" && isLast && pendingField && v.status === "collecting") {
      questionBubble(t.text, pendingField, turn);
    } else {
      bubble(t.who, t.text, false, turn);
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
  // The terminal's whole point: the petition reaches the printer without
  // anybody having to find a button. A no-op everywhere else.
  kioskMaybePrint(v);
  clearTimeout(generationPoll);
  if (v.status === "generating" && !requestPending) {
    generationPoll = setTimeout(recover, 2500);
  }
  syncControls();
  if (typeof drawVersions === "function") drawVersions(v);
  void speakReply(v);
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
// Conflicts the citizen has already answered, so the question is not
// re-asked on every repaint. Held on the page rather than the server on
// purpose: it records what they have SEEN, not what the petition says,
// and the petition is the server's business.
const dismissedConflicts = new Set();

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
        ${f.where ? `<span class="ap-where">${esc(f.where)}</span>` : ""}
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

  // Where a confirmed document disagrees with what the citizen told us. Both
  // values are shown with their source and NEITHER is applied: the current
  // answer is already on the petition and stays there unless they pick the
  // other one. Dismissing is therefore the safe default, which is why "Keep
  // mine" needs no server call at all.
  const conflicts = (a?.conflicts || []).filter(
    c => !dismissedConflicts.has(`${c.attachment_id}:${c.field}`));
  $("attachConflictList").innerHTML = conflicts.map(c => `
    <div class="ap-conflict" data-conflict="${esc(c.attachment_id)}:${esc(c.field)}">
      <p class="ap-conflict-head">${esc(t.attachConflictHead)}</p>
      <p class="ap-conflict-ask">${esc(t.attachConflictField[c.field] || c.field)} —
         ${esc(t.attachConflictAsk)}</p>
      <div class="ap-conflict-pair">
        <div>
          <span>${esc(t.attachConflictCurrent)}</span>
          <strong>${esc(c.current)}</strong>
        </div>
        <div>
          <span>${esc(t.attachConflictDocument)}${c.where ? ` · ${esc(c.where)}` : ""}</span>
          <strong>${esc(c.proposed)}</strong>
          <q>${esc(c.filename)}</q>
        </div>
      </div>
      <div class="ap-confirm-actions">
        <button class="btn primary" type="button" data-keep="1">${esc(t.attachConflictKeep)}</button>
        ${c.adoptable === false ? "" : `<button class="btn" type="button" data-use="${esc(c.field)}"
                data-value="${esc(c.proposed)}">${esc(t.attachConflictUse)}</button>`}
      </div>
      ${c.adoptable === false ? `<p class="ap-conflict-note">${esc(t.attachConflictNameOnly)}</p>` : ""}
    </div>`).join("");

  $("attachConflictList").querySelectorAll("[data-keep]").forEach(b => {
    b.onclick = () => {
      // Nothing to send. The petition already holds the citizen's own value;
      // this only stops asking about a question they have answered.
      dismissedConflicts.add(b.closest("[data-conflict]").dataset.conflict);
      drawAttachments(view);
    };
  });
  $("attachConflictList").querySelectorAll("[data-use]").forEach(b => {
    b.onclick = () => {
      // Through the ordinary field editor, so the value from a document is
      // validated exactly as one the citizen typed would be. A malformed
      // address read off a scan is rejected here, not printed.
      dismissedConflicts.add(b.closest("[data-conflict]").dataset.conflict);
      attachmentAction(`/api/sessions/${sid}/field`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: b.dataset.use, value: b.dataset.value }),
      });
    };
  });

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
    // The mark is DRAWN, so the shape changes rather than the text. Setting
    // textContent here would delete the svg and leave a bare character.
    const mark = $("outcomeIcon").querySelector("path");
    if (mark) {
      mark.setAttribute("d", ok
        ? "m5 12.5 4.5 4.5L19 7.5"                  // a tick
        : "M12 6.5v7.5M12 17.6v.2");                // a bar and a dot: "!"
    }
    $("outcomeTitle").textContent = ok ? t.readyTitle : t.verifyBad;
    $("outcomeText").textContent = ok
      ? (v.verification ? t.verifyOk(v.verification.checked) + " · " + t.readyText : t.readyText)
      : t.readyText;
    $("outcomeRef").hidden = !doc.reference;
    $("refValue").textContent = doc.reference || "";
    if (!editingLetter) drawLetter(v.letter_text);
    drawEnclosures(v.attachments);
    // The mode switch appears only once something is attached; with nothing
    // enclosed the two modes are the same document.
    const hasEnclosures = (v.attachments?.items || []).length > 0;
    $("previewModes").hidden = !hasEnclosures || editingLetter;
    if (hasEnclosures && !editingLetter) {
      drawPackagePages(v);
      setPreviewMode(packageMode);
    } else {
      setPreviewMode(false);
    }
    paintEmblem(v.emblem);
  } else {
    $("outcome").hidden = true;
    // No letter yet, so nothing to be enclosed with.
    if ($("enclosures")) $("enclosures").hidden = true;
  }

  // The package or the letter alone. Offered only when something is actually
  // attached: with nothing enclosed the two files are identical and the
  // choice would be a control that does nothing.
  // TWO OUTPUTS, and they are now genuinely different things rather than
  // one file with a checkbox:
  //
  //   Download PDF / Word   the generated petition, on its own
  //   Full Package          petition + index + the ORIGINAL attachments
  //
  // The checkbox used to decide whether the plain download carried the
  // attachments rasterised into it. That was a worse version of the package
  // — pictures of pages, capped at twelve per file, no text layer — offered
  // in the same place as the real one. The package copies the pages across
  // instead, so there is nothing left for the toggle to choose between.
  const enclosedCount = (v.attachments?.items || []).length;
  $("packageToggle").hidden = true;
  const form = (url) => (url ? `${url}?enclosures=0` : url);

  setLink($("pdf"), form(doc.pdf_url), t.pdf, t.noPdf);
  setLink($("docx"), form(doc.docx_url), t.docx);
  // Built on request, so it is a plain link rather than something prepared
  // at generation time: most petitions are never packaged, and copying a
  // hundred attached pages is not work to do speculatively.
  //
  // DERIVED FROM THE SESSION, not from `pdf_url`. It used to be built by
  // rewriting the PDF link, so whenever the PDF was still converting — Word
  // and LibreOffice both take seconds — `pdf_url` was null, this came out
  // empty, and the button for the one download that carries the citizen's
  // documents disappeared with no explanation. The package endpoint renders
  // the letter itself and never needed that file.
  const sid = v.session_id || doc.session_id || "";
  const packageUrl = sid
    ? `/api/sessions/${encodeURIComponent(sid)}/document/package.pdf`
    : (doc.docx_url || "").replace(/\/document\.docx.*$/, "/document/package.pdf");
  $("packagePdf").hidden = !hasLetter || enclosedCount === 0 || !packageUrl;
  setLink($("packagePdf"), packageUrl, t.packagePdf);
  $("printBtn").disabled = !hasLetter;
  $("readBtn").disabled = !hasLetter;
  $("readBtn").classList.toggle("reading", typing.reading);
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
  $("send").disabled = !canSend() || !$("text").value.trim() || $("text").value.length > 6000;
  $("text").disabled = !canSend();

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
    // NO GENERIC KEYBOARD HINT. "Enter to send, Shift + Enter for a new
    // line" was shown under the box for every ordinary question, which is
    // most of the interview — a permanent line of instructions about the
    // keyboard, sitting under a form that also has a Send button. The hints
    // that remain each say something the citizen could not otherwise know:
    // that only the last four digits of a number will be shown, what a
    // useful grievance contains, and what kind of change can be asked for.
    : view?.awaiting === "grievance" ? X().longHint : "";
  if ($("inputCount")) $("inputCount").textContent = `${$("text").value.length.toLocaleString(lang)} / 6,000`;
  $("new").disabled = generating;
  $("lang").disabled = generating;
  $("restart").disabled = unavailable && Boolean(sid);
  document.querySelectorAll("[data-edit], [data-reveal], [data-editform] button, [data-editform] input, [data-editform] textarea")
    .forEach(el => { el.disabled = unavailable; });
  // Edit mode swaps the toolbar: the Edit button becomes Save and Cancel.
  $("reviseBtn").hidden = editingLetter;
  paintVoice();
  $("editSave").hidden = !editingLetter;
  $("editCancel").hidden = !editingLetter;
  $("editSave").disabled = busy || requestPending || editConflict || connectionLost;
  $("editCancel").disabled = busy || requestPending;
  $("reviseBtn").disabled = status !== "ready" || unavailable;
  for (const id of ["pdf", "docx", "printBtn", "copyBtn"]) $(id).hidden = editingLetter;
  if (editingLetter) $("packagePdf").hidden = true;
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
  typing.message = "";
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
  if (!text || !canSend() || text.length > 6000) return;
  closeDictation();
  stopPlayback();
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

// Something to READ, with one way out of it.
//
// `confirmThen` below is for a decision — it has two buttons because it is
// asking a question. "How it works" asks nothing, and putting a second
// button on it offered a destructive action to somebody who had pressed a
// question mark. The steps are an <ol> rather than a paragraph with "1." and
// "2." typed into it: three separate instructions read as three, and a
// screen reader announces them as a list of three.
function explain(title, steps, note, closeLabel) {
  if (document.querySelector(".modal-backdrop")) return;
  const priorFocus = document.activeElement;
  const back = document.createElement("div");
  back.className = "modal-backdrop";
  back.innerHTML =
    `<div class="modal" role="dialog" aria-modal="true" aria-labelledby="mt">
       <h3 id="mt">${esc(title)}</h3>
       <ol class="modal-steps">${
         (steps || []).map((step) => `<li>${esc(step)}</li>`).join("")
       }</ol>
       ${note ? `<p class="modal-note">${esc(note)}</p>` : ""}
       <div class="modal-actions">
         <button class="btn primary" data-keep>${esc(closeLabel)}</button>
       </div>
     </div>`;
  document.body.appendChild(back);
  const close = () => {
    back.remove();
    document.removeEventListener("keydown", onKey);
    priorFocus?.focus();
  };
  const onKey = (e) => {
    if (e.key === "Escape") close();
    // One button, so Tab has nowhere else to go and must not leave the dialog.
    if (e.key === "Tab") { e.preventDefault(); back.querySelector("[data-keep]").focus(); }
  };
  back.querySelector("[data-keep]").onclick = close;
  back.onclick = (e) => { if (e.target === back) close(); };
  document.addEventListener("keydown", onKey);
  back.querySelector("[data-keep]").focus();
}

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

/* ------------------------------------------------------------------ kiosk
   A self-service terminal standing in a government office. The citizen walks
   up, answers the questions on screen or by voice, and takes the printed
   petition away with them.

   IT IS THE SAME FLOW, not a copy of it. Kiosk is a flag on the page that
   already exists: the same graph, the same questions, the same document, the
   same voice, the same Tamil. A kiosk page of its own would be a second copy
   of the form, the document panel and the voice layer, drifting from the
   original from the day it was written — and the copy is always the one
   nobody remembers to change.

   WHAT THE PAGE IS ALLOWED TO CLAIM ABOUT PRINTING is the part worth being
   careful with. A browser cannot tell whether paper came out of a printer.
   `window.print()` opens a dialog somebody has to confirm; on a terminal
   launched with `--kiosk-printing` it goes straight to the default printer
   and no dialog appears. The page cannot detect which of those happened.

   So the DEPLOYMENT says which it is — `KIOSK_PRINT_MODE=dialog` or
   `silent`, dialog by default — and the wording follows it. In dialog mode
   the citizen is told the dialog is open. In silent mode they are told the
   petition was SENT to the printer. Neither says "printed successfully",
   because neither is something this code can know. */

const kioskState = {
  on: false,
  // From the server, so a terminal is configured rather than guessed at.
  print_mode: "dialog",
  auto_print: true,
  idle_timeout_seconds: 120,
  reset_after_finish: true,
  // petition + document version already sent to the printer, so a re-render
  // — an edit, a reconnect, a duplicate response — cannot print again.
  printedKey: null,
  countdown: null,
  idleTimer: null,
  askedIfStillThere: false,
};

function kioskConfig() {
  const from = healthState?.kiosk;
  if (!from) return;
  for (const key of ["print_mode", "auto_print", "idle_timeout_seconds",
                     "reset_after_finish"]) {
    if (from[key] !== undefined) kioskState[key] = from[key];
  }
}

function setKioskMode(on) {
  kioskState.on = Boolean(on);
  document.body.classList.toggle("kiosk", kioskState.on);
  stopKioskCountdown();
  stopKioskIdle();
  $("kioskDone").hidden = true;
  $("kioskWelcome").hidden = !kioskState.on;
  if (kioskState.on) { kioskConfig(); paintKioskWelcome(); }
}

/* ------------------------------------------------------------- welcome */

function paintKioskWelcome() {
  const t = T();
  $("kioskWelcomeTitle").textContent = t.kioskWelcomeTitle;
  $("kioskWelcomeText").textContent = t.kioskWelcomeText;
  $("kioskStart").textContent = t.kioskStart;
}

$("kioskStart").onclick = async () => {
  $("kioskWelcome").hidden = true;
  kioskState.printedKey = null;
  await start();
  kioskTouch();
};

/* --------------------------------------------------------------- print */

/** The petition is ready and verified. Send it, once. */
function kioskMaybePrint(v) {
  if (!kioskState.on || !kioskState.auto_print) return;
  if (!v || v.status !== "ready" || !v.letter_text) return;
  // NOT merely "generated". A document that failed verification is not one
  // to put on paper and hand to a government office.
  if (!v.verification?.ok && !v.verification?.hand_edited
      && !v.verification?.user_edited) return;

  const key = `${v.session_id}:${v.document?.version ?? 0}`;
  if (kioskState.printedKey === key) return;
  kioskState.printedKey = key;
  kioskPrint();
}

/** Ask the browser to print, and describe only what actually happened. */
function kioskPrint() {
  const t = T();
  showKioskDone(t.kioskPrinting, "");
  // The CURRENT page, not a popup. `window.open` from a timer rather than a
  // click is blocked by default and a kiosk has nobody to press "allow";
  // the print stylesheet already reduces this page to the letter alone.
  let opened = false;
  try {
    window.print();
    opened = true;
  } catch {
    opened = false;
  }
  if (!opened) { showKioskFailed(); return; }
  // `window.print()` returns when the dialog closes, which is not the same
  // as paper existing. The wording says what is known and no more.
  showKioskDone(
    kioskState.print_mode === "silent" ? t.kioskSentTitle : t.kioskDialogTitle,
    kioskState.print_mode === "silent" ? t.kioskSentText : t.kioskDialogText);
}

function showKioskDone(title, text) {
  const t = T();
  $("kioskDoneTitle").textContent = title;
  $("kioskDoneText").textContent = text;
  $("kioskPrintAgain").textContent = t.kioskPrintAgain;
  $("kioskFinish").textContent = t.kioskFinish;
  $("kioskDone").classList.remove("failed");
  $("kioskDone").hidden = false;
  if (text) startKioskCountdown(text);
}

function showKioskFailed() {
  const t = T();
  $("kioskDoneTitle").textContent = t.kioskFailedTitle;
  $("kioskDoneText").textContent = t.kioskFailedText;
  $("kioskPrintAgain").textContent = t.kioskRetryPrint;
  $("kioskFinish").textContent = t.kioskFinish;
  $("kioskDone").classList.add("failed");
  $("kioskDone").hidden = false;
  // NOT cleared on a failure. The petition is still on the screen and still
  // on the server, and wiping it because a printer is out of paper would
  // lose the only thing the citizen came for.
  stopKioskCountdown();
}

/* An explicit second copy is a different thing from an accidental one. */
$("kioskPrintAgain").onclick = () => { stopKioskCountdown(); kioskPrint(); };
$("kioskFinish").onclick = () => { void kioskRestart(); };

/* ----------------------------------------------------------- clearing */

/** Clear the screen for the next citizen, visibly and interruptibly.
 *
 *  Visible, because a screen that wipes itself without warning loses
 *  somebody's work. Interruptible, because the person reading it may be
 *  slow, and needing more time is a reasonable thing to need.
 */
function startKioskCountdown(baseText) {
  stopKioskCountdown();
  if (!kioskState.reset_after_finish) return;
  let left = KIOSK_CLEAR_SECONDS;
  const tick = () => {
    $("kioskDoneText").textContent = `${baseText} ${T().kioskClearing(left)}`;
    if (left <= 0) { stopKioskCountdown(); void kioskRestart(); return; }
    left -= 1;
  };
  tick();
  kioskState.countdown = setInterval(tick, 1000);
}

function stopKioskCountdown() {
  if (kioskState.countdown) { clearInterval(kioskState.countdown); kioskState.countdown = null; }
}

const KIOSK_CLEAR_SECONDS = 45;

/** Everything the last citizen left behind, gone before the next one looks. */
async function kioskRestart() {
  stopKioskCountdown();
  stopKioskIdle();
  stopVoice({ tell: false });
  $("kioskDone").hidden = true;
  kioskState.printedKey = null;
  kioskState.askedIfStillThere = false;
  forgetSession();
  resetInterface();
  $("log").innerHTML = "";
  $("text").value = "";
  view = null;
  sid = null;
  $("kioskWelcome").hidden = false;
  paintKioskWelcome();
}

/* ------------------------------------------------------- walked away */

/** A terminal nobody is using must not sit there holding somebody's
 *  address. Asked first, because a citizen thinking about what to write is
 *  not the same as a citizen who has left. */
function kioskTouch() {
  if (!kioskState.on) return;
  kioskState.askedIfStillThere = false;
  stopKioskIdle();
  const seconds = Math.max(30, Number(kioskState.idle_timeout_seconds) || 120);
  kioskState.idleTimer = setTimeout(() => {
    kioskState.askedIfStillThere = true;
    bubble("system", T().kioskStillThere);
    // Half as long again to answer, then the screen clears.
    kioskState.idleTimer = setTimeout(() => { void kioskRestart(); },
                                      (seconds / 2) * 1000);
  }, seconds * 1000);
}

function stopKioskIdle() {
  if (kioskState.idleTimer) { clearTimeout(kioskState.idleTimer); kioskState.idleTimer = null; }
}

for (const event of ["pointerdown", "keydown"]) {
  document.addEventListener(event, () => { if (kioskState.on) kioskTouch(); },
                            { passive: true });
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

/* Manual dictation and spoken responses are independent. Neither transcript
   events nor audio playback can call the petition workflow. */
const voice = { wants: false };
const typing = {
  phase: 'idle', epoch: 0, stream: null, ctx: null, node: null, socket: null,
  committedText: '', partialText: '', finals: new Set(), rendered: '', rate: 16000,
  timer: null, message: '', speaking: false, reading: false, responses: true, speechEpoch: 0,
  audio: null, speechAbort: null, speechUrl: null, lastReply: '',
};
try { typing.responses = localStorage.getItem('petition.voiceResponses') !== 'off'; } catch {}
function voiceWords() {
  return lang === 'ta' ? {
    start: 'குரல் தட்டச்சைத் தொடங்கு', stop: 'குரல் தட்டச்சை நிறுத்து',
    stopLabel: 'குரல் பதிவை நிறுத்து', listening: 'கேட்கிறேன்...', connecting: 'ஒலிவாங்கியைத் தயாரிக்கிறேன்...',
    finishing: 'குரல் உரையை முடிக்கிறேன்...', review: 'உரையைச் சரிபார்த்து, திருத்தி, அனுப்பு என்பதை அழுத்தவும்.',
    permission: 'குரல் தட்டச்சிற்கு ஒலிவாங்கி அனுமதி தேவை. நீங்கள் தொடர்ந்து தட்டச்சு செய்யலாம்.',
    unavailable: 'குரல் தட்டச்சு தற்காலிகமாகக் கிடைக்கவில்லை. உங்கள் பதிலைத் தட்டச்சு செய்யவும்.',
    speaking: 'பதிலை வாசிக்கிறேன்...', on: 'குரல் பதில்கள் ON', off: 'குரல் பதில்கள் OFF',
    audio: 'குரல் பதில் கிடைக்கவில்லை. கேள்வியைப் படித்து தொடர்ந்து பதிலளிக்கலாம்.',
    hear: 'இதை வாசித்துக் காட்டு', hearStop: 'வாசிப்பதை நிறுத்து',
    readDoc: 'வாசித்துக் காட்டு', readStop: 'நிறுத்து',
    reading: 'மனுவை வாசிக்கிறேன்...',
    limit: 'உரை முழுவதும் பாதுகாக்கப்பட்டுள்ளது. அனுப்புவதற்கு முன் 6,000 எழுத்துகளுக்குள் திருத்தவும்.',
  } : {
    start: 'Start voice typing', stop: 'Stop voice typing', stopLabel: 'Stop dictation',
    listening: 'Listening...', connecting: 'Preparing microphone...', finishing: 'Finishing dictation...',
    review: 'Review or edit your words, then press Send.',
    permission: 'Microphone access is required for voice typing. You can continue typing.',
    unavailable: 'Voice typing is temporarily unavailable. Please type your answer.',
    speaking: 'Reading the assistant’s response...', on: 'Voice Responses ON', off: 'Voice Responses OFF',
    audio: 'Spoken response unavailable. You can read the question and continue typing.',
    hear: 'Read this aloud', hearStop: 'Stop reading',
    readDoc: 'Read aloud', readStop: 'Stop',
    reading: 'Reading the petition...',
    limit: 'All text is preserved. Edit to 6,000 characters before sending.',
  };
}
function paintVoice() {
  const words = voiceWords();
  const active = typing.phase === 'recording';
  const pending = typing.phase === 'connecting' || typing.phase === 'finishing';
  const mic = $('micInline');
  mic.classList.toggle('dictating', active);
  mic.setAttribute('aria-pressed', String(active));
  mic.setAttribute('aria-label', active ? words.stopLabel : words.start);
  mic.title = active ? words.stop : words.start;
  mic.disabled = typing.speaking || pending || (!active && !canSend());
  $('mic').disabled = false;
  $('mic').setAttribute('aria-pressed', String(typing.responses));
  $('mic').title = typing.responses ? words.on : words.off;
  $('micText').textContent = typing.responses ? words.on : words.off;
  $('dictationStatus').textContent = typing.message || (typing.speaking ? words.speaking : active ? words.listening : pending ? (typing.phase === 'finishing' ? words.finishing : words.connecting) : '');
  if (active) $('text').placeholder = words.listening;
}
function joinDictation(a, b) {
  if (!a) return b;
  if (!b) return a;
  return a + (/\s$/.test(a) || /^[,.;:!?\s]/.test(b) ? '' : ' ') + b;
}
function releaseTypingAudio() {
  if (typing.node) { typing.node.onaudioprocess = null; try { typing.node.disconnect(); } catch {} typing.node = null; }
  if (typing.stream) { typing.stream.getTracks().forEach(track => track.stop()); typing.stream = null; }
  if (typing.ctx) { void typing.ctx.close().catch(() => {}); typing.ctx = null; }
}
function closeDictation(message = '') {
  typing.epoch++;
  clearTimeout(typing.timer);
  releaseTypingAudio();
  const socket = typing.socket; typing.socket = null;
  if (socket) { socket.onclose = null; try { socket.close(); } catch {} }
  typing.phase = 'idle'; voice.wants = false;
  typing.committedText = $('text').value; typing.partialText = '';
  typing.message = message;
  syncControls();
}
function stopVoice() { closeDictation(); stopPlayback(); }
function stopDictation() {
  if (typing.phase !== 'recording') return;
  releaseTypingAudio(); // The physical microphone stops immediately, before final STT.
  typing.phase = 'finishing'; voice.wants = false; typing.message = '';
  paintVoice();
  if (typing.socket?.readyState === 1) typing.socket.send(JSON.stringify({type:'dictation.stop'}));
  else { closeDictation(voiceWords().unavailable); return; }
  typing.timer = setTimeout(() => closeDictation(voiceWords().unavailable), 35000);
}
function acceptTranscript(message) {
  const id = String(message.segment);
  if (typing.finals.has(id)) return;
  // A keyboard edit wins even if an STT event was already queued.
  if ($('text').value !== typing.rendered) { closeDictation(); return; }
  const said = String(message.text || '').trim();
  if (message.type === 'stt.final') {
    typing.finals.add(id);
    // Preserve the last visible partial if a provider's final result is empty.
    typing.committedText = joinDictation(typing.committedText, said || typing.partialText);
    typing.partialText = '';
  } else typing.partialText = said;
  typing.rendered = joinDictation(typing.committedText, typing.partialText);
  $('text').value = typing.rendered;
  autoGrow(); syncControls();
  $('text').scrollTop = $('text').scrollHeight;
  if (typing.rendered.length > 6000) closeDictation(voiceWords().limit);
}
function resampleTo(input, inRate, outRate) {
  if (inRate === outRate) return input;
  const ratio = inRate / outRate, out = new Float32Array(Math.floor(input.length / ratio));
  for (let i=0;i<out.length;i++) {
    const start=Math.floor(i*ratio), end=Math.min(Math.floor((i+1)*ratio),input.length);
    let sum=0; for(let j=start;j<end;j++) sum+=input[j];
    out[i]=end>start ? sum/(end-start) : input[start]||0;
  }
  return out;
}
async function toggleDictation() {
  if (typing.phase === 'recording') { stopDictation(); return; }
  if (typing.phase !== 'idle' || typing.speaking || !canSend()) return;
  const epoch = ++typing.epoch;
  const session = sid;
  typing.phase='connecting'; typing.message=''; voice.wants=true;
  typing.committedText=$('text').value; typing.partialText=''; typing.rendered=$('text').value; typing.finals.clear();
  paintVoice();
  try {
    if (!navigator.mediaDevices?.getUserMedia) throw Error('unavailable');
    const stream = await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1}});
    if(epoch!==typing.epoch || session!==sid) {stream.getTracks().forEach(t=>t.stop());return;}
    typing.stream=stream;
    const ctx = new AudioContext(); typing.ctx=ctx;
    await ctx.resume();
    if(epoch!==typing.epoch) return;
    const socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws/dictation/${encodeURIComponent(sid)}`);
    typing.socket=socket;
    typing.timer=setTimeout(()=>{if(epoch===typing.epoch)closeDictation(voiceWords().unavailable);},20000);
    socket.onmessage=event=>{
      if(epoch!==typing.epoch) return;
      let message;try{message=JSON.parse(event.data);}catch{return;}
      if(message.type==='dictation.ready') {
        if(typing.phase!=='connecting')return;
        clearTimeout(typing.timer);typing.rate=message.sample_rate||16000;
        const source=ctx.createMediaStreamSource(stream), node=ctx.createScriptProcessor(4096,1,1), mute=ctx.createGain();
        typing.node=node;mute.gain.value=0;source.connect(node);node.connect(mute);mute.connect(ctx.destination);
        node.onaudioprocess=e=>{
          if(epoch!==typing.epoch || typing.phase!=='recording' || socket.readyState!==1)return;
          if(socket.bufferedAmount>1024*1024){closeDictation(voiceWords().unavailable);return;}
          const samples=resampleTo(e.inputBuffer.getChannelData(0),ctx.sampleRate,typing.rate), pcm=new Int16Array(samples.length);
          for(let i=0;i<samples.length;i++)pcm[i]=Math.max(-1,Math.min(1,samples[i]))*32767;
          socket.send(pcm.buffer);
        };
        typing.phase='recording';paintVoice();
      } else if(message.type==='stt.partial'||message.type==='stt.final')acceptTranscript(message);
      else if(message.type==='dictation.stopped')closeDictation(voiceWords().review);
      else if(message.type==='error')closeDictation(voiceWords().unavailable);
    };
    socket.onclose=()=>{if(epoch===typing.epoch)closeDictation(voiceWords().unavailable);};
    socket.onerror=()=>{if(epoch===typing.epoch)closeDictation(voiceWords().unavailable);};
    stream.getTracks().forEach(track=>track.onended=()=>{if(epoch===typing.epoch && typing.phase==='recording')stopDictation();});
  } catch(error) {
    if(epoch===typing.epoch)closeDictation(error.name==='NotAllowedError'||error.name==='SecurityError'?voiceWords().permission:voiceWords().unavailable);
  }
}
function stopPlayback() {
  typing.speechEpoch++;
  typing.reading = false;
  typing.speechAbort?.abort(); typing.speechAbort=null;
  if(typing.audio){typing.audio.pause();typing.audio.removeAttribute('src');typing.audio.load();typing.audio=null;}
  if(typing.speechUrl){URL.revokeObjectURL(typing.speechUrl);typing.speechUrl=null;}
  typing.speaking=false;paintVoice();
}
/* ONE PLAYBACK PATH for all three things that speak: the reply that arrives
   on its own, a question said again from its speaker icon, and the finished
   petition read section by section. They share `typing.speechEpoch`, so
   starting any of them silences the others, and they share `typing.speaking`,
   so the microphone stays disabled for the whole of it — which is the only
   self-transcription guard this design needs. */
function playClip(blob, epoch) {
  return new Promise(resolve => {
    typing.speechUrl = URL.createObjectURL(blob);
    const audio = new Audio(typing.speechUrl);
    typing.audio = audio;
    const done = ok => { if (epoch === typing.speechEpoch) syncControls(); resolve(ok); };
    audio.onended = () => done(true);
    audio.onerror = () => done(false);
    audio.play().catch(() => done(false));
  });
}

/** Fetch one piece of speech and play it to the end. Resolves false when
 *  anything went wrong or a newer request has taken over. */
async function speakFrom(url, epoch) {
  const controller = new AbortController();
  typing.speechAbort = controller;
  const timeout = setTimeout(() => controller.abort(), 25000);
  try {
    const response = await fetch(url, {signal: controller.signal, cache: 'no-store'});
    if (!response.ok) throw Error('audio unavailable');
    const blob = await response.blob();
    if (epoch !== typing.speechEpoch) return false;
    clearTimeout(timeout);
    return await playClip(blob, epoch);
  } catch {
    return false;
  } finally { clearTimeout(timeout); }
}

/** Say one thing, from wherever. Used by the speaker icons and the reply. */
async function speakOnce(url) {
  closeDictation(); stopPlayback();
  const epoch = typing.speechEpoch;
  typing.speaking = true; typing.message = ''; paintVoice();
  const ok = await speakFrom(url, epoch);
  if (epoch !== typing.speechEpoch) return;
  stopPlayback();
  if (!ok) { typing.message = voiceWords().audio; paintVoice(); }
}

/* THE FINISHED PETITION, read out.
   Section by section rather than in one request: a petition runs past what
   a speech service takes at once, and a citizen who has heard enough can
   stop between sections instead of waiting out the whole document. */
async function readPetition() {
  if (typing.reading) { typing.reading = false; stopPlayback(); syncControls(); return; }
  if (!sid) return;
  closeDictation(); stopPlayback();
  const epoch = typing.speechEpoch;
  typing.reading = true; typing.speaking = true;
  typing.message = voiceWords().reading; paintVoice(); syncControls();
  let index = 0;
  while (typing.reading && epoch === typing.speechEpoch) {
    const ok = await speakFrom(
      `/api/sessions/${encodeURIComponent(sid)}/speech?section=${index}`, epoch);
    if (!ok) break;            // ran off the end of the document, or failed
    index++;
  }
  if (epoch !== typing.speechEpoch) return;
  typing.reading = false;
  stopPlayback();
  if (!index) { typing.message = voiceWords().audio; paintVoice(); }
  syncControls();
}

async function speakReply(v, force=false) {
  const key=`${v.session_id}:${v.transcript?.length}:${v.reply}`;
  if(!typing.responses || !v.reply || v.status==='generating' || (!force&&typing.lastReply===key))return;
  typing.lastReply=key;
  closeDictation();stopPlayback();
  const epoch=typing.speechEpoch;
  typing.speaking=true;typing.message='';paintVoice();
  const controller=new AbortController();typing.speechAbort=controller;
  let timeout=setTimeout(()=>controller.abort(),25000);
  try {
    const response=await fetch(`/api/sessions/${encodeURIComponent(v.session_id)}/speech`,{signal:controller.signal,cache:'no-store'});
    if(!response.ok)throw Error('audio unavailable');
    const blob=await response.blob();
    if(epoch!==typing.speechEpoch)return;
    clearTimeout(timeout);
    typing.speechUrl=URL.createObjectURL(blob);
    const audio=new Audio(typing.speechUrl);typing.audio=audio;
    const finished=()=>{if(epoch===typing.speechEpoch){stopPlayback();syncControls();}};
    audio.onended=finished;audio.onerror=()=>{if(epoch===typing.speechEpoch){finished();typing.message=voiceWords().audio;paintVoice();}};
    await audio.play();
  } catch(error) {
    if(epoch===typing.speechEpoch){stopPlayback();typing.message=voiceWords().audio;paintVoice();}
  } finally {clearTimeout(timeout);}
}
$('mic').onclick=()=>{
  typing.responses=!typing.responses;
  try{localStorage.setItem('petition.voiceResponses',typing.responses?'on':'off');}catch{}
  if(typing.responses && view)void speakReply(view,true);else stopPlayback();
  paintVoice();
};
$("readBtn").onclick = () => { void readPetition(); };
$('micInline').onclick=toggleDictation;
// Editing, Send and navigation invalidate late results, preserving visible text.
$('text').addEventListener('input',()=>{if(typing.phase!=='idle')closeDictation();});
window.addEventListener('pagehide',stopVoice);
$('withEnclosures').onchange=()=>{if(view)drawOutcome(view);};

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

// Which document the centre shows. The scroll position is left alone on
// purpose: a citizen switching back to the package expects to be where they
// were, not thrown to the top of a hundred pages.
$("modeLetter")?.addEventListener("click", () => setPreviewMode(false));
$("modePackage")?.addEventListener("click", () => {
  setPreviewMode(true);
  if (view) drawPackagePages(view);
});
// The page indicator follows the scroll. Throttled to animation frames so a
// long document does not recompute it on every scroll event.
let indicatorPending = false;
function watchScroll(target) {
  target?.addEventListener("scroll", () => {
    if (indicatorPending) return;
    indicatorPending = true;
    requestAnimationFrame(() => { indicatorPending = false; updatePageIndicator(); });
  }, { passive: true });
}
watchScroll(window);

$("retryConnection")?.addEventListener("click", recover);
$("detailsToggle")?.addEventListener("click", () => {
  const workspace = document.querySelector("main.workspace");
  const open = workspace.classList.toggle("details-open");
  $("detailsToggle").setAttribute("aria-expanded", String(open));
  $("detailsToggleText").textContent = open ? X().conversation : X().details;
  if (open) $("detailsPanel").scrollIntoView({ behavior: "smooth", block: "start" });
});
$("helpBtn")?.addEventListener("click", () => {
  explain(X().helpTitle, X().helpSteps, X().helpNote, X().close);
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

// The attached documents, drawn after the letter.
//
// WHY. The letter says "Enclosures: 1. Copy of earlier petition" and stops.
// The generated document really does carry the pages — a two-page petition
// with a two-page attachment comes out as four pages plus an index — but the
// only way to discover that was to download the file and open it. A citizen
// at a counter reported the attachment as missing for exactly this reason,
// and they were right about what they could see.
//
// This shows the file itself, with its page count, so "it is attached" is
// something they can check rather than something they are told.
// The signature of what is currently drawn, so a repaint that changes
// nothing does not restart an attachment download.
let enclosureKey = "";

// ---------------------------------------------------------------------------
// The continuous combined-package preview
// ---------------------------------------------------------------------------
//
// WHAT THIS REPLACES. The centre used to show the petition and, underneath
// it, a card saying a document was attached. That told the citizen the file
// existed; it did not show it to them. This draws the package the way it
// will be filed — petition, index, then the originals — as one scrollable
// run of pages.
//
// HOW IT SURVIVES A HUNDRED PAGES. The server renders one page at a time as
// an image and the browser asks for them as they come into view. Nothing is
// inlined into the HTML, the browser's PDF plugin is not involved, and a
// 103-page annexure costs one request per page the citizen actually scrolls
// to. Pages already drawn stay drawn; pages never reached are never fetched.
let packageMode = true;          // Full Package is the default once attached
let packageState = { sid: "", version: "", total: 0 };
let pageWatcher = null;

function packageWatcher() {
  if (pageWatcher) return pageWatcher;
  if (typeof IntersectionObserver !== "function") return null;
  // THE ROOT IS THE VIEWPORT, and that was established by measuring rather
  // than by reading the stylesheet. `.paper-wrap` carries `overflow-y:auto`,
  // which makes it look like the scrolling element, but at the layout this
  // page actually uses it computes to `visible` and grows to fit: measured
  // at 27535px tall with clientHeight == scrollHeight. The window scrolls.
  //
  // Rooting the observer on that element was tried and is much worse than
  // wrong — every sheet is inside it at all times, so all 103 pages of a
  // hundred-page annexure loaded at once, which is the exact thing this
  // observer exists to prevent.
  pageWatcher = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) loadPackagePage(entry.target);
    });
    // One screen of margin above and below, so scrolling at a normal speed
    // never shows an empty sheet.
  }, { root: null, rootMargin: "800px 0px", threshold: 0.01 });
  return pageWatcher;
}

function loadPackagePage(sheet) {
  if (!sheet || sheet.dataset.loaded === "1" || sheet.dataset.loading === "1") return;
  const number = sheet.dataset.page;
  const url = sheet.dataset.url;
  if (!number || !url) return;
  sheet.dataset.loading = "1";

  const image = new Image();
  image.className = "pp-image";
  image.alt = (T().packagePageAlt || "Page {n}").replace("{n}", number);
  image.decoding = "async";
  image.onload = () => {
    sheet.dataset.loaded = "1";
    delete sheet.dataset.loading;
    sheet.replaceChildren(image);
    packageWatcher()?.unobserve(sheet);
  };
  image.onerror = () => {
    // One page failing must not cost the citizen the whole preview.
    delete sheet.dataset.loading;
    const t = T();
    const note = document.createElement("div");
    note.className = "pp-failed";
    const said = document.createElement("p");
    said.textContent = t.packagePageFailed;
    note.appendChild(said);
    const open = document.createElement("a");
    open.className = "btn off";
    open.href = sheet.dataset.original || url;
    open.target = "_blank";
    open.rel = "noopener";
    open.textContent = t.packageOpenOriginal;
    note.appendChild(open);
    sheet.replaceChildren(note);
  };
  image.src = url;
}

function packageSheet(entry, pageUrl, t) {
  const wrap = document.createElement("div");
  wrap.className = "pp-page";

  // A boundary at the top of each attachment, so a citizen scrolling can see
  // where their own letter ends and the document they brought begins.
  if (entry.section === "attachment" && entry.first) {
    const divider = document.createElement("div");
    divider.className = "pp-divider";
    const which = document.createElement("span");
    which.className = "pp-divider-label";
    which.textContent = `${t.attachmentWord} ${entry.attachment}`;
    divider.appendChild(which);
    const name = document.createElement("strong");
    // The package labels its index entries "1. Copy of earlier petition".
    // The divider already says which attachment this is, so the ordinal is
    // dropped here rather than printed twice.
    name.textContent = String(entry.label || entry.filename || "")
      .replace(/^\s*\d+\.\s*/, "");
    divider.appendChild(name);
    wrap.appendChild(divider);
  }

  const sheet = document.createElement("div");
  sheet.className = "pp-sheet";
  sheet.dataset.page = String(entry.page);
  sheet.dataset.url = pageUrl.replace("{n}", String(entry.page));
  // A skeleton rather than a blank white block: "do not leave blank white
  // blocks with no indication".
  const loading = document.createElement("div");
  loading.className = "pp-loading";
  loading.textContent = t.packagePageLoading;
  sheet.appendChild(loading);
  wrap.appendChild(sheet);

  const number = document.createElement("p");
  number.className = "pp-number";
  number.textContent = String(entry.page);
  wrap.appendChild(number);
  return { wrap, sheet };
}

async function drawPackagePages(v) {
  const box = $("packagePages");
  if (!box) return;
  const t = T();
  const sid = v.session_id || "";
  const version = String(v.document?.version || v.version || 1);
  const enclosed = (v.attachments?.items || []).length;

  if (!sid || !enclosed) { box.hidden = true; box.replaceChildren(); return; }
  // Already drawn for this exact petition version — leave it alone, so that
  // scrolling is not reset and drawn pages are not re-fetched on a repaint.
  if (packageState.sid === sid && packageState.version === version
      && box.childElementCount) return;

  box.replaceChildren();
  const waiting = document.createElement("p");
  waiting.className = "pp-status";
  waiting.textContent = t.packageBuilding;
  box.appendChild(waiting);

  let plan;
  try {
    const response = await fetch(
      `/api/sessions/${encodeURIComponent(sid)}/document/package/pages`,
      { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    plan = await response.json();
  } catch (error) {
    // The package could not be built — most often because this server has no
    // PDF engine. Say so, and keep the petition preview usable.
    box.replaceChildren();
    const failed = document.createElement("p");
    failed.className = "pp-status";
    failed.textContent = t.packageUnavailable;
    box.appendChild(failed);
    setPreviewMode(false, true);
    return;
  }

  packageState = { sid, version, total: plan.total || 0 };
  box.replaceChildren();
  const watcher = packageWatcher();
  (plan.pages || []).forEach((entry) => {
    const { wrap, sheet } = packageSheet(entry, plan.page_url, t);
    box.appendChild(wrap);
    if (watcher) watcher.observe(sheet);
    else loadPackagePage(sheet);          // no observer: draw them all
  });

  // Anything that could not be merged is named rather than quietly dropped.
  (plan.not_included || []).forEach((item) => {
    const wrap = document.createElement("div");
    wrap.className = "pp-page";
    const sheet = document.createElement("div");
    sheet.className = "pp-sheet pp-sheet-note";
    const name = document.createElement("strong");
    name.textContent = item.label || item.filename || "";
    sheet.appendChild(name);
    const why = document.createElement("p");
    why.textContent = t.packageNotMerged;
    sheet.appendChild(why);
    wrap.appendChild(sheet);
    box.appendChild(wrap);
  });

  box.hidden = !packageMode;
  updatePageIndicator();
}

function setPreviewMode(full, force) {
  packageMode = Boolean(full);
  const letterBox = $("letter");
  const pages = $("packagePages");
  const enclosures = $("enclosures");
  if (pages) pages.hidden = !packageMode;
  // The letter's own sheet is the Petition Only view. In package mode the
  // petition pages are drawn as images like everything else, so showing both
  // would print the letter twice.
  const sheet = document.querySelector(".paper-sheet");
  if (sheet) sheet.hidden = packageMode;
  if (letterBox) letterBox.setAttribute("aria-hidden", packageMode ? "true" : "false");
  if (enclosures) enclosures.hidden = packageMode || !enclosures.childElementCount;
  const t = T();
  $("modeLetter")?.setAttribute("aria-pressed", packageMode ? "false" : "true");
  $("modePackage")?.setAttribute("aria-pressed", packageMode ? "true" : "false");
  $("modeLetter")?.classList.toggle("on", !packageMode);
  $("modePackage")?.classList.toggle("on", packageMode);
  if ($("modeLetter")) $("modeLetter").textContent = t.modeLetter;
  if ($("modePackage")) $("modePackage").textContent = t.modePackage;
  updatePageIndicator();
  if (force) {
    $("modePackage")?.setAttribute("disabled", "disabled");
  }
}

// "Page 41 of 103", from whichever sheet is nearest the middle of the view.
function updatePageIndicator() {
  const label = $("pageIndicator");
  if (!label) return;
  if (!packageMode || !packageState.total) { label.textContent = ""; return; }
  const sheets = document.querySelectorAll("#packagePages .pp-sheet[data-page]");
  let current = 1;
  // The viewport, for the same reason the observer uses it.
  const middle = window.innerHeight / 2;
  sheets.forEach((sheet) => {
    const box = sheet.getBoundingClientRect();
    if (box.top <= middle) current = Number(sheet.dataset.page) || current;
  });
  label.textContent = T().pageOf
    .replace("{n}", current).replace("{total}", packageState.total);
}

function drawEnclosures(attachments) {
  // `T()` per call, the way every other painter here does it. Reaching for a
  // bare `t` compiled fine and then threw ReferenceError at runtime, which
  // aborted `paint()` partway: the enclosure box was emptied, and everything
  // after this call — the download links, the emblem, the toolbar buttons —
  // never ran, so the whole toolbar rendered disabled. A real browser found
  // it; no unit test would have.
  const t = T();
  const box = $("enclosures");
  if (!box) return;
  const items = (attachments && attachments.items) || [];

  // REBUILT ONLY WHEN SOMETHING CHANGED. `paint()` runs on every state
  // update, and tearing the DOM down each time cancelled the <iframe>'s
  // in-flight PDF request and started it again — two aborted fetches for one
  // attachment, measured in the browser. On a large scan over a slow link
  // that is a preview which restarts forever and never draws.
  const key = JSON.stringify([
    items.map((a) => [a.attachment_id, a.pages, a.label, a.file_url]),
    editingLetter, t.enclosuresHeading,
  ]);
  if (key === enclosureKey) return;
  enclosureKey = key;

  box.replaceChildren();
  if (!items.length || editingLetter) { box.hidden = true; return; }
  box.hidden = false;

  const heading = document.createElement("h3");
  heading.className = "enclosures-title";
  heading.textContent = t.enclosuresHeading;
  box.appendChild(heading);

  items.forEach((item, index) => {
    const card = document.createElement("figure");
    card.className = "enclosure";

    const caption = document.createElement("figcaption");
    const name = document.createElement("strong");
    name.textContent = `${index + 1}. ${item.label || item.filename || ""}`;
    caption.appendChild(name);

    const detail = document.createElement("span");
    detail.className = "enclosure-detail";
    // The page count is the part that answers the question. Omitted rather
    // than guessed when the file could not be read — a wrong count is worse
    // than none, because it is checked against paper in somebody's hand.
    const pages = Number(item.pages) || 0;
    detail.textContent = [
      item.filename,
      fileType(item.content_type, item.filename),
      pages ? (pages === 1 ? t.onePage : t.manyPages.replace("{n}", pages)) : "",
    ].filter(Boolean).join(" · ");
    caption.appendChild(detail);
    card.appendChild(caption);

    // A PHOTOGRAPH IS SHOWN, A PDF IS NOT, and that is a decision rather
    // than an omission. An image is one cheap request and seeing it is the
    // whole point — a citizen recognises their own photograph instantly.
    //
    // Embedding a PDF meant handing Chromium's PDF plugin an attachment that
    // may be a hundred pages, inside a preview the citizen is scrolling. It
    // also re-issued its own request every time, which showed up as aborted
    // fetches in the browser. The card carries what identifies the document
    // — name, type, page count — and View opens it properly in its own tab.
    const type = String(item.content_type || "");
    if (item.file_url && type.startsWith("image/")) {
      const img = document.createElement("img");
      img.className = "enclosure-view";
      img.src = item.file_url;
      img.alt = item.label || item.filename || "";
      img.loading = "lazy";
      card.appendChild(img);
    } else if (!item.readable) {
      const note = document.createElement("p");
      note.className = "enclosure-note";
      note.textContent = t.enclosureUnreadable;
      card.appendChild(note);
    }

    if (item.file_url) {
      const actions = document.createElement("div");
      actions.className = "enclosure-actions";
      // Open it, or take it away. Both are the citizen's own file, served
      // from their own session — see `attachment_file` in `rest.py`.
      const open = document.createElement("a");
      open.className = "btn off";
      open.href = item.file_url;
      open.target = "_blank";
      open.rel = "noopener";
      open.textContent = t.enclosureView;
      actions.appendChild(open);

      const save = document.createElement("a");
      save.className = "btn off";
      save.href = `${item.file_url}?download=1`;
      save.setAttribute("download", item.filename || "");
      save.textContent = t.enclosureDownload;
      actions.appendChild(save);
      card.appendChild(actions);
    }

    const foot = document.createElement("p");
    foot.className = "enclosure-note";
    foot.textContent = t.enclosureIncluded;
    card.appendChild(foot);
    box.appendChild(card);
  });
}

// "PDF", "PNG", "JPEG" — what the citizen would call it, from the declared
// type and the filename as a fallback. Shown because "2 pages" alone does
// not tell somebody whether the thing they attached is the scan or the photo.
function fileType(contentType, filename) {
  const known = {
    "application/pdf": "PDF", "image/png": "PNG", "image/jpeg": "JPEG",
    "image/webp": "WEBP", "text/plain": "TXT",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
  };
  const byType = known[String(contentType || "")];
  if (byType) return byType;
  const ext = String(filename || "").split(".").pop();
  return ext && ext.length <= 5 && ext !== filename ? ext.toUpperCase() : "";
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


