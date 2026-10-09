"""The grievance classifier, scored against the whole evaluation set.

Written for the same reason as `test_intent_benchmark.py`: the unit tests next
door check particular behaviours, and this one runs the BENCHMARK, so that a
change which quietly trades one language for another cannot land without
something going red.

THE NUMBER THIS FILE EXISTS FOR is the per-language one. An overall accuracy
figure hid a complete failure for months: the service offered five languages
and this classifier had words for two, so every grievance written in
Malayalam, Telugu or Hindi came back UNKNOWN — not often, not usually, but
always — while the overall score still read 0.609 because English and Tamil
carried it. A single aggregate number cannot catch that, and did not.

The floors below are deliberately set under what is measured today. They are
regression guards, not targets; tightening them to the current figure would
make every ordinary improvement a test failure.
"""

from __future__ import annotations

import pytest

from benchmarks.grievance_cases import CATEGORIES, dataset
from benchmarks.run_grievance_benchmark import builtin, score

RESULT = score(builtin, dataset())
ROWS = RESULT["rows"]


def _accuracy(rows) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if r["got"] == r["case"].expected) / len(rows)


def test_the_set_covers_every_category_and_language():
    cases = dataset()
    assert len(cases) >= 60, len(cases)

    languages = {case.language for case in cases}
    assert languages == {"en", "ta", "ml", "te", "hi"}, languages

    # Every category the application can return, except OTHER, has at least one
    # case. A vocabulary nothing exercises is a vocabulary nobody has checked.
    covered = {case.expected for case in cases}
    missing = set(CATEGORIES) - covered - {"OTHER"}
    assert not missing, f"no case expects: {sorted(missing)}"

    # A third or so must expect UNKNOWN, or the set only proves the classifier
    # is willing to answer.
    unclear = [c for c in cases if c.expected == "UNKNOWN"]
    assert len(unclear) >= 10, len(unclear)


@pytest.mark.parametrize("language", ["en", "ta", "ml", "te", "hi"])
def test_no_language_is_carried_by_the_others(language):
    """THE REGRESSION THIS FILE WAS WRITTEN FOR.

    Malayalam, Telugu and Hindi each scored 0.000 here — every grievance
    UNKNOWN, always — while the overall figure looked merely mediocre. If any
    language goes to zero again, this is what says so.
    """
    rows = [r for r in ROWS if r["case"].language == language]
    assert rows, f"no cases for {language}"
    accuracy = _accuracy(rows)
    assert accuracy >= 0.6, (
        f"{language} fell to {accuracy:.3f} — "
        + str([(r["case"].text[:40], r["got"]) for r in rows
               if r["got"] != r["case"].expected]))


def test_the_classifier_reads_most_of_the_set():
    assert _accuracy(ROWS) >= 0.80, _accuracy(ROWS)


def test_a_confident_wrong_subject_stays_rare():
    """Not the same mistake as UNKNOWN, and far more expensive.

    UNKNOWN sends a petition to a human, which is what should happen when the
    text is genuinely unclear. A confident wrong subject puts a misleading
    hint in front of an officer who has no reason to doubt it.
    """
    wrong = [r for r in ROWS
             if r["got"] != r["case"].expected
             and r["got"] not in ("UNKNOWN", "OTHER")]
    assert len(wrong) / len(ROWS) <= 0.15, [
        (r["case"].language, r["case"].text[:45], r["case"].expected, r["got"])
        for r in wrong]


def test_two_complaints_are_not_answered_with_one_of_them():
    """A citizen reporting a road AND a street light has made two complaints.
    Picking one is worse than admitting there are two, because the one not
    picked is the one that never gets fixed."""
    rows = [r for r in ROWS if r["case"].expected == "UNKNOWN"]
    answered = [r for r in rows if r["got"] not in ("UNKNOWN", "OTHER")]
    assert len(answered) <= 3, [
        (r["case"].text[:50], r["got"]) for r in answered]


def test_every_answer_is_in_the_vocabulary():
    """A category the application has never heard of cannot be rendered, and
    would reach the officer's panel as a raw string."""
    for row in ROWS:
        assert row["got"] in CATEGORIES, (row["case"].text[:50], row["got"])


def test_a_decision_costs_nothing_measurable():
    """No model, no network, no warm-up — the property that lets this run on
    the happy path at all. Generous, because CI machines are not quiet."""
    slowest = max(row["ms"] for row in ROWS)
    assert slowest < 100, f"{slowest:.1f} ms for one classification"
