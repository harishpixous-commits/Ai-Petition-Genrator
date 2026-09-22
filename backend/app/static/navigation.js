/* Page navigation and saved-petition browsing. The existing generator remains
   the only editor; every card opens its persisted server session. */
const NAV = {
  en: {
    home: "Home", create: "Create Petition", petitions: "My Petitions", view: "View", edit: "Edit",
    search: "Search reference, petitioner or subject", all: "All", language: "Language",
    department: "Department", category: "Category", status: "Status", from: "From date", to: "To date",
    newest: "Newest", oldest: "Oldest", updated: "Recently updated", clear: "Clear filters",
    generated: "Generated", updatedStatus: "Updated", draft: "Draft", failed: "Requires attention",
    cancelled: "Cancelled", generating: "Preparing", current: "Current", version: "Version",
    history: "Version history", noResults: "No petitions match your search.",
    noResultsText: "Try a different reference, name, date, or filter.",
    empty: "Your petitions will appear here.", emptyText: "Create a petition and generate its document to save it here.",
    error: "We couldn’t load your petitions. Check the connection and try again.", retry: "Try again",
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
    homeDescription: "Turn the details of your concern into a clear petition. Get guided help in English or Tamil, review every detail, and keep your documents in one place.",
    homeLanguage: "English & Tamil",
    homeReview: "Review before downloading",
    homeCaption: "From your words to a clear document",
    homeCreateEyebrow: "START SOMETHING NEW",
    homeCreateTitle: "Create a petition",
    homeCreateDescription: "A guided conversation, a complete draft, and a document ready for your review.",
    homePetitionsEyebrow: "PICK UP WHERE YOU LEFT OFF",
    homePetitionsTitle: "My petitions",
    homePetitionsDescription: "Find, open, and manage your saved petitions, with their documents and versions.",
    homeGuideEyebrow: "THREE SIMPLE STEPS",
    homeGuideTitle: "A little guidance, all the way.",
    homeStepOneTitle: "Share your concern",
    homeStepOneText: "Answer a few questions and add supporting documents if you have them.",
    homeStepTwoTitle: "Make it yours",
    homeStepTwoText: "Check your details, review the draft, and make any changes you need.",
    homeStepThreeTitle: "Download & keep",
    homeStepThreeText: "Save your document and return to My Petitions whenever you need it.",
    petitionsEyebrow: "YOUR DOCUMENT WORKSPACE", petitionsTitle: "My petitions",
    petitionsDescription: "Find a petition, review its details, and pick up where you left off.",
    petitionsCreateText: "Create petition",
    petitionsLoadingTitle: "Loading your petitions",
    petitionsLoadingText: "Getting your saved documents ready.",
    petitionsEmptyCreate: "Create your first petition",
    petitionsErrorTitle: "We couldn’t load your petitions",
    filterTitle: "Find a petition", loading: "Loading saved petitions…", sort: "Sort by",
    resultsNote: "Saved documents and drafts",
    selectAll: "Select all", selectAllMatching: "Select all {n}", selectedCount: "{n} selected",
    clearSelection: "Clear selection", deleteLabel: "Delete", deleting: "Deleting…",
    pickLabel: "Select petition {ref}",
    deleteTitle: "Delete permanently?",
    deleteOne: "This petition, its document and anything attached to it will be removed from this computer. This cannot be undone.",
    deleteMany: "These {n} petitions, their documents and anything attached to them will be removed from this computer. This cannot be undone.",
    deleteKeep: "Keep", deleteGo: "Delete permanently",
    deleteDone: "{n} deleted.", deleteNothing: "Nothing was deleted — those petitions were already gone.",
    deleteFailed: "Those petitions could not be deleted. Try again.",
    deletePartial: "{n} deleted, {f} could not be.",
  },
  ta: {
    home: "முகப்பு", create: "மனு உருவாக்கு", petitions: "எனது மனுக்கள்", view: "காண்க", edit: "திருத்து",
    search: "தொடர்பு எண், பெயர் அல்லது பொருள் தேடவும்", all: "அனைத்தும்", language: "மொழி",
    department: "துறை", category: "வகை", status: "நிலை", from: "தொடக்கத் தேதி", to: "முடிவுத் தேதி",
    newest: "புதியவை முதலில்", oldest: "பழையவை முதலில்", updated: "சமீபத்திய திருத்தம்", clear: "வடிகட்டிகளை நீக்கு",
    generated: "தயாரிக்கப்பட்டது", updatedStatus: "புதுப்பிக்கப்பட்டது", draft: "வரைவு", failed: "கவனம் தேவை",
    cancelled: "ரத்து", generating: "தயாராகிறது", current: "தற்போதையது", version: "பதிப்பு",
    history: "பதிப்பு வரலாறு", noResults: "உங்கள் தேடலுக்கு மனுக்கள் இல்லை.",
    noResultsText: "வேறு எண், பெயர், தேதி அல்லது வடிகட்டியை முயற்சிக்கவும்.",
    empty: "உங்கள் மனுக்கள் இங்கே தோன்றும்.", emptyText: "மனுவை உருவாக்கி ஆவணத்தைத் தயாரித்ததும் இங்கே சேமிக்கப்படும்.",
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
    homePetitionsEyebrow: "நிறுத்திய இடத்திலிருந்து தொடருங்கள்",
    homePetitionsTitle: "எனது மனுக்கள்",
    homePetitionsDescription: "சேமித்த மனுக்களை அவற்றின் ஆவணங்கள் மற்றும் பதிப்புகளுடன் தேடலாம், திறக்கலாம், நிர்வகிக்கலாம்.",
    homeGuideEyebrow: "மூன்று எளிய படிகள்",
    homeGuideTitle: "ஒவ்வொரு படியிலும் வழிகாட்டுதல்.",
    homeStepOneTitle: "உங்கள் குறையைச் சொல்லுங்கள்",
    homeStepOneText: "சில கேள்விகளுக்குப் பதிலளியுங்கள்; ஆதார ஆவணங்கள் இருந்தால் இணைக்கலாம்.",
    homeStepTwoTitle: "உங்களுக்கேற்ப மாற்றுங்கள்",
    homeStepTwoText: "உங்கள் விவரங்களைச் சரிபாருங்கள், வரைவைப் படித்து, தேவையான மாற்றங்களைச் செய்யுங்கள்.",
    homeStepThreeTitle: "பதிவிறக்கிப் பாதுகாக்கவும்",
    homeStepThreeText: "ஆவணத்தைச் சேமித்து, தேவைப்படும்போது எனது மனுக்கள் பகுதிக்குத் திரும்பலாம்.",
    petitionsEyebrow: "உங்கள் ஆவணப் பணியிடம்", petitionsTitle: "எனது மனுக்கள்",
    petitionsDescription: "மனுவைத் தேடி, விவரங்களைப் பார்த்து, நிறுத்திய இடத்திலிருந்து தொடரலாம்.",
    petitionsCreateText: "மனு உருவாக்கு",
    petitionsLoadingTitle: "உங்கள் மனுக்கள் ஏற்றப்படுகின்றன",
    petitionsLoadingText: "சேமித்த ஆவணங்கள் தயாராகின்றன.",
    petitionsEmptyCreate: "உங்கள் முதல் மனுவை உருவாக்குங்கள்",
    petitionsErrorTitle: "மனுக்களைப் பெற இயலவில்லை",
    filterTitle: "மனுவைத் தேடு", loading: "மனுக்கள் ஏற்றப்படுகின்றன…", sort: "வரிசை",
    resultsNote: "சேமித்த ஆவணங்களும் வரைவுகளும்",
    selectAll: "அனைத்தையும் தேர்வு", selectAllMatching: "{n} அனைத்தையும் தேர்வு",
    selectedCount: "{n} தேர்வு செய்யப்பட்டது",
    clearSelection: "தேர்வை நீக்கு", deleteLabel: "நீக்கு", deleting: "நீக்கப்படுகிறது…",
    pickLabel: "{ref} மனுவைத் தேர்வு செய்",
    deleteTitle: "நிரந்தரமாக நீக்கவா?",
    deleteOne: "இந்த மனு, அதன் ஆவணம் மற்றும் இணைப்புகள் இந்தக் கணினியிலிருந்து நீக்கப்படும். இதை மீட்க முடியாது.",
    deleteMany: "இந்த {n} மனுக்கள், அவற்றின் ஆவணங்கள் மற்றும் இணைப்புகள் இந்தக் கணினியிலிருந்து நீக்கப்படும். இதை மீட்க முடியாது.",
    deleteKeep: "வேண்டாம்", deleteGo: "நிரந்தரமாக நீக்கு",
    deleteDone: "{n} நீக்கப்பட்டது.", deleteNothing: "எதுவும் நீக்கப்படவில்லை — அவை ஏற்கெனவே இல்லை.",
    deleteFailed: "இந்த மனுக்களை நீக்க இயலவில்லை. மீண்டும் முயற்சிக்கவும்.",
    deletePartial: "{n} நீக்கப்பட்டது, {f} நீக்க இயலவில்லை.",
  },
};
const N = () => NAV[lang];
let currentRoute = "home";
let petitionPage = 1;
let listRequest = 0;
let listController = null;
let searchTimer = null;
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
const picked = new Set();
let listNotice = "";
let deleting = false;
let lastListTotal = 0;

function navigationLabels() {
  const n = N();
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.dataset.i18n;
    if (n[key]) el.textContent = n[key];
  });
  for (const [id, text] of Object.entries({ navHome: n.home, navCreate: n.create,
    navPetitions: n.petitions, clearFilters: n.clear,
    petitionsRetry: n.retry, petitionsPrevious: n.previous, petitionsNext: n.next })) {
    if ($(id)) $(id).textContent = text;
  }
  if ($("petitionSearch")) $("petitionSearch").placeholder = n.search;
  for (const [id, text] of Object.entries({ selectAllText: n.selectAll,
    clearSelection: n.clearSelection, deleteSelectedText: n.deleteLabel,
    petitionsResultsNote: listNotice || n.resultsNote })) {
    if ($(id)) $(id).textContent = text;
  }
  syncSelection();
  if ($("petitionSort")) for (const option of $("petitionSort").options) option.textContent = n[option.value];
  for (const id of ["filterDepartment", "filterCategory", "filterStatus", "filterLanguage"]) {
    const first = $(id)?.querySelector('option[value=""]');
    if (first) first.textContent = n.all;
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
  $("mic").hidden = currentRoute !== "generator";
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
  $("petitionsPage").hidden = route !== "petitions";
  $("generatorPage").hidden = route !== "generator";
  routeHash = hash;
  if (location.hash !== hash) window.history[replace ? "replaceState" : "pushState"](null, "", hash);
  document.title = `${route === "home" ? N().home : route === "petitions" ? N().petitions : (view?.document?.reference || N().create)} · ${T().title}`;
  syncNavigation();
  window.scrollTo({ top: 0, behavior: "instant" });
}

function showGenerator(id, replace = false) { setPage("generator", `#petition/${id}`, replace); }

async function navigate(route, options = {}) {
  if (requestPending || busy) return;
  if (!options.checked && !guardUnsaved(() => navigate(route, { ...options, checked: true }))) return;
  if (editingLetter) stopEditing(true);
  stopVoice();
  if (route === "create") { await start(); return; }
  if (route === "generator") { await openPetition(options.id, options.edit, options.replace); return; }
  setPage(route === "petitions" ? "petitions" : "home", route === "petitions" ? "#petitions" : "#home", options.replace);
  if (route === "petitions") await loadPetitions();
}

async function openPetition(id, edit = false, replace = false) {
  if (requestPending || !/^[\da-f-]{36}$/i.test(id || "")) return;
  requestPending = true; syncControls();
  const result = await api(`/api/sessions/${id}`, { timeout: 30000, quiet: true });
  requestPending = false;
  if (!result) {
    if (currentRoute === "petitions") {
      $("petitionsError").hidden = false;
      $("petitionsErrorText").textContent = N().openError;
    } else {
      setPage("generator", `#petition/${id}`, replace);
      connectionNotice([404, 410].includes(lastApiStatus) ? X().expired : X().offline);
    }
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

async function loadPetitions() {
  if (!$("petitionsList")) return;
  const request = ++listRequest;
  listController?.abort();
  listController = new AbortController();
  const params = new URLSearchParams({ page: String(petitionPage), page_size: "12" });
  for (const [id, name] of Object.entries(FILTER_PARAMS)) {
    const value = $(id).value.trim();
    if (value) params.set(name, value);
  }
  const from = $("filterDateFrom").value, to = $("filterDateTo").value;
  $("filterDateTo").setCustomValidity(from && to && from > to ? N().dateError : "");
  if (!$("petitionFilters").reportValidity()) return;
  $("petitionsLoading").hidden = false;
  $("petitionsError").hidden = true;
  $("petitionsEmpty").hidden = true;
  $("petitionsPagination").hidden = true;
  $("petitionsList").replaceChildren();
  $("petitionsList").setAttribute("aria-busy", "true");
  const timer = setTimeout(() => listController?.abort(), 30000);
  try {
    const response = await fetch(`/api/petitions?${params}`, { cache: "no-store", signal: listController.signal });
    if (!response.ok) throw new Error("catalog unavailable");
    const data = await response.json();
    if (request !== listRequest) return;
    drawPetitions(data);
  } catch {
    if (request !== listRequest) return;
    $("petitionsError").hidden = false;
    $("petitionsErrorText").textContent = N().error;
    $("petitionCount").textContent = "";
  } finally {
    clearTimeout(timer);
    if (request === listRequest) {
      $("petitionsLoading").hidden = true;
      $("petitionsList").setAttribute("aria-busy", "false");
    }
  }
}

function dateLabel(value, time = false) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(lang === "ta" ? "ta-IN" : "en-IN", {
    day: "numeric", month: "short", year: "numeric", ...(time ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(date);
}

function statusLabel(key) {
  const map = { generated: N().generated, updated: N().updatedStatus, draft: N().draft,
    ready: N().generated, collecting: N().draft, confirming: N().draft, attachments: N().draft,
    failed: N().failed, cancelled: N().cancelled, generating: N().generating };
  return map[String(key || "").toLowerCase()] || key;
}

function fillFilter(id, values, label = value => value) {
  const el = $(id), selected = el.value;
  el.replaceChildren(new Option(N().all, ""));
  const available = [...new Set(values || [])];
  if (selected && !available.includes(selected)) available.push(selected);
  for (const value of available) el.add(new Option(label(value), value));
  el.value = selected;
}

function phrase(template, values) {
  return String(template || "").replace(/\{(\w+)\}/g,
    (whole, key) => (key in values ? String(values[key]) : whole));
}

/** Every tick box currently drawn, page by page. */
function pickBoxes() {
  return [...document.querySelectorAll("#petitionsList input[data-pick]")];
}

function syncSelection() {
  const n = N(), boxes = pickBoxes(), count = picked.size;
  if ($("petitionSelection")) $("petitionSelection").hidden = count === 0;
  if ($("selectAllWrap")) $("selectAllWrap").hidden = boxes.length === 0;
  if ($("selectionCount")) {
    $("selectionCount").textContent = deleting ? n.deleting
      : phrase(n.selectedCount, { n: count.toLocaleString(lang) });
  }
  const all = $("selectAllPetitions");
  if (all) {
    const onPage = boxes.filter(box => picked.has(box.dataset.pick)).length;
    all.checked = boxes.length > 0 && onPage === boxes.length;
    // Neither state is honest when some are ticked and some are not.
    all.indeterminate = onPage > 0 && onPage < boxes.length;
    all.disabled = deleting || boxes.length === 0;
  }
  for (const box of boxes) box.checked = picked.has(box.dataset.pick);
  if ($("deleteSelected")) $("deleteSelected").disabled = deleting || count === 0;
  if ($("clearSelection")) $("clearSelection").disabled = deleting;

  // Offered only when there is more than this page to take, and never as the
  // default: selecting two hundred petitions has to be something somebody
  // chose to do.
  const more = $("selectAllMatching");
  if (more) {
    const total = Number(lastListTotal || 0);
    more.hidden = deleting || total <= pickBoxes().length || count === 0;
    more.textContent = phrase(N().selectAllMatching, { n: total.toLocaleString(lang) });
    more.disabled = deleting;
  }
}

function clearSelection() { picked.clear(); syncSelection(); }

/** Collect the ids of everything the current filter matches, not just this
    page. Asked for explicitly, and sent to the server explicitly — the delete
    endpoint takes ids and never a filter, so what is deleted is exactly what
    was listed here and nothing the filter might match a moment later. */
async function selectAllMatching() {
  const params = new URLSearchParams({ page_size: "100" });
  for (const [id, name] of Object.entries(FILTER_PARAMS)) {
    const value = $(id).value.trim();
    if (value) params.set(name, value);
  }
  for (let page = 1; page <= 20; page += 1) {
    params.set("page", String(page));
    let data;
    try {
      const response = await fetch(`/api/petitions?${params}`, { cache: "no-store" });
      if (!response.ok) break;
      data = await response.json();
    } catch { break; }
    for (const item of data.items || []) picked.add(item.session_id);
    if (!data.has_next) break;
  }
  syncSelection();
}

async function deletePicked() {
  const ids = [...picked];
  if (!ids.length || deleting) return;
  deleting = true;
  syncSelection();

  let deleted = 0, failed = 0;
  // The endpoint takes two hundred at a time; more than that is sent as
  // several requests rather than silently truncated.
  for (let at = 0; at < ids.length; at += 200) {
    const batch = ids.slice(at, at + 200);
    try {
      const response = await fetch("/api/petitions/delete", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_ids: batch }),
      });
      if (!response.ok) { failed += batch.length; continue; }
      const data = await response.json();
      deleted += (data.deleted || []).length;
      failed += (data.failed || []).length;
    } catch { failed += batch.length; }
  }

  const n = N();
  listNotice = failed && deleted ? phrase(n.deletePartial, { n: deleted, f: failed })
    : failed ? n.deleteFailed
    : deleted ? phrase(n.deleteDone, { n: deleted.toLocaleString(lang) })
    : n.deleteNothing;

  // If the petition open in the workspace was one of them, the workspace must
  // not go on showing a document that no longer exists anywhere.
  if (sid && ids.includes(sid)) {
    forgetSession();
    resetInterface();
  } else if (ids.includes(savedSession()?.id)) {
    forgetSession();
  }

  deleting = false;
  picked.clear();
  petitionPage = 1;
  await loadPetitions();
}

function drawPetitions(data) {
  const n = N(), items = data.items || [];
  $("petitionCount").textContent = `${Number(data.total || 0).toLocaleString(lang)} ${n.count}`;
  fillFilter("filterDepartment", data.filters?.departments);
  fillFilter("filterCategory", data.filters?.categories);
  fillFilter("filterStatus", data.filters?.statuses, statusLabel);
  fillFilter("filterLanguage", data.filters?.languages, value => value === "ta" ? "தமிழ்" : "English");
  $("petitionsEmpty").hidden = items.length !== 0;
  $("petitionsEmptyTitle").textContent = data.total_saved ? n.noResults : n.empty;
  $("petitionsEmptyText").textContent = data.total_saved ? n.noResultsText : n.emptyText;
  $("petitionsList").innerHTML = items.map(item => {
    const state = item.status === "ready" ? "ready" : ["failed", "generating"].includes(item.status) ? item.status : "draft";
    const downloads = item.document || {};
    return `<article class="petition-item">
      <label class="petition-pick"><input type="checkbox" data-pick="${esc(item.session_id)}"
        ${picked.has(item.session_id) ? "checked" : ""}
        aria-label="${esc(phrase(n.pickLabel, { ref: item.reference || item.subject || "" }))}"></label>
      <div class="petition-item-main" data-open-petition="${esc(item.session_id)}"
           role="button" tabindex="0">
        <div class="petition-item-top"><span class="petition-reference">${esc(item.reference || "—")}</span>
          <span class="petition-status status-${state}">${esc(statusLabel(item.status_label || item.status))}</span>
          ${item.attention_required ? `<span class="petition-status status-failed">${esc(n.attention)}</span>` : ""}</div>
        <h3 class="petition-subject">${esc(item.subject || T().title)}</h3>
        <p class="petition-applicant">${esc(item.petitioner_name || "—")}</p>
        <div class="petition-meta">${[item.department, item.category, item.language === "ta" ? "தமிழ்" : "English",
          `${n.created} ${dateLabel(item.created_at)}`, `${n.edited} ${dateLabel(item.updated_at)}`, `${n.version} ${item.version || 1}`]
          .filter(Boolean).map(value => `<span>${esc(value)}</span>`).join("")}</div>
      </div>
      <div class="petition-item-actions">
        <button class="btn primary" type="button" data-open-petition="${esc(item.session_id)}">${esc(n.view)}</button>
        <button class="btn" type="button" data-edit-petition="${esc(item.session_id)}">${esc(n.edit)}</button>
        ${downloads.pdf_url ? `<a class="btn" href="${esc(downloads.pdf_url)}" download>${esc(T().pdf)}</a>` : ""}
        ${downloads.docx_url ? `<a class="btn" href="${esc(downloads.docx_url)}" download>${esc(T().docx)}</a>` : ""}
      </div></article>`;
  }).join("");
  lastListTotal = Number(data.total || 0);
  $("petitionsResultsNote").textContent = listNotice || n.resultsNote;
  listNotice = "";
  syncSelection();
  $("petitionsPagination").hidden = !items.length || data.pages <= 1;
  $("petitionsPrevious").disabled = data.page <= 1;
  $("petitionsNext").disabled = !data.has_next;
  $("petitionsPageInfo").textContent = `${n.page} ${data.page} ${n.of} ${data.pages || 1}`;
}

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
  const open = e.target.closest("[data-open-petition], [data-edit-petition]");
  if (open) navigate("generator", { id: open.dataset.openPetition || open.dataset.editPetition, edit: Boolean(open.dataset.editPetition) });
  const version = e.target.closest("[data-version]");
  if (version) previewVersion(Number(version.dataset.version));
});

$("petitionsRetry").onclick = loadPetitions;
$("petitionsList").addEventListener("change", (e) => {
  const box = e.target.closest?.("input[data-pick]");
  if (!box) return;
  if (box.checked) picked.add(box.dataset.pick); else picked.delete(box.dataset.pick);
  syncSelection();
});
$("selectAllPetitions").addEventListener("change", (e) => {
  for (const box of pickBoxes()) {
    if (e.target.checked) picked.add(box.dataset.pick); else picked.delete(box.dataset.pick);
  }
  syncSelection();
});
$("selectAllMatching").onclick = selectAllMatching;
$("clearSelection").onclick = clearSelection;
$("deleteSelected").onclick = () => {
  const count = picked.size;
  if (!count || deleting) return;
  const n = N();
  confirmThen(n.deleteTitle,
    count === 1 ? n.deleteOne : phrase(n.deleteMany, { n: count.toLocaleString(lang) }),
    n.deleteKeep, n.deleteGo, deletePicked);
};
$("petitionsPrevious").onclick = () => { petitionPage = Math.max(1, petitionPage - 1); loadPetitions(); };
$("petitionsNext").onclick = () => { petitionPage++; loadPetitions(); };
$("clearFilters").onclick = () => {
  $("petitionFilters").reset(); clearSelection(); petitionPage = 1; loadPetitions();
};
$("petitionFilters").onsubmit = e => { e.preventDefault(); petitionPage = 1; loadPetitions(); };
$("petitionFilters").addEventListener("change", (e) => {
  // NOT for the search box. `change` on a text input fires when it loses
  // focus — which is exactly what clicking a result does. The list was then
  // re-rendered between mousedown and mouseup, the node under the pointer was
  // replaced, and the browser never completed the click: the card simply did
  // nothing for anyone who typed a search and then clicked a result. The
  // search has its own debounced `input` handler and needs nothing here.
  if (e.target === $("petitionSearch")) return;
  clearSelection();
  petitionPage = 1;
  loadPetitions();
});
$("petitionSearch").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { clearSelection(); petitionPage = 1; loadPetitions(); }, 300);
});
window.addEventListener("beforeunload", e => {
  if (editingLetter && editorText() !== editBackup.trimEnd()) { e.preventDefault(); e.returnValue = ""; }
});

async function routeFromHash(initial = false) {
  const hash = location.hash;
  if (!initial && (busy || requestPending)) { window.history.replaceState(null, "", routeHash); return; }
  const match = /^#petition\/([\da-f-]{36})$/i.exec(hash);
  const route = match ? "generator" : hash === "#petitions" ? "petitions" : hash === "#create" ? "create" : "home";
  if (!initial && !guardUnsaved(() => navigate(route, { id: match?.[1], checked: true, replace: true }))) {
    window.history.replaceState(null, "", routeHash); return;
  }
  await navigate(route, { id: match?.[1], checked: true, replace: true });
}
window.addEventListener("hashchange", () => routeFromHash());

(async () => {
  const saved = savedSession();
  if (saved) { lang = saved.language === "ta" ? "ta" : "en"; lastLang = lang; }
  labels(); syncControls();
  void loadHealth();
  await routeFromHash(true);
})();
