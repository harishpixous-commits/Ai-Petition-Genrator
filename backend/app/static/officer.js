"use strict";
(() => {
  // Every language the service serves, named in its own script. The
  // dropdown, the filter and both displays are built from this one map.
  // They used to be four separate edits up to sixty lines apart, so
  // adding a language to the dropdown alone filtered on the wrong code
  // and showed an officer English petitions with no error and no empty
  // result to notice.
  const LANGUAGES = {en: "English", ta: "தமிழ்", ml: "മലയാളം", te: "తెలుగు", hi: "हिन्दी"};
  const languageName = (code) => LANGUAGES[code] || code;
  const main = document.getElementById("officerMain"),
    account = document.getElementById("account");
  const esc = (v) =>
    String(v ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const date = (v) =>
    v
      ? !/^\d{4}-\d{2}-\d{2}/.test(String(v)) ||
        Number.isNaN(new Date(v).getTime())
        ? String(v)
        : new Date(v).toLocaleDateString("en-IN", {
            day: "2-digit",
            month: "short",
            year: "numeric",
          })
      : "Not recorded";
  const statuses = [
    "New / Pending",
    "Acknowledged",
    "Routed to Department",
    "Under Review",
    "Field Inspection Scheduled",
    "Resolved",
    "Rejected",
  ];
  const departments = [
    "Revenue and Disaster Management Department",
    "Municipal Administration and Water Supply Department",
    "Rural Development and Panchayat Raj Department",
    "Social Welfare and Women Empowerment Department",
    "Co-operation, Food and Consumer Protection Department",
    "Energy Department",
    "Home, Prohibition and Excise Department",
    "Housing and Urban Development Department",
    "Highways and Minor Ports Department",
    "Other / Collectorate Review",
  ];
  let demo = new URLSearchParams(location.search).has("preview"),
    user = null,
    records = [],
    acks = [],
    tab = "petitions",
    page = 1;
  const demoRows = [
    [
      "sample-1",
      "CP-2026-00142",
      "Ravi Kumar",
      "Street lights not working on Gandhi Street",
      "Municipal Administration",
      "Infrastructure",
      "Under Review",
      "en",
    ],
    [
      "sample-2",
      "CP-2026-00143",
      "மீனா ராஜன்",
      "குடிநீர் விநியோகத்தை சீரமைக்க வேண்டுதல்",
      "Municipal Administration",
      "Water supply",
      "New / Pending",
      "ta",
    ],
    [
      "sample-3",
      "CP-2026-00144",
      "Lakshmi S",
      "Request for correction of land record",
      "Revenue",
      "Land records",
      "Acknowledged",
      "en",
    ],
    [
      "sample-4",
      "CP-2026-00145",
      "Arun P",
      "Drainage overflow near residential area",
      "",
      "Sanitation",
      "New / Pending",
      "en",
    ],
    [
      "sample-5",
      "CP-2026-00146",
      "Fathima B",
      "Request to repair damaged local road",
      "Highways",
      "Infrastructure",
      "New / Pending",
      "en",
    ],
    [
      "sample-6",
      "CP-2026-00147",
      "Suresh M",
      "Water connection restored",
      "Municipal Administration",
      "Water supply",
      "Resolved",
      "en",
    ],
  ].map(
    ([
      id,
      reference,
      petitioner_name,
      subject,
      department,
      category,
      status,
      language,
    ]) => ({
      id,
      reference,
      petitioner_name,
      subject,
      department,
      category,
      status,
      language,
      assigned_department: department,
      created_at: "2026-09-20T10:00:00Z",
    }),
  );
  const sampleDetail = (p) => ({
    ...p,
    letter_text:
      p.language === "ta"
        ? "அனுப்புநர்\nமீனா ராஜன்\n12, காந்தி தெரு, கோயம்புத்தூர்\n\nபெறுநர்\nசம்பந்தப்பட்ட அலுவலர்\n\nநாள்: 20.09.2026\nஇடம்: கோயம்புத்தூர்\n\nபொருள்: குடிநீர் விநியோகத்தை சீரமைக்க வேண்டுதல்\n\nமதிப்பிற்குரிய ஐயா / அம்மா,\n\nஎங்கள் பகுதியில் கடந்த இரண்டு வாரங்களாக குடிநீர் விநியோகம் சீராக இல்லை. இதனால் அன்றாட தேவைகளுக்கு தண்ணீர் கிடைக்காமல் மக்கள் சிரமப்படுகின்றனர்.\n\nகுடிநீர் விநியோகத்தை ஆய்வு செய்து சீரமைக்க நடவடிக்கை எடுக்குமாறு கேட்டுக்கொள்கிறேன்.\n\nநன்றி,\nமீனா ராஜன்"
        : `From\n${p.petitioner_name}\n12, Gandhi Street, Coimbatore\n\nTo\nThe concerned officer\n\nDate: 20 September 2026\nPlace: Coimbatore\n\nSubject: ${p.subject}\n\nRespected Sir / Madam,\n\nThe street lights on Gandhi Street have not been working for three months. The unlit road makes it difficult for residents to travel safely in the evening. Two earlier complaints have been made at the local office.\n\nI request an inspection and repair of the affected street lights, and an update on the action taken.\n\nYours faithfully,\n${p.petitioner_name}\n\nEnclosures: Previous complaint receipt (sample)`,
    summary:
      p.language === "ta"
        ? "குடிநீர் விநியோகம் இரண்டு வாரங்களாக சீராக இல்லை. ஆய்வு செய்து சீரமைக்க கோரிக்கை."
        : "Resident reports street lights out of service for three months, with two previous complaints. Requests inspection, repairs and an action update.",
    facts: {
      Location: "Gandhi Street, Coimbatore",
      Duration: "Three months",
      "Previous complaint": "Two submissions reported",
    },
    analysis: {},
    attachments: [
      {
        id: "sample-receipt",
        filename: "Previous complaint receipt · sample",
        kind: "acknowledgement",
        relationship: {
          value: "ACKNOWLEDGEMENT",
          confidence: 0.8,
          reason: "reads as a receipt",
        },
      },
      {
        // The case an officer most needs to be able to see at a glance, so
        // the design preview carries it rather than only the easy one.
        id: "sample-third-party",
        filename: "Earlier petition · sample",
        kind: "previous_petition",
        relationship: {
          value: "THIRD_PARTY_SUPPORTING_DOCUMENT",
          confidence: 0.85,
          reason: "a petition naming a different person",
        },
      },
    ],
    notes: [],
  });
  function url(path) {
    return path + (demo ? "?preview=1" : "");
  }
  function go(path) {
    history.pushState({}, "", url(path));
    render();
    window.scrollTo(0, 0);
  }
  function notify(t, kind = "info") {
    const el = document.getElementById("notice");
    el.textContent = t;
    el.dataset.kind = kind;
    setTimeout(() => { el.textContent = ""; delete el.dataset.kind; }, 5000);
  }

  /* localStorage, in a try/except so a private tab or quota-full browser
     silently falls back to in-memory only. All reads tolerate `null`. */
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch {} },
    del(k) { try { localStorage.removeItem(k); } catch {} },
  };
  const noteKey = (id) => `officer:note-draft:${id}`;
  const sortKey = () => "officer:dashboard-sort";
  const neighboursKey = "officer:detail-neighbours";

  /* Keep a snapshot of the filtered dashboard list so the detail page can
     walk Previous/Next without re-fetching. Written on every table()
     render and on every "View →" click. */
  function recordNeighbours(filteredIds) {
    try { sessionStorage.setItem(neighboursKey, JSON.stringify(filteredIds)); } catch {}
  }
  function readNeighbours() {
    try { return JSON.parse(sessionStorage.getItem(neighboursKey) || "[]"); } catch { return []; }
  }
  async function api(path, options = {}) {
    const r = await fetch("/api/officer" + path, {
      ...options,
      headers: { "Content-Type": "application/json", ...options.headers },
    });
    if (r.status === 401) {
      user = null;
      if (!path.endsWith("/login")) go("/officer/login");
    }
    if (!r.ok) {
      let d = await r.json().catch(() => ({}));
      throw Error(
        d.detail || "Unable to load this information. Please try again.",
      );
    }
    return r.status === 204 ? null : r.json();
  }
  const badge = (s) =>
    `<span class="badge ${esc(s.toLowerCase().replaceAll(" ", "-"))}">${esc(s)}</span>`;
  // Whose document this appears to be, as System-1 classified it at upload.
  // Labelled as AI-assisted every time it is shown: it is a classification an
  // officer may disagree with, not a determination, and nothing in the
  // service routes on it. A third party's document is called out because that
  // is the case an officer most needs to notice — the petition in front of
  // them encloses somebody else's paperwork.
  const RELATIONSHIP_LABELS = {
    OWN_PREVIOUS_PETITION: "Petitioner's own earlier petition",
    THIRD_PARTY_SUPPORTING_DOCUMENT: "Third-party supporting document",
    ACKNOWLEDGEMENT: "Acknowledgement / receipt",
    GOVERNMENT_RESPONSE: "Reply from an office",
    CERTIFICATE: "Certificate",
    PHOTO_EVIDENCE: "Photograph",
    GENERAL_SUPPORTING_DOCUMENT: "Supporting document",
    UNRELATED: "Does not appear related to this complaint",
    UNKNOWN: "Could not be established",
  };
  const relationship = (f) => {
    const r = f && f.relationship;
    if (!r || !r.value) return "";
    const label = RELATIONSHIP_LABELS[r.value] || r.value;
    const flag = r.value === "THIRD_PARTY_SUPPORTING_DOCUMENT" ? " third-party" : "";
    const confidence =
      typeof r.confidence === "number" && r.confidence > 0
        ? `<span class="rel-confidence">Confidence ${r.confidence.toFixed(2)}</span>`
        : "";
    return `<div class="relationship${flag}"><span class="rel-label">Document relationship</span><strong>${esc(
      label,
    )}</strong>${confidence}${
      r.reason ? `<p class="muted">${esc(r.reason)}</p>` : ""
    }<p class="rel-caveat">AI-assisted classification · not an official determination · officer review required</p></div>`;
  };
  const banner = () =>
    demo
      ? '<div class="sample-banner">Design preview · Fictional sample records. Changes stay in this preview; no official action is taken.</div>'
      : "";
  function header() {
    if (!user) {
      account.innerHTML = '<a class="hbtn" href="/#home">← Citizen Portal</a>';
      return;
    }
    const adminLink = user.role === "admin"
      ? '<a class="hbtn ghost" href="/officer/admin" data-go>Admin panel</a>'
      : "";
    const accountLink =
      '<a class="hbtn ghost" href="/officer/account" data-go>My account</a>';
    account.innerHTML =
      `<div class="account-name">${esc(user.name)}` +
      `<small>${esc(user.title || user.role)}</small></div>` +
      `${adminLink}${accountLink}` +
      '<button class="hbtn" id="logout">Log out</button>';
    document.getElementById("logout")?.addEventListener("click", async () => {
      try {
        if (!demo) await api("/logout", { method: "POST" });
        user = null;
        records = [];
        acks = [];
        go("/officer/login");
      } catch (e) {
        notify(e.message);
      }
    });
  }
  function login() {
    header();
    /* No pre-filled credentials. The portal is live in front of real
       citizens' petitions: a username and password printed into the markup
       is a liability now, not a convenience. The admin panel at
       /officer/admin is where new logins are created from here on. */
    main.innerHTML = `${banner()}<div class="login-layout"><section class="login-copy"><p class="eyebrow">A CLEARER PATH TO ACTION</p><h2>Every petition deserves a thoughtful review.</h2><p>A dedicated workspace to understand citizen concerns, review supporting documents and identify the right next step.</p><div class="service-points"><span><b>01</b>Petitions and acknowledgements, together</span><span><b>02</b>Original documents, always in focus</span><span><b>03</b>Source-backed information for your review</span></div></section><section class="panel login-card"><p class="eyebrow">OFFICER PORTAL</p><h2>Welcome back</h2><p class="muted">Secure access for petition review and processing</p><form id="loginForm"><div class="field"><label for="username">Email / Username</label><input id="username" name="username" autocomplete="username" required maxlength="150" placeholder="Enter your official username" autofocus></div><div class="field"><label for="password">Password</label><div class="password-wrap"><input type="password" id="password" autocomplete="current-password" required maxlength="256" placeholder="Enter your password"><button type="button" id="showPassword" aria-label="Show password">Show</button></div></div><p class="error" id="loginError" role="alert"></p><button class="hbtn primary wide" type="submit">Sign In →</button></form><div class="login-foot"><a href="/#home">← Back to Citizen Portal</a><p class="muted">Need access? Ask an administrator to create one.</p></div></section></div>`;
    document.getElementById("showPassword").onclick = (e) => {
      const p = document.getElementById("password");
      p.type = p.type === "password" ? "text" : "password";
      e.target.textContent = p.type === "password" ? "Show" : "Hide";
      e.target.setAttribute("aria-label", e.target.textContent + " password");
    };
    document.getElementById("loginForm").onsubmit = async (e) => {
      e.preventDefault();
      const b = e.target.querySelector("[type=submit]");
      b.disabled = true;
      try {
        user = demo
          ? { name: "Sample Officer", role: "officer", title: "Review officer" }
          : await api("/login", {
              method: "POST",
              body: JSON.stringify({
                username: document.getElementById("username").value,
                password: document.getElementById("password").value,
              }),
            });
        go("/officer/dashboard");
      } catch (err) {
        document.getElementById("loginError").textContent = err.message;
      } finally {
        b.disabled = false;
      }
    };
  }
  function select(id, label, values) {
    return `<div><label for="${id}">${label}</label><select id="${id}"><option value="">All ${label.toLowerCase()}</option>${values.map((v) => `<option>${esc(v)}</option>`).join("")}</select></div>`;
  }
  async function dashboard() {
    main.innerHTML = '<p role="status">Loading petitions…</p>';
    if (demo) {
      records = demoRows;
      acks = [
        {
          id: "sample-ack",
          reference: "ACK-2026-00038",
          petition_id: "sample-3",
          petition_reference: "CP-2026-00144",
          petitioner_name: "Lakshmi S",
          department: "Revenue",
          created_at: "2026-09-20",
          status: "Acknowledged",
          language: "en",
          category: "Land records",
        },
      ];
    } else {
      // Together, not one after the other. These are two independent
      // reads and the page shows neither until both land, so fetching
      // them in sequence spent the slower one's time twice over.
      const [petitions, acknowledgements] = await Promise.all([
        api("/petitions"),
        api("/acknowledgements"),
      ]);
      records = petitions.items;
      acks = acknowledgements.items;
    }
    main.innerHTML = `${banner()}<div class="row"><div><p class="eyebrow">PETITION REVIEW WORKSPACE</p><h2>Officer Portal</h2><p class="muted">Review, understand and route citizen petitions.</p></div><span class="muted">${demo ? "Sample workspace" : "Authorized office records"}</span></div><section class="stats" aria-label="Petition totals">${[
      ["Total Petitions", records.length],
      [
        "New / Pending",
        records.filter((p) => p.status === "New / Pending").length,
      ],
      [
        "Under Review",
        records.filter((p) => p.status === "Under Review").length,
      ],
      [
        "Acknowledged",
        records.filter((p) => p.status === "Acknowledged").length,
      ],
      ["Resolved", records.filter((p) => p.status === "Resolved").length],
      ["Needs Routing", records.filter((p) => !p.assigned_department).length],
    ]
      .map(
        ([s, n]) =>
          `<div class="panel stat"><span>${s}</span><strong>${n}</strong></div>`,
      )
      .join(
        "",
      )}</section><div class="tabs" role="tablist" aria-label="Record type"><button role="tab" id="petitionsTab" aria-controls="recordPanel" aria-selected="${tab === "petitions"}">Petitions <span class="muted">${records.length}</span></button><button role="tab" id="acksTab" aria-controls="recordPanel" aria-selected="${tab === "acknowledgements"}">Acknowledgements <span class="muted">${acks.length}</span></button></div><section id="recordPanel" role="tabpanel" aria-labelledby="${tab === "petitions" ? "petitionsTab" : "acksTab"}"><div class="filters"><div><label for="search">Search ${tab}</label><input id="search" type="search" placeholder="Reference, petitioner or subject…"></div>${select("status", "Status", statuses)}${select("department", "Assigned Department", [...new Set((tab === "petitions" ? records.map((p) => p.assigned_department || "Needs routing") : acks.map((p) => p.department || "Not recorded")).filter(Boolean))])}${select("category", "Category", [...new Set(records.map((p) => p.category).filter(Boolean))])}${select("language", "Language", Object.values(LANGUAGES))}</div><div class="filter-dates"><div><label for="from">From date</label><input id="from" type="date"></div><div><label for="to">To date</label><input id="to" type="date"></div><button class="hbtn" id="clear">Clear Filters</button></div><div id="results" class="panel table-panel"></div></section>`;
    if (tab === "acknowledgements" && !demo) {
      const lookup = document.createElement("section");
      lookup.className = "panel ack-lookup";
      lookup.innerHTML = `<h3>Record a paper petition receipt</h3><p class="muted">Enter its petition reference to acknowledge receipt and print a slip.</p><form id="ackLookupForm" class="ack-lookup-form"><div><label for="ackReference">Petition reference number</label><input id="ackReference" maxlength="40" placeholder="AP/2026/B38DBC" required></div><button class="hbtn primary" type="submit">Acknowledge &amp; create slip</button></form><div class="ack-lookup-result" id="ackLookupResult" aria-live="polite"></div>`;
      main.querySelector("#recordPanel").prepend(lookup);
    }
    for (const [id, t] of [
      ["petitionsTab", "petitions"],
      ["acksTab", "acknowledgements"],
    ])
      document.getElementById(id).onclick = () => {
        tab = t;
        page = 1;
        dashboard().catch(fail);
      };
    for (const id of [
      "search",
      "status",
      "department",
      "category",
      "language",
      "from",
      "to",
    ])
      document.getElementById(id).addEventListener("input", () => {
        page = 1;
        table();
      });
    document.getElementById("clear").onclick = () => {
      for (const el of main.querySelectorAll("input,select")) el.value = "";
      page = 1;
      table();
    };
    document.getElementById("ackLookupForm")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = event.currentTarget.querySelector("button");
      const result = document.getElementById("ackLookupResult");
      button.disabled = true;
      result.textContent = "Looking up petition…";
      try {
        const receipt = await api("/acknowledgements/lookup", {
          method: "POST",
          body: JSON.stringify({ reference: document.getElementById("ackReference").value.trim() }),
        });
        result.innerHTML = `<article class="paper ack-slip"><p class="eyebrow">COLLECTORATE ACKNOWLEDGEMENT</p><h2>${esc(receipt.reference)}</h2><p>Petition reference: <strong>${esc(receipt.petition_reference)}</strong></p><dl class="details"><dt>Petitioner</dt><dd>${esc(receipt.petitioner_name || "Not recorded")}</dd><dt>Subject</dt><dd>${esc(receipt.subject || "Not recorded")}</dd><dt>Department</dt><dd>${esc(receipt.department || "To be routed")}</dd><dt>Received</dt><dd>${esc(date(receipt.created_at))}</dd><dt>Status</dt><dd>Acknowledged</dd></dl><button type="button" class="hbtn primary" id="printAckSlip">Print acknowledgement slip</button></article>`;
        document.getElementById("printAckSlip").onclick = () => window.print();
        const existing = acks.findIndex((item) => item.id === receipt.id);
        if (existing >= 0) acks[existing] = { ...acks[existing], reference: receipt.reference, status: receipt.status, created_at: receipt.created_at };
        else acks.unshift({ ...receipt, id: receipt.id, petition_id: receipt.id, language: receipt.language, category: "" });
        document.getElementById("acksTab").innerHTML = `Acknowledgements <span class="muted">${acks.length}</span>`;
        table();
      } catch (error) {
        result.textContent = error.message || "Could not find that petition reference.";
      } finally {
        button.disabled = false;
      }
    });
    table();
  }
  /* Column sort state, read from localStorage so it persists across page
     loads. One key per tab; shape: {column: "created_at", dir: "desc"}. */
  function readSort() {
    try { return JSON.parse(store.get(sortKey()) || "{}")[tab] || null; }
    catch { return null; }
  }
  function writeSort(order) {
    try {
      const all = JSON.parse(store.get(sortKey()) || "{}");
      if (order) all[tab] = order;
      else delete all[tab];
      store.set(sortKey(), JSON.stringify(all));
    } catch {}
  }
  function compareRows(key, dir) {
    const sign = dir === "asc" ? 1 : -1;
    return (a, b) => {
      const av = (a[key] ?? "").toString().toLowerCase();
      const bv = (b[key] ?? "").toString().toLowerCase();
      if (av < bv) return -1 * sign;
      if (av > bv) return 1 * sign;
      return 0;
    };
  }
  function table() {
    const val = (id) => document.getElementById(id).value;
    let filtered = (tab === "petitions" ? records : acks).filter(
      (p) =>
        (!val("search") ||
          [p.reference, p.petition_reference, p.petitioner_name, p.subject]
            .join(" ")
            .toLowerCase()
            .includes(val("search").toLowerCase())) &&
        (!val("status") || p.status === val("status")) &&
        (!val("department") ||
          (tab === "petitions"
            ? (p.assigned_department || "Needs routing")
            : (p.department || "Not recorded")) === val("department")) &&
        (!val("category") || p.category === val("category")) &&
        (!val("language") ||
          p.language === (Object.keys(LANGUAGES).find(
            (c) => LANGUAGES[c] === val("language")) || "en")) &&
        (!val("from") || String(p.created_at).slice(0, 10) >= val("from")) &&
        (!val("to") || String(p.created_at).slice(0, 10) <= val("to")),
    );
    const order = readSort();
    if (order && order.key) {
      filtered = filtered.slice().sort(compareRows(order.key, order.dir));
    }
    /* Record the filtered id order so the detail page can walk it. */
    recordNeighbours(filtered.map((r) => r.id));
    /* Columns and the record-key each sorts on. "Action" has no key —
       sorting a link column is nonsense. */
    const cols = tab === "petitions"
      ? [
          ["Reference No.",   "reference"],
          ["Petitioner",      "petitioner_name"],
          ["Subject / Issue", "subject"],
          ["Assigned Department", "assigned_department"],
          ["Date",            "created_at"],
          ["Status",          "status"],
          ["Language",        "language"],
          ["Action",          null],
        ]
      : [
          ["Acknowledgement No.", "reference"],
          ["Petitioner",          "petitioner_name"],
          ["Petition Reference",  "petition_reference"],
          ["Department",          "department"],
          ["Date",                "created_at"],
          ["Status",              "status"],
          ["Language",            "language"],
          ["Action",              null],
        ];
    const rows = filtered.slice((page - 1) * 10, page * 10);
    const headerCell = ([label, key]) => {
      if (!key) return `<th scope="col">${label}</th>`;
      const active = order && order.key === key;
      const arrow = active ? (order.dir === "asc" ? " ↑" : " ↓") : "";
      const nextDir = active ? (order.dir === "asc" ? "desc" : null) : "asc";
      const aria = active ? (order.dir === "asc" ? "ascending" : "descending") : "none";
      return `<th scope="col" aria-sort="${aria}"><button type="button" class="sortable" data-sort-key="${esc(key)}" data-sort-next="${nextDir || ""}">${label}${arrow}</button></th>`;
    };
    document.getElementById("results").innerHTML = filtered.length
      ? `<table><thead><tr>${cols.map(headerCell).join("")}</tr></thead><tbody>${rows.map((p) => `<tr>${[esc(p.reference || "Not assigned"), esc(p.petitioner_name || "Not recorded"), `<span class="subject">${esc(p.subject || p.petition_reference || "Untitled petition")}</span>`, esc(tab === "petitions" ? (p.assigned_department || "Needs routing") : (p.department || "Not recorded")), esc(date(p.created_at)), badge(p.status), languageName(p.language), `<a href="${url("/officer/" + (tab === "petitions" ? "petitions" : "acknowledgements") + "/" + encodeURIComponent(p.id))}" data-go aria-label="View ${esc(p.reference)}">View →</a>`].map((v, i) => `<td data-label="${cols[i][0]}">${v}</td>`).join("")}</tr>`).join("")}</tbody></table><div class="table-footer"><span class="muted">${(page - 1) * 10 + 1}–${Math.min(page * 10, filtered.length)} of ${filtered.length} ${tab}</span><div class="actions"><button class="hbtn" id="prev" ${page === 1 ? "disabled" : ""}>Previous</button><button class="hbtn" id="next" ${page * 10 >= filtered.length ? "disabled" : ""}>Next</button></div></div>`
      : `<div class="empty"><h3>No ${tab} found</h3><p>Try another search or clear the filters.</p></div>`;
    document.getElementById("prev")?.addEventListener("click", () => {
      page--;
      table();
    });
    document.getElementById("next")?.addEventListener("click", () => {
      page++;
      table();
    });
    main.querySelectorAll(".sortable").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.getAttribute("data-sort-key");
        const next = btn.getAttribute("data-sort-next");
        writeSort(next ? { key, dir: next } : null);
        page = 1;
        table();
      });
    });
  }
  /* The empty-finding placeholder. "Verification required" read like
     mockup text next to blank fields; this says the same thing more
     precisely so it does not look placeholder-y. */
  const EMPTY_FINDING = '<p class="muted">No verified source identified from the retrieved passages.</p>';

  /* Dedupe source cards on the way to render. The backend already dedupes
     within a single finding; this one covers the case where the SAME
     source rides under two different Suggested-Process steps and the
     screen would otherwise show the card twice. The signature follows the
     backend's: (document_title, first 60 chars of section, page_number). */
  function dedupSources(sources, seen) {
    const out = [];
    for (const s of sources || []) {
      const key = [
        (s.document_title || "").trim(),
        (s.section || "").slice(0, 60).trim().toLowerCase(),
        s.page_number || "",
      ].join("|");
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(s);
    }
    return out;
  }

  /* Render N source cards with the rest tucked into a <details> so the
     page is not drowned when retrieval returns many thin chunks. The
     user screenshot showed five near-identical ULB Rules 2023 cards in
     one block; two visible is enough. */
  function sourceList(sources, { visible = 2, seen = new Set(), suppressTitle = null } = {}) {
    const unique = dedupSources(sources, seen);
    if (!unique.length) return "";
    const render = (s) => source(s, { suppressTitle });
    const head = unique.slice(0, visible).map(render).join("");
    const tail = unique.slice(visible);
    if (!tail.length) return head;
    const label = tail.length === 1 ? "1 more source" : `${tail.length} more sources`;
    return head +
      `<details class="more-sources"><summary>Show ${label}</summary>${tail.map(render).join("")}</details>`;
  }

  /* One finding in its own card so two findings in a list (two Acts, two
     candidate departments) do not visually bleed into each other.

     `suppressTitle` is passed to the source renderer so a source whose
     document_title matches the finding's own value does NOT repeat the
     title at the top of the card — the user saw "Tamil Nadu Urban Local
     Bodies Rules, 2023" written three times in a row (finding value plus
     two source headings) and read as noise. The <strong> stays when the
     source refers to a different document than the finding is about.  */
  function finding(f, options = {}) {
    if (!f?.value) return EMPTY_FINDING;
    const inner = sourceList(f.sources || [], { ...options, suppressTitle: f.value });
    return `<article class="finding"><p class="finding-value">${esc(f.value)}</p>${inner}</article>`;
  }

  /* A list of findings (applicable_acts, applicable_rules, government_orders)
     with ONE "no verified source" fallback for the whole list, not one per
     empty entry. */
  function findingList(items) {
    const safe = (items || []).filter((f) => f && f.value);
    if (!safe.length) return EMPTY_FINDING;
    const seen = new Set();
    return safe.map((f) => finding(f, { seen })).join("");
  }

  /* Suggested-Process rendering collapses sources shared across steps so
     the ULB Act §118 passage, cited under more than one step, does not
     render as four identical source cards down the page. The step texts
     stay as a numbered list; the sources live in one shared "References"
     footer under them. */
  function processBlock(steps) {
    const list = (steps || []).filter((s) => s && s.value);
    if (!list.length) return EMPTY_FINDING;
    const items = list.map((s) => `<li>${esc(s.value)}</li>`).join("");
    const seen = new Set();
    const allSources = [];
    for (const step of list) for (const s of (step.sources || [])) {
      const key = [
        (s.document_title || "").trim(),
        (s.section || "").slice(0, 60).trim().toLowerCase(),
        s.page_number || "",
      ].join("|");
      if (seen.has(key)) continue;
      seen.add(key);
      allSources.push(s);
    }
    const refs = allSources.length
      ? `<p class="muted source-label">Grounded in:</p>${allSources.map(source).join("")}`
      : "";
    return `<ol class="process-steps">${items}</ol>${refs}`;
  }

  function source(s, { suppressTitle = null } = {}) {
    let link = "";
    try {
      const u = new URL(s.source_url);
      if (["https:", "http:"].includes(u.protocol))
        link = `<a target="_blank" rel="noopener noreferrer" href="${esc(u.href)}">View Source ↗</a>`;
    } catch {}
    const title = (s.document_title || "").trim();
    const titleBar = (suppressTitle && title === String(suppressTitle).trim())
      ? ""   /* finding value already names the document; do not repeat it */
      : `<strong>${esc(title)}</strong><br>`;
    const meta = esc([s.date, s.section, s.page_number ? "Page " + s.page_number : ""].filter(Boolean).join(" · "));
    const excerpt = s.excerpt ? `<p>${esc(s.excerpt)}</p>` : "";
    return `<div class="source">${titleBar}${meta}${excerpt}${link}</div>`;
  }
  async function detail(id) {
    let p = demo
      ? sampleDetail(demoRows.find((r) => r.id === id) || demoRows[0])
      : await api("/petitions/" + encodeURIComponent(id));
    const a = p.analysis || {};
    main.innerHTML = `${banner()}<a data-go href="${url("/officer/dashboard")}">← All petitions</a><div class="row spaced-row"><div><p class="eyebrow">PETITION REVIEW</p><h2>${esc(p.subject || "Petition details")}</h2><p class="muted">${esc(p.reference || "Reference not assigned")} · Created ${esc(date(p.created_at))} · ${languageName(p.language)}</p></div>${badge(p.status)}</div><div class="review-grid"><section><div class="panel preview-tools"><div class="row"><h3 class="flat-title">Petition Preview</h3><div class="actions">${["pdf", "docx"].map((ext) => (p.document?.[ext + "_url"] ? `<a class="hbtn" href="${esc(p.document[ext + "_url"])}">Download ${ext === "pdf" ? "PDF" : "Word"}</a>` : `<button class="hbtn" disabled title="${demo ? "Not available for sample records" : "Document not generated"}">Download ${ext === "pdf" ? "PDF" : "Word"}</button>`)).join("")}<button class="hbtn" id="print">Print</button></div></div></div><div class="paper-frame"><article class="paper" aria-label="Petition document" lang="${p.language === "ta" ? "ta" : "en"}"><div class="paper-brand"><img src="/assets/emblem/tamil-nadu-web.png" alt="" width="32" height="36"><strong>${demo ? "SAMPLE PETITION" : "CITIZEN PETITION"}</strong></div><div class="letter-text">${esc(p.letter_text || "The petition document has not yet been generated.")}</div></article></div></section><aside class="review-side" aria-label="Knowledge and officer review"><section class="panel"><p class="eyebrow">OFFICER ASSISTANCE</p><h3>Petition Summary</h3><p>${esc(p.summary || "No grievance recorded.")}</p><p class="muted">Based on the citizen’s recorded information. The original petition remains authoritative.</p></section><section class="panel"><h3>Grievance Summary</h3><dl class="details">${
      Object.entries(p.facts || {})
        .filter(([, v]) => v)
        .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`)
        .join("") || "<dt>Details</dt><dd>Not recorded</dd>"
    }</dl></section><section class="panel"><h3>Recommended Department</h3>${finding(a.department)}<h4>Responsible authority / office</h4>${finding(a.responsible_authority)}</section><section class="panel"><h3>Applicable Acts &amp; Rules</h3>${(a.warnings || []).map((w) => `<p class="warning">${esc(w)}</p>`).join("")}${[
      ["Act", "applicable_acts"],
      ["Rule", "applicable_rules"],
      ["Government Order", "government_orders"],
    ]
      .map(
        ([l, k]) =>
          `<h4>${l}</h4>${findingList(a[k])}`,
      )
      .join(
        "",
      )}<p class="muted">Source-grounded assistance. Officer verification is required.</p></section><section class="panel"><h3>Suggested Process</h3><p class="muted">Review → Verify department → Confirm authority → Record action → Closure</p>${processBlock(a.processing_steps)}<h4>Processing hierarchy / escalation</h4>${processBlock(a.processing_hierarchy)}<h4>Current status</h4>${badge(p.status)}<p class="muted">No automatic routing or official decision is made.</p></section><section class="panel"><h3>Supporting Documents</h3>${(p.attachments || []).map((f) => `<div class="attachment"><strong>${esc(f.filename)}</strong><p class="muted">${esc(f.kind || "Document")}</p>${relationship(f)}${f.url ? `<div class="actions"><a target="_blank" rel="noopener" href="${esc(f.url)}">View ↗</a><a href="${esc(f.url)}?download=1">Download ↓</a></div>` : '<p class="muted">Sample file · No document uploaded</p>'}${f.metadata ? `<p>${esc(f.metadata)}</p>` : ""}</div>`).join("") || '<p class="muted">No supporting documents attached.</p>'}</section><section class="panel"><h3>Officer Review</h3><div id="savedNotes">${(p.notes || []).map((n) => `<div class="note">${esc(n.text)}<p class="muted">${esc(n.author)} · ${esc(date(n.created_at))}</p></div>`).join("")}</div><form class="review-form" id="reviewForm"><div><label for="note">Officer notes</label><textarea id="note" rows="3" maxlength="4000" placeholder="Record observations or the next step…"></textarea></div><div><label for="reviewStatus">Status</label><select id="reviewStatus">${statuses.map((s) => `<option ${p.status === s ? "selected" : ""}>${s}</option>`).join("")}</select></div><button class="hbtn primary" type="submit">Save review</button><p id="reviewError" class="error" role="alert"></p></form></section></aside></div>`;
    const actionSection = document.getElementById("reviewForm").closest("section.panel");
    actionSection.querySelector("h3").textContent = "Collectorate Action Panel";
    const suggestedDepartment = a.department?.value || p.department || "";
    const suggestedAuthority = a.responsible_authority?.value || "";
    const departmentChoices = [...new Set([...departments, suggestedDepartment].filter(Boolean))];
    const chosenDepartment = p.assigned_department || suggestedDepartment;
    const priorityChoice = `${p.priority || "Normal"}|${p.sla_target || "15 Days"}`;
    const form = document.getElementById("reviewForm");
    form.innerHTML = `
      <div class="field-grid">
        <div><label for="assignedDepartment">Assigned Department</label><select id="assignedDepartment"><option value="">Select a department</option>${departmentChoices.map((department) => `<option value="${esc(department)}" ${department === chosenDepartment ? "selected" : ""}>${esc(department)}</option>`).join("")}</select></div>
        <div><label for="assignedAuthority">Assigned Officer / Authority</label><input id="assignedAuthority" maxlength="200" value="${esc(p.assigned_authority || suggestedAuthority)}" placeholder="Choose or confirm the responsible office"></div>
      </div>
      <div class="field-grid">
        <div><label for="prioritySla">Priority &amp; SLA target</label><select id="prioritySla"><option value="Normal|15 Days" ${priorityChoice === "Normal|15 Days" ? "selected" : ""}>Normal - 15 Days</option><option value="High Priority|7 Days" ${priorityChoice === "High Priority|7 Days" ? "selected" : ""}>High Priority - 7 Days</option><option value="Urgent / Essential Utility|48 Hours" ${priorityChoice === "Urgent / Essential Utility|48 Hours" ? "selected" : ""}>Urgent / Essential Utility - 48 Hours</option></select></div>
        <div><label for="reviewStatus">Status</label><select id="reviewStatus">${statuses.map((status) => `<option ${p.status === status ? "selected" : ""}>${esc(status)}</option>`).join("")}</select></div>
      </div>
      <div><label for="officialReply">Official Reply / Action Taken Note (Visible to Citizen)</label><textarea id="officialReply" rows="4" maxlength="4000" placeholder="Write the update the citizen may see on the tracking page.">${esc(p.official_reply || "")}</textarea></div>
      <div><label for="note">Private Officer Notes</label><textarea id="note" rows="3" maxlength="4000" placeholder="Internal observations for the review record."></textarea></div>
      <p class="muted action-target-note">Targets are officer-set estimates; statutory and service-charter timelines take precedence.</p>
      <button class="hbtn primary" type="submit">Save action</button><p id="reviewError" class="error" role="alert"></p>`;
    document.getElementById("print").onclick = () => window.print();

    /* Officer notes autosave to localStorage, keyed by petition id.
       Prevents a stray refresh from losing a half-written observation.
       Cleared only after a successful review save. */
    const noteBox = document.getElementById("note");
    const noteDraftTag = document.createElement("span");
    noteDraftTag.className = "draft-indicator";
    noteBox.parentNode.appendChild(noteDraftTag);
    const draft = store.get(noteKey(id));
    if (draft && !noteBox.value) {
      noteBox.value = draft;
      noteDraftTag.textContent = "Draft restored";
      noteDraftTag.dataset.state = "restored";
    }
    let draftTimer;
    noteBox.addEventListener("input", () => {
      noteDraftTag.textContent = "Unsaved";
      noteDraftTag.dataset.state = "dirty";
      clearTimeout(draftTimer);
      draftTimer = setTimeout(() => {
        store.set(noteKey(id), noteBox.value);
        noteDraftTag.textContent = "Draft saved";
        noteDraftTag.dataset.state = "saved";
      }, 400);
    });

    /* Previous / Next walk the filtered dashboard list.
       `recordNeighbours` writes the id order on the dashboard; this reads
       it. If the officer landed here from a bookmark, both buttons stay
       hidden — no fake navigation without context. */
    const neighbours = readNeighbours();
    const here = neighbours.indexOf(id);
    const prevId = here > 0 ? neighbours[here - 1] : null;
    const nextId = here !== -1 && here < neighbours.length - 1 ? neighbours[here + 1] : null;
    const nav = document.createElement("nav");
    nav.className = "detail-nav";
    nav.setAttribute("aria-label", "Petition navigation");
    nav.innerHTML = `
      ${prevId ? `<a class="hbtn" data-go href="${url("/officer/petitions/" + encodeURIComponent(prevId))}">← Previous (${here}/${neighbours.length})</a>` : ""}
      ${nextId ? `<a class="hbtn" data-go href="${url("/officer/petitions/" + encodeURIComponent(nextId))}">Next (${here + 2}/${neighbours.length}) →</a>` : ""}
    `.trim();
    if (nav.innerHTML) main.querySelector(".review-grid")?.before(nav);

    document.getElementById("reviewForm").onsubmit = async (e) => {
      e.preventDefault();
      const b = e.target.querySelector("button");
      b.disabled = true;
      try {
        const body = {
          note: document.getElementById("note").value,
          status: document.getElementById("reviewStatus").value,
          assigned_department: document.getElementById("assignedDepartment").value,
          assigned_authority: document.getElementById("assignedAuthority").value,
          priority: document.getElementById("prioritySla").value.split("|")[0],
          sla_target: document.getElementById("prioritySla").value.split("|")[1],
          official_reply: document.getElementById("officialReply").value,
        };
        if (demo) {
          demoRows.find((r) => r.id === id).status = body.status;
          if (body.note) {
            const n = document.createElement("div");
            n.className = "note";
            n.textContent = body.note;
            document.getElementById("savedNotes").append(n);
          }
          document.getElementById("note").value = "";
        } else {
          await api("/petitions/" + encodeURIComponent(id) + "/review", {
            method: "POST",
            body: JSON.stringify(body),
          });
          store.del(noteKey(id));
          await detail(id);
        }
        store.del(noteKey(id));
        notify(
          demo ? "Sample review updated in this preview." : "Review saved.",
          "success",
        );
      } catch (err) {
        document.getElementById("reviewError").textContent = err.message;
        notify("Could not save: " + (err.message || "request failed"), "error");
      } finally {
        b.disabled = false;
      }
    };
  }
  async function acknowledgement(id) {
    const a = demo
      ? {
          ...acks[0],
          reference: "ACK-2026-00038",
          petition_id: "sample-3",
          petition_reference: "CP-2026-00144",
          petitioner_name: "Lakshmi S",
          department: "Revenue",
          created_at: "2026-09-20",
          status: "Acknowledged",
        }
      : await api("/acknowledgements/" + encodeURIComponent(id));
    main.innerHTML = `${banner()}<a data-go href="${url("/officer/dashboard")}">← Officer dashboard</a><h2>Acknowledgement</h2><div class="review-grid"><article class="paper"><p class="eyebrow">${demo ? "SAMPLE RECEIPT" : "RECORDED ACKNOWLEDGEMENT"}</p><h2>${esc(a.reference || "Reference not recorded")}</h2><p>Linked petition: <a data-go href="${url("/officer/petitions/" + encodeURIComponent(a.petition_id))}">${esc(a.petition_reference)}</a></p><dl class="details"><dt>Petitioner</dt><dd>${esc(a.petitioner_name)}</dd><dt>Department</dt><dd>${esc(a.department || "Not recorded")}</dd><dt>Date</dt><dd>${esc(date(a.created_at))}</dd><dt>Status</dt><dd>${badge(a.status)}</dd></dl><h4>Receipt preview</h4><p>${esc(a.text || "Open the original supporting document to review the acknowledgement receipt.")}</p>${a.url ? `<a class="hbtn" target="_blank" rel="noopener" href="${esc(a.url)}">View original receipt ↗</a>` : ""}</article><section class="panel"><h3>Linked petition</h3><p>${esc(a.petition_reference)}</p><a class="hbtn" data-go href="${url("/officer/petitions/" + encodeURIComponent(a.petition_id))}">Open petition →</a><p class="muted">A recorded receipt is evidence of a previous submission; it does not confirm resolution.</p></section></div>`;
  }
  /* ---------- Admin panel + account page ------------------------------ */

  function roleBadge(role) {
    const kind = role === "admin" ? "admin" : "officer";
    const label = role === "admin" ? "Administrator" : "Review officer";
    return `<span class="role-badge role-${kind}">${label}</span>`;
  }

  async function adminPanel() {
    if (user.role !== "admin") {
      main.innerHTML =
        '<section class="panel empty"><h2>Administrator access is required</h2>' +
        '<p>Your account does not have user-management rights. Ask an administrator ' +
        'if you need to add or edit officer logins.</p>' +
        '<a class="hbtn" href="/officer/dashboard" data-go>Back to petitions</a></section>';
      return;
    }
    let users = [];
    try {
      users = (await api("/users")).users || [];
    } catch (e) {
      main.innerHTML = `<section class="panel empty"><h2>Could not load users</h2><p>${esc(e.message)}</p></section>`;
      return;
    }
    const rows = users.map((u) => `
      <tr data-username="${esc(u.username)}">
        <td>${esc(u.name)}</td>
        <td class="monospace">${esc(u.username)}</td>
        <td>${roleBadge(u.role)}</td>
        <td class="row-actions">
          <button class="hbtn ghost small" data-edit="${esc(u.username)}">Edit</button>
          <button class="hbtn ghost small" data-pw="${esc(u.username)}">Reset password</button>
          <button class="hbtn danger small" data-del="${esc(u.username)}" ${u.username === user.username ? "disabled title='You cannot delete your own account'" : ""}>Delete</button>
        </td>
      </tr>`).join("");
    main.innerHTML = `
      <section class="panel admin-panel">
        <header class="admin-head">
          <div>
            <p class="eyebrow">OFFICER PORTAL · ADMIN</p>
            <h2>User management</h2>
            <p class="muted">Add officers, change their roles and reset passwords without touching GitHub.</p>
          </div>
          <button class="hbtn primary" id="newUser">+ Add officer</button>
        </header>
        <table class="admin-users">
          <thead><tr><th>Name</th><th>Username</th><th>Role</th><th></th></tr></thead>
          <tbody>${rows || '<tr><td colspan="4" class="muted">No officers yet.</td></tr>'}</tbody>
        </table>
        <div id="adminDialog"></div>
      </section>`;

    document.getElementById("newUser").onclick = () => showCreateDialog();
    document.querySelectorAll("[data-edit]").forEach((b) => {
      b.onclick = () => showEditDialog(users.find((u) => u.username === b.dataset.edit));
    });
    document.querySelectorAll("[data-pw]").forEach((b) => {
      b.onclick = () => showResetDialog(b.dataset.pw);
    });
    document.querySelectorAll("[data-del]").forEach((b) => {
      if (b.disabled) return;
      b.onclick = async () => {
        const name = b.closest("tr").querySelector("td").textContent;
        if (!confirm(`Delete the "${name}" account? This cannot be undone.`)) return;
        try {
          await api(`/users/${encodeURIComponent(b.dataset.del)}`, { method: "DELETE" });
          notify(`Deleted ${name}.`, "ok");
          adminPanel();
        } catch (e) {
          notify(e.message, "err");
        }
      };
    });
  }

  function dialogShell(title, body) {
    const host = document.getElementById("adminDialog");
    host.innerHTML = `
      <div class="dialog-backdrop" id="dialogBack">
        <div class="dialog" role="dialog" aria-modal="true" aria-label="${esc(title)}">
          <header><h3>${esc(title)}</h3><button class="hbtn ghost small" id="dialogClose" aria-label="Close">×</button></header>
          <div class="dialog-body">${body}</div>
        </div>
      </div>`;
    const close = () => (host.innerHTML = "");
    document.getElementById("dialogClose").onclick = close;
    document.getElementById("dialogBack").onclick = (e) => {
      if (e.target.id === "dialogBack") close();
    };
    return close;
  }

  function showCreateDialog() {
    const close = dialogShell("Add an officer", `
      <form id="createForm" class="form-stack">
        <label>Display name<input id="newName" required maxlength="150" placeholder="e.g. Ravi Kumar"></label>
        <label>Username<input id="newUsername" required maxlength="64" placeholder="lowercase, 3–64 chars, letters/digits/._-"></label>
        <label>Password<input id="newPassword" type="password" required minlength="12" maxlength="256" placeholder="At least 12 characters"></label>
        <label>Role
          <select id="newRole">
            <option value="officer" selected>Review officer</option>
            <option value="admin">Administrator</option>
          </select>
        </label>
        <p class="error" id="createError" role="alert"></p>
        <div class="dialog-actions">
          <button type="button" class="hbtn ghost" id="createCancel">Cancel</button>
          <button type="submit" class="hbtn primary">Create</button>
        </div>
      </form>`);
    document.getElementById("createCancel").onclick = close;
    document.getElementById("createForm").onsubmit = async (e) => {
      e.preventDefault();
      try {
        await api("/users", {
          method: "POST",
          body: JSON.stringify({
            username: document.getElementById("newUsername").value,
            name: document.getElementById("newName").value,
            password: document.getElementById("newPassword").value,
            role: document.getElementById("newRole").value,
          }),
        });
        close();
        notify("Officer created.", "ok");
        adminPanel();
      } catch (err) {
        document.getElementById("createError").textContent = err.message;
      }
    };
  }

  function showEditDialog(u) {
    const isSelf = u.username === user.username;
    const close = dialogShell(`Edit "${u.name}"`, `
      <form id="editForm" class="form-stack">
        <label>Display name<input id="editName" value="${esc(u.name)}" required maxlength="150"></label>
        <label>Username<input id="editUsername" value="${esc(u.username)}" required maxlength="64"></label>
        <label>Role
          <select id="editRole" ${isSelf ? "disabled title='You cannot change your own role'" : ""}>
            <option value="officer" ${u.role === "officer" ? "selected" : ""}>Review officer</option>
            <option value="admin" ${u.role === "admin" ? "selected" : ""}>Administrator</option>
          </select>
        </label>
        ${isSelf ? '<p class="muted small">You cannot change your own role. Ask another administrator, or promote someone else and then demote yourself.</p>' : ""}
        <p class="error" id="editError" role="alert"></p>
        <div class="dialog-actions">
          <button type="button" class="hbtn ghost" id="editCancel">Cancel</button>
          <button type="submit" class="hbtn primary">Save changes</button>
        </div>
      </form>`);
    document.getElementById("editCancel").onclick = close;
    document.getElementById("editForm").onsubmit = async (e) => {
      e.preventDefault();
      try {
        const payload = {
          name: document.getElementById("editName").value,
          new_username: document.getElementById("editUsername").value,
        };
        if (!isSelf) payload.role = document.getElementById("editRole").value;
        await api(`/users/${encodeURIComponent(u.username)}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        close();
        notify("Changes saved.", "ok");
        adminPanel();
      } catch (err) {
        document.getElementById("editError").textContent = err.message;
      }
    };
  }

  function showResetDialog(username) {
    const close = dialogShell(`Reset password for ${username}`, `
      <form id="resetForm" class="form-stack">
        <p class="muted small">Setting a new password here will sign this user out of every current session.</p>
        <label>New password<input id="resetPw" type="password" required minlength="12" maxlength="256" placeholder="At least 12 characters"></label>
        <p class="error" id="resetError" role="alert"></p>
        <div class="dialog-actions">
          <button type="button" class="hbtn ghost" id="resetCancel">Cancel</button>
          <button type="submit" class="hbtn primary">Reset password</button>
        </div>
      </form>`);
    document.getElementById("resetCancel").onclick = close;
    document.getElementById("resetForm").onsubmit = async (e) => {
      e.preventDefault();
      try {
        await api(`/users/${encodeURIComponent(username)}/password`, {
          method: "PUT",
          body: JSON.stringify({ new_password: document.getElementById("resetPw").value }),
        });
        close();
        notify("Password reset.", "ok");
      } catch (err) {
        document.getElementById("resetError").textContent = err.message;
      }
    };
  }

  function accountPanel() {
    main.innerHTML = `
      <section class="panel account-panel">
        <header>
          <p class="eyebrow">OFFICER PORTAL</p>
          <h2>My account</h2>
          <p class="muted">You are signed in as <strong>${esc(user.name)}</strong> (<span class="monospace">${esc(user.username)}</span>). Role: ${roleBadge(user.role)}</p>
        </header>
        <form id="accountForm" class="form-stack">
          <h3>Change my password</h3>
          <label>Current password<input id="curPw" type="password" autocomplete="current-password" required maxlength="256"></label>
          <label>New password<input id="newPw" type="password" autocomplete="new-password" required minlength="12" maxlength="256" placeholder="At least 12 characters"></label>
          <label>Confirm new password<input id="confirmPw" type="password" autocomplete="new-password" required minlength="12" maxlength="256"></label>
          <p class="error" id="accountError" role="alert"></p>
          <div class="dialog-actions">
            <button type="submit" class="hbtn primary">Change password</button>
          </div>
        </form>
      </section>`;
    document.getElementById("accountForm").onsubmit = async (e) => {
      e.preventDefault();
      const errEl = document.getElementById("accountError");
      errEl.textContent = "";
      const newPw = document.getElementById("newPw").value;
      if (newPw !== document.getElementById("confirmPw").value) {
        errEl.textContent = "The two new-password entries do not match.";
        return;
      }
      try {
        await api("/me/password", {
          method: "POST",
          body: JSON.stringify({
            current_password: document.getElementById("curPw").value,
            new_password: newPw,
          }),
        });
        notify("Password changed. Your other sessions have been signed out.", "ok");
        document.getElementById("accountForm").reset();
      } catch (err) {
        errEl.textContent = err.message;
      }
    };
  }

  function fail(e) {
    main.innerHTML = `<section class="panel empty"><h2>Unable to open this page</h2><p role="alert">${esc(e.message)}</p><button class="hbtn" id="retry">Try again</button> <a href="/officer/login">Return to sign in</a></section>`;
    document.getElementById("retry").onclick = render;
  }
  async function render() {
    try {
      const path = location.pathname;
      if (path.endsWith("/login")) return login();
      if (!user) {
        if (demo) user = { name: "Sample Officer", role: "officer", title: "Review officer" };
        else user = await api("/me");
      }
      header();
      if (path.endsWith("/admin")) await adminPanel();
      else if (path.endsWith("/account")) accountPanel();
      else if (path.includes("/petitions/"))
        await detail(decodeURIComponent(path.split("/").pop()));
      else if (path.includes("/acknowledgements/"))
        await acknowledgement(decodeURIComponent(path.split("/").pop()));
      else await dashboard();
    } catch (e) {
      if (location.pathname.endsWith("/login")) login();
      else fail(e);
    }
  }
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-go]");
    if (a && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      go(new URL(a.href).pathname);
    }
  });

  /* Keyboard shortcuts. All require the focus NOT be on an input, so
     typing "/" or "n" into a textarea does what the user expects. */
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const inField = /^(input|textarea|select)$/i.test(e.target.tagName);
    if (inField) {
      if (e.key === "Escape") e.target.blur();
      return;
    }
    if (e.key === "/") {
      const search = document.getElementById("search");
      if (search) { e.preventDefault(); search.focus(); }
      return;
    }
    if (e.key === "j" || e.key === "n") {
      const next = document.querySelector(".detail-nav a:last-child[href*='/petitions/']");
      if (next) { e.preventDefault(); next.click(); }
      return;
    }
    if (e.key === "k" || e.key === "p") {
      const prev = document.querySelector(".detail-nav a:first-child[href*='/petitions/']");
      if (prev) { e.preventDefault(); prev.click(); }
      return;
    }
  });

  window.addEventListener("popstate", render);
  render();
})();
