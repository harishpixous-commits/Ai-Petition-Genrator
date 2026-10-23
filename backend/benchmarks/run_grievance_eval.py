"""Score the grievance classifier properly, on a named split.

    python -m benchmarks.run_grievance_eval --split dev
    python -m benchmarks.run_grievance_eval --split heldout
    python -m benchmarks.run_grievance_eval --split all --classifier laya

WHY THIS EXISTS BESIDE `run_grievance_benchmark`. That one answers "is this
classifier better than that one" in a form a person can read at a glance. This
one answers "how good is it, per language, per category, and is its confidence
worth believing" — macro-F1, precision and recall per class, a confusion
matrix, and calibration error.

THE SPLITS ARE NOT INTERCHANGEABLE.

    dev      look at this as often as you like. It is what the taxonomy and
             the matcher were tuned against, so a number from it is optimistic
             by construction and is NOT a measure of the classifier.

    heldout  written before any tuning and not consulted during it. Scored at
             the end. This is the number to quote.

Scoring `heldout`, finding a failure, and adding the failing phrase to the
taxonomy converts it into a development set and destroys the only unbiased
measurement the project has. If that happens it has to be said out loud and a
fresh held-out set written.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time

from benchmarks.grievance_cases import CATEGORIES, Case
from benchmarks.grievance_cases import dataset as dev_core
from benchmarks.grievance_heldout import dataset as heldout_set
from benchmarks.grievance_heldout2 import dataset as heldout2_set
from benchmarks.metrics import evaluate, render
from benchmarks.run_grievance_benchmark import CLASSIFIERS, resident_mb


def dev_set() -> tuple[Case, ...]:
    """Development cases: the original set plus anything added for tuning."""
    cases = list(dev_core())
    try:
        from benchmarks.grievance_dev import EXTRA

        cases.extend(EXTRA)
    except ImportError:
        pass
    return tuple(cases)


SPLITS = {
    "dev": dev_set,
    # The first held-out set. Scored cleanly once at 0.7174; its failures were
    # then read, which spends a held-out set. Still useful for comparison,
    # but it is no longer unbiased evidence.
    "heldout": heldout_set,
    # Written after the first was spent and before the semantic reader was
    # scored on anything. THIS is the number to quote.
    "heldout2": heldout2_set,
    "all": lambda: dev_set() + heldout_set() + heldout2_set(),
}


def run(classifier, cases: tuple[Case, ...], *,
        semantic: bool = False) -> list[dict]:
    """Classify every case, keeping the confidence so calibration can be read.

    `semantic` runs the full application path — the deterministic reader
    first, and the embedding comparison only where it found nothing. That is
    what the service actually does, so it is the honest thing to measure; it
    needs a configured embedder and reaches the network.
    """
    from app.services.system_one import DeterministicProvider

    provider = DeterministicProvider()
    is_builtin = classifier.__name__ == "builtin"

    if semantic and is_builtin:
        return asyncio.run(_run_semantic(cases))

    rows: list[dict] = []
    for case in cases:
        start = time.perf_counter()
        confidence = None
        try:
            if is_builtin:
                # Taken from the Decision rather than re-derived, so the
                # calibration figure describes the number the application
                # actually acts on.
                decision = provider.classify_grievance(
                    grievance=case.text, language=case.language)
                got, confidence = decision.value, decision.confidence
            else:
                got = classifier(case.text, case.language)
        except Exception as exc:  # noqa: BLE001
            got = f"ERROR:{type(exc).__name__}"
        rows.append({"case": case, "got": got, "confidence": confidence,
                     "ms": (time.perf_counter() - start) * 1000})
    return rows


async def _run_semantic(cases: tuple[Case, ...]) -> list[dict]:
    """The application's own path, including the embedding fallback."""
    from app.services import system_one

    rows: list[dict] = []
    for case in cases:
        start = time.perf_counter()
        try:
            decision = await system_one.classify_grievance(
                grievance=case.text, language=case.language)
            got, confidence = decision.value, decision.confidence
        except Exception as exc:  # noqa: BLE001
            got, confidence = f"ERROR:{type(exc).__name__}", None
        rows.append({"case": case, "got": got, "confidence": confidence,
                     "ms": (time.perf_counter() - start) * 1000})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default="dev", choices=sorted(SPLITS))
    parser.add_argument("--classifier", default="builtin",
                        choices=sorted(CLASSIFIERS))
    parser.add_argument("--no-confusion", action="store_true")
    parser.add_argument("--semantic", action="store_true",
                        help="run the application's full path, including the "
                             "embedding fallback (needs a configured embedder "
                             "and reaches the network)")
    args = parser.parse_args(argv)

    cases = SPLITS[args.split]()
    before = resident_mb()
    rows = run(CLASSIFIERS[args.classifier], cases, semantic=args.semantic)
    after = resident_mb()

    report = evaluate(rows, CATEGORIES)
    label = f"{args.classifier}{'+semantic' if args.semantic else ''}"
    print(render(report, f"{label} on {args.split} ({len(cases)} cases)",
                 show_confusion=not args.no_confusion))

    timings = sorted(r["ms"] for r in rows)
    print()
    print(f"  latency   median {statistics.median(timings):.3f} ms"
          f"   p95 {timings[int(len(timings) * 0.95) - 1]:.3f} ms")
    print(f"  memory    {before:.0f} -> {after:.0f} MB")

    if args.split.startswith("heldout"):
        print()
        print("  This is the held-out number. Do not tune against it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
