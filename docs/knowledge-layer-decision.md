# The government knowledge layer: what was built, and why this shape

Written for: the engineering and procurement reviewers of the Citizen Petition
Assistant.

## The reference repository

`https://github.com/rajveersinghcse/Agentic_RAG` — studied, nothing copied.

**It carries no licence.** The GitHub API reports `"license": null` and the
repository contains four files (`.gitignore`, `README.md`, `app.py`,
`requirements.txt`, 12 KB in total) with no `LICENSE`. Code published without a
licence is not public domain: default copyright applies and all rights are
reserved. So none of its source may be copied into a government service, and
none has been.

Reading a design and writing an independent implementation is not copying, and
the useful part of that repository is a design rather than an implementation.
Three ideas were worth having:

1. **Hierarchical retrieval with an explicit refusal.** Its agent tries the
   uploaded PDFs, then the crawled websites, and if neither answers it *says
   the question is outside the knowledge base* rather than answering anyway.
   That is the single most important behaviour for this application, where the
   failure mode is a petition citing an Act that does not exist.
2. **Fallback search as a distinct, lower tier** rather than a peer of the
   indexed corpus.
3. **Ingestion of PDFs and crawled pages into one store**, so a department's
   circulars and its website answer the same query.

Its stack — Qdrant, OpenAI, LiteLLM, Streamlit, DuckDuckGo — is not adopted.
Streamlit is a second UI this application does not need, and Qdrant is a server
to deploy, back up and secure for a corpus that is a few hundred documents.

## What was built instead

`backend/app/knowledge/`, inside the existing service. No new process, no new
port, no new database server.

```
document / URL
   ↓  extract      pypdf, python-docx, lxml, plain text
   ↓  clean        de-hyphenate, collapse rules, drop page furniture
   ↓  chunk        ~1200 chars on section and paragraph boundaries
   ↓  metadata     act, rule, GO number, department, section, page, URL, date
   ↓  embed        provider abstraction (Gemini today, local fallback always)
   ↓  store        SQLite: FTS5 for lexical, sqlite-vec for vectors
```

### The store is SQLite, because the service already is

The session checkpointer is SQLite. `sqlite-vec` adds vector search to it as a
loadable extension — one file, no server, and the corpus lives next to the
sessions it serves. FTS5 ships with SQLite itself and gives the lexical half of
hybrid retrieval for free.

This is the "do not introduce additional infrastructure unnecessarily" answer.
If the corpus ever outgrows it, `KnowledgeStore` is one class behind one
interface and Qdrant slots in there.

### The search index stores its own text

FTS5 can be told `content=''` to avoid duplicating the text it indexes. That was
the first version, and it was wrong: a contentless FTS5 table cannot be deleted
from with `DELETE`. Removing a row means replaying its original column values
through a special `'delete'` command, and if those values have drifted by so
much as a space the index corrupts silently. Document deletion and re-indexing
have to be reliable, so the table keeps its own copy of the text. For a corpus
of a few hundred documents that trade is not close.

### Retrieval is hybrid, and works with no network

Lexical (FTS5/BM25) and vector results are fused by reciprocal rank. That is
not only for quality: **the lexical half needs no embedding provider**, so the
knowledge layer degrades rather than disappears when nothing is reachable —
which is the same posture as the rest of this service, whose whole test suite
runs with no model, no dictation and no PDF converter.

An official source outranks an unofficial one at equal relevance, and a
document marked superseded is excluded unless nothing else answers.

**Nearest is not the same as near.** A vector index asked for eight results
returns eight, however unrelated the corpus is to the question — a pension
grievance searched against two land documents comes back holding both of them.
That was caught by a test that asserted the *absence* of a result, and the fix
is a floor: a passage the word index did not match at all has to clear a
similarity threshold before it counts, and when the embedder is the local
hashed one it cannot clear it at all, because its "similarity" is word overlap
that FTS5 has already measured better. Nothing downstream would have fabricated
a citation from those passages, but they would have consumed the one model call
and put the wrong Act next to the right grievance.

## The rule that shapes everything

**Nothing is reported that is not in a retrieved document.**

The analysis is not "ask a model about Tamil Nadu law". Every Act, Rule,
Government Order number, authority and procedural step returned is checked back
against the text of the chunks that were retrieved, and anything that does not
appear there is dropped before the result leaves the module. A finding with no
surviving citation is not returned at all.

When retrieval finds nothing that clears the threshold, the answer is the
sentence the brief asks for, and nothing else:

> Relevant official information could not be verified from the available
> knowledge base.

This mirrors `_numbers_are_grounded` in `compose`, which drops any drafted
sentence containing a figure the citizen never gave. The discipline is the
same: a plausible invention on a government form is worse than an absence.

## Citizen data never enters the corpus

The knowledge base holds government reference documents. It is written to by
ingestion and by nothing else — there is no code path from a session to a
write.

The grievance is used as a *query*. Before it reaches an external embedding
provider it goes through the same `mask_pii` boundary every other outbound text
goes through, so an Aadhaar or mobile number typed inside a complaint is
redacted there as it is everywhere else. Queries are not persisted.

## When it runs

Once, when the grievance first arrives — not on every message. It is advisory,
it runs through the existing `extensions.registry` (which already bounds it to
five seconds, swallows its failures, and marks its output `verified: false`),
and the petition is produced whether it succeeds, fails or times out.

## Two levels of grounding, and why prose gets the weaker one

An Act, a Rule, a G.O. number, a department and an authority must appear
**verbatim** in a cited passage. Those are names; a name is either in the
document or it was invented.

The steps of a procedure and the documents to attach are checked differently,
because a correct summary is not a substring of anything and demanding one
would leave the panel permanently empty — which teaches an officer to ignore
it. They are checked by content-word overlap instead, with two hard conditions
on top that no overlap score can override:

* **every proper noun must be present.** "Appeal to the Tribunal within thirty
  days" scored 0.67 against a passage naming the Revenue Divisional Officer:
  the filler words carried an invented body past the threshold.
* **every quantity must be present**, spelled out or in digits. "ninety days"
  is not a digit, so a digit-only rule never saw a changed deadline — and a
  wrong deadline on a government form costs a citizen their appeal.

Over-rejection is the deliberate direction. The cost of dropping a true line is
a shorter advisory panel; the cost of keeping a false one is a citizen sent to
an office with no such jurisdiction.

## Conflicting and superseded documents

A departmental folder is not a consistent snapshot. It holds the 1998 Rules and
the 2019 amendment, a G.O. and its revision, a circular and the notice
withdrawing it. Retrieval returns passages from two of them at once, and the
failure mode is not a wrong answer — it is a *tidy* answer assembled across the
seam, where an officer reading "the fee is fifty rupees" has no way to see that
the sentence came from something that stopped being operative years ago.

So `conflicts.py` runs before the analyst reads anything, and there are exactly
two permitted outcomes:

**preferred_newer** — one document is demonstrably current: it is marked
superseded, or it is plainly older by date. The other is set aside as evidence
and *recorded*, so the version history survives and an officer can still see
what the rule used to be.

**undetermined** — nothing establishes which is in force. Both are kept, neither
is treated as settled, and a warning is attached that says so in as many words
and is printed above the findings, not below them.

There is no third outcome. Silently merging them is the thing this exists to
prevent.

Two bugs were found building it, both of which made it quietly inert:

* Documents were grouped by instrument name, and "Sample Licensing Rules, 1998"
  and "..., 2019" are different strings — so the single most common shape of a
  real conflict was never compared at all. A trailing year is now stripped from
  the grouping key and used as the discriminator instead.
* The no-model fallback path read the *unfiltered* retrieval, so on any machine
  without a reachable model — which is every test run and every offline
  deployment — the superseded document was cited anyway.

## Official is earned, not asserted

`authority` decides ranking, and it is the only thing that can turn a suggested
attachment into one a citizen is told is mandatory. So it cannot be a flag
somebody types.

A document keeps `official` or `departmental` only if its origin is on the
record: a `--provenance` note (a gazette citation, or the officer who verified
the copy), a `source_url`, or a G.O. number — which is itself a citation a
reader can look up. Without one it is indexed as `unknown`: still searchable,
still cited, but it no longer outranks anything and can never make a document
required. The downgrade is logged at warning.

This is the enforceable half of "if source authenticity cannot be established,
do not treat the document as an official legal source". The other half is not
enforceable in software: retrieval and the grounding check both work faithfully
against whatever is in the corpus, and **neither can tell a real gazette from a
convincing imitation.** That judgement belongs to whoever runs ingestion.

## Citizen attachments are a different store, on purpose

`var/attachments/<session-id>/` holds what a citizen encloses with one petition.
It is never embedded, never searchable, and never read by retrieval. An Aadhaar
card, a photograph of a street, a previous petition naming a person and their
complaint — putting any of those into a shared vector index means the next
citizen's grievance can retrieve them.

There is no code path from a session to a corpus write. A test asserts that
`KnowledgeStore` is not importable from outside `app/knowledge`, and another
walks a whole petition with an attachment and asserts the corpus is the size it
started.

## What this costs, honestly

**The corpus ships empty, and that is not a gap left for later.**

While building this, two Tamil Nadu documents were written into a development
corpus to exercise the pipeline end to end. They were reconstructed from
memory, not copied from the gazette — and it showed: the text had a "Section 2"
whose body referred to liability arising "under section 3". Retrieval cited it
correctly and the grounding check passed it, because both do their job against
whatever is indexed. Neither can tell an authentic Act from a convincing
imitation of one. **That is the job of whoever runs ingestion, and it cannot be
delegated to this system.** The development corpus has been deleted.

So: a knowledge layer is only as good as what is in it, and seeding it with
reconstructed Acts to make a demonstration look complete would be the exact
failure this design exists to prevent. `scripts/ingest.py` takes files,
directories and URLs. Until a department's real documents are loaded, the panel
is absent — not empty, not spinning, absent — and every petition is produced
exactly as it is today.

`--official` and `--departmental` are flags a person passes. Nothing infers
authority from a filename or a domain, because the difference between a gazette
and somebody's summary of one is a judgement, and it is the judgement the whole
ranking rests on.

The local embedding fallback is a hashed bag-of-words, not a trained model. It
is enough for lexical-adjacent recall and is not pretending to be semantic; when
`GEMINI_API_KEYS` is set, `gemini-embedding-001` does the real work.

## Verified

`gemini-embedding-001` indexing two real documents, then three grievances put
through the full analyst against them:

| Grievance | Result |
|---|---|
| Unauthorised occupation of poromboke land | The Land Encroachment Act 1905, the Collector, and the thirty-day appeal to the Revenue Divisional Officer — each cited to the section it was read from |
| No drinking water for three weeks | The TWAD Board, the Assistant Engineer, and the fifteen-day escalation to the Executive Engineer |
| Pension not credited for March | *Relevant official information could not be verified from the available knowledge base.* |

The third is the one that matters. Nothing in the corpus was about pensions, and
nothing was said.

A model that was fed the right excerpts and asked to report on them returned a
fabricated Act, a fabricated G.O. number and a fabricated authority alongside
the real Act in a test; all three were removed by the grounding check and the
real one survived.
