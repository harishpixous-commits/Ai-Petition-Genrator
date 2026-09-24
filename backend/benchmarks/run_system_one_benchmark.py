"""Score a System-1 provider on the four tasks.

    python -m benchmarks.run_system_one_benchmark
    python -m benchmarks.run_system_one_benchmark --provider laya

Reports accuracy per task and per language, the confusions in full, and
latency. It scores a PROVIDER rather than the engine, so a candidate can be
measured without being wired into anything.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.system_one import DeterministicProvider  # noqa: E402
from benchmarks.system_one_cases import Case, dataset  # noqa: E402

# THE SETS ARE NOT EQUAL EVIDENCE. Three of these four have already caused a
# change to the tables, which means they can confirm a fix but can no longer
# measure one. Only a set that has never been tuned against gives an honest
# number, and each file's docstring states where it stands.
SETS = {
    "tuning": "benchmarks.system_one_cases",
    "holdout": "benchmarks.system_one_holdout",     # spent: removed the near-tie rule
    "holdout2": "benchmarks.system_one_holdout2",   # spent: added romanised Tamil
    "holdout3": "benchmarks.system_one_holdout3",   # spent: found the corporation bug
    "final_tamil": "benchmarks.system_one_final_tamil",  # spent: romanised folding
}

# What each set measured the FIRST time it was run, before it had changed
# anything. These are the only unbiased figures in the project and they are
# printed alongside the current scores so the two are never confused.
FIRST_RUN = {
    "tuning": "0.918 (then tuned against — not evidence)",
    "holdout": "0.917",
    "holdout2": "0.868",
    "holdout3": "0.860",
    "final_tamil": "0.775",
}


def ask(provider, case: Case):
    if case.task == "grievance":
        return provider.classify_grievance(**case.payload)
    if case.task == "relationship":
        return provider.classify_attachment_relationship(**case.payload)
    if case.task == "relevance":
        return provider.classify_attachment_relevance(**case.payload)
    if case.task == "review":
        from app.services.system_one import Decision

        payload = dict(case.payload)
        return provider.needs_review(
            relationship=Decision(payload["relationship"]),
            relevance=Decision(payload["relevance"]),
            category=Decision(payload["category"]),
            attention=payload["attention"])
    raise ValueError(case.task)


def load(name: str):
    if name == "deterministic":
        return DeterministicProvider()
    if name == "laya":
        from app.services.system_one import LayaProvider

        return LayaProvider()          # raises with instructions, deliberately
    raise SystemExit(f"unknown provider {name!r}")


def load_set(name: str) -> list[Case]:
    import importlib

    return importlib.import_module(SETS[name]).dataset()


def score_every_set(provider, verbose: bool = False) -> int:
    """All four at once, which is the view worth looking at.

    A single high number means little when three of the sets helped produce
    it. Four numbers side by side show whether the rules generalise or
    whether they were fitted to whichever sentence was last in a terminal.
    """
    worst = 0
    print(f"\nProvider: {provider.name}\n")
    for name in SETS:
        cases = load_set(name)
        wrong = [c for c in cases if ask(provider, c).value != c.want]
        right, total = len(cases) - len(wrong), len(cases)
        print(f"  {name:12s} {right:3d}/{total:<3d}  {right / total:.3f}"
              f"   first run: {FIRST_RUN.get(name, '?')}")
        for case in wrong:
            text = case.payload.get("grievance") or case.payload.get("text") or ""
            print(f"       wanted {case.want:26s} {str(text)[:40]}")
        worst = max(worst, len(wrong))
    print("\n  THE LEFT COLUMN IS NOT EVIDENCE. Every set here has caused the")
    print("  tables to change, so each one now agrees with code that was")
    print("  adjusted until it did. The first-run column is the honest one.")
    print("  The last unbiased measurement was final_tamil at 0.775 overall")
    print("  (grievance 0.735, relationship 1.000). A new figure needs a new set.")
    return 0 if worst == 0 else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="deterministic")
    parser.add_argument("--set", default="tuning", choices=[*SETS, "all"],
                        help="which case set to score (default: tuning)")
    parser.add_argument("--verbose", action="store_true",
                        help="print every case, not only the wrong ones")
    args = parser.parse_args()

    provider = load(args.provider)
    if args.set == "all":
        return score_every_set(provider, args.verbose)
    cases = load_set(args.set)
    by_task: dict[str, list[bool]] = defaultdict(list)
    by_language: dict[str, list[bool]] = defaultdict(list)
    wrong: list[tuple[Case, str, str]] = []
    timings: list[float] = []

    for case in cases:
        started = time.perf_counter()
        answer = ask(provider, case)
        timings.append((time.perf_counter() - started) * 1000)
        right = answer.value == case.want
        by_task[case.task].append(right)
        by_language[case.language].append(right)
        if not right:
            wrong.append((case, answer.value, answer.reason))
        elif args.verbose:
            print(f"  ok   {case.task:12s} {case.want:32s} {case.note}")

    print(f"\nProvider: {args.provider}   cases: {len(cases)}\n")
    print("By task")
    for task, results in sorted(by_task.items()):
        hit = sum(results)
        print(f"  {task:14s} {hit:3d}/{len(results):<3d}  {hit / len(results):.3f}")
    print("\nBy language")
    for language, results in sorted(by_language.items()):
        hit = sum(results)
        print(f"  {language:14s} {hit:3d}/{len(results):<3d}  {hit / len(results):.3f}")

    total = sum(sum(v) for v in by_task.values())
    print(f"\nOverall        {total:3d}/{len(cases):<3d}  {total / len(cases):.3f}")
    print(f"Latency        median {statistics.median(timings):.3f} ms   "
          f"max {max(timings):.3f} ms")

    # THE ONE THAT MATTERS MOST, called out on its own. Reading somebody
    # else's petition as the citizen's own is what let an attachment rename
    # a petitioner.
    third_party = [c for c in cases
                   if c.task == "relationship"
                   and c.want == "THIRD_PARTY_SUPPORTING_DOCUMENT"]
    missed = [c for c in third_party
              if ask(provider, c).value == "OWN_PREVIOUS_PETITION"]
    print(f"\nThird-party petitions read as the citizen's own: "
          f"{len(missed)}/{len(third_party)}")

    if wrong:
        print(f"\n{len(wrong)} wrong:\n")
        for case, got, reason in wrong:
            payload = case.payload.get("grievance") or case.payload.get("text") or case.payload
            print(f"  {case.task}/{case.language}: wanted {case.want}, got {got}")
            print(f"     input : {str(payload)[:72]}")
            print(f"     reason: {reason}")
            if case.note:
                print(f"     note  : {case.note}")
            print()
    return 1 if wrong or missed else 0


if __name__ == "__main__":
    sys.exit(main())
