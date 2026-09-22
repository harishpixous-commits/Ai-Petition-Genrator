"""Score a voice-intent classifier against the petition assistant's own set.

    python -m benchmarks.run_intent_benchmark                # the one in service
    python -m benchmarks.run_intent_benchmark --classifier laya

WHY A HARNESS AND NOT A SCRIPT PER CANDIDATE. The question "should we replace
the intent classifier" is only answerable if the incumbent and the candidate
are measured on the same cases, in the same units, on this machine. Anything
else compares our real workload against somebody else's benchmark table.

WHAT IT REPORTS
    accuracy overall, and separately for English, Tamil and mixed input
    a confusion matrix, because WHICH mistakes matter more than how many
    the false-confirm rate, which is the number that can commit a wrong
        value to a government form
    median and p95 latency per decision, measured here
    resident memory before and after loading the classifier

THE ADAPTER. The application reads three intents (`confirm` / `retry` /
`replace`) plus two predicates (`finished`, `wants_more`). The brief's
vocabulary is wider. `builtin()` maps one onto the other so a candidate that
speaks the wider vocabulary can be scored directly — it is the interface a
`LayaDecisionService` would have to satisfy, written here rather than in the
application because nothing in the application needs it yet.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from collections import Counter
from collections.abc import Callable

from benchmarks.intent_cases import (
    CONFIRMING,
    DICTATING,
    LONG_CONFIRMING,
    Case,
    dataset,
)

Classifier = Callable[[str, str, str], str]


# --------------------------------------------------------------------------- #
# The classifier in service
# --------------------------------------------------------------------------- #

def builtin(text: str, language: str, context: str) -> str:
    """The deterministic reader the application uses today.

    Context-aware by construction: `finished` and `wants_more` are only asked
    while a long answer is being collected, and the three-way reading is only
    asked at a confirmation prompt. That is the same rule the socket applies,
    reproduced here rather than approximated.
    """
    from app.domain.answer_intent import finished, read, wants_more

    tongue = "ta" if language == "ta" else "en"

    if context == DICTATING:
        # Mid-narration the ONLY control word is an ending. "also" inside a
        # sentence is part of the complaint, and the socket does not ask
        # about it here — consulting `wants_more` at this point was the
        # harness being stricter than the thing it was measuring, and it
        # scored a correct classifier as wrong.
        return "FINISHED" if finished(text, tongue) else "UNKNOWN"

    if context == LONG_CONFIRMING:
        if finished(text, tongue):
            return "FINISHED"
        if wants_more(text, tongue):
            return "ADD_MORE"
        reading = read(text, tongue)
        if reading.intent == "confirm":
            return "CONFIRM"
        return "CORRECT" if reading.intent == "replace" else "RETRY"

    if context == CONFIRMING:
        reading = read(text, tongue)
        if reading.intent == "confirm":
            return "CONFIRM"
        if reading.intent == "replace":
            return "CORRECT"
        return "RETRY"

    return "UNKNOWN"


def laya(text: str, language: str, context: str) -> str:  # pragma: no cover
    """A candidate, loaded once and reused.

    Not installed by this file. `torch`, `transformers` and a 322M-421M
    parameter checkpoint are a multi-gigabyte addition to an image that is
    currently CPU-only, so the import failing is the expected outcome until
    somebody has decided to pay for that.
    """
    raise SystemExit(
        "Laya is not installed.\n"
        "  pip install 'torch>=2.14' 'transformers>=5' 'huggingface_hub>=1'\n"
        "  ...then implement the adapter here against laya.Router.\n"
        "Read the report in docs/ first: the repository's own benchmark puts\n"
        "the zero-shot base checkpoints BELOW the majority-class baseline on\n"
        "typed decisions, and this dataset is the thing to beat.")


CLASSIFIERS: dict[str, Classifier] = {"builtin": builtin, "laya": laya}


# --------------------------------------------------------------------------- #

def resident_mb() -> float:
    """Resident memory, or 0.0 where it cannot be read without a dependency."""
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except Exception:
        try:
            import ctypes
            import ctypes.wintypes

            class Counters(ctypes.Structure):
                _fields_ = [("cb", ctypes.wintypes.DWORD),
                            ("PageFaultCount", ctypes.wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t),
                            ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]

            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            ctypes.windll.psapi.GetProcessMemoryInfo(
                ctypes.windll.kernel32.GetCurrentProcess(),
                ctypes.byref(counters), counters.cb)
            return counters.WorkingSetSize / (1024 * 1024)
        except Exception:
            return 0.0


def score(classifier: Classifier, cases: list[Case]) -> dict:
    wrong: list[tuple[Case, str]] = []
    confusion: Counter[tuple[str, str]] = Counter()
    by_language: Counter[tuple[str, bool]] = Counter()
    timings: list[float] = []

    for case in cases:
        started = time.perf_counter()
        got = classifier(case.text, case.language, case.context)
        timings.append((time.perf_counter() - started) * 1000)

        confusion[(case.want, got)] += 1
        ok = got == case.want
        by_language[(case.language, ok)] += 1
        if not ok:
            wrong.append((case, got))

    right = sum(n for (want, got), n in confusion.items() if want == got)
    # The number that matters most: content read as agreement. Every one of
    # these commits a value the citizen did not confirm.
    false_confirms = sum(n for (want, got), n in confusion.items()
                         if got == "CONFIRM" and want != "CONFIRM")
    return {
        "total": len(cases),
        "right": right,
        "accuracy": right / len(cases) if cases else 0.0,
        "false_confirms": false_confirms,
        "confusion": confusion,
        "by_language": by_language,
        "wrong": wrong,
        "median_ms": statistics.median(timings) if timings else 0.0,
        "p95_ms": (statistics.quantiles(timings, n=20)[-1]
                   if len(timings) > 20 else max(timings, default=0.0)),
    }


def report(name: str, result: dict, memory_delta: float) -> None:
    print(f"\n=== {name} ===")
    print(f"cases            {result['total']}")
    print(f"accuracy         {result['accuracy']:.3f} "
          f"({result['right']}/{result['total']})")
    print(f"false CONFIRMs   {result['false_confirms']}  "
          "(content read as agreement — each one commits a wrong answer)")

    print("\nby language")
    for language in ("en", "ta", "mixed"):
        ok = result["by_language"][(language, True)]
        bad = result["by_language"][(language, False)]
        if ok + bad:
            print(f"  {language:<6} {ok / (ok + bad):.3f}  ({ok}/{ok + bad})")

    print("\nconfusion (want -> got, mistakes only)")
    mistakes = [(w, g, n) for (w, g), n in sorted(result["confusion"].items())
                if w != g]
    if not mistakes:
        print("  none")
    for want, got, n in mistakes:
        print(f"  {want:<9} -> {got:<9} {n}")

    if result["wrong"]:
        print("\nmisread")
        for case, got in result["wrong"][:25]:
            print(f"  [{case.language}] {case.text!r}  want {case.want}, got {got}")
        if len(result["wrong"]) > 25:
            print(f"  ... and {len(result['wrong']) - 25} more")

    print(f"\nlatency          median {result['median_ms']:.4f} ms, "
          f"p95 {result['p95_ms']:.4f} ms")
    print(f"memory added     {memory_delta:.1f} MB")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classifier", default="builtin", choices=sorted(CLASSIFIERS))
    args = parser.parse_args(argv)

    cases = dataset()
    before = resident_mb()
    classifier = CLASSIFIERS[args.classifier]
    # One warm call, so the measurement is of steady state rather than of
    # Python importing a module.
    classifier("yes", "en", CONFIRMING)
    after = resident_mb()

    result = score(classifier, cases)
    report(args.classifier, result, after - before)
    return 0 if result["false_confirms"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
