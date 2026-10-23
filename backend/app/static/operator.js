// The operator console, moved out of the page so the CSP can be strict.
//
// This was an inline <script> in `operator.html`. An inline block forces
// either `script-src 'unsafe-inline'`, which disables the policy for exactly
// the thing it exists to protect, or a per-response nonce threaded through
// the template. The code had no reason to be inline, so it is a file now and
// the policy needs no exception anywhere in the service.

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[<>&"]/g, c =>
  ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" })[c]);

// A token may be supplied as ?token=… so an operator can bookmark the page on a
// machine that is not the server itself. It is never stored.
const TOKEN = new URLSearchParams(location.search).get("token") || "";

const CLASS = {
  ready: "ok", available: "ok", empty: "idle", not_ready: "idle",
  not_installed: "idle", degraded: "warn", workstation_only: "warn",
  attention: "warn", unavailable: "bad", not_available: "bad", disabled: "idle",
};
const WORD = {
  ready: "Ready", available: "Available", not_installed: "Not installed",
  not_ready: "Not ready", workstation_only: "Workstation only",
  unavailable: "Unavailable", not_available: "Not available",
  degraded: "Degraded", empty: "Empty", attention: "Needs attention",
  disabled: "Disabled",
};

function pill(state) {
  return `<span class="pill ${CLASS[state] || "idle"}">${esc(WORD[state] || state)}</span>`;
}


/* Providers. Nothing here ever receives a key from the service: the screen
   is told how many are set, where they came from, and what each one's last
   probe said, by position. */
function drawProviders(data) {
  const p = data || {};
  $("provNote").textContent = p.note || "";
  const counts = p.counts || {}, sources = p.sources || {};
  $("cntGemini").textContent = `${counts.GEMINI_API_KEYS || 0} set \u00b7 ${sources.GEMINI_API_KEYS || "unset"}`;
  $("cntSarvam").textContent = `${counts.SARVAM_API_KEYS || 0} set \u00b7 ${sources.SARVAM_API_KEYS || "unset"}`;
  const s = p.settings || {};
  $("allowAi").checked = Boolean(s.allow_external_ai);
  if (s.stream_asr_provider) $("asrProv").value = "";
  if (s.tts_provider) $("ttsProv").value = "";

  const health = p.health || {};
  $("provChecked").textContent = health.checked_at
    ? `last checked ${esc(health.checked_at)}` : "not checked yet";
  const rows = (health.providers || []).map(prov => {
    const keys = (prov.keys || []).map(k =>
      `<tr><td>key ${k.position}</td><td>${pill(k.state)}</td>` +
      `<td>${esc(k.detail || "")}</td></tr>`).join("");
    const summary = prov.total
      ? `${prov.usable} of ${prov.total} usable`
      : esc(prov.note || "not configured");
    return `<h3>${esc(prov.name)} <span class="kv">${summary}</span></h3>` +
           (keys ? `<table><tbody>${keys}</tbody></table>` : "");
  }).join("");
  $("provList").innerHTML = rows ||
    "<p class=\"note\">No provider configured. Petitions use the standard wording; typing still works.</p>";
  $("provAdvice").innerHTML = (p.advice || [])
    .map(line => `<p class="note">${esc(line)}</p>`).join("");
}

async function providerRequest(path, options) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options && options.body ? { "Content-Type": "application/json" } : {}),
      ...(TOKEN ? { "x-operator-token": TOKEN } : {}),
    },
  });
  if (!response.ok) throw new Error(`The service answered ${response.status}.`);
  return response.json();
}

if ($("provCheck")) {
  $("provCheck").onclick = async () => {
    $("provCheck").disabled = true;
    $("provChecked").textContent = "checking\u2026";
    try { drawProviders(await providerRequest("/api/operator/providers/check", { method: "POST" })); }
    catch (err) { $("provChecked").textContent = err.message; }
    finally { $("provCheck").disabled = false; }
  };
}

if ($("provForm")) {
  $("provForm").onsubmit = async (e) => {
    e.preventDefault();
    const form = new FormData($("provForm"));
    const body = {};
    for (const name of ["gemini_api_keys", "sarvam_api_keys", "llm_provider",
                        "stream_asr_provider", "tts_provider"]) {
      const value = (form.get(name) || "").toString();
      // An untouched field is left alone; a field the operator emptied is
      // sent as "" on purpose, which clears the override.
      if (value !== "") body[name] = value;
    }
    body.allow_external_ai = $("allowAi").checked;
    $("provSaved").textContent = "saving\u2026";
    try {
      drawProviders(await providerRequest("/api/operator/providers",
        { method: "POST", body: JSON.stringify(body) }));
      // Never leave a credential sitting in the DOM after it is sent.
      $("provForm").reset();
      $("provSaved").textContent = "applied";
    } catch (err) { $("provSaved").textContent = err.message; }
  };
}

async function loadProviders() {
  try { drawProviders(await providerRequest("/api/operator/providers")); }
  catch { /* the status call already reported why the screen is unreachable */ }
}
async function load() {
  let data;
  try {
    const response = await fetch("/api/operator/status", {
      headers: TOKEN ? { "x-operator-token": TOKEN } : {},
    });
    if (response.status === 404) {
      throw new Error(
        "This screen is not reachable from here. It answers only on the server " +
        "itself unless OPERATOR_TOKEN is set — then add ?token=… to the URL.");
    }
    if (!response.ok) throw new Error(`The service answered ${response.status}.`);
    data = await response.json();
  } catch (err) {
    $("error").style.display = "block";
    $("error").textContent = err.message;
    return;
  }

  $("body").hidden = false;
  void loadProviders();
  const k = data.knowledge;

  $("kbHealth").outerHTML = pill(k.health).replace("<span", '<span id="kbHealth"');
  $("kbPath").innerHTML = k.path ? `<span>${esc(k.path)}</span>` : "";
  $("mDocs").textContent = k.documents ?? 0;
  $("mOfficial").textContent = k.official_documents ?? 0;
  $("mUnverified").textContent = k.unverified_documents ?? 0;
  $("mSuperseded").textContent = k.superseded_documents ?? 0;
  $("mConflicts").textContent = k.unresolved_conflicts ?? 0;
  $("mChunks").textContent = k.chunks ?? 0;
  $("kbNote").textContent = k.note || "";
  $("kbNote").className = "note" + (k.health === "ready" || k.health === "empty" ? "" : " warn");

  const e = k.embeddings || {};
  // "local" is a hashed bag-of-words, not a trained model. Saying only its name
  // reads like success, so the screen says what it is.
  $("embProvider").textContent = e.provider
    ? (e.semantic ? e.provider : `${e.provider} (lexical, not semantic)`) : "—";
  $("embDim").textContent = e.dimension ?? "—";
  $("embVector").textContent = e.vector_search ? "on" : "off (lexical only)";
  $("lastIngest").textContent = k.last_ingested_at
    ? new Date(k.last_ingested_at).toLocaleString() : "never";

  $("conflictList").innerHTML = (k.conflicts || []).map(c => `
    <div class="conflict">
      <p>${esc(c.message)}</p>
      <ul>${(c.documents || []).map(d =>
        `<li>${esc(d.title)}${d.date ? ` · ${esc(d.date)}` : " · no date"}
         <code>${esc(d.document_id)}</code></li>`).join("")}</ul>
    </div>`).join("");

  $("caps").innerHTML = Object.values(data.capabilities || {}).map(c => `
    <tr>
      <td class="cap">${esc(c.name)}</td>
      <td>${pill(c.state)}</td>
      <td class="detail">${esc(c.detail)}</td>
    </tr>`).join("");

  $("generated").textContent = new Date(data.generated_at).toLocaleString();
  $("access").textContent = data.access;
}

load();
setInterval(load, 30000);
