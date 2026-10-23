# Requirements traceability matrix — SRS v1.1 vs the current repository

Written for: Harish and whoever reviews release-readiness. This is the audit
output the SRS v1.1 §K requires. It states what is in the tree today, what the
SRS asks for, and where the gap is. **No application code was changed to
produce this file.** Three files already changed earlier in the same working
session are listed at the end; they are correctness fixes with their own tests,
not SRS implementation.

---

## 0. Baseline

- Repository root: `C:\Users\haris\Downloads\Ai petition new update\`
- Backend: `backend/` — FastAPI, Python 3.12, SQLite (sqlite-vec + FTS5),
  LangGraph for conversation state, static web UI in `backend/app/static/`.
- Branch: `main`. Working tree has unstaged changes (see §9); no commits made
  in this session.
- Test collection: **2,391 tests across 70 test files** (`python -m pytest
  --collect-only -q` from `backend/`).
- Baseline run on 2026-10-13: `python -m pytest -q` from `backend/` exits 0.
  Markers counted from the raw dot stream: 4 `s` (skip), 1 `x` (xfail), 0 `F`
  (fail), 0 errors. Dependency on `var/knowledge.sqlite` means some
  corpus-grounded tests are skipped when the DB is absent; it is present here.
- Static type-check / lint: `ruff` is configured in `backend/pyproject.toml`;
  neither it nor a formatter was run in this audit pass.
- Vector-index coverage: `python scripts/ingest.py integrity` reports
  **8,072 / 8,344 chunks (96.74%) correct for gemini-embedding-001 / 1536
  dims**; 272 remaining chunks are all in `tn-ulb-rules-2023` and are blocked on
  Gemini `RESOURCE_EXHAUSTED` quota, not on code.
- Independently measured retrieval quality (see §4, AC-16): hybrid Recall@5 is
  **1.00 for English (n=10)** and **0.00 for Malayalam and Hindi, 0.20 for
  Tamil and Telugu (n=5 each)**.

---

## 1. Legend

| Status | Meaning |
|---|---|
| Implemented | A specific file+line in the repo, with a passing test, satisfies the requirement. |
| Partial | The capability exists in part; a named production gap remains. |
| Missing | No evidence found in the repository. |
| Blocked | External decision, credential, source, or integration is required before implementation can start or finish. |
| N/A | The SRS requirement does not apply to this deployment scope. |

Risk uses the SRS §14.4 severity scale (Critical / High / Medium / Low).

---

## 2. Functional requirements (FR-001 — FR-020)

### FR-001 Language selection — **Partial**, **High**
- Evidence: `backend/app/domain/languages.py:100-123` declares five SUPPORTED
  codes (`en`, `ta`, `ml`, `te`, `hi`) and `backend/app/letter_templates/
  petition.yaml` has 10 per-language keys × 5 languages. Tests:
  `tests/test_languages.py`, `tests/test_five_language_acceptance.py`.
- Gap: `backend/app/graph/state.py:19` and `app/domain/phrasing.py:23` still
  declare `Language = Literal["en", "ta"]`; the three Indic additions are not
  wired through the state machine. The measured retrieval numbers in §4
  confirm the gap: ml/te/hi do not come back from retrieval, even though the
  UI advertises them.
- Required change: single-source `Language` typedef (remove the duplicates
  the plan file lists at seven locations) and prove each language with the
  AC-02 test matrix. Do not advertise ml/hi/te as supported until measured.
- Test coverage: UI-level yes, state-machine level no. Needs per-language
  end-to-end tests.
- Phase: 1 (safety) and 3 (multilingual).
- Blocker: translator-reviewed strings for ~1,000 UI keys (`UI`/`EXPERIENCE`/
  `NAV` in `app/static/app.js`). Machine translation of government interview
  wording is explicitly ruled out by project memory `[[build-for-government-
  not-engineers]]`.

### FR-002 Mixed input — **Partial**, **Medium**
- Evidence: push-to-talk dictation at `app/api/dictation.py:57` (ws
  `/ws/dictation/{session_id}`); typed input via REST `app/api/rest.py:343`;
  attachments at `app/api/rest.py:423`. All three write back into the same
  LangGraph state (`app/graph/state.py`, `workflow.py`).
- Gap: no provenance tag per input (text/voice/attachment) is persisted on
  the conversation turn so the SRS "retain provenance of each input" is not
  met at the DB level. Audit by `grep "provenance" app/graph/state.py`
  returns nothing.
- Required change: add `source` field to the conversation-turn record and
  surface it in the officer view.
- Phase: 1.

### FR-003 Conversation state — **Implemented** (not after-generation),
  **Medium**
- Evidence: LangGraph `LetterState` TypedDict in `app/graph/state.py:39`,
  SqliteSaver checkpoint via `workflow_lifespan` in `app/graph/workflow.py`,
  session recovery in `app/api/rest.py:313`.
- Gap: SRS requires state coherence "after generation and page refresh".
  Post-generation editing is wired in `rest.py:847` (revise) and `887`
  (submit), but a refresh after generation is not covered by an existing test
  — the AC-10 scenario is tested only through `revise` not through a hard
  reload.
- Required change: AC-10 Playwright script that reloads after generation and
  asserts the edited draft survives.
- Phase: 1.

### FR-004 Missing information — **Implemented**, **Low**
- Evidence: `app/graph/nodes.py` has the missing-field branch; the
  conversation only asks for fields that are null. Tests:
  `tests/test_conversation.py`, `tests/test_flow.py`.
- Gap: none at the behaviour level.

### FR-005 Confirmation — **Implemented**, **Low**
- Evidence: `app/graph/nodes.py` has a confirm step; `tests/test_flow.py`
  covers the summary-and-correct cycle.
- Gap: none observed.

### FR-006 Structured extraction — **Partial**, **Medium**
- Evidence: Pydantic schemas in `app/graph/state.py`; extraction prompt in
  `app/graph/nodes.py`; field validators in `app/domain/fields.py`.
- Gap: no per-field confidence is returned to the client. SRS requires
  "field-level provenance and confidence".
- Required change: extend the structured output schema with a confidence
  band and the span the value came from.
- Phase: 1.

### FR-007 Classification — **Implemented**, **High** residual quality risk
- Evidence: `app/services/system_one.py` with a closed vocabulary and
  mandatory `UNKNOWN`. Benchmarks in `benchmarks/run_system_one_benchmark.py`
  and `benchmarks/run_grievance_eval.py`.
- Gap: measured macro-F1 **0.7317 on held-out data (docs/hardening-
  report.md:14)**, well below the SRS target. Confidence is not calibrated;
  no per-language slice is reported.
- Required change: do NOT tune on the eval set (SRS §17.2 (7) and project
  memory `[[petition-fixed-decisions]]`). Grow the labelled corpus and
  measure per language + per category per SRS Table 9.
- Phase: 4.

### FR-008 Department suggestion — **Missing**, **Critical**
- Evidence: `petition.yaml:31-37` hard-codes the address block to "District
  Collectorate"; no department taxonomy, no routing rules, no urban/rural
  flag. Confirmed by the plan file: zero occurrences of "ULB" in the repo
  before this audit.
- Required change: Phase 2 of the plan — geography model (district → taluk →
  ULB / panchayat with urban/rural), choice field type, choice UI control,
  real routing rules. The TN state datasets are referenced as sources.
- Phase: 2 (geography) + 4 (routing).
- Blocker: official TN taluk/ULB/panchayat master data must be sourced
  before any routing can be built.

### FR-009 Legal/source assistance — **Partial**, **High**
- Evidence: full RAG in `app/knowledge/` (ingest, store, retrieve, analyst,
  legal_status, vector_integrity, embeddings). 18 documents + 8,344 chunks
  indexed. `legal_relationships.yaml` encodes 18 amendment relationships with
  Gazette evidence. Grounding check `analyst.grounded()` at `analyst.py:215`.
- Gap: measured cross-language retrieval is weak outside English (Tamil R@5
  = 0.20; Malayalam/Hindi = 0.00; Telugu = 0.20). Officer-side consumers do
  not yet render the `legal_status.state`/`notes`/`changes` fields the
  schema already carries.
- Required change: measurement surface — the eval report (just produced in
  `var/reports/retrieval.json`) is the baseline a future improvement must
  beat. Officer UI change to show legal_status is a Phase-2 UX task.
- Phase: 4 (RAG) + 6 (officer UI).

### FR-010 Petition generation — **Implemented**, **Medium**
- Evidence: `app/graph/nodes.py` compose node, `app/services/package.py`
  renders the PDF, `tests/test_grievance_benchmark.py` and
  `tests/test_conversation.py` cover the drafting flow.
- Gap: the grounding guard against invented acts/GOs runs on `analyst`
  findings, not on the final draft prose. A compose model that writes
  "Section 45 of the TN Panchayats Act" with no supporting chunk would not
  be caught today unless the analyst layer surfaces the claim first.
- Required change: post-compose grounding re-check that walks every statute/
  rule/GO reference in the rendered letter against the retrieval set.
- Phase: 8.

### FR-011 Edit / regenerate — **Partial**, **Medium**
- Evidence: `app/api/rest.py:847` revise endpoint, `app/domain/revisions.py`,
  `tests/test_revision.py`. Chat-driven edits via `/ws/voice` and the dictation
  socket.
- Gap: a regeneration does not currently produce a preview/diff before
  replacing an accepted version. SRS requires "clearly preview the proposed
  changes".
- Required change: a diff view in the citizen workspace before
  substantial AI replacements, and a confirmation step.
- Phase: 1.

### FR-012 My Petitions — **Implemented**, **Low** on data model, **High** on
  access control
- Evidence: `app/api/catalog.py` listing + delete; `app/services/
  petition_catalog.py`; `tests/test_petition_catalog.py`.
- Gap: the citizen-scope guard in `app/services/officer_store.py:102-105`
  returns `None` (no filter) when the officers table is empty — fail-open.
  Called out in the plan file as the Phase 0.1 blocker and still unresolved
  in the tree today.
- Required change: fail-closed when there is no officer, until an operator
  has been seeded.
- Phase: 0.
- Risk: Critical if the API is exposed to the public internet before an
  officer account exists.

### FR-013 Export — **Implemented**, **Low**
- Evidence: `app/api/rest.py:1286` (`.pdf`), `app/api/rest.py:1301`
  (`.docx`), `app/api/rest.py:991` (package PDF), `app/services/package.py`
  for rendering; `tests/test_package.py`, `tests/test_documents.py`.
- Gap: Unicode PDF rendering uses LibreOffice `soffice`. The font map in
  `app/services/package.py:50-52, 212-213` picks a font by a literal Tamil
  codepoint test only; a Malayalam, Telugu, Hindi or Devanagari petition
  renders with `.notdef` boxes unless a per-language font map is added. SRS
  §9.3 requires Unicode for all five scripts.
- Required change: ship Noto Devanagari/Telugu/Malayalam/Tamil, install
  wherever LibreOffice runs, and share one per-language font map across the
  four render paths listed in the plan file.
- Phase: 1b.
- Blocker: open source Noto fonts are licence-clean; nothing to resolve.

### FR-014 Attachments — **Implemented** (minus malware), **High**
- Evidence: upload at `app/api/rest.py:423`, storage at `app/services/
  attachment_store.py`, extraction at `app/services/extraction.py` and
  `app/services/document_intelligence.py`, OCR at `app/services/ocr.py`
  (per-page via `TesseractEngine.pdf_pages`), separation from RAG enforced
  by `tests/test_attachments.py:473-514`.
- Gap: no malware scanning. `grep -rln "clamav\|malware\|virus_scan" app/`
  returns nothing. SRS §6.2 (2) is explicit: "scan for malware and reject
  encrypted, malformed or suspicious files".
- Required change: add a ClamAV adapter (or an equivalent server-side
  service) behind a provider interface, store scan state per attachment, and
  block downstream extraction until the scan clears.
- Phase: 5.
- Blocker: operations decision on whether to run ClamAV in-container or as a
  side service, and licence for a managed scanner if that is preferred.

### FR-015 Deletion / retention — **Partial**, **Medium**
- Evidence: `app/services/removal.py` deletes petition data on request;
  attachment removal cascades.
- Gap: no retention policy configuration surfaces today. SRS §10.2 and §H
  require separate approved periods for drafts, originals, voice recordings,
  attachments, generated documents, audit events, notifications, RAG sources,
  AI evaluation data, integration logs; a legal-hold suspension; and
  verifiable completion of a deletion job.
- Required change: retention schema per entity, scheduled sweep, legal-hold
  flag, deletion audit event.
- Phase: 6.
- Blocker: product owner must approve the periods.

### FR-016 No false submission — **Implemented**, **Low**
- Evidence: `app/api/rest.py:887` `submit_petition` stores a local
  acknowledgement with timestamp only and does not call out to any
  government integration (`rest.py:810-818` plan-file quote: "transmits
  nothing to any department"). `tests/test_submit.py` covers it.
- Gap: the status display reads `submitted` once this local record is
  written, which is accurate against the SRS definition only if read as "an
  internal submission to the officer portal queue". A hard-wired integration
  does not exist, so the risk here is wording in the citizen UI.
- Required change: label this as "Ready for officer review" rather than
  "Submitted" until a real integration exists.
- Phase: 1.

### FR-017 Recoverability — **Partial**, **Medium**
- Evidence: LangGraph SqliteSaver autosaves conversation state;
  `tests/test_api_reliability.py` and `tests/test_service_reliability.py`
  cover restart recovery.
- Gap: duplicate-petition protection on resume relies on a session-id check;
  the submit endpoint does not currently carry an idempotency key per SRS §J.
- Required change: idempotency key on `/sessions/{id}/submit` and on the
  future external-submission call.
- Phase: 1 (local) + 9 (external).

### FR-018 Accessibility — **Partial**, **Medium**
- Evidence: 67 `aria-*` attributes in `app/static/index.html`, 51 in
  `app/static/app.js`. Responsive CSS at `app/static/app.css` with ~32
  breakpoints and the Playwright harness `scripts/responsive_check.py`.
- Gap: no automated keyboard-only or screen-reader path test runs in CI;
  focus state on dynamic voice status announcements is not verified.
- Required change: axe-core run in `responsive_check.py`; test for the
  dynamic status announcements SRS §12.1 asks for.
- Phase: 1 + 2.

### FR-019 Feedback — **Missing**, **Low**
- Evidence: `grep -rln "feedback\|report_incorrect" app/` finds nothing in
  the API/UI surface.
- Required change: a report-this-is-wrong path for transcription,
  classification, source and generated text, writing to a reviewer queue.
- Phase: 4 (classification) + 6 (RAG) + 2 (UX).

### FR-020 Operational diagnostics — **Missing**, **High**
- Evidence: `grep -rn "correlation_id\|request_id\|X-Request-ID" app/`
  returns nothing. `app/logging_setup.py` sets up JSON logs but without a
  per-request correlation ID.
- Gap: without a correlation ID the AC-13 and SRS §10.4 audit requirements
  cannot be met: an officer cannot trace a user-reported bug through
  attachment upload → extraction → classification → compose → export.
- Required change: FastAPI middleware that assigns a correlation ID per
  request/websocket, propagates it to the LLM/STT/TTS adapters, and renders
  it in logs. The mask layer `app/services/mask.py` already keeps secrets
  and identity numbers out of logs; the gap is only the correlation ID.
- Phase: 0.

---

## 3. Acceptance tests (AC-01 — AC-18)

For each row: current pass/fail against the test suite as it exists today,
and the measurement that would actually prove it.

| AC | Status | Evidence / measurement needed |
|---|---|---|
| AC-01 | Partial | Typed path works end-to-end (`tests/test_flow.py`). Verified by `/api/sessions` POST + message loop; no voice provider is needed. |
| AC-02 | **Fails** | Voice/draft in each advertised language is tested only in Tamil (`tests/test_tamil_conversation.py`, `tests/test_every_language_interview.py`). English + Tamil pass; Malayalam/Hindi/Telugu voice path has not been exercised and the retrieval numbers in §4 say the knowledge layer would answer wrongly even if it had been. |
| AC-03 | Partial | `tests/test_voice_states.py`, `tests/test_voice_turn_taking.py`, `tests/test_voice_generating_socket.py` cover reconnection and duplicate-commit protection. Not covered: hard refresh *after* generation. |
| AC-04 | Implemented | `tests/test_attachment_upload.py`, `tests/test_document_intelligence.py`, `tests/test_ocr_pages.py`. Page-level OCR provenance verified by `test_ocr_pages.py` (added earlier this session). |
| AC-05 | Implemented | `tests/test_attachments.py:473-514` asserts no citizen upload reaches the shared RAG store. The invariant is enforced by `app/services/attachment_store.py:1-22`. |
| AC-06 | Partial | `app/knowledge/analyst.py:215` grounding check protects the analyst layer. Final rendered letter prose is NOT re-checked against the retrieval set, so an invented reference inserted at compose time by a model would survive. See FR-010 gap. |
| AC-07 | Partial | Citations resolve to real indexed chunks via `app/knowledge/schema.py:62`, `source_url` and `app/knowledge/legal_status.py`. No test proves the cited passage *supports the specific claim* beyond substring presence; before this session, `rule 29` substring-matched `rule 290` and `No. 16` matched `No. 164` — now fixed, with tests. See §9. |
| AC-08 | Implemented | `tests/test_corpus_current_law.py`, `tests/test_legal_status.py`, `tests/test_conflicts.py`. Empty-corpus path returns `UNVERIFIED` via `tests/test_knowledge.py::TestAnalyst::test_it_reports_the_refusal_sentence_when_nothing_is_indexed`. |
| AC-09 | **Missing** | Routing does not exist (FR-008). An AC-09 test would fail construction. |
| AC-10 | Partial | `tests/test_grievance_edit.py`, `tests/test_revision.py`. No preview/diff before an AI regeneration overwrites approved text — see FR-011. |
| AC-11 | Partial | `tests/test_package.py` opens the generated DOCX/PDF. Tamil is checked; the font path for ml/te/hi is not — see FR-013. |
| AC-12 | **Fails open** | `tests/test_officer.py`, `tests/test_privacy.py` check the authenticated case. The fail-open path in `officer_store.py:102-105` means an unauthenticated public request would list every petition. Must be fixed before any public deploy. |
| AC-13 | Partial | `tests/test_privacy.py` + `app/services/mask.py` cover identity-number masking. No test proves a correlation ID is present and no raw grievance leaks. See FR-020. |
| AC-14 | Implemented | `tests/test_failover.py`, `tests/test_service_reliability.py`, `tests/test_api_reliability.py`. The retrieval evaluation already surfaced that a Gemini `RESOURCE_EXHAUSTED` degrades retrieval honestly. |
| AC-15 | Partial | `docs/operations.md`, `docs/releases-and-rollback.md`, `deploy/scripts/backup-offsite.sh`, `deploy/scripts/restore-test.sh` exist. Scheduled off-instance backup is documented but not confirmed installed on the running EC2 host (plan file §0.5). |
| AC-16 | **Measured for the first time** | `benchmarks/run_retrieval_eval.py` + `var/reports/retrieval.json`: EN hybrid R@5 1.00, Tamil 0.20, Malayalam 0.00, Telugu 0.20, Hindi 0.00 (n=30 queries). Classification per-language slice not yet reported. |
| AC-17 | Not applicable yet | No external submission integration exists (FR-016). Nothing is displayed as submitted to a department. |
| AC-18 | Missing | Pilot sign-off record does not exist in the repository. |

---

## 4. Non-functional requirements — summary by SRS section

| SRS | Status | Notes |
|---|---|---|
| §5.1 languages | Partial | 5 declared, 2 wired through state (FR-001). |
| §5.3 voice | Partial | `/ws/voice` is built (`app/api/ws.py:353`, `app/services/voice.py`) with VAD/barge-in/half-duplex. **It is not opened by the citizen UI**: `grep /ws/voice app/static/app.js` returns nothing, and `tests/test_page_translation.py:247-251` asserts it must not. Push-to-talk via `/ws/dictation` is used instead. Re-enabling the full agent reopens a deliberate safety decision (see plan §Phase 5). |
| §6 attachments | Partial | No malware scan (FR-014). |
| §7 routing | **Missing** | No department taxonomy, geography, urban/rural (FR-008). |
| §8 RAG | Partial | Corpus exists, grounding exists, measurement exists, cross-language is weak (FR-009, AC-16). |
| §9 export | Partial | Tamil + English fonts only (FR-013). |
| §10.1 identity/access | Partial / fail-open | `officer_store.py` fail-open gap (FR-012). |
| §10.2 data protection | Partial | Secrets never logged (`app/services/mask.py`); retention policy unset (FR-015). |
| §10.3 prompt injection | Partial | Attachment content is treated as data, not instructions (`app/services/document_intelligence.py` has no eval). No red-team test today. |
| §10.4 audit | Partial | No correlation ID (FR-020). Officer actions audited in `app/api/officer.py:348` (`review`). |
| §11.4 API contract | Partial | OpenAPI generated by FastAPI. No explicit stable error-code vocabulary. |
| §12.2 monitoring | Partial | `/api/health` at `rest.py:198` exists; no alert ownership defined in-repo; the plan calls out that `/health` is unauthenticated and discloses build SHA and provider inventory, which is a disclosure risk. |
| §12.3 cost/quota | Partial | Embedding provider rotates 10 Gemini keys; voice/LLM providers have failover chains in `config.py`. Per-session user quotas: not configured. |
| §13 data model | Partial | Core entities present; SRS §J calls for Petition revision / Document-generation version / Submission attempt / External reference mapping / Attachment scan status / Retention policy / Legal hold / Workflow transition rule / SLA deadline / Knowledge-source approval history / Consent event — most are missing. |
| §15 ops | Partial | Dockerfile + nginx + deploy scripts in `deploy/`; CI runs no tests before deploy (plan §0.2). |

---

## 5. Blockers requiring stakeholder decision

1. **Final product name** (addendum §A). SRS calls it "Citation Petition
   Assistant"; the repo and UI use "Citizen Petition Assistant"; stakeholders
   have not picked one.
2. **Release scope**: Option A (web + kiosk + officer only) or Option B
   (+ Android + iOS). Project memory `[[petition-fixed-decisions]]` and the
   plan file assume Option A.
3. **Citizen access model** (addendum §C): assisted kiosk, OTP, resume link,
   anonymous. The repo today assumes assisted kiosk; `app/services/
   officer_store.py:102-105` is the fail-open path to close.
4. **Approved source corpus** completeness: 18 TN instruments are indexed;
   SRS §8.6 wants corpus health exposed. Which departments are in scope and
   which GOs the knowledge curator approves is a decision outside this repo.
5. **Retention periods** for every entity (addendum §H).
6. **Numeric acceptance thresholds** per language and per task
   (addendum §E) — must be approved before AC-16 can grade pass/fail.
7. **Legal-hold policy** (addendum §H).
8. **ClamAV adoption** (FR-014).
9. **Translation of ~1,000 UI strings** by native speakers (FR-001).

---

## 6. Phase 0 — safety baseline (LANDED, awaiting local verification)

Smallest-safe-change scope, no scope creep. Each row carries the change,
the file(s), the test that pins it, and whatever caveat belongs with it.

| # | Change | File(s) | Test | Status |
|---|---|---|---|---|
| 0.1 | Close the fail-open citizen scope | `backend/app/services/officer_store.py` (`can_access` added; `citizen_scope` no longer answers `None`), `backend/app/api/{rest,dictation,ws}.py` wire-up | `backend/tests/test_citizen_scope.py` (10 tests, new); `tests/test_officer.py`, `tests/test_petition_catalog.py`, `tests/test_privacy.py` kept green | **Done** |
| 0.2 | Pytest gate on CI deploy | `.github/workflows/deploy.yml` already runs `python -m pytest` at the `tests` job (lines 185-245) and `deploy` carries `needs: [preserve-previous, tests, build-and-analyze]` at line 272 | existing CI | **Was already in place.** The audit matrix originally repeated an outdated claim; this row corrects it. No workflow change was needed. |
| 0.3 | Correlation ID middleware | `backend/app/api/middleware.py` (new); `backend/app/logging_setup.py` (`_correlation_id` ContextVar, `correlation_context`, formatters updated); `backend/app/main.py` adds it outermost | `backend/tests/test_correlation_id.py` (10 tests, new) | **Done** |
| 0.4 | Rate-limit `/ws/dictation`; cache `/api/health` | `backend/app/api/dictation.py` (dedicated `ws_limits.Gate` for dictation, same shape as the voice gate); `backend/app/api/rest.py` (`_HEALTH_TTL = 30s` process-wide cache for `/api/health` behind an `asyncio.Lock`, probes no longer run per hit) | `backend/tests/test_dictation_gate.py`, `backend/tests/test_health_caching.py` (6 tests, new) | **Done**. Nginx-level rate limiting is still an administrator action; the application-level cache turns a provider-probe DoS into a cheap steady state. |
| 0.5 | Prepare off-instance backup — scripts, syntax check, docs | `deploy/scripts/{backup.sh,backup-offsite.sh,restore-test.sh}` all pass `bash -n`; `docs/operations.md` extended with a "Current install state" section noting none of this is installed on production yet | `backend/tests/test_deploy_scripts_syntax.py` (3 tests, new) | **Prepared locally; NOT scheduled on production** per the rule `[[local-first-then-approval]]`. The administrator action — cron entries, S3 bucket, Secrets Manager entry, instance role — stays with the person who owns those credentials. |

Open the Phase 1 (petition data integrity) scope only after 0.1-0.5 land and
Harish tests them locally per project memory `[[local-first-then-approval]]`.

---

## 7. Phase 1 — petition state, canonical versions, recoverability, Start Over safety

Status: **implemented locally; awaiting Harish's local review**. No commits,
no deploy, no production data touched. Full test suite exit 0 (2,440
passing, 4 skip, 0 fail, 0 error from `backend/`).

| # | Change | File(s) | Test | Status |
|---|---|---|---|---|
| 1.1 | Status transition audit log — one row per status move with from, to, actor, source, reason, timestamp and correlation id. Bounded to the last 200 entries. The interrupted-render recovery is logged with `source="recover"`, `actor="system"`. | `backend/app/graph/state.py` (`transitions` field added), `backend/app/graph/workflow.py` (`_record_transition`, `_transition_entry`, invoke/update/snapshot call sites, `as_node="verify"` on recovery and `"validate"` on metadata write) | `backend/tests/test_transition_log.py` — 6 tests covering: no-move produces no row; a real move writes one row of the SRS shape; the correlation id present at request time shows up on the row; the recovery path writes `actor=system`, `source=recover`; the log is capped at `_TRANSITIONS_LIMIT` | **Done** |
| 1.2 | SRS-aligned lifecycle label — `srs_label(state)` renders the internal 7-value status set into the SRS 10-value vocabulary, including the two derived states (`Exported` when a document exists, `Submitted (local record only — not an official filing)` when `submitted_at` is set). Exposed in `/api/sessions/*` responses under `lifecycle`. Behaviour unchanged; this is a formatter. | `backend/app/domain/lifecycle.py` (new), `backend/app/api/views.py` (`lifecycle` key in `session_view`) | `backend/tests/test_srs_lifecycle.py` — 12 tests covering: every internal → SRS mapping; the two derived labels; the submission label explicitly says "local record only" so a UI reader cannot mistake it for a filing (FR-016); the helper does not mutate input and handles `None` safely | **Done** |
| 1.3 | Restart no longer leaks the previous petition — attachments on the state and on disk, `attachments_offered`, `attachments_done`, `analysis`, `emblem`, `submitted_at` and `translation_origin` are cleared; `attachment_store.discard_session(session_id)` runs as a best-effort side effect. `merge_turns` learns a reset sentinel so the chat log is actually discarded on Start Over, not appended-onto. | `backend/app/graph/nodes.py` (restart branch), `backend/app/graph/state.py` (`_RESET_MARKER`, `reset_marker_turn`, updated `merge_turns`) | `backend/tests/test_restart_isolation.py` — 4 tests covering: fields and output cleared; every leak class cleared; the real `attachment_store.discard_session` is called with the exact session id; the previous conversation does not reappear in the next session (the SPECIFIC regression the Phase 1 brief flagged) | **Done** |
| 1.4 | Kiosk cleanup discards the server-side session, not only the browser's localStorage. `kioskRestart` POSTs to `/api/sessions/{sid}/restart` before `forgetSession()`, so the next citizen does not inherit the previous one's enclosures or draft. | `backend/app/static/app.js` (`kioskRestart`) | existing kiosk-test coverage still passes; new coverage not added because the UI-level timeout is Playwright territory and runs outside this suite (listed in §9 remaining risks) | **Done (code-level); still needs a Playwright pass before AC-02 can be re-graded for kiosk** |
| 1.5 | Database migration safety — the single new field (`transitions: list[dict]`) was added to the TypedDict only; the LangGraph SqliteSaver stores state as JSON blobs so no SQL schema change is required. Reads on legacy sessions degrade safely via `state.get("transitions") or []`. | `backend/app/graph/state.py` | implicit — covered by the existing checkpoint-recovery tests (`tests/test_api_reliability.py`, `tests/test_service_reliability.py`), which continue to pass | **Done** |

### 7.1 What Phase 1 does NOT yet touch

- A full internal-vocabulary migration to the SRS 10-value set. The 7-value
  set stays as the single source of truth; `srs_label` is the formatter. A
  rename ripples through ~90 call sites and belongs to a dedicated phase.
- A `revision/version conflict` resolver with merge semantics. Today the
  version guard (`_version_guard` in `app/api/rest.py`) rejects a stale
  write with 409; an officer-side merge path is not implemented. The SRS
  §9.2 asks for a diff/preview on substantial AI regenerations; that is
  the FR-011 preview-and-confirm UX from §2 of this matrix.
- Explicit "Approved by citizen" as a status value. Today the service
  conflates "generated" with "approved" at `status == "ready" AND
  confirmed == True`. A distinct `approved` state would need a new UI
  button + an audit row + a Playwright test — out of this phase's scope.
- Idempotency keys on `/sessions/{id}/submit`. The current submit is
  already idempotent for repeated clicks (keeps first timestamp) but does
  not carry a request-level key per SRS §J. Deferred to Phase 9.

### 7.2 Phase 1 scenarios — mapping to tests

## 9. Phase 2 — India Code TN importer, quarantine, curator review (14 October 2026)

Status: **plumbing built end-to-end; live upstream could not be fetched
this session; 0 documents discovered**.

The brief limited Phase 2 to a single importer (India Code TN) with a
quarantine-first flow and a curator-review screen. Everything on the
"written in code and tested" axis landed. On the "ran against live
upstream" axis, India Code's TN collection page returned 504 Gateway
Timeout and `robots.txt` was unreachable — Python's `urllib.robotparser`
treats an unreachable robots.txt as "disallow all", so the CLI refused to
proceed. That is the safer default; nothing was fetched. It would be
dishonest to populate the quarantine with fabricated rows to make the
screen look full.

| # | Change | File(s) | Test | Status |
|---|---|---|---|---|
| 9.1 | Quarantine schema — SQLite table storing the twelve fields the brief named plus `review_reason`, `reviewer`, `reviewed_at`, `duplicate_of`. Row id is a local UUID; `(source_id, official_url)` is unique so a second discovery is a no-op. States: `discovered`, `pdf_fetched`, `unreachable`, `approved`, `rejected`, `duplicate`, `outdated`. Terminal states only reachable via `review()` — `set_status()` refuses them so a reviewer attribution can never be bypassed | `backend/app/knowledge/quarantine.py` (new) | `backend/tests/test_quarantine.py` — 16 tests covering idempotent insert, document-type whitelist, http(s) check, state transitions, review-requires-reason, review-twice refused, listing + status filter, SHA-256, PDF path | **Done** |
| 9.2 | India Code DSpace parser — collection listing and item page as pure functions over HTML. Correctly classifies Act, Rule, Regulation, Ordinance, Notification, Government Order, Amendment. `amendment_status` is NEVER inferred — per rule 11, it stays `unknown` until a curator reads the Gazette | `backend/app/knowledge/india_code.py` (new) | `backend/tests/test_india_code.py` — 11 tests: collection listing + dedupe, Act item parsed with Dublin Core + table rows, missing Act number lands as None, amendment classification + `amends:` recovered into `extra`, PDF-less item parses, empty/404/no-metadata HTML raises `ParseError` | **Done** |
| 9.3 | Discovery CLI — polite 3s/host, service User-Agent, respects robots.txt, caps at 100 items unless `--limit` says otherwise. Writes JSON report. `fetch-pdfs` is a separate step so a slow upstream does not stall discovery. `stats` prints the quarantine counts | `backend/scripts/ingest_india_code_tn.py` (new) | `backend/tests/test_ingest_india_code_tn.py` — 3 tests: `_source` resolves `indiacode-tn`, refuses `wikipedia-tn-laws` with "non-citable", refuses an unknown source id | **Done** |
| 9.4 | Curator review API — list, read, approve/reject/duplicate/outdated with reason. Reviewer id is pulled from the signed-in officer, NOT the request body. Cross-origin review refused. Same-origin + officer auth = standard officer surface | `backend/app/api/officer.py` (`/api/officer/curator/*` endpoints added) | `backend/tests/test_curator_api.py` — 15 tests covering auth, listing, filtering, every review action, reason-required cases, duplicate-needs-target, reviewing-twice-refused, cross-origin refused | **Done** |
| 9.5 | Curator review screen — new SPA route at `/officer/curator`. Table of pending rows with inline review form per row; approval links to the next operator pass, does not auto-write to the corpus | `backend/app/static/officer.js` (`curator()` function, dashboard link) | manual verification once live. The underlying API is covered by the test file above | **Done** |

### 9.1 Live-upstream result, said plainly

Running `python scripts/ingest_india_code_tn.py discover --limit 5` from
this environment on 14 October 2026 returned:

```
{
  "status": "robots_disallowed",
  "source": "https://www.indiacode.nic.in/handle/123456789/2507/"
}
```

The sibling `scripts/discover.py check --source indiacode-tn` returns
`unreachable` on the TN handle page (504 Gateway Timeout observed), and
`https://www.indiacode.nic.in/robots.txt` itself timed out. Python's
`RobotFileParser` reads an unreachable `robots.txt` as "disallow all" —
which is the correct default — and the CLI's `--limit 5` run refused to
touch the site.

**Discovered this session: 0. Quarantined: 0. Approved: 0. Rejected: 0.**
The plumbing is proven by 45 passing tests plus the full-suite sweep.
Nothing was fabricated to pad the counts.

### 9.2 What this scope will NOT do

- No bulk download of every TN Act from India Code — one `--limit N` pass
  at a time, polite spacing, upstream-respecting.
- No automatic promotion of an approved row into `corpus/tamil_nadu.yaml`.
  Approval is a signal; the write is a deliberate operator pass.
- No automatic amendment-relationship extraction — the parser surfaces the
  `Amends` row into `extra.detail_rows` so the curator can see it and
  write a `legal_relationships.yaml` row by hand after approving both the
  parent Act and the amendment.

### 9.3 Phase 2 scenario → test mapping (brief rule 10)

| Rule-10 scenario | Covered by |
|---|---|
| duplicate documents | `test_quarantine.py::TestInsertAndIdempotency::test_the_same_url_twice_returns_the_first_id`, `test_curator_api.py::TestReviewActions::test_duplicate_with_a_target_links_the_two` |
| broken URLs | `test_india_code.py::TestBrokenHtml` (3 tests), `test_india_code.py::TestMissingPdfLink`; CLI also marks rows `unreachable` on timeout/4xx — behaviour tested indirectly via the `set_status` state transition tests |
| outdated documents | `test_curator_api.py::TestReviewActions::test_outdated_with_a_reason_records_everything`; parser never claims current status (`test_india_code.py::TestItemPage::test_a_normal_act_item_is_parsed` holds the invariant) |
| missing Act numbers | `test_india_code.py::TestItemWithoutActNumber` |
| amendment relationships | `test_india_code.py::TestAmendmentDetection::test_an_amendment_items_metadata_is_surfaced_in_extra` |
| discovery-only source blocking | `test_source_registry.py::TestTheDiscoveryOnlyLine` (registry side) + `test_ingest_india_code_tn.py::TestTheRegistryGate::test_a_discovery_only_source_cannot_be_targeted` (CLI side) |

---

## 8. Legal intelligence — source registry and discovery (14 October 2026)

Status: **source catalogue and reach-check landed; per-portal ingest not
built, see [docs/legal-intelligence-roadmap.md](legal-intelligence-roadmap.md)**.

The operator brief asked for a crawler across 33+ TN government portals.
That is a multi-month engineering project; this session built the
foundation and the enforcement line, not the crawler.

| # | Change | File(s) | Test | Status |
|---|---|---|---|---|
| 8.1 | Source registry — 42 URLs across six priority tiers from the brief, with the discovery-only line enforced at parse time | `backend/corpus/source_registry.yaml` (new), `backend/app/knowledge/source_registry.py` (new) | `backend/tests/test_source_registry.py` — 16 tests covering: file loads cleanly, every tier/kind/access is valid, ids and urls are unique, Wikipedia is discovery-only, tier_6 and `access: discovery_only` are coupled both ways (two symmetric tests) | **Done** |
| 8.2 | Officer-side source ranking — findings order by tier so Gazette citations read above repository ones | `backend/app/api/officer.py::grounded` | 3 tests under `TestFindingsRankedByTier` in `tests/test_source_registry.py`, existing officer tests still green | **Done** |
| 8.3 | Reachability probe — HEAD-check with polite spacing, robots.txt, discovery_only lockout, dry-run mode, per-source and per-tier filters, JSON report | `backend/scripts/discover.py` (new) | smoke-tested with `python scripts/discover.py list` and `check --dry-run` (shell-level, no new pytest row — the script is a thin wrapper around `httpx` and the already-tested registry) | **Done** |
| 8.4 | Officer-view "expose, don't withhold" fix for undetermined conflicts (also covered in §7 above as the Phase-1 live-screen fix) | `backend/app/api/officer.py::grounded` early return removed | `tests/test_officer.py::test_grounding` re-pinned to the SRS §8.5 behaviour; `tests/test_officer_layout.py` + `tests/test_conflicts.py` still green | **Done** |

### 8.1 Deferred to Phase 2 (named, not stubbed)

- Per-portal ingesters. India Code TN handle is the highest-value next
  one (~2 days). Thirty-plus is a 4-6 month project (roadmap §4).
- Automatic amendment detection from the Gazette feed. ~1-2 weeks of
  LLM+regex work; every row produced needs curator approval.
- Scheduled crawler on the production host. Administrator action.
- Curator-review UI for the quarantine queue. ~3-5 days.
- Bilingual (Tamil↔English) Act titles on the officer page. ~2-3 days.

### 8.2 What this scope will NOT do, said plainly

- No fabricated URLs, G.O. numbers, section numbers or document contents.
  Documents enter the corpus only via `tamil_nadu.yaml` after a curator has
  read the actual PDF and recorded the exact URL and legal status.
- No bulk crawling against government portals from this session.
- No Wikipedia citation under any circumstance.
- No automatic marking of a document as "current law" based on its
  presence in an index — SRS §8.5 and the brief are explicit.

---

| Phase 1 scenario (from the brief) | Covered by |
|---|---|
| Create a new draft, save after every answer | `tests/test_flow.py`, `tests/test_conversation.py` (existing, kept green) |
| Refresh during intake | `tests/test_api_reliability.py` (existing) |
| Resume a saved draft | `tests/test_api_reliability.py`, `tests/test_service_reliability.py` (existing) |
| Lose network / AI timeout / STT fail / attachment fail | `tests/test_failover.py`, `tests/test_voice_states.py` (existing) |
| Duplicate retry request | `tests/test_voice_turn_taking.py` + submit idempotency in `tests/test_submit.py` (existing) |
| Concurrent edit conflict | `_version_guard` in `app/api/rest.py`; `tests/test_revision.py` (existing) |
| Edit after generation | `tests/test_grievance_edit.py`, `tests/test_revision.py` (existing) |
| Start Over with confirmation; cancellation | `kioskRestart` + UI `confirmThen`; `tests/test_restart_isolation.py` (new) covers the backend half |
| New Petition after an incomplete draft; previous conversation does not appear | `tests/test_restart_isolation.py::test_old_conversation_messages_do_not_reappear` (new) |
| Kiosk timeout and cleanup | `tests/test_kiosk.py` (existing) + the new `kioskRestart` server-side cleanup — Playwright still needed |
| Access another citizen's draft | `tests/test_citizen_scope.py` (Phase 0.1) |
| Export a specific petition version | `tests/test_revision.py` (existing) |
| Submitted cannot be created without authoritative confirmation | `tests/test_srs_lifecycle.py::test_submission_label_names_itself_as_a_LOCAL_record_only` (new) — the label makes the local-only nature explicit on every read |

---

## 7. What was NOT touched by this audit

- `app/` application code: unchanged by this audit pass.
- `scripts/`, `benchmarks/`, `tests/`: unchanged.
- Database `var/knowledge.sqlite`: not re-ingested or re-written.
- `corpus/`, `deploy/`: unchanged.
- Git: no `add`, `commit`, `push`, `rebase`, `amend`, or branch change.

---

## 8. Earlier same-session changes (correctness fixes, not SRS scope)

Three correctness changes landed earlier in this working session, before
this audit was written. They have their own tests and belong to the
knowledge layer. They are listed here for traceability so the diff is not
mistaken for SRS implementation.

1. `app/knowledge/analyst.py:215-249` — whole-token digit guard in
   `grounded()`. Three new tests in `tests/test_knowledge.py`.
2. `app/knowledge/legal_status.py:218-234` — `UNKNOWN` state when a passage
   has no heading in an instrument that has declared amendments. One test
   added and one test updated in `tests/test_legal_status.py`.
3. `app/knowledge/ingest.py:598-633` — carry a section label across page
   boundaries in `chunk_document`. Two new tests in
   `tests/test_knowledge.py`.

These address three defects that were masking the AC-07 citation-support
guarantee. Chunk IDs are unchanged (text + ordinal based), so the stored
index remains valid.

---

## 9. Production-readiness verdict

**NOT READY — audit incomplete**: this document is the first pass of the §K
matrix. **NOT READY — acceptance gates failing** on AC-02, AC-09, AC-12, and
on measured cross-language retrieval for AC-16. **BLOCKED — external
decision or dependency required** on items 1-9 of §5.

The system may not be marketed, piloted, or deployed outside the
pixoustech test host until the Phase 0 items in §6 land, Harish confirms
them locally, and the §5 decisions are recorded.
