"""Scoring a classifier honestly.

WHY NOT JUST ACCURACY. A grievance classifier that answers WATER for every
input scores 11% on a balanced eleven-category set and 100% on a set that is
all water complaints. Accuracy measures the set as much as the classifier, and
on an unbalanced set it measures mostly the set.

Macro-F1 is the headline here because it weights every category equally, so a
classifier that handles the common ones and gives up on certificates cannot
hide behind the common ones. The per-language breakdown is reported beside it
for the same reason at a different level: an aggregate figure hid a total
failure in three languages for months, because English and Tamil carried it.

WHAT UNKNOWN DOES TO THESE NUMBERS, and why it is counted apart. UNKNOWN is a
real answer with a real meaning — "a human should look at this" — and it is
the correct answer for a two-subject complaint. But a classifier can also
reach it by giving up. Those are opposite behaviours with the same label, so
they are separated:

    refusal rate     UNKNOWN where the truth was a category  (gave up)
    correct refusal  UNKNOWN where the truth was UNKNOWN     (did its job)
    wrong subject    a confident answer that is wrong        (the expensive one)

CALIBRATION, because confidence is used as a gate. A classifier that says 0.9
and is right 60% of the time is worse than one that says 0.6 and is right 60%
of the time, because something downstream believes the number. Expected
Calibration Error is the standard measure and is computed over equal-width
bins.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class PerClass:
    """Precision, recall and F1 for one category."""

    label: str
    true_positive: int = 0
    false_positive: int = 0
    false_negative: int = 0
    support: int = 0

    @property
    def precision(self) -> float:
        denominator = self.true_positive + self.false_positive
        return self.true_positive / denominator if denominator else 0.0

    @property
    def recall(self) -> float:
        denominator = self.true_positive + self.false_negative
        return self.true_positive / denominator if denominator else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


@dataclass
class Report:
    """Everything worth knowing about one run, computed once."""

    labels: tuple[str, ...]
    per_class: dict[str, PerClass] = field(default_factory=dict)
    confusion: dict[tuple[str, str], int] = field(default_factory=dict)
    per_language: dict[str, dict[str, int]] = field(default_factory=dict)
    total: int = 0
    correct: int = 0
    wrong_subject: int = 0
    refusals: int = 0
    correct_refusals: int = 0
    errors: int = 0
    _confidence: list[tuple[float, bool]] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # Headline figures
    # ------------------------------------------------------------------ #

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    @property
    def macro_f1(self) -> float:
        """The headline. Every category counts the same.

        Computed over the categories that ACTUALLY OCCUR in the truth, not
        over the whole vocabulary: averaging in an F1 of zero for a category
        the set never exercises measures the set, not the classifier.
        """
        present = [c for c in self.per_class.values() if c.support]
        return sum(c.f1 for c in present) / len(present) if present else 0.0

    @property
    def micro_f1(self) -> float:
        tp = sum(c.true_positive for c in self.per_class.values())
        fp = sum(c.false_positive for c in self.per_class.values())
        fn = sum(c.false_negative for c in self.per_class.values())
        p = tp / (tp + fp) if (tp + fp) else 0.0
        r = tp / (tp + fn) if (tp + fn) else 0.0
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def weighted_f1(self) -> float:
        present = [c for c in self.per_class.values() if c.support]
        total = sum(c.support for c in present)
        if not total:
            return 0.0
        return sum(c.f1 * c.support for c in present) / total

    @property
    def wrong_subject_rate(self) -> float:
        return self.wrong_subject / self.total if self.total else 0.0

    @property
    def refusal_rate(self) -> float:
        """How often it gave up on a question that had an answer."""
        return self.refusals / self.total if self.total else 0.0

    def language_accuracy(self, language: str) -> float:
        counts = self.per_language.get(language)
        if not counts or not counts["total"]:
            return 0.0
        return counts["correct"] / counts["total"]

    def language_macro_f1(self, language: str) -> float:
        """Macro-F1 restricted to one language's cases."""
        return self.per_language.get(language, {}).get("macro_f1_x1000", 0) / 1000

    # ------------------------------------------------------------------ #
    # Calibration
    # ------------------------------------------------------------------ #

    def calibration(self, bins: int = 10) -> tuple[float, list[tuple[float, float, int]]]:
        """Expected Calibration Error, and the bins it came from.

        Returns (ece, [(mean_confidence, accuracy, count), ...]). A perfectly
        calibrated classifier has mean confidence equal to accuracy in every
        bin, and an ECE of zero.
        """
        if not self._confidence:
            return 0.0, []

        buckets: dict[int, list[tuple[float, bool]]] = defaultdict(list)
        for confidence, was_right in self._confidence:
            index = min(int(confidence * bins), bins - 1)
            buckets[index].append((confidence, was_right))

        total = len(self._confidence)
        ece = 0.0
        rows: list[tuple[float, float, int]] = []
        for index in sorted(buckets):
            entries = buckets[index]
            mean_confidence = sum(c for c, _ in entries) / len(entries)
            accuracy = sum(1 for _, ok in entries if ok) / len(entries)
            ece += (len(entries) / total) * abs(mean_confidence - accuracy)
            rows.append((mean_confidence, accuracy, len(entries)))
        return ece, rows


# --------------------------------------------------------------------------- #
# Building a report
# --------------------------------------------------------------------------- #

#: Answers that mean "I am not committing to a category".
ABSTENTIONS = ("UNKNOWN", "OTHER")


def evaluate(rows: list[dict], labels: tuple[str, ...]) -> Report:
    """Score a list of {case, got, confidence} rows.

    `case` must carry `.expected` and `.language`.
    """
    report = Report(labels=labels)
    report.per_class = {label: PerClass(label) for label in labels}

    by_language: dict[str, list[dict]] = defaultdict(list)

    for row in rows:
        case = row["case"]
        got = str(row.get("got") or "")
        expected = case.expected
        report.total += 1
        by_language[case.language].append(row)

        if got.startswith("ERROR"):
            report.errors += 1
            # An error is a false negative for the truth and nothing else; it
            # must not be charged as a wrong subject, which is a different
            # failure with a different fix.
            if expected in report.per_class:
                report.per_class[expected].false_negative += 1
                report.per_class[expected].support += 1
            report.confusion[(expected, "ERROR")] = (
                report.confusion.get((expected, "ERROR"), 0) + 1)
            continue

        report.confusion[(expected, got)] = report.confusion.get((expected, got), 0) + 1

        if expected in report.per_class:
            report.per_class[expected].support += 1

        if got == expected:
            report.correct += 1
            if got in report.per_class:
                report.per_class[got].true_positive += 1
            if expected in ABSTENTIONS:
                report.correct_refusals += 1
        else:
            if expected in report.per_class:
                report.per_class[expected].false_negative += 1
            if got in report.per_class:
                report.per_class[got].false_positive += 1
            if got in ABSTENTIONS and expected not in ABSTENTIONS:
                report.refusals += 1
            elif got not in ABSTENTIONS:
                report.wrong_subject += 1

        confidence = row.get("confidence")
        if isinstance(confidence, (int, float)):
            report._confidence.append((float(confidence), got == expected))

    for language, group in by_language.items():
        sub = _language_counts(group, labels)
        report.per_language[language] = sub

    return report


def _language_counts(rows: list[dict], labels: tuple[str, ...]) -> dict[str, int]:
    """Totals for one language, including its own macro-F1.

    Stored as an integer thousandth so the dict stays a plain dict[str, int]
    and nothing downstream has to special-case a float in it.
    """
    per_class = {label: PerClass(label) for label in labels}
    correct = 0
    for row in rows:
        case = row["case"]
        got = str(row.get("got") or "")
        expected = case.expected
        if expected in per_class:
            per_class[expected].support += 1
        if got == expected:
            correct += 1
            if got in per_class:
                per_class[got].true_positive += 1
        else:
            if expected in per_class:
                per_class[expected].false_negative += 1
            if got in per_class:
                per_class[got].false_positive += 1

    present = [c for c in per_class.values() if c.support]
    macro = sum(c.f1 for c in present) / len(present) if present else 0.0
    return {"total": len(rows), "correct": correct,
            "macro_f1_x1000": int(round(macro * 1000))}


# --------------------------------------------------------------------------- #
# Printing
# --------------------------------------------------------------------------- #

def render(report: Report, name: str, *, show_confusion: bool = True) -> str:
    """The report as text, in the order the numbers should be read."""
    out: list[str] = []
    add = out.append

    add("=" * 74)
    add(name)
    add("=" * 74)
    add(f"  cases                {report.total}")
    add(f"  MACRO-F1             {report.macro_f1:.4f}      <- the headline")
    add(f"  micro-F1             {report.micro_f1:.4f}")
    add(f"  weighted-F1          {report.weighted_f1:.4f}")
    add(f"  accuracy             {report.accuracy:.4f}  "
        f"({report.correct}/{report.total})")
    add(f"  WRONG SUBJECT        {report.wrong_subject}  "
        f"({report.wrong_subject_rate:.4f})   <- the expensive mistake")
    add(f"  gave up (UNKNOWN)    {report.refusals}  ({report.refusal_rate:.4f})")
    add(f"  correct refusals     {report.correct_refusals}")
    if report.errors:
        add(f"  ERRORS               {report.errors}")

    add("")
    add("  by language")
    add(f"    {'lang':<6} {'macro-F1':>9} {'accuracy':>9} {'n':>5}")
    for language in sorted(report.per_language):
        counts = report.per_language[language]
        add(f"    {language:<6} {report.language_macro_f1(language):>9.4f} "
            f"{report.language_accuracy(language):>9.4f} {counts['total']:>5}")

    add("")
    add("  by category")
    add(f"    {'category':<14} {'prec':>7} {'recall':>7} {'F1':>7} {'n':>5}")
    for label in report.labels:
        cls = report.per_class[label]
        if not cls.support:
            continue
        flag = "" if cls.f1 >= 0.9 else "   <-"
        add(f"    {label:<14} {cls.precision:>7.3f} {cls.recall:>7.3f} "
            f"{cls.f1:>7.3f} {cls.support:>5}{flag}")

    ece, bins = report.calibration()
    if bins:
        add("")
        add(f"  calibration   ECE {ece:.4f}")
        add(f"    {'confidence':>11} {'accuracy':>9} {'n':>5}")
        for mean_confidence, accuracy, count in bins:
            add(f"    {mean_confidence:>11.3f} {accuracy:>9.3f} {count:>5}")

    if show_confusion:
        wrong = {k: v for k, v in report.confusion.items() if k[0] != k[1]}
        if wrong:
            add("")
            add("  confusion (expected -> got), wrong only")
            for (expected, got), count in sorted(
                    wrong.items(), key=lambda kv: -kv[1]):
                add(f"    {expected:<14} -> {got:<14} {count}")

    return "\n".join(out)
