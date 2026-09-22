"""The intent classifier, scored against the whole evaluation set.

The unit tests next door check particular behaviours. This one runs the
BENCHMARK — the same cases any replacement would be judged on — as a test, so
that a change which quietly trades Tamil accuracy for English cannot land
without something going red.

Two numbers matter, and they are not the same number:

    accuracy        how often it is right
    false CONFIRMs  how often it agrees with something that was not agreement

The second is the one that reaches a citizen's petition. A classifier at 95%
whose failures are all false confirms is far worse than one at 90% whose
failures all ask the citizen to repeat themselves.
"""

from __future__ import annotations

import pytest

from benchmarks.intent_cases import dataset
from benchmarks.run_intent_benchmark import builtin, score

RESULT = score(builtin, dataset())


def test_the_set_is_big_enough_to_mean_something():
    cases = dataset()
    assert len(cases) >= 200
    # Roughly a third must be things that are NOT control words, or the set
    # only proves the classifier says yes.
    decoys = [c for c in cases if c.want == "UNKNOWN"]
    assert len(decoys) >= 30, len(decoys)


def test_nothing_that_is_not_agreement_is_read_as_agreement():
    """The number that can put a wrong value on a government form. It is
    zero, and a change that makes it non-zero is not a tuning decision."""
    assert RESULT["false_confirms"] == 0, [
        (c.text, got) for c, got in RESULT["wrong"] if got == "CONFIRM"]


def test_the_classifier_reads_the_whole_set_correctly():
    assert RESULT["accuracy"] == 1.0, [
        (c.language, c.text, c.want, got) for c, got in RESULT["wrong"]]


@pytest.mark.parametrize("language", ["en", "ta", "mixed"])
def test_neither_language_is_carried_by_the_other(language):
    """An aggregate can hide a classifier that works in English and guesses
    in Tamil, which is the failure mode that matters most here."""
    ok = RESULT["by_language"][(language, True)]
    bad = RESULT["by_language"][(language, False)]
    assert ok + bad > 0, language
    assert bad == 0, [(c.text, got) for c, got in RESULT["wrong"]
                      if c.language == language]


def test_a_decision_costs_nothing_measurable():
    """The bar any replacement has to clear. A round trip to a language
    model is three orders of magnitude slower than this and cannot be made
    faster by tuning."""
    assert RESULT["median_ms"] < 5.0, RESULT["median_ms"]
