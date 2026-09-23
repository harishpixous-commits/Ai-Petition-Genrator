"use strict";
(() => {
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
    "New",
    "Pending",
    "Under Review",
    "Acknowledged",
    "Resolved",
    "Needs Review",
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
      "New",
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
      "Needs Review",
      "en",
    ],
    [
      "sample-5",
      "CP-2026-00146",
      "Fathima B",
      "Request to repair damaged local road",
      "Highways",
      "Infrastructure",
      "Pending",
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
  function notify(t) {
    document.getElementById("notice").textContent = t;
    setTimeout(
      () => (document.getElementById("notice").textContent = ""),
      5000,
    );
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
  const banner = () =>
    demo
      ? '<div class="sample-banner">Design preview · Fictional sample records. Changes stay in this preview; no official action is taken.</div>'
      : "";
  function header() {
    account.innerHTML = user
      ? `<div class="account-name">${esc(user.name)}<small>${esc(user.role)}</small></div><button class="hbtn" id="logout">Log out</button>`
      : '<a class="hbtn" href="/#home">← Citizen Portal</a>';
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
    main.innerHTML = `${banner()}<div class="login-layout"><section class="login-copy"><p class="eyebrow">A CLEARER PATH TO ACTION</p><h2>Every petition deserves a thoughtful review.</h2><p>A dedicated workspace to understand citizen concerns, review supporting documents and identify the right next step.</p><div class="service-points"><span><b>01</b>Petitions and acknowledgements, together</span><span><b>02</b>Original documents, always in focus</span><span><b>03</b>Source-backed information for your review</span></div></section><section class="panel login-card"><p class="eyebrow">OFFICER PORTAL</p><h2>Welcome back</h2><p class="muted">Secure access for petition review and processing</p><form id="loginForm"><div class="field"><label for="username">Email / Username</label><input id="username" name="username" autocomplete="username" required maxlength="150" placeholder="Enter your official username"></div><div class="field"><label for="password">Password</label><div class="password-wrap"><input type="password" id="password" autocomplete="current-password" required maxlength="256" placeholder="Enter your password"><button type="button" id="showPassword" aria-label="Show password">Show</button></div></div><p class="error" id="loginError" role="alert"></p><button class="hbtn primary wide" type="submit">Sign In →</button></form><div class="login-foot"><a href="/#home">← Back to Citizen Portal</a><p class="muted">Need access? Contact your system administrator.</p></div></section></div>`;
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
          ? { name: "Sample Officer", role: "Review officer" }
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
        records.filter((p) => ["New", "Pending"].includes(p.status)).length,
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
      ["Needs Routing", records.filter((p) => !p.department).length],
    ]
      .map(
        ([s, n]) =>
          `<div class="panel stat"><span>${s}</span><strong>${n}</strong></div>`,
      )
      .join(
        "",
      )}</section><div class="tabs" role="tablist" aria-label="Record type"><button role="tab" id="petitionsTab" aria-controls="recordPanel" aria-selected="${tab === "petitions"}">Petitions <span class="muted">${records.length}</span></button><button role="tab" id="acksTab" aria-controls="recordPanel" aria-selected="${tab === "acknowledgements"}">Acknowledgements <span class="muted">${acks.length}</span></button></div><section id="recordPanel" role="tabpanel" aria-labelledby="${tab === "petitions" ? "petitionsTab" : "acksTab"}"><div class="filters"><div><label for="search">Search ${tab}</label><input id="search" type="search" placeholder="Reference, petitioner or subject…"></div>${select("status", "Status", statuses)}${select("department", "Department", [...new Set(records.map((p) => p.department).filter(Boolean))])}${select("category", "Category", [...new Set(records.map((p) => p.category).filter(Boolean))])}${select("language", "Language", ["English", "Tamil"])}</div><div class="filter-dates"><div><label for="from">From date</label><input id="from" type="date"></div><div><label for="to">To date</label><input id="to" type="date"></div><button class="hbtn" id="clear">Clear Filters</button></div><div id="results" class="panel table-panel"></div></section>`;
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
    table();
  }
  function table() {
    const val = (id) => document.getElementById(id).value;
    const filtered = (tab === "petitions" ? records : acks).filter(
      (p) =>
        (!val("search") ||
          [p.reference, p.petition_reference, p.petitioner_name, p.subject]
            .join(" ")
            .toLowerCase()
            .includes(val("search").toLowerCase())) &&
        ["status", "department", "category"].every(
          (k) => !val(k) || p[k] === val(k),
        ) &&
        (!val("language") ||
          p.language === (val("language") === "Tamil" ? "ta" : "en")) &&
        (!val("from") || String(p.created_at).slice(0, 10) >= val("from")) &&
        (!val("to") || String(p.created_at).slice(0, 10) <= val("to")),
    );
    const cols =
      tab === "petitions"
        ? [
            "Reference No.",
            "Petitioner",
            "Subject / Issue",
            "Department",
            "Date",
            "Status",
            "Language",
            "Action",
          ]
        : [
            "Acknowledgement No.",
            "Petitioner",
            "Petition Reference",
            "Department",
            "Date",
            "Status",
            "Language",
            "Action",
          ];
    const rows = filtered.slice((page - 1) * 10, page * 10);
    document.getElementById("results").innerHTML = filtered.length
      ? `<table><thead><tr>${cols.map((c) => `<th scope="col">${c}</th>`).join("")}</tr></thead><tbody>${rows.map((p) => `<tr>${[esc(p.reference || "Not assigned"), esc(p.petitioner_name || "Not recorded"), `<span class="subject">${esc(p.subject || p.petition_reference || "Untitled petition")}</span>`, esc(p.department || "Verification required"), esc(date(p.created_at)), badge(p.status), p.language === "ta" ? "தமிழ்" : "English", `<a href="${url("/officer/" + (tab === "petitions" ? "petitions" : "acknowledgements") + "/" + encodeURIComponent(p.id))}" data-go aria-label="View ${esc(p.reference)}">View →</a>`].map((v, i) => `<td data-label="${cols[i]}">${v}</td>`).join("")}</tr>`).join("")}</tbody></table><div class="table-footer"><span class="muted">${(page - 1) * 10 + 1}–${Math.min(page * 10, filtered.length)} of ${filtered.length} ${tab}</span><div class="actions"><button class="hbtn" id="prev" ${page === 1 ? "disabled" : ""}>Previous</button><button class="hbtn" id="next" ${page * 10 >= filtered.length ? "disabled" : ""}>Next</button></div></div>`
      : `<div class="empty"><h3>No ${tab} found</h3><p>Try another search or clear the filters.</p></div>`;
    document.getElementById("prev")?.addEventListener("click", () => {
      page--;
      table();
    });
    document.getElementById("next")?.addEventListener("click", () => {
      page++;
      table();
    });
  }
  function finding(f) {
    if (!f?.value) return '<p class="muted">Verification required</p>';
    return `<p>${esc(f.value)}</p>${(f.sources || []).map(source).join("")}`;
  }
  function source(s) {
    let link = "";
    try {
      const u = new URL(s.source_url);
      if (["https:", "http:"].includes(u.protocol))
        link = `<a target="_blank" rel="noopener noreferrer" href="${esc(u.href)}">View Source ↗</a>`;
    } catch {}
    return `<div class="source"><strong>${esc(s.document_title)}</strong><br>${esc([s.date, s.section, s.page_number ? "Page " + s.page_number : ""].filter(Boolean).join(" · "))}${s.excerpt ? `<p>${esc(s.excerpt)}</p>` : ""}${link}</div>`;
  }
  async function detail(id) {
    let p = demo
      ? sampleDetail(demoRows.find((r) => r.id === id) || demoRows[0])
      : await api("/petitions/" + encodeURIComponent(id));
    const a = p.analysis || {};
    main.innerHTML = `${banner()}<a data-go href="${url("/officer/dashboard")}">← All petitions</a><div class="row" style="margin-top:18px"><div><p class="eyebrow">PETITION REVIEW</p><h2>${esc(p.subject || "Petition details")}</h2><p class="muted">${esc(p.reference || "Reference not assigned")} · Created ${esc(date(p.created_at))} · ${p.language === "ta" ? "தமிழ்" : "English"}</p></div>${badge(p.status)}</div><div class="review-grid"><section><div class="panel preview-tools"><div class="row"><h3 style="margin:0">Petition Preview</h3><div class="actions">${["pdf", "docx"].map((ext) => (p.document?.[ext + "_url"] ? `<a class="hbtn" href="${esc(p.document[ext + "_url"])}">Download ${ext === "pdf" ? "PDF" : "Word"}</a>` : `<button class="hbtn" disabled title="${demo ? "Not available for sample records" : "Document not generated"}">Download ${ext === "pdf" ? "PDF" : "Word"}</button>`)).join("")}<button class="hbtn" id="print">Print</button></div></div></div><div class="paper-frame"><article class="paper" aria-label="Petition document" lang="${p.language === "ta" ? "ta" : "en"}"><div class="paper-brand"><img src="/assets/emblem/tamil-nadu-web.png" alt="" width="32" height="36"><strong>${demo ? "SAMPLE PETITION" : "CITIZEN PETITION"}</strong></div><div class="letter-text">${esc(p.letter_text || "The petition document has not yet been generated.")}</div></article></div></section><aside class="review-side" aria-label="Knowledge and officer review"><section class="panel"><p class="eyebrow">OFFICER ASSISTANCE</p><h3>Petition Summary</h3><p>${esc(p.summary || "No grievance recorded.")}</p><p class="muted">Based on the citizen’s recorded information. The original petition remains authoritative.</p></section><section class="panel"><h3>Grievance Summary</h3><dl class="details">${
      Object.entries(p.facts || {})
        .filter(([, v]) => v)
        .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`)
        .join("") || "<dt>Details</dt><dd>Not recorded</dd>"
    }</dl></section><section class="panel"><h3>Recommended Department</h3>${finding(a.department)}<h4>Responsible authority / office</h4>${finding(a.responsible_authority)}</section><section class="panel"><h3>Applicable Acts &amp; Rules</h3>${(a.warnings || []).map((w) => `<p class="error">${esc(w)}</p>`).join("")}${[
      ["Act", "applicable_acts"],
      ["Rule", "applicable_rules"],
      ["Government Order", "government_orders"],
    ]
      .map(
        ([l, k]) =>
          `<h4>${l}</h4>${a[k]?.length ? a[k].map(finding).join("") : '<p class="muted">Not identified in verified sources</p>'}`,
      )
      .join(
        "",
      )}<p class="muted">Source-grounded assistance. Officer verification is required.</p></section><section class="panel"><h3>Suggested Process</h3><p class="muted">Review → Verify department → Confirm authority → Record action → Closure</p>${(a.processing_steps || []).map(finding).join("")}<h4>Processing hierarchy / escalation</h4>${(a.processing_hierarchy || []).map(finding).join("") || '<p class="muted">Verification required</p>'}<h4>Current status</h4>${badge(p.status)}<p class="muted">No automatic routing or official decision is made.</p></section><section class="panel"><h3>Supporting Documents</h3>${(p.attachments || []).map((f) => `<div class="attachment"><strong>${esc(f.filename)}</strong><p class="muted">${esc(f.kind || "Document")}</p>${f.url ? `<div class="actions"><a target="_blank" rel="noopener" href="${esc(f.url)}">View ↗</a><a href="${esc(f.url)}?download=1">Download ↓</a></div>` : '<p class="muted">Sample file · No document uploaded</p>'}${f.metadata ? `<p>${esc(f.metadata)}</p>` : ""}</div>`).join("") || '<p class="muted">No supporting documents attached.</p>'}</section><section class="panel"><h3>Officer Review</h3><div id="savedNotes">${(p.notes || []).map((n) => `<div class="note">${esc(n.text)}<p class="muted">${esc(n.author)} · ${esc(date(n.created_at))}</p></div>`).join("")}</div><form class="review-form" id="reviewForm"><div><label for="note">Officer notes</label><textarea id="note" rows="3" maxlength="4000" placeholder="Record observations or the next step…"></textarea></div><div><label for="reviewStatus">Status</label><select id="reviewStatus">${statuses.map((s) => `<option ${p.status === s ? "selected" : ""}>${s}</option>`).join("")}</select></div><button class="hbtn primary" type="submit">Save review</button><p id="reviewError" class="error" role="alert"></p></form></section></aside></div>`;
    document.getElementById("print").onclick = () => window.print();
    document.getElementById("reviewForm").onsubmit = async (e) => {
      e.preventDefault();
      const b = e.target.querySelector("button");
      b.disabled = true;
      try {
        const body = {
          note: document.getElementById("note").value,
          status: document.getElementById("reviewStatus").value,
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
          await detail(id);
        }
        notify(
          demo ? "Sample review updated in this preview." : "Review saved.",
        );
      } catch (err) {
        document.getElementById("reviewError").textContent = err.message;
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
  function fail(e) {
    main.innerHTML = `<section class="panel empty"><h2>Unable to open this page</h2><p role="alert">${esc(e.message)}</p><button class="hbtn" id="retry">Try again</button> <a href="/officer/login">Return to sign in</a></section>`;
    document.getElementById("retry").onclick = render;
  }
  async function render() {
    try {
      const path = location.pathname;
      if (path.endsWith("/login")) return login();
      if (!user) {
        if (demo) user = { name: "Sample Officer", role: "Review officer" };
        else user = await api("/me");
      }
      header();
      if (path.includes("/petitions/"))
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
  window.addEventListener("popstate", render);
  render();
})();
