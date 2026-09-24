# System-1 decision engine — review

**Status: relationship classifier wired in and enabled. Grievance category is a
hint only and does not route. Nothing pushed, nothing deployed.**

The figures below are what was measured, including the ones that are
unflattering, and the two kinds of figure are kept apart throughout.

---

## Reading the numbers

Two columns appear everywhere in this document and they are not the same thing.

**Untouched.** What a case set scored the FIRST time it was run, before it had
caused any change. This is evidence.

**Post-fix.** What the same set scores now, after the defects it exposed were
fixed. This is a regression check. It is not evidence, because the code was
adjusted until the set agreed with it.

A set that has changed the code can confirm a fix. It can never measure one.
Each set's own docstring records which tier it is in.

| Set | Cases | **Untouched** | Post-fix | What it caught |
|---|---|---|---|---|
| `system_one_cases` (tuning) | 61 | 0.918 | 1.000 | "street" read as a road complaint |
| `system_one_holdout` | 36 | **0.917** | 0.972 | the near-tie rule was over-triggering |
| `system_one_holdout2` | 38 | **0.868** | 1.000 | no romanised Tamil at all |
| `system_one_holdout3` | 43 | **0.860** | 1.000 | the `corporation` bug |
| `system_one_final_tamil` | 40 | **0.775** | 0.975 | STT spellings, spoken Tamil |

**0.775 is the last unbiased measurement** — overall, on the final Tamil set.
By script, on that same untouched run:

| Script | **Untouched** |
|---|---|
| Romanised / Tanglish | **0.722** (13/18) |
| Tamil script | **0.818** (18/22) |

Broken out by task:

| Task | **Untouched** | Across all five sets |
|---|---|---|
| Grievance category | **0.735** (final Tamil), 0.778 (holdout3) | 150/152 |
| **Attachment relationship** | **1.000** (6/6 final, 34/34 all held-out) | **49/49** |
| Attachment relevance | 1.000 (small sample) | 7/7 |
| Officer review | 1.000 (small sample) | 10/10 |

Post-fix across everything: **216/218**. That number is a regression check and
is not the benchmark.

One correction worth recording: the final Tamil set first read 0.825, and two
of its labels were wrong — "current romba neram illa" and "கரண்ட் போயிடுச்சு"
had been labelled UNKNOWN, which was a prediction about what the code would do
rather than what the answer is. A human officer says ELECTRICITY to both.
Corrected to ground truth before scoring, the untouched figure is 0.775. The
lower number is the true one.

Run them with:

```
python -m benchmarks.run_system_one_benchmark --set all
```

---

## What is enabled, and what is not

**The attachment relationship classifier is wired into the existing upload
path and enabled.** It measured 1.000 on every held-out set, and it is the
task this work was started for.

**The grievance category is a hint and routes nothing.** It measured 0.735 on
the set that never informed it. It is carried as `suggested_category` and
shown as a suggestion; department, authority, Act and Rule continue to come
from verified RAG and officer review. A test asserts that nothing outside
`system_one.py` reads the field, so it cannot quietly acquire an effect.

Routing policy, unchanged from the brief:

| Level | Used for |
|---|---|
| 0 · deterministic | confirm/retry intent — `answer_intent.py` measures 1.000 and keeps the job |
| 1 · System-1 | attachment relationship, relevance, review triage |
| 2 · LLM / RAG | legal reasoning, department, authority, Act, Rule |

---

## Where it is wired

The existing pipeline, with one step added. No second pipeline was created and
no storage was duplicated.

```
upload → read/OCR → extract (prior_petition) → RELATIONSHIP → relevance
       → stored on the attachment → officer portal
```

`describe_attachment()` in `app/services/system_one.py` produces one advisory
record, stored on `Attachment.relationship` beside the existing `relevance`
field:

```json
{
  "value": "THIRD_PARTY_SUPPORTING_DOCUMENT",
  "confidence": 0.85,
  "reason": "a petition naming a different person",
  "source": "system-1/deterministic",
  "requires_review": true,
  "first_person_allowed": false,
  "suggested_category": "WATER"
}
```

The name compared is always the one the **citizen** gave, never the one read
off the page.

### The one thing it is allowed to do

It has a single power and it is a power to withhold.

`_prior_reference()` in `app/graph/nodes.py` composes the sentence *"I had
previously submitted a petition regarding the same issue under acknowledgement
number N."* It required three conditions, all of them the citizen's own
decision: a document was attached, something was read from it, and the citizen
confirmed what was read.

All three were satisfied in the reported failure. Harish attached Sethubala's
petition, extraction read it **correctly**, and Harish confirmed that the
extraction was right — because it was. The document was genuine and the
acknowledgement number was genuine. The sentence built from them was not:
Harish had never submitted petition 4412.

Confirming that a document *says* something is not the same as claiming it is
*about you*, and nothing in those three conditions can tell the difference. So
a fourth was added, and it is the only one the citizen cannot see: the
document must not be, on the face of it, somebody else's.

A third party's document is still enclosed, still listed on the petition, and
still evidence. It simply does not get to speak in the citizen's first person.

The officer portal's "Previous submissions" fact is gated the same way. A
reference number belonging to somebody else now appears under its own heading
— *"Referenced in an enclosed document (not the petitioner's)"* — rather than
being listed as this citizen's history.

### Deny-list, not allow-list

The withholding rule fires on **evidence that a document belongs to somebody
else**, not on absence of evidence that it belongs to the citizen.

Written the other way round — only `OWN_PREVIOUS_PETITION` may speak — every
citizen whose acknowledgement slip carries no legible petitioner name would
silently lose the reference sentence they are entitled to, and most scanned
slips carry no legible name. `UNKNOWN` therefore keeps the behaviour the
service has always had, and is flagged for an officer instead.

---

## Provenance

The priority order is unchanged and this layer sits underneath all of it:

1. the citizen's confirmed data
2. the citizen's corrections
3. confirmed attachment evidence
4. verified government RAG
5. never a guess

Attachment-sourced values already carried their own provenance before this
work — `prior_petition.Extracted` holds `value`, `evidence`, `confidence`,
`page` and `unit` — and they are never flattened into the citizen's field
dictionary. The composer is structurally separated: `build_letter_text()`
receives the citizen's `fields`, the enclosure list, and a prior-reference
*sentence*. It never receives the extracted attachment dictionary, so an
attachment value has no path into the petitioner block.

The name is additionally marked non-adoptable in `attachment_conflicts.py`:
the disagreement is still shown to the citizen, but the swap is not offered.
That guard exists because OCR over a scanned Tamil letter produced "சேபாலா" —
a syllable short of the name actually on the page — and offered it as a
one-click replacement for a name the citizen had typed correctly.

---

## The defects worth naming

**`"ration"` is a substring of `"corporation"`.** Matching Latin text by
substring classified *"the corporation has not lifted the rubbish"* as a
welfare-scheme complaint. Half the petitions in this state name a corporation.
Latin is now matched on a word boundary; Tamil is not, because a regex
boundary cannot see the script.

**`குடிநீர்` does not occur inside `குடிநீரும்`.** A Tamil suffix *replaces*
the virama rather than following it, so the word for drinking water went
unmatched in a sentence about drinking water. Needles ending in a pure
consonant are now also tried with the mark dropped.

**Almost every Tamil grievance contains the word for street**, because that is
where people live. Locational words are now weighted below subject words.

**A petition carrying its own acknowledgement number was filed as a receipt.**
Receipts are checked before petitions, and the bare word "acknowledgement" was
enough. A real previous petition almost always quotes its own receipt number,
so this would have mislabelled the common case. What separates them is who is
speaking: a petition addresses an officer and asks for something.

**Romanised Tamil is normalised, not listed.** There is no correct
romanisation of Tamil, so a word list can only chase spellings. The variation
is systematic — doubled consonants, long vowels, compound splitting, digraphs
— and is folded away instead. The known limit: an English loanword spelled
phonetically ("pension" heard as "penshan") is not a systematic variation of
anything, and the final holdout records it as a gap.

---

## Failure behaviour

If the classifier times out, raises, is unavailable, or returns UNKNOWN or low
confidence:

- the attachment is still stored, still enclosed and still listed
- no citizen field is touched
- the record reads `UNKNOWN` and is flagged `requires_review`
- the reference sentence keeps its pre-existing behaviour
- **petition generation never fails because classification failed**

Two guards, and they catch different things. The engine catches a provider
that misbehaves and answers UNKNOWN. `describe_attachment` catches everything
else, including a failure to construct the engine at all — which was found by
a test, because the engine was originally built outside the guard.

---

## Laya

**Not recommended, and the seam is kept anyway.**

On Laya's own published numbers the fine-tuned ceiling is 0.766 and the
English checkpoint scores 0.306 on non-English intent. The incumbent intent
reader in `domain/answer_intent.py` measures 1.000 on its 244-case set at
0.16 ms with no dependency. The host has no GPU and the image has neither
torch nor transformers.

`LayaProvider` raises on construction with a pointer to this document rather
than quietly behaving like the deterministic provider. The harness scores a
*provider*, so a future checkpoint can be measured on the same cases before
anything is enabled.

Laya is not used for petition generation, STT, TTS or OCR, and cannot modify
citizen data.

---

## Known limitations

- **Two-subject complaints are found only when coordinated.** *"The drain is
  blocked and the road above it has collapsed"* still resolves to one
  category; plain "and" is too common to treat as a marker.
- **Romanised folding does not cover phonetic English loanwords.** "penshan"
  is the recorded example.
- **The category vocabulary is hand-built** and will miss words. Every miss
  returns UNKNOWN rather than a wrong answer — on the final Tamil set, every
  single failure was UNKNOWN, never a misclassification.
- **All five case sets are now spent.** The next honest figure needs a set
  nobody has seen.

## The flaky dictation test

Investigated rather than silenced, and **no production code was changed.**

`test_manual_dictation.py` failed roughly once in four full-suite runs with
`CancelledError`, and never once in fourteen runs of that file alone. Three
hypotheses were tested and two were wrong:

1. *The handler swallows its own cancellation.* Deterministically true —
   `except (WebSocketDisconnect, asyncio.CancelledError): pass` absorbs a
   cancel — but **not the cause**, because the exception arrives from the
   awaits in `finally`, after the `except` clauses have run.
2. *The handler has not finished cleaning up.* Wrong. Sleeping 20 ms before
   teardown changed nothing (7 failures vs 10 across 300 runs each).
3. *It is the harness.* Confirmed.

Starlette's `WebSocketTestSession.__exit__` runs its callbacks LIFO:

```
close(1000)             queue a disconnect for the app
portal.call(cs.cancel)  cancel the app's cancel scope
fut.result()            re-raise whatever the task ended as
```

The first two are back to back with no guaranteed window between them, so a
handler still parked in `receive()` is simply cancelled, the task future ends
CANCELLED, and `fut.result()` raises into the test thread.

The decisive measurement: **a twenty-line websocket endpoint containing no
project code, parked the same way, fails at the same rate (12/300); the same
endpoint that has already returned fails 0/300.** Against the real dictation
handler, a clean protocol close is 300/300.

So the two tests now send `dictation.stop` and wait for the acknowledgement —
which is what the browser does, making them more faithful, not quieter. The
other socket tests in that file already closed this way and never flaked.

**Confirmed: six consecutive full-suite runs after the change, zero failures**,
against one failure in four before it.

## Tests

- `tests/test_system_one.py` — 39 tests, each a regression from a measured failure
- `tests/test_attachment_relationship_flow.py` — 34 integration tests, cases A–G,
  provenance separation, and the officer portal
- Mutation-tested twice: all nine System-1 fixes and all eight wiring
  behaviours were reverted one at a time, and every one killed a test (17/17)
