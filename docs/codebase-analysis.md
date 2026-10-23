# Codebase analysis — Citizen Petition Assistant

Written for: Harish. Snapshot as of 2026-10-15, taken against the local
working tree (no commits, no pushes). Numbers are measured against the
current files, not against docstrings.

---

## 1. At a glance

| Area | Measurement |
|---|---|
| Backend Python LOC | **~32,700** across **76 modules** (`app/`), plus 4,341 in `scripts/` and 3,371 in `benchmarks/` |
| Test code | **26,664 LOC**, **85 test files**, **2,491 tests collected**, 6 `skipif` markers, 0 `xfail` |
| Static UI | **8,940 LOC** — `app.js` 4,364, `officer.js` 654, `app.css` 1,683, `officer.css` 755, three HTML shells |
| Dependencies | 17 top-level in `requirements.txt`. No framework sprawl. |
| API surface | **41 REST endpoints** + **2 WebSockets** across 5 routers (`rest`, `officer`, `operator`, `catalog`, `dictation`) |
| Knowledge corpus | **18 documents / 8,344 chunks / 8,072 vectors (96.74%)** against `gemini-embedding-001 @ 1536d`. 272 remaining chunks are all `tn-ulb-rules-2023`, blocked on Gemini rate limits. |
| Legal relationships | **10 instruments / 18 Gazette-evidenced changes** (10 `amends`, 5 `inserts`, 3 `substitutes`) in `corpus/legal_relationships.yaml` |
| Source registry | **42 sources / 6 priority tiers**; only `wikipedia-tn-laws` is non-citable (`discovery_only`) |
| Full-suite exit | **0 FAILED, 0 ERROR, 4 skip** on last run |
| Working tree | 35 modified files + ~45 untracked (Phase 0–2 work, local only) |

---

## 2. Architecture

### 2.1 Shape

```
┌────────────────────────────────────────────────┐
│  app/static/           CITIZEN PAGE (app.js)   │
│                        OFFICER (officer.js)    │
│                        OPERATOR (operator.js)  │
└─────────────────┬──────────────────────────────┘
                  │  HTTP + WS
┌─────────────────▼──────────────────────────────┐
│  app/api/              5 routers, 41 REST,     │
│  middleware.py         2 WS (/voice, /dictation)│
└─┬──────────────┬───────────┬─────────┬────────┘
  │              │           │         │
┌─▼──────────┐┌──▼─────────┐┌▼───────┐┌▼──────────┐
│ app/graph/ ││ app/services││app/     ││ app/      │
│ LangGraph  ││ asr/tts/ocr││knowledge││ domain/   │
│ (nodes,    ││ llm/mask/  ││RAG      ││ fields,   │
│ workflow)  ││ render/pkg ││stack    ││ lang,     │
└────┬───────┘└────┬────────┘└───┬─────┘└───────────┘
     │             │             │
┌────▼─────────────▼─────────────▼───────────────┐
│  var/  sessions.sqlite (LangGraph checkpoint)  │
│        knowledge.sqlite (sqlite-vec + FTS5)    │
│        officer.sqlite, local_bodies.sqlite,    │
│        quarantine.sqlite (India Code imports)  │
└────────────────────────────────────────────────┘
```

### 2.2 Load-bearing choices

- **Single-process**. `--workers 1` is architecturally mandatory today: in-process asyncio locks (`Workflow._locks` is a `WeakValueDictionary`), one SQLite file, an `app.state` cache (`ws_gate`, `dictation_gate`, health cache). Scaling to multiple workers would need Redis for the gates and either a server DB or SQLite-WAL contention tolerance.
- **Deliberate egress gate**. `allow_external_ai` defaults false in `app/config.py`. A key present without the flag set does nothing. Citizen text does not leave the box by accident.
- **LangGraph for conversation**. One citizen utterance = one `ainvoke`. The checkpoint persists per `session_id`. A dropped WebSocket loses nothing.
- **sqlite-vec + FTS5** for retrieval. No vector-DB server, no re-indexing step on redeploy. Hybrid retrieval uses reciprocal-rank fusion.
- **Two voice paths**. `/ws/voice` is the full continuous-dictation agent, built and tested (~2 KLOC in `ws.py`, 549 LOC `asr.py`, 500+ in `voice.py`). It is **not opened by the citizen page** — `test_page_translation.py` asserts the fetch URL contains no `/ws/voice`. Push-to-talk `/ws/dictation` is the live path. Re-enabling the agent reopens a deliberate safety decision.

### 2.3 Hotspot modules (by LOC)

```
app/api/ws.py                  2,061   full voice-agent socket
app/graph/nodes.py             1,752   every intent handler
app/api/rest.py                1,427   41 REST endpoints
app/services/system_one.py       954   grievance classifier
app/knowledge/ingest.py          844   PDF → chunks pipeline
app/domain/fields.py             799   per-field validators
app/services/render.py           735   DOCX + PDF rendering
app/services/llm.py              710   provider rotation
app/domain/phrasing.py           650   per-language prompts
app/services/speech_text.py      617   TTS normalisation
app/domain/letter.py             609   letter template engine
```

`ws.py` and `nodes.py` are structurally the two files most worth test
coverage; both are well covered (ws.py by `test_voice_*.py`, nodes by
`test_conversation.py`, `test_flow.py`, `test_grievance_edit.py`).

---

## 3. Phase status — what shipped vs what is pending

### 3.1 Shipped locally in this working tree (not yet committed)

**Phase 0 safety baseline** — all five items landed with tests. See
[docs/requirements-traceability.md §6](requirements-traceability.md).
- `0.1` fail-closed `can_access` ([officer_store.py](../backend/app/services/officer_store.py)) + 10-test `test_citizen_scope.py`
- `0.2` pytest already a CI deploy gate (deploy.yml `tests` job + `deploy` needs it)
- `0.3` correlation-ID middleware (new `app/api/middleware.py`, 10 tests)
- `0.4` `/ws/dictation` rate gate + `/api/health` 30 s cache (6 new tests)
- `0.5` backup / restore-test scripts in `deploy/scripts/` with `bash -n` test. **Not scheduled on production** — administrator action.

**Phase 1 petition state + Start Over** — all four items landed with
tests. See [§7 of the matrix](requirements-traceability.md).
- `1.1` status-transition audit log on `LetterState.transitions` (6 tests)
- `1.2` SRS-aligned `lifecycle` label via `domain/lifecycle.py` (12 tests)
- `1.3` restart leak closed — attachments + state + chat log (4 tests)
- `1.4` kiosk-restart server-side discard
- `1.5` no DB migration needed (checkpointer JSON-backed)

**Phase 2 legal intelligence** — foundation only, as the brief limited it.
See [§8-9 of the matrix](requirements-traceability.md) and
[docs/legal-intelligence-roadmap.md](legal-intelligence-roadmap.md).
- `source_registry.yaml` — 42 URLs, 6 tiers, parser (16 tests)
- `scripts/discover.py` — HEAD-only reach probe with robots.txt + polite
- `app/knowledge/india_code.py` + `scripts/ingest_india_code_tn.py` — DSpace parser + CLI
- `app/knowledge/quarantine.py` — staging table with full curator lifecycle
- Officer-page tier ranking of citations
- **Curator UI removed** per your 2026-10-15 request. The underlying data layer (quarantine schema, India Code parser, discovery CLI) stays importable and tested so a future UI can be added without rewriting the backend.

**Officer-page cleanup** (2026-10-14/15, driven by your paste reviews):
- Grounded view "expose, don't withhold" fix behind undetermined conflicts
- Source dedup by (title, section, page)
- Warning dedup (first-six-word prefix)
- Finding cards with soft borders, "Show N more" expandable
- Suggested Process shared "Grounded in:" footer
- Source title suppression when it matches the finding value

### 3.2 Known gaps (not shipped in this tree)

| Area | SRS | Status |
|---|---|---|
| Attachment malware scan | FR-014, §6.2 (2) | **Missing**. `grep -rln clamav` empty. Admin decision on ClamAV vs managed service. |
| Nginx-level rate limits | §12.2 | **Deferred** — administrator action on `deploy/nginx/`. |
| Backup cron scheduled on prod | §15.3 | **Deferred** — bucket + secret + instance role are admin owned. |
| Feedback path for wrong citation / wrong transcript | FR-019 | **Missing**. No endpoint. |
| Preview/diff before AI regenerate | FR-011 | **Partial** — `_version_guard` returns 409 on stale; no diff UI. |
| Idempotency keys on `/submit` | §J | **Partial** — repeat clicks keep first timestamp; no cross-worker key. |
| Approved-by-citizen state | §3.3 Table 4 | **Partial** — conflated with `ready + confirmed`. |
| Font support ml/te/hi/dev | §9.3 | **Missing** fonts; renderer picks font by Tamil-codepoint test only. |
| `Language` typed in LangGraph state | FR-001 | **Partial** — `Literal["en","ta"]` in `graph/state.py:19` even though 5 languages are in `SUPPORTED`. |
| Automatic amendment detection | §8.5 | **Not built** — Gazette-feed → amendment-regex is ~1-2 weeks per [roadmap §4](legal-intelligence-roadmap.md). |
| Per-portal ingesters (33+) | §8.2 | **Not built** — see [roadmap §3](legal-intelligence-roadmap.md). India Code TN is the only one wired. |

---

## 4. Measured quality

### 4.1 Retrieval (var/reports/retrieval.json, 2026-10-13)

Hybrid Recall@5 against the labelled set in `benchmarks/retrieval_cases.py`:

| Lang | n | R@1 | R@3 | R@5 | MRR |
|---|---|---|---|---|---|
| **en** | 10 | 0.90 | 1.00 | 1.00 | 0.93 |
| ta | 5 | 0.00 | 0.20 | 0.20 | 0.10 |
| ml | 5 | 0.00 | 0.00 | 0.00 | 0.00 |
| te | 5 | 0.20 | 0.20 | 0.20 | 0.20 |
| hi | 5 | 0.00 | 0.00 | 0.00 | 0.00 |

Dense column has `n=2` because 28 of 30 Gemini embedding calls hit
`RESOURCE_EXHAUSTED` during the eval — the two that completed scored 1.00
R@5. The hybrid score for ml/hi is therefore effectively lexical-only
against English-indexed text, which is why it is zero. The English number
is a real production-ready signal; the four other languages need either
corpus translations, cross-lingual embeddings in both directions, or
query translation on the citizen side.

### 4.2 Classifier (docs/hardening-report.md)

```
Dev (90 cases) macro-F1   0.8640
Held-out       macro-F1   0.7317    ← the real number
Dev calibration (ECE)     0.1261
```

The dev / held-out gap is the honest statement: the classifier overfits
the dev set. SRS §14.3 asked for ≥95%; the honest 0.73 is **not** that.
Fix is corpus growth, not threshold tuning.

### 4.3 Suite execution

```
python -m pytest -q    →   2,491 tests collected
                           0 FAILED, 0 ERROR, 4 skip, 0 xfail
                           exit 0
```

Zero FAILED/ERROR on every phase sweep this session.

---

## 5. Security posture

### 5.1 Enforced in code

| Control | Where |
|---|---|
| Fail-closed citizen access | `app/services/officer_store.py:can_access`, 6 call sites |
| Correlation id on every HTTP + WS | `app/api/middleware.py`, log formatters in `logging_setup.py` |
| CSP + Permissions-Policy headers | `app/main.py:289-326` |
| GZip + CORS, allow-credentials true, origin list restricted | `app/main.py` |
| Rate gate on `/ws/voice` and `/ws/dictation` (separate counters) | `app/api/ws_limits.py:Gate`, wired in `ws.py:_gate` and `dictation.py:_dictation_gate` |
| `/api/health` cached 30 s, provider probes do not run per hit | `app/api/rest.py:_HEALTH_TTL` |
| PII mask on every log line | `app/services/mask.py::mask_pii`, applied in `JsonFormatter`/`TextFormatter` scrub |
| Officer login rate limit, scrypt password hash, HttpOnly SameSite=strict cookie | `app/services/officer_store.py` |
| Officer same-origin check on all mutating routes | `app/api/officer.py::same_origin` |
| Grounding guard — citations must appear whole in retrieved text; `rule 29` no longer matches `rule 290` | `app/knowledge/analyst.py::grounded` |
| Attachment store never writes under user-provided filenames | `app/services/attachment_store.py` |
| Restart wipes attachments on disk + state + chat log | `app/graph/nodes.py` restart branch + reset-marker in `state.py::merge_turns` |
| Audit log of state transitions, 200 max, keeps correlation id | `app/graph/workflow.py::_record_transition` |

### 5.2 Open items

Enumerated in [requirements-traceability.md §5](requirements-traceability.md),
condensed:

1. Attachment malware scan (admin: ClamAV vs managed).
2. Nginx-level rate limits (admin: production nginx config).
3. Backup cron (admin: S3 bucket, Secrets Manager, instance role).
4. CSRF token on same-origin posts (currently relies on same-origin + sec-fetch-site; a scheme that passes those but spoofs origin header is not blocked).
5. Numeric per-language acceptance thresholds (product owner).

### 5.3 What is in the tree but not in production

The server runs on `pixoustech` EC2 via `.github/workflows/deploy.yml`
auto-deploy from `main`. Everything in [§3.1 above](#31-shipped-locally-in-this-working-tree-not-yet-committed)
is **local-only**. Per project memory `[[local-first-then-approval]]` the
rule is: Harish tests locally, then approves a push.

---

## 6. Test coverage reading

Every `app/` module is imported by at least one test file (checked by
grepping `from app.*{name}` across `tests/`). No orphan code paths at
module level. Specific heavy coverage:

| Module | Covering tests (file count) |
|---|---|
| `app/knowledge/ingest` | 6 |
| `app/knowledge/store` | 5 |
| `app/knowledge/analyst`, `embeddings`, `schema` | 4 each |
| `app/knowledge/retrieve` | 3 |
| `app/knowledge/legal_status`, `conflicts`, `source_registry`, `vector_integrity`, `india_code` | 1 each — focused, non-redundant |

Coverage breadth is good; depth varies. Specifically well-covered: the
voice state machine (`test_voice_states.py`, `test_voice_turn_taking.py`,
`test_voice_grievance_flow.py`), the five-language acceptance path
(`test_five_language_acceptance.py`), the officer surface
(`test_officer.py`, `test_officer_layout.py`), citizen access control
(`test_citizen_scope.py`), petition catalog
(`test_petition_catalog.py`), start-over isolation
(`test_restart_isolation.py`), and transition audit
(`test_transition_log.py`).

Specifically under-covered:
- `app/api/ws.py` edge cases for simultaneous reconnect under flaky TTS
- Multi-language retrieval quality (we have `benchmarks/run_retrieval_eval.py` producing numbers, but no acceptance threshold test wired into CI).

---

## 7. Dependency surface

```
fastapi, uvicorn[standard], pydantic, pydantic-settings
langgraph, langgraph-checkpoint-sqlite, aiosqlite
httpx, websockets, PyYAML, python-docx
sqlite-vec, pypdf, lxml
python-multipart, PyMuPDF, xberg (optional)
```

Observations:
- No native Rust / native build dependencies beyond PyMuPDF; wheels cover
  manylinux_2_28 and bookworm per the Dockerfile.
- No LangChain, no OpenAI SDK, no Anthropic SDK — all providers hit via
  `httpx` directly (`app/services/llm.py`). This keeps the service
  resilient when a provider SDK changes shape.
- No feature-flag library — flags live on `app/config.py` as pydantic
  settings.
- No ORM — raw `sqlite3` + context managers. Deliberate; the service runs
  five SQLite files and migrations are JSON-shaped checkpoint changes.
- No observability SDK (no OTel, no Sentry). Logs are the sole channel.

---

## 8. Deployment posture

- `Dockerfile` builds a single-process image on Python 3.12.
- `.github/workflows/deploy.yml` runs `tests` → `deploy` to `pixoustech`
  EC2 on push to `main`. Deploy restricted to four actor usernames.
- `deploy/nginx/` holds the production nginx config.
- `deploy/scripts/`: `backup.sh`, `backup-offsite.sh`, `restore-test.sh`,
  `preflight.sh`, `rollback.sh`, `write-env.sh`.
- `deploy/env/app.env.example` — the template. Real file is written by
  `write-env.sh` from GitHub secrets.
- Observability: structured JSON logs via `app/logging_setup.py`
  (`JsonFormatter`), stdout only. No external log aggregator wired in
  this tree.

---

## 9. Working-tree snapshot vs HEAD

### Modified against main (35 files)

Phase 0.1 fallout (`officer_store.py`, `dictation.py`, `rest.py`,
`ws.py`), Phase 0.3 (`logging_setup.py`, `main.py`), Phase 0.4
(`rest.py`), Phase 1 (`graph/state.py`, `graph/workflow.py`,
`graph/nodes.py`, `api/views.py`, `static/app.js`), Phase 2
(`officer.py`, `officer.js`, `officer.css`), earlier correctness
(`analyst.py`, `legal_status.py`, `ingest.py`, `store.py`, `schema.py`,
`embeddings.py`, `ocr.py`), test rewrites to match.

### Untracked new files

```
app/api/middleware.py                 Phase 0.3 correlation id
app/api/ws_limits.py                  Phase 0.4 shared gate
app/domain/lifecycle.py               Phase 1 SRS label
app/domain/local_bodies.py            jurisdiction directory
app/domain/taxonomy.py                category taxonomy
app/knowledge/india_code.py           Phase 2 DSpace parser
app/knowledge/legal_status.py         amendment status
app/knowledge/quarantine.py           Phase 2 staging table
app/knowledge/source_registry.py      Phase 2 catalogue
app/knowledge/vector_integrity.py     repair + sidecar
app/services/semantic_category.py     retrieval-side classifier
scripts/{discover,ingest_india_code_tn,fetch_corpus,verify_backup,
         build_directory}.py
benchmarks/{run_grievance_eval,run_retrieval_eval,metrics,
            grievance_dev,grievance_heldout,grievance_heldout2,
            retrieval_cases}.py
tests/test_{citizen_scope,correlation_id,health_caching,dictation_gate,
           deploy_scripts_syntax,corpus_current_law,legal_status,
           local_bodies,ocr_pages,restart_isolation,transition_log,
           srs_lifecycle,source_registry,india_code,quarantine,
           ingest_india_code_tn,ws_limits,vector_integrity,taxonomy,
           five_language_acceptance,security_headers}.py
corpus/{legal_relationships,source_registry,tamil_nadu}.yaml
docs/{hardening-report,knowledge-base-evidence,operations,
      requirements-traceability,legal-intelligence-roadmap,
      codebase-analysis}.md
deploy/scripts/{backup-offsite,restore-test}.sh
```

---

## 10. What to do next (strictly suggestions, not scope)

Ranked by return on effort, each sized in days.

1. **Decide on a Phase 0 commit series** (0.5 day). The Phase 0 safety
   baseline is important and local-only. Pushing it is one small commit
   per `0.1-0.5` with the test file beside each change.
2. **India Code live retry** (0.5 day). The TN handle was 504 on
   2026-10-14. If upstream has recovered, one `discover --limit 25` run
   fills the quarantine with real rows, and we can decide whether to
   bring the curator UI back.
3. **Font map for ml/te/hi/dev** (2-3 days). Ship Noto Devanagari/
   Telugu/Malayalam, install wherever LibreOffice runs, share one
   per-language font map across the four render paths listed in the
   earlier plan file.
4. **Collapse `Language` typing to one place** (1 day). Remove six
   duplicate `Literal["en","ta"]` and the ternaries. Enables real ml/te/
   hi support through the state machine instead of only through
   `petition.yaml`.
5. **Classifier corpus growth** (ongoing, 1-2 days per batch). The
   held-out 0.73 is a corpus problem, not a model problem. Growing the
   labelled set in `benchmarks/grievance_dev.py` + `grievance_heldout.py`
   is the mechanism; project memory says NEVER tune on the eval set.
6. **Attachment malware scanning** (2-3 days). ClamAV container + a
   provider interface + a scan-status column on the attachment row.
7. **Per-language acceptance threshold tests** (1 day). Wire
   `run_retrieval_eval.py` output into a `test_cross_language_retrieval`
   that fails CI if any language falls below an approved number.
8. **Phase 2 India Code UI, if you want it back** (2-3 days from
   quarantine schema restore). The data layer is intact; only the UI +
   API endpoints need re-adding when a curator role is defined.

---

## 11. One-page summary

A FastAPI + LangGraph + SQLite stack, ~32 KLOC backend, ~27 KLOC tests,
2,491 tests all green. Single-process by design, deliberate egress gate
on citizen text, hybrid retrieval over 18 Tamil Nadu documents with 97%
vector coverage, hand-written grounded citation guard, SRS-aligned
lifecycle labelling, correlation-id audit, and a mature officer page
that now dedupes and ranks its citations.

Open blockers are mostly administrator-owned (nginx, backup cron, ClamAV
decision, product-owner thresholds). The next week of engineering could
reasonably close:
- The five-language render path (fonts + typed Language).
- A live India Code pass with the quarantine schema already in place.
- A pass to commit the Phase 0 safety baseline that is just sitting here.

Nothing in this tree has been pushed, deployed or rotated. Nothing has
been fabricated — every number in this document is traceable to a file
or a measurement log.
