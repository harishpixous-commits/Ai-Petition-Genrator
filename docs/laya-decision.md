# Laya as a System-1 decision layer: analysed, benchmarked, not integrated

Written for: the engineering and procurement reviewers of the Citizen Petition
Assistant.

## The decision

**Do not integrate Laya.** Keep the deterministic intent reader in
`backend/app/domain/answer_intent.py`.

Nothing is installed, vendored, downloaded or added to the image. The
evaluation harness built for this assessment is kept, because the question
will be asked again and the measuring stick should already exist.

This is not a judgement on Laya as a project. It is Apache 2.0, the
engineering is interesting, and the router idea is sound. It is a judgement
about whether it improves *this* system, and on our own numbers it does not.

## What was assessed

`https://github.com/NandhaKishorM/laya` — a non-autoregressive typed-decision
engine. Three checkpoints: `laya` (ModernBERT-large, 421M, English),
`laya-multilingual` (mmBERT-base, 322M, 100+ languages),
`laya-typed-decisions` (421M, fine-tuned). A `Router` picks between them by
script detection. Dependencies: `torch>=2.14`, `transformers>=5`,
`huggingface_hub>=1`. Licence: Apache 2.0 — compatible, and not the problem.

The proposed use was the highest-value one in the brief: classifying the
citizen's reply to "is that correct?" into CONFIRM / RETRY / CORRECT /
ADD_MORE / FINISHED / UNKNOWN.

## The measurement

`backend/benchmarks/intent_cases.py` is a 244-case evaluation set written for
this: Tamil, English and code-switched control phrases, plus roughly a third
decoys — names, house numbers, grievance sentences containing the words
"correct", "all" and "also", and the short acknowledgements a transcription
service invents out of silence. All synthetic; no citizen data.

`backend/benchmarks/run_intent_benchmark.py` scores any classifier on it.

**The incumbent, measured on this machine:**

| | |
|---|---|
| Accuracy | 1.000 (244/244) |
| English / Tamil / mixed | 1.000 / 1.000 / 1.000 |
| False CONFIRMs | 0 |
| Median latency | 0.16 ms |
| p95 latency | 0.44 ms |
| Memory | 0 MB (no model, no dependency) |

Fourteen genuine gaps were found *by building this set* and have been fixed —
"ஆமா", "இல்ல", "முடிஞ்சது", "quite right", "move ahead" and others were
previously misread. That is the assessment's main concrete benefit, and it
came from the dataset rather than from Laya.

**Laya, from its own README:**

> "The base checkpoints are near chance on typed-decisions zero-shot — 0.362
> and 0.352 against a 0.318 random baseline and a 0.461 majority-class
> baseline."

Below the majority-class baseline. Fine-tuning recovers to **0.766**. The
English checkpoint scores **0.306** on non-English MASSIVE intent against
0.783 in English; Khmer is reported at "0.000 at 95.2% confidence", which is
a confidently wrong answer and the exact failure mode a confirmation
classifier must not have.

## Why that settles it

A fine-tuned ceiling of 0.766 means roughly one reply in four is misread. The
replies in question are the citizen agreeing to what goes on a government
petition. A quarter of those going wrong is not a latency trade-off; it is a
different product.

The incumbent is not merely more accurate here — it is *categorically*
cheaper: 0.16 ms against 193–464 ms on CPU (Laya's own figure; our EC2 host
has no GPU), and 0 MB against a multi-gigabyte torch/transformers install in
an image that currently has neither.

There is also nothing to replace. The brief's premise is that simple
confirmations are being sent to Gemini. They are not, and never have been:
`answer_intent.read()` is a pure-Python table, the workflow's happy path
makes zero LLM calls by design (`petition-fixed-decisions`, rule 5), and the
tests enforce it. **Adding Laya would not remove a Gemini call. It would add
a model to a path that currently has none.**

## Where Laya might genuinely help, later

Not intent classification. The two candidates worth re-testing if the picture
changes:

- **Grievance category triage** (water / street light / road / pension / …)
  as a *candidate* fed to the existing government RAG for verification. This
  is a real gap — nothing classifies grievances today — and a wrong answer is
  caught downstream rather than printed.
- **Attachment relevance**, where `attachment_relevance.py` currently uses
  term overlap and a low-confidence answer already routes to the citizen.

Both are places where being wrong is cheap. Neither is worth a
multi-gigabyte dependency on its own; both would be worth revisiting if Laya
were already in the image for another reason.

## What would change this decision

1. A fine-tuned checkpoint on our own dataset scoring **≥ 0.99 with zero
   false CONFIRMs** on `benchmarks/intent_cases.py`, Tamil included.
2. CPU latency under ~50 ms on the deployment host.
3. A resident-memory figure the EC2 instance can actually carry alongside
   LibreOffice and the workflow.

The harness is in place to check all three. Run:

```
python -m benchmarks.run_intent_benchmark --classifier laya
```

It currently exits with installation instructions rather than installing
anything, which is deliberate.

## What is kept from this exercise

- The 244-case evaluation set, wired into the suite as
  `backend/tests/test_intent_benchmark.py` so accuracy and the false-confirm
  count cannot regress unnoticed.
- The benchmark harness, with a `laya` slot ready for an adapter.
- Fourteen classifier fixes that came out of building the set.

---

# Part two: Laya for grievance classification, measured

Written 9 October 2026, after the first assessment named this as the one place
Laya might genuinely help. It was asked for again, so it was measured rather
than argued about.

**The decision is unchanged: do not integrate Laya.** Nothing is installed,
vendored or added to the image. What follows is why, on numbers produced on
this machine rather than quoted from anybody's table.

## This is a different question from part one

Part one rejected Laya as an INTENT classifier — reading "yes, that's right"
at a confirmation prompt. This is grievance CATEGORY: water, road, street
light, sanitation, pension and six others. Part one explicitly set it aside as
worth re-testing, because a wrong category is caught downstream instead of
being printed.

## Laya was installed and run, not read about

The previous assessment recorded `torch>=2.14`, `transformers>=5` and
`huggingface_hub>=1`, taken from the README. **The README is wrong about its
own package.** `pyproject.toml` requires `torch>=2.0.0`,
`transformers>=4.48.0`, `huggingface_hub>=0.20.0`. Laya 0.4.1 installed
cleanly against the torch 2.13 this project already has.

So the dependency objection from part one is weaker than recorded, and the
measurement below is the real reason rather than a convenient one.

Checkpoints are all subfolders of one repository, `convaiinnovations/laya`,
not three repositories as the README's table implies. `Router` chose the
English checkpoint for Latin text and the multilingual one for Indic text, by
script detection, exactly as documented.

## The measurement

`backend/benchmarks/grievance_cases.py` — 64 cases written for this: eleven
categories across English, Tamil, Malayalam, Telugu and Hindi, plus romanised
Tamil, two-subject complaints that should return UNKNOWN, and decoys where a
category word is scenery rather than the subject. All invented; no citizen
text.

`backend/benchmarks/run_grievance_benchmark.py` scores any classifier on it.

| | incumbent | Laya (zero-shot) |
|---|---|---|
| Accuracy | **0.891** | 0.391 |
| English | 0.788 | 0.667 |
| Tamil | **1.000** | 0.000 |
| Malayalam | **1.000** | 0.000 |
| Telugu | **1.000** | 0.000 |
| Hindi | **1.000** | 0.429 |
| Wrong subject | 5 | 8 |
| Median latency | **0.19 ms** | 2,374 ms |
| p95 latency | **0.24 ms** | 5,732 ms |
| Dependency | none | torch + transformers + a 322M–421M checkpoint |

Laya answered `OTHER` for 31 of the 64 cases and scored zero on all 24
Tamil, Malayalam and Telugu ones. That is not an anomaly: it is consistent
with the repository's own published figure of 0.352 for multilingual
zero-shot typed decisions.

**A correction, recorded because the number was nearly published.** A first
run scored Laya at 0.172. That was my bug, not Laya's result: `predict`
returns `{"model", "answers", "usage", "routing"}` and the adapter read
`out["category"]` instead of `out["answers"]["category"]`, so every case came
back `None`. A classifier that answers one label for all 64 inputs has not
been measured, it has been misused. The adapter was fixed and the run
repeated; 0.172 appears nowhere except here.

Laya also warns on load that this checkpoint "ships invalid temperatures or
values outside [0.5, 5] ... Treat confidence from the affected entries as
uncalibrated". Confidence is what a gate would read, so that matters.

## What the measurement actually found

Not something about Laya. **The incumbent had no Malayalam, Telugu or Hindi at
all.** Of 105 category words, 41 were Tamil and none were in the other three
scripts; and `_hits` tested `TAMIL.search` to decide how to match, so even
added words would have been matched with a Latin word boundary, which drops
Indic combining marks.

Every grievance in three of the five languages this service offers returned
UNKNOWN, always, and nothing said so because nothing measured it. The reader
scored 0.609 before this was fixed and 0.891 after — the whole gain came from
Malayalam, Telugu and Hindi going from 0.000 to 1.000.

That is the second time a benchmark written to evaluate Laya has paid for
itself by finding a defect in the thing it was measuring against. It is the
main reason to keep writing them.

## What would change this decision

The bar from part one stands, restated for this task:

1. A fine-tuned checkpoint scoring **above 0.891** on
   `benchmarks/grievance_cases.py`, with Tamil, Malayalam, Telugu and Hindi
   each above 0.9 — because that is what the service now does without it.
2. CPU latency under ~50 ms on the deployment host. Measured here: 2,374 ms
   median, 42 s worst case.
3. Calibrated confidence, since an uncalibrated score cannot gate anything.

Run it:

```
python -m benchmarks.run_grievance_benchmark                  # the incumbent
python -m benchmarks.run_grievance_benchmark --classifier laya
```

## What is kept from part two

- The 64-case grievance set and its harness.
- Malayalam, Telugu and Hindi in the category tables, and a matcher that reads
  any Indic script rather than Tamil alone.
- `LayaProvider` stays a seam that raises on construction. The question will
  be asked a third time, and now there are two measuring sticks ready.
