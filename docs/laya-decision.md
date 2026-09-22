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
