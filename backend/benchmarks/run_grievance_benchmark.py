"""Score a grievance classifier against the petition assistant's own cases.

    python -m benchmarks.run_grievance_benchmark                  # in service
    python -m benchmarks.run_grievance_benchmark --classifier laya

WHY A HARNESS AND NOT A SCRIPT PER CANDIDATE, for the same reason as
`run_intent_benchmark`: "should we replace the grievance reader" is only
answerable if incumbent and candidate are measured on the same cases, in the
same units, on this machine. A published benchmark table measures somebody
else's workload.

WHAT IT REPORTS, and why each number is here

    accuracy overall, and per language — a classifier that reads English and
        guesses at Malayalam is not usable in a service that offers five
        languages, and an overall figure hides that completely.

    the WRONG-SUBJECT rate, counted separately from UNKNOWN. These are not the
        same mistake. UNKNOWN sends a petition to a human, which is what is
        supposed to happen when the text is genuinely unclear. A confident
        wrong subject puts a misleading hint in front of an officer. Only one
        of those is expensive.

    the MISSED rate: a clear single-subject complaint answered UNKNOWN. Cheap,
        but it is the whole value of the feature being given up.

    median and p95 latency, measured here rather than quoted.

    resident memory before and after, because the deployment host runs
        LibreOffice and the workflow in the same container.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from collections import Counter
from collections.abc import Callable

from benchmarks.grievance_cases import CATEGORIES, Case, dataset

Classifier = Callable[[str, str], str]


# --------------------------------------------------------------------------- #
# The classifier in service
# --------------------------------------------------------------------------- #

def builtin(text: str, language: str) -> str:
    """The deterministic reader the application uses today."""
    from app.services.system_one import DeterministicProvider

    decision = DeterministicProvider().classify_grievance(
        grievance=text, language=language)
    return decision.value


# --------------------------------------------------------------------------- #
# Laya, loaded once and reused
# --------------------------------------------------------------------------- #

_ROUTER = None

#: What each label means, in the words an officer would use. Laya's `choice`
#: primitive takes a criteria map and reads it as part of the forward pass, so
#: this is not a comment — it is the model's only description of the task.
_CRITERIA = {
    "WATER": "drinking water supply, taps, water connection, water tankers",
    "ROAD": "roads, potholes, road laying, culverts, footpaths",
    "STREET_LIGHT": "street lights, lamps, public lighting on a road",
    "SANITATION": "garbage collection, sewage, drains, public toilets, cleaning",
    "PENSION": "old age, widow, disability or other government pension payments",
    "WELFARE": "ration card, housing scheme, scholarship, welfare entitlements",
    "LICENCE": "trade licence, building plan approval, permits from an office",
    "CERTIFICATE": "community, income, nativity, birth or death certificates",
    "PROPERTY": "land, patta, encroachment, boundary, property transfer",
    "ELECTRICITY": "power supply, power cuts, transformers, electricity bills",
    "OTHER": "a government grievance that none of the other options covers",
    "UNKNOWN": ("the text names no subject, or it names TWO separate "
                "complaints and picking one would be wrong"),
}


def laya(text: str, language: str) -> str:  # pragma: no cover — optional dep
    """A candidate. Not installed by this repository; see docs/laya-decision.md.

    Loaded on first use and kept, because a per-call load would measure the
    disk rather than the model.
    """
    global _ROUTER
    if _ROUTER is None:
        try:
            from laya import Router
        except ImportError:
            raise SystemExit(
                "Laya is not installed.\n"
                "  pip install laya\n"
                "Read docs/laya-decision.md first: the repository's own numbers\n"
                "put the zero-shot base checkpoints BELOW the majority-class\n"
                "baseline on typed decisions, and these cases are the thing to\n"
                "beat.") from None
        _ROUTER = Router(device="cpu", default="multilingual", preload=True)

    if not str(text or "").strip():
        return "UNKNOWN"

    questions = {
        "category": {
            "type": "choice",
            "instructions": ("What is the citizen complaining about in "
                             "`grievance`?"),
            "criteria": _CRITERIA,
        }
    }
    # THE ANSWERS ARE NESTED. `predict` returns
    # {"model": ..., "answers": {<question>: {...}}, "usage": ..., "routing": ...}
    # and reading `out["category"]` instead of `out["answers"]["category"]`
    # yields None for every case — which scored Laya at 0.172 on a first run
    # and was entirely this line. A classifier that answers one label for every
    # input has not been measured, it has been misused; that number was thrown
    # away rather than reported.
    out = _ROUTER.predict({"grievance": text}, questions)
    answer = (out.get("answers") or {}).get("category") or {}
    return str(answer.get("choice") or "UNKNOWN")


CLASSIFIERS: dict[str, Classifier] = {"builtin": builtin, "laya": laya}


# --------------------------------------------------------------------------- #

def resident_mb() -> float:
    """Resident memory in MB, or 0.0 where it cannot be read."""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32

        class Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_uint32),
                        ("PageFaultCount", ctypes.c_uint32),
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
        ok = kernel32.K32GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
        if ok:
            return counters.WorkingSetSize / 1_048_576
    except Exception:
        pass
    try:
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except Exception:
        return 0.0


def score(classifier: Classifier, cases: tuple[Case, ...]) -> dict:
    """Run every case and collect what happened, without judging it yet."""
    rows = []
    for case in cases:
        start = time.perf_counter()
        try:
            got = classifier(case.text, case.language)
        except Exception as exc:  # noqa: BLE001
            got = f"ERROR:{type(exc).__name__}"
        rows.append({"case": case, "got": got,
                     "ms": (time.perf_counter() - start) * 1000})
    return {"rows": rows}


def report(name: str, result: dict, before: float, after: float) -> int:
    """Print the findings. Returns the number of confidently wrong answers."""
    rows = result["rows"]
    total = len(rows)
    correct = sum(1 for r in rows if r["got"] == r["case"].expected)

    # The three failure modes, which are not equally expensive.
    wrong_subject = [r for r in rows
                     if r["got"] != r["case"].expected
                     and r["got"] not in ("UNKNOWN", "OTHER")
                     and not r["got"].startswith("ERROR")]
    missed = [r for r in rows
              if r["got"] in ("UNKNOWN", "OTHER")
              and r["case"].expected not in ("UNKNOWN", "OTHER")]
    errors = [r for r in rows if r["got"].startswith("ERROR")]

    print(f"\n{'=' * 70}\n{name}\n{'=' * 70}")
    print(f"  cases                 {total}")
    print(f"  accuracy              {correct / total:.3f}  ({correct}/{total})")
    print(f"  WRONG SUBJECT         {len(wrong_subject)}  "
          f"({len(wrong_subject) / total:.3f})   <- the expensive mistake")
    print(f"  missed (said UNKNOWN) {len(missed)}  ({len(missed) / total:.3f})")
    if errors:
        print(f"  ERRORS                {len(errors)}")

    print("\n  by language")
    languages: dict[str, list] = {}
    for row in rows:
        languages.setdefault(row["case"].language, []).append(row)
    for language in sorted(languages):
        group = languages[language]
        hit = sum(1 for r in group if r["got"] == r["case"].expected)
        print(f"    {language}   {hit / len(group):.3f}  ({hit}/{len(group)})")

    print("\n  by expected category")
    expected_groups: dict[str, list] = {}
    for row in rows:
        expected_groups.setdefault(row["case"].expected, []).append(row)
    for category in CATEGORIES:
        group = expected_groups.get(category)
        if not group:
            continue
        hit = sum(1 for r in group if r["got"] == r["case"].expected)
        flag = "" if hit == len(group) else "   <-"
        print(f"    {category:<13} {hit}/{len(group)}{flag}")

    if wrong_subject:
        print("\n  every confidently wrong answer")
        for row in wrong_subject:
            case = row["case"]
            text = case.text if len(case.text) <= 58 else case.text[:55] + "..."
            print(f"    [{case.language}] expected {case.expected:<13} "
                  f"got {row['got']:<13}")
            print(f"        {text}")
            if case.note:
                print(f"        note: {case.note}")

    timings = sorted(r["ms"] for r in rows)
    if timings:
        print(f"\n  latency   median {statistics.median(timings):.2f} ms"
              f"   p95 {timings[int(len(timings) * 0.95) - 1]:.2f} ms"
              f"   max {timings[-1]:.2f} ms")
    print(f"  memory    {before:.0f} MB -> {after:.0f} MB "
          f"(+{after - before:.0f} MB)")

    counted = Counter(r["got"] for r in rows)
    print(f"  answers   {dict(sorted(counted.items()))}")
    return len(wrong_subject)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classifier", default="builtin",
                        choices=sorted(CLASSIFIERS))
    args = parser.parse_args(argv)

    cases = dataset()
    before = resident_mb()
    classifier = CLASSIFIERS[args.classifier]
    result = score(classifier, cases)
    after = resident_mb()
    report(args.classifier, result, before, after)
    return 0


if __name__ == "__main__":
    sys.exit(main())
