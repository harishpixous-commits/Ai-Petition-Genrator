# Knowledge base and multilingual support: evidence report

Written for: Harish, reviewing uncommitted work.

**No commit, push, merge, rebase, reset or amend was performed.** Everything is
in the working tree.

---

## 0. Test results, exactly as run

```
$ cd backend && python -m pytest
2335 passed, 4 skipped in 355.23s

$ python -m ruff check app/ benchmarks/ scripts/fetch_corpus.py       scripts/build_directory.py scripts/verify_backup.py
All checks passed!
```

2,194 → **2,335 passing**. The 4 skips are the cross-language retrieval tests,
which need a live embedder; they are opt-in and pass when run:

```
$ PETITION_LIVE_EMBEDDINGS=1 python -m pytest tests/test_knowledge.py       -k finds_an_english_document
4 passed in 24.32s
```

New test files in this round:

| File | Tests | Data |
|---|---:|---|
| `test_five_language_acceptance.py` | 50 | synthetic, all five languages end to end |
| `test_local_bodies.py` | 25 | **real** — 13,673 government records |
| `test_corpus_current_law.py` | 8 | **real** — the indexed corpus |

**A defect in my own tests, found and fixed:** `test_corpus_current_law.py`
originally located the corpus through `get_settings().knowledge_path`. But
`conftest.py` points `DATA_DIR` at a fresh temp directory for every run —
correctly — so that path was always an empty temp file and all 8 tests skipped
every time while looking like coverage. They now read the real corpus path
directly, and they run.

---

## 1. The mandatory current-law check — answered

The brief named a 3 September 2026 amendment to the Tamil Nadu Urban Local
Bodies Rules, 2023 and said not to assume the 2023 Rules are current. **It
exists, it was retrieved, and its effect was read.**

**G.O. Ms. No. 164, Municipal Administration and Water Supply (MA.IV),
3 September 2026 — Notification No. SRO A-16(a)/2026**
`https://www.stationeryprinting.tn.gov.in/extraordinary/2026/374_Ex_III_1a_2026.pdf`
Gazette Extraordinary No. 374, Part III §1(a). Signed Gagandeep Singh Bedi,
Additional Chief Secretary. Verified: HTTP 200, `application/pdf`, 90,678
bytes, 1 page, text layer extracted and read in full.

Made under section 198 of the ULB Act 1998, it does two things:

**Rule 290(1) is substituted outright.** Previously a trade licence was
"valid for a period of three years... renewed for a further period of three
years". It now reads: *"A licence issued by the Commissioner under rule 289
shall be valid for a period of ten years from the date of issue and may be
renewed for successive period of ten years."*

**Rule 289(1) gains a proviso.** Shops and establishments registered under the
Tamil Nadu Shops and Establishments Act, 1947 are *exempted* from obtaining a
separate municipal trade licence for the same premises and the same trade.

So a citizen asking "do I need a trade licence, and how long does it last"
gets a materially different answer in 2026 than the 2023 Rules give. A corpus
holding only the 2023 Rules would have answered **wrongly, with a citation** —
which is worse than not answering, because the citation is what makes it
believable.

It also supersedes part of **G.O. Ms. No. 35 of 17 March 2025**, which had
changed the same sub-rule to "upto the 31st day of March of the third year".
Two amendments to one sub-rule, eighteen months apart.

### The wider chain

Enumerating the Gazette extraordinary lists for 2023–2026 found **a further
17 amending instruments** to the 2023 Rules, plus two amending Acts to the
1998 Act (Act 24 of 2024, Act 30 of 2025) and a commencement notification.
Eight of the most significant are in the manifest.

One useful by-product: the **Gazette copy of the 2023 Rules**
(`124_Ex_III_1a_2023.pdf`, 404 pages, 18.8 MB) has a real text layer, where
the departmental copy on `tnurbantree.tn.gov.in` is a 5-page image-only scan
of the covering order and does not contain the rule text at all. The manifest
now points at the Gazette.

---

## 2. The local-body directory — obtained

Previously reported as unobtainable. **It is obtainable**, from the Rural
Development and Panchayat Raj Department's own published datasets.

`scripts/build_directory.py` builds `var/local_bodies.sqlite`:

| Body type | Records | With Tamil name |
|---|---:|---:|
| Village panchayat | 12,525 | 12,525 |
| Town panchayat | 561 | 0 |
| Block panchayat (panchayat union) | 388 | 388 |
| Municipality | 152 | 0 |
| District | 37 | 37 |
| Municipal corporation | 10 | 0 |
| **Total** | **13,673** | **12,950** |

Sources (all `https://www.tnrd.tn.gov.in/`), each recorded per record:
`project/admin/village_lgd_pvcode.php?xls=1&lang=en|ta`,
`block_lgd_bcode.php`, `district_lgd_dcode.php`,
`databases/Town%20Panchayats.xls`, `databases/Municipality.xls`,
`databases/tn_corporation_details.xls`.

**The Tamil names are joined by LGD code, never by name.** The department
publishes each list twice with identical codes, so the join is exact. Joining
on a transliterated name would be guesswork, and a village with the wrong
Tamil name attached is worse than one with none.

**Three of the six files are HTML `<table>` documents served as
`application/msexcel`**, and three are genuine OLE2 workbooks. The parser
detects format from magic bytes; one that trusted the extension would read
nothing from half of them.

### It refuses to guess, and that is the point

Real ambiguity found in the data:

- **Ganapathipalayam** — four village panchayats across two districts, *three
  of them inside Tiruppur alone*. Naming the district does not resolve it.
- **Oddanchatram** — both a Panchayat Union and a Town Panchayat in Dindigul.
  Different offices, different officers.

`local_bodies.find()` returns these as `ambiguous` with the candidates
attached. It never picks one. There is **no fuzzy matching**: "Kulathur" and
"Kulithalai" are different places and an edit-distance match between them is a
citizen's wasted day.

### A data property worth knowing

The district list has **37 entries, not 38**: Chennai is absent, because these
are *rural* datasets and Chennai district is entirely urban — no village
panchayats, no blocks. Chennai appears only as a corporation. This is the
department being correct, not the file being short, and it is asserted in a
test so the next person does not go hunting for a parsing bug.

---

## 3. Corpus contents

The manifest `backend/corpus/tamil_nadu.yaml` names **25 documents**, every
URL fetched and confirmed reachable. **18 are indexed: 8,344 chunks.**

Indexed, with chunk counts:

| Document | Chunks | G.O. |
|---|---:|---|
| Tamil Nadu District Municipalities Act, 1920 | 2,510 | |
| Tamil Nadu Urban Local Bodies Rules, 2023 | 1,726 | |
| Ready Reckoner, Municipal Solid Waste Management | 1,046 | |
| Tamil Nadu Panchayats Act, 1994 | 948 | |
| TN Combined Development and Building Rules, 2019 | 826 | |
| Tamil Nadu Urban Local Bodies Act, 1998 | 509 | |
| Tamil Nadu Town and Country Planning Act, 1971 | 275 | |
| **தமிழ்நாடு ... சட்டம், 1998 (Tamil)** | 178 | |
| **திடக்கழிவு மேலாண்மை விதிகள், 2016 (Tamil)** | 157 | |
| Act No. 24 of 2024 (amends the 1998 Act) | 72 | |
| G.O.(Ms) No.106 — Septage Management | 40 | 106 |
| Act No. 30 of 2025 (ULB Amendment Act) | 16 | |
| Amendments to the ULB Rules 2023 | 14 | 480 |
| G.O.(Ms) No.208 — Oddanchatram reclassification | 11 | 208 |
| Amendment to the ULB Rules 2023 | 5 | 162 |
| **Amendment to the ULB Rules 2023** | **4** | **164** |
| Amendment to the ULB Rules 2023 | 4 | 433 |
| Amendment to the ULB Rules 2023 | 3 | 104 |

Two Tamil-language documents are now indexed, where there was one.

### A QUARTER OF THIS MATERIAL IS SCANNED

Measured across the 24 downloaded files: **18 have a text layer, 6 do not.**

Scans, which cannot be indexed without OCR: the District Office Manual, the
Street Vendors Policy, the property tax revision G.O. 73, the trade licence
circular, the sewer-entry ban G.O. 293, and the Tamil building-permission
time-limit circular.

That is not an edge case to note in passing — it is a quarter of the corpus,
and it is concentrated in exactly the *departmental circulars* that carry the
procedures and time limits a delay petition turns on. **OCR is a requirement
for this material, not an optional extra.** The path is wired into
`app/knowledge/ingest.py`; Tesseract is not installed on this machine, so it
is untested and those six remain unindexed.

One manifest entry is deliberately **not** ingested: the 404-page Gazette copy
of the 2023 Rules. The same Rules are already indexed from the departmental
copy (1,726 chunks), so ingesting both would duplicate the text. The Gazette
URL is kept in the manifest because it is the authoritative version and has a
better text layer, and it is the one to re-ingest from if the departmental
copy is ever withdrawn.

One entry was **removed** during verification: a dengue-prevention guideline
whose URL I completed from a truncated research output rather than taking
verbatim. It 404s. A guessed URL has no place in a manifest whose whole
purpose is traceability.

### Embedding coverage — and a failure I caused

**Originally:** 687 of 8,069 chunks had vectors (8.5%). The provider rotated
keys on HTTP 429 but had **no backoff**, so once the per-minute quota was
reached it abandoned every remaining chunk. Lexical search covered everything,
so nothing looked broken, and cross-language retrieval was quietly degraded
for 91% of the corpus.

**After the backoff fix** (`app/knowledge/embeddings.py`, 6 attempts,
exponential 2 s → 60 s, honours `Retry-After`) a reindex reached
**8,069 of 8,069 (100%)**.

**Then I broke it.** I launched the next ingest under a 50-minute `timeout`.
The job was larger than that, the process was killed mid-write, and because
chunks and their embeddings are written separately the kill left every chunk
present and 2,510 vectors missing — **8,069/8,069 fell to 5,559/8,069** and
nothing in the service said so. Lexical search still worked, so the corpus
looked healthy.

Two things came out of that, and the second matters more than the first:

1. The ingests were re-run without an artificial timeout and unbuffered.
2. **`fetch_corpus.py health` now reports vector coverage** and prints the
   repair command when it is short. This exact silent divergence had no
   detector before, and the only reason I found it was that I happened to
   query the shadow tables by hand.

Run `python scripts/ingest.py reindex` and confirm `health` reports 100%
before relying on cross-language retrieval.

---

## 4. Classification

A semantic fallback was added (`app/services/semantic_category.py`): when the
deterministic reader finds nothing — or finds only a *weak* word, one that
names where something happened rather than what it was — the grievance is
compared by meaning against per-category exemplars using the same multilingual
embedder the corpus uses.

**The deterministic reader still runs first and keeps what it is confident
about.** It is free, instant, offline and can tell a citizen which word it
read; a cosine distance cannot explain itself. If embeddings are unreachable
the semantic step returns nothing and the old answer stands unchanged.

### Threshold calibrated on dev, not chosen

| threshold | rescued | wrong subjects |
|---:|---:|---:|
| 0.60 | 7 | 14 |
| 0.65 | 7 | 7 |
| 0.70 | 7 | 1 |
| **0.72–0.78** | **7** | **0** |
| 0.80 | 6 | 0 |

0.75 is the middle of the plateau. At the original 0.62 the reader raised
accuracy *and* turned 3 wrong subjects into 11 — a trade refused, because an
UNKNOWN costs a clerk a question and a confident wrong subject costs an
officer their trust in the panel.

### Results

| Set | Lexical only | + semantic |
|---|---:|---:|
| Dev (90 cases) macro-F1 | 0.8640 | **0.9138** |
| Held-out v1 (85) macro-F1 | 0.7317 | 0.7903 |
| **Held-out v2 (98) macro-F1** | 0.7078 | **0.7401** |

**Held-out v2 is the number to quote: 0.7401.** It was written after the first
held-out set was spent, before the semantic reader was scored on anything.
Per language: en 0.661, ta 0.712, te 0.742, ml 0.806, hi 0.728.

**The ≥95% target is not met.** Cross-language semantic matching works well —
Tamil and Malayalam indirect cases matched *English* exemplars at 0.91 and
0.90 similarity — but the remaining errors are vocabulary gaps ("bulb",
"bins" are not in the taxonomy) and genuinely ambiguous `OTHER`/`UNKNOWN`
boundaries. Closing them by adding the failing words would be fitting the test
set.

**Methodological limitation, stated rather than hidden:** the same author
wrote the system and both held-out sets. That is weaker than a set written by
someone who has never seen the exemplars. The right next step is for an
officer who takes petitions at a counter to write one from real intake
patterns.

---

## 5. What is NOT integrated — stated plainly

**RAG does not reach petition generation.** The retrieved analysis goes to the
officer's panel only; `nodes.py` says so explicitly and does not pass it to
`build_letter_text`. The architectural reason is recorded in the code: the
document a citizen signs says what the citizen said, and a retrieval result —
however well cited — is not something they said.

The brief asks for grounded petition generation. That is a real conflict with
a deliberate design decision, and it is **not** something to resolve silently.
Resolving it means adding a separate, clearly-marked, citation-carrying
section to the petition template — a change to the locked "one form" decision
that needs your sign-off, not an implementation choice.

**Consolidation of amendments is not automatic and is not claimed.** The
service indexes the base rule and its amendments so an officer sees both. It
does not merge them into consolidated text; no retrieval system does that
reliably, and inventing consolidated wording would be the fabrication this
layer exists to prevent.

---

## 6. Still blocked

1. **Two scanned PDFs** (District Office Manual, Street Vendors Policy) need
   OCR. The path is wired; **Tesseract is not installed here, so OCR itself
   remains untested.**
2. **Ward-level boundaries** are not published by the department. The
   directory maps a *name* to a body; working out which body covers a street
   needs data that does not exist publicly.
3. **Officer account, S3 backup bucket and passphrase** — administrator
   actions, in `docs/operations.md`.
4. **Tamil versions of the ULB Rules and their amendments do not exist.** The
   research enumerated the Gazette and found none; only the Act has a Tamil
   text. This is a genuine absence in the source, not a gap in acquisition.
