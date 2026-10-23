# Tamil Nadu Legal Intelligence — scope, status and roadmap

Written for: Harish and whoever decides what to approve next. The operator
brief dated 14 October 2026 asked for a "complete Tamil Nadu Legal
Intelligence System" that crawls thirty-plus official portals, ingests
every current Act, Rule and Government Order, and feeds verified citations
to the officer page. This document says plainly what is in the tree today,
what is deliberately NOT built, and what the honest cost is for the rest.

---

## 1. The one line that frames everything else

The brief has a hard rule: **do not fabricate laws, citations, authorities
or deadlines**. Everything below works outward from that line. A plausible
URL that nobody fetched is not evidence. A GO number read off a page title
is not a Government Order until the page was actually opened. A crawler
that "indexes 33 portals" without someone having read the result produces
a database the service cannot cite from.

## 2. What landed in this session

### 2.1 Source registry — the catalogue of what the service may look at

`backend/corpus/source_registry.yaml` lists all 42 URLs from the brief
(the 33 the brief named plus nine siblings already linked from them) under
six priority tiers that follow §D of the brief:

| Tier | Name | Example |
|---|---|---|
| 1 | Gazette or signed PDF | `tn-gazette-publications`, `egazette-india` |
| 2 | Current Act/Rule repository | `indiacode-home`, `indiacode-tn`, `legislative-dept-acts-policies` |
| 3 | Issuing department / authority | `tn-godept-list`, `tn-acts-ordinances`, `tn-rules-index`, `tnrd` |
| 4 | Official court portal | `madras-hc`, `supreme-court`, `ecourts` |
| 5 | Grievance / routing portal | `india-services`  (there are more; most are not in the brief) |
| 6 | Discovery only — never cited | `wikipedia-tn-laws` |

Each row carries:

- `tier` (one of the six above)
- `kind` (hub / index / document / search / directory / discovery)
- `access` policy (`polite` HTTP, `manual` curator action, `discovery_only`)
- the departments it covers
- what the URL yields in practice (`gazette_pdfs`, `go_pdfs`, `act_pdfs`, etc.)
- curator notes on quirks (JS, pagination, encoded parameters)

### 2.2 Parser and classifier

`backend/app/knowledge/source_registry.py` reads the YAML and refuses to
load an inconsistent file. Two rules are enforced structurally and tested
in [tests/test_source_registry.py](../backend/tests/test_source_registry.py):

- Any `tier_6_discovery` row **must** declare `access: discovery_only`.
- Any `access: discovery_only` row **must** be in `tier_6_discovery`.

That coupling is the gate between discovery material and the citation
pipeline. A Wikipedia URL that drifts into any other tier is a load-time
error; a repository URL misclassified as discovery-only is also a load-time
error. Both would otherwise fail silently later.

The parser also exports `rank_findings(findings)` — a stable sort by source
tier that the officer view now uses so the Gazette citation reads above
the India Code one when both support the same point.

### 2.3 Reachability probe

`backend/scripts/discover.py` is a HEAD-check for the registry. It:

- introduces itself as `CitizenPetitionAssistant/1.0 (reachability probe)`;
- waits 3 seconds between hits to the same host;
- reads `/robots.txt` and skips disallowed URLs with the reason recorded;
- refuses `discovery_only` sources outright;
- writes a per-run report to `var/reports/discovery-<utc>.json`;
- supports `list`, `check --dry-run`, `check --source <id>`, `check --tier`.

**What it is not.** It is not a crawler. It does not follow links, does
not download PDFs, does not parse index pages. See §3.

### 2.4 Officer view ranking

`backend/app/api/officer.py::grounded` now orders each finding's sources
by tier priority before handing them to the officer page. The Phase 1 fix
removed the "withhold everything when a conflict is undetermined" early
return; this change makes the sources behind a kept finding show up in
"strongest evidence first" order.

### 2.5 The Phase 1 bug on the user's live screen

Before this session the officer page showed "Not identified in verified
sources" because the `grounded()` helper withheld everything behind any
undetermined conflict. The real analysis for a street-lighting grievance
carried the TN ULB Act 1998 §118, the District Municipalities Act 1920
§136 ("Provision for lighting public streets"), five chunks of the TN ULB
Rules 2023 and the responsible authority — all of them hidden by one
Act↔Rules timing conflict that was unrelated to the District
Municipalities finding. That fix is in [app/api/officer.py:96-150](../backend/app/api/officer.py#L96)
with the test re-pinned to SRS §8.5 ("expose, don't withhold").

---

## 3. What is deliberately NOT built

The brief asks for a crawler across 33+ portals that discovers new
documents, OCRs them, categorises them, flags conflicts, and updates on a
schedule. None of that is in the tree, and the honest reasons are below.

### 3.1 Per-portal crawling is per-portal engineering

Each portal has to be touched separately. The complexity, measured by
opening each one in a browser:

| Portal | Documents | Complexity |
|---|---|---|
| `stationeryprinting.tn.gov.in` Gazette search | PDFs; one PDF per issue; search form with date/part/dept | Form POST required; results paginated; PDFs behind a session-ish link |
| `tn.gov.in/godept_list.php` | PDFs; one per G.O. | Department select → year page → list of G.O.s; each department page is its own list; year parameter changes shape |
| `tn.gov.in/act_ordinances.php` | PDFs; one per Act | A–Z and department-wise listings; same structure across departments |
| `indiacode.nic.in` | PDFs (consolidated); XML metadata | Mature structure, stable URLs; **ingestable with ~1-2 days of focused work** |
| `egazette.gov.in` | PDFs | Session-driven, CAPTCHA on some paths |
| `mhc.tn.gov.in/judis/` | HTML + PDFs | Search by date/party/case; JS-rendered results |
| `hcservices.ecourts.gov.in` | JSON + PDFs | Supports e-filing API where authorised; otherwise CAPTCHA |
| `tnlasdigital.tn.gov.in` | OCR'd PDFs | Legacy records from 1921; search by Act/Bill number |
| … | | |

A credible single-portal ingester is 2-5 days of work from a developer
reading the actual site. Thirty-plus of those is a multi-month project.
Doing a bad one is worse than nothing: it would populate the corpus with
documents nobody has read, and the citizen screen would start citing them.

### 3.2 Robots, terms of service, rate

The brief says the assistant must respect site terms and robots directives.
A production crawler would need per-site review of:

- `robots.txt`
- the department's own terms of use (several TN portals explicitly forbid
  automated extraction without written approval)
- `sitemap.xml` / `sitemap_index.xml` where present
- a courtesy email to the operator naming the service

The probe at `scripts/discover.py` already respects `robots.txt`. Anything
beyond HEAD checks needs the per-portal review above.

### 3.3 Scheduled updates

Scheduling the probe is one line of cron. Scheduling a crawler is only
useful once the crawler exists. The Phase 0.5 "install the backup cron"
decision applies here identically — the production host is the
administrator's territory, this session does not change it.

### 3.4 "Flag outdated or conflicting information"

Already implemented:

- `backend/app/knowledge/legal_status.py` reads `corpus/
  legal_relationships.yaml` and marks every passage CURRENT /
  HISTORICAL / INCOMPLETE / UNKNOWN based on Gazette-evidenced
  amendment relationships;
- `backend/app/knowledge/conflicts.py` detects two instruments covering
  the same topic without a settled supersession and surfaces the pair to
  the officer;
- today's `officer.py` fix makes conflicting findings coexist on the
  page with a warning instead of hiding behind a single abstention flag.

Not yet implemented: automatic amendment detection from the Gazette feed.
That reads a new Extraordinary Gazette, finds the amendment language,
and writes a `substitutes` / `amends` / `inserts` row to
`legal_relationships.yaml`. It is a focused LLM-plus-regex task that needs
curator approval on every row produced. Scope: ~1-2 weeks.

### 3.5 Tamil + English with OCR

Already in the tree, Phase 1 vintage:

- `app/services/ocr.py` + `app/services/document_intelligence.py` run per-page
  OCR on scanned PDFs through Tesseract when installed;
- `app/knowledge/ingest.py` keeps every page (even empty ones) so OCR
  can fill them without losing page provenance;
- `app/domain/languages.py` carries all five SRS languages with scripts
  and locales.

Not yet implemented: a translation layer for Tamil Act titles to English
officer-side rendering. Officers who read English see Tamil titles today
as transliterated text; a bilingual title column is a focused Phase-6 task.

---

## 4. The honest cost

| Deliverable | Session (today) | Phase 2 commit | Full ask |
|---|---|---|---|
| Source registry (42 URLs, 6 tiers, parser, tests) | **done** | — | — |
| Reachability probe (HEAD, robots, polite, dry-run) | **done** | — | — |
| Officer-side tier ranking of sources | **done** | — | — |
| Officer-side "expose, don't withhold" fix | **done** | — | — |
| One per-portal ingester (e.g. India Code) | — | 2-3 days | — |
| 33+ per-portal ingesters | — | — | 4-6 months |
| Automatic amendment detection from Gazette | — | 1-2 weeks | — |
| Scheduled crawler on production host | — | administrator action | administrator action |
| Curator-review UI for quarantine queue | — | 3-5 days | — |
| Tamil↔English bilingual titles | — | 2-3 days | — |

Phase 2 commit = the next natural slice, probably India Code (TN handle)
+ a quarantine review UI + bilingual titles. Each is single-digit days of
focused work with concrete tests. Nothing in this session fakes any of them.

---

## 5. What the operator should do next

1. **Review the registry.** Open `backend/corpus/source_registry.yaml`,
   confirm the departments and the discovery-only line match current policy.
2. **Decide the Phase 2 slice.** The highest-value next step is probably
   India Code TN handle — stable URLs, machine-readable metadata, and the
   data (Act and Rule PDFs with amendments) is what the officer page
   actually asks for. ~2 days.
3. **Approve the probe schedule.** `scripts/discover.py check` is cheap
   enough to run nightly from `/opt/ai-petition/`. The administrator
   decides whether to schedule it. The cron line is one entry; the result
   file lands under `var/reports/`.
4. **Keep the Phase 0 blockers moving.** The nginx rate limits and the
   backup cron (Phase 0 §5 of the traceability matrix) have the same
   administrator-action shape; this scope added work, it did not finish
   those.
