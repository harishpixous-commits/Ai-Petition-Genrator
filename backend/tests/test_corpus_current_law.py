"""The corpus answers from current law, not from the text it started with.

THE CASE THIS IS BUILT AROUND IS REAL AND WAS VERIFIED DOCUMENT BY DOCUMENT.

    The Tamil Nadu Urban Local Bodies Rules, 2023 (G.O. Ms. No. 45, Gazette
    Extraordinary 124 of 12 April 2023) say at rule 290(1) that a trade
    licence "shall be valid for a period of three years from the date of issue
    and may be renewed for a further period of three years."

    G.O. Ms. No. 35 of 17 March 2025 changed that wording.

    G.O. Ms. No. 164 of 3 September 2026 (SRO A-16(a)/2026, Gazette
    Extraordinary 374) SUBSTITUTES rule 290(1) outright: ten years, renewable
    for successive periods of ten years. It also adds a proviso to rule 289(1)
    exempting shops registered under the Tamil Nadu Shops and Establishments
    Act, 1947 from needing a separate municipal trade licence for the same
    premises and trade.

So a citizen asking "how long is my trade licence valid" has a different
answer in 2026 than the 2023 Rules give, and a corpus that holds only the 2023
Rules answers wrongly WITH A CITATION — which is worse than not answering,
because the citation is what makes it believable.

WHAT THESE TESTS ASSERT, and what they deliberately do not. They assert the
amending instruments are present and retrievable, because that is the
precondition for ever getting this right. They do NOT assert that the analyst
automatically reconciles an amendment chain into consolidated text: it does
not do that, no retrieval system does it reliably, and claiming otherwise
would be the fabrication this whole layer exists to prevent. What the service
does is put the amendment in front of the officer alongside the base rule.

REAL DATA. These run against `var/knowledge.sqlite` as built by
`scripts/fetch_corpus.py ingest`, and skip with the exact command when it has
not been built.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

#: THE REAL CORPUS, by path, NOT via `get_settings()`.
#:
#: `conftest.py` points DATA_DIR at a fresh temporary directory for every run —
#: correctly, because the suite must not touch real data. But that also means
#: `get_settings().knowledge_path` is a temp file that is always empty, so a
#: guard built on it skips every time and reports eight passing-looking skips
#: forever. A test that can never run is worse than no test: it looks like
#: coverage.
#:
#: Read-only, and only ever read. Nothing here writes to it.
KNOWLEDGE = Path(__file__).resolve().parent.parent / "var" / "knowledge.sqlite"


def _documents() -> list[tuple[str, str]]:
    """(title, document_type) for everything indexed."""
    if not KNOWLEDGE.exists():
        return []
    db = sqlite3.connect(f"file:{KNOWLEDGE}?mode=ro", uri=True)
    try:
        names = {row[1] for row in db.execute("PRAGMA table_info(documents)")}
        if not names:
            return []
        return [(str(r[0]), str(r[1])) for r in db.execute(
            "SELECT title, document_type FROM documents")]
    except sqlite3.DatabaseError:
        return []
    finally:
        db.close()


DOCUMENTS = _documents()

pytestmark = pytest.mark.skipif(
    not DOCUMENTS,
    reason="the government corpus has not been ingested — run "
           "`python scripts/fetch_corpus.py ingest`")


def _titles() -> str:
    return " || ".join(title for title, _ in DOCUMENTS)


class TestTheAmendmentChainIsPresent:
    def test_the_base_rules_are_indexed(self):
        assert "Urban Local Bodies Rules, 2023" in _titles()

    def test_the_2026_amendment_is_indexed(self):
        """G.O. Ms. No. 164 of 3 September 2026. Without this the corpus
        answers the trade licence question from 2023 text."""
        titles = _titles()
        assert "164" in titles, (
            "G.O. Ms. No. 164 is missing. The corpus will answer trade licence "
            "questions from superseded 2023 Rules.")

    def test_several_amendments_are_indexed_not_just_the_latest(self):
        """An amendment chain is a chain. The 2025 and 2024 instruments change
        other provisions, and holding only the newest would leave those
        answered from the base text."""
        titles = _titles()
        present = [go for go in ("164", "480", "433", "104", "162")
                   if go in titles]
        assert len(present) >= 3, f"only found {present}"

    def test_the_amending_acts_are_indexed_too(self):
        """Rules are amended by G.O.; the ACT is amended by an Act. Both
        matter and they are different instruments."""
        titles = _titles().lower()
        assert "act no. 24 of 2024" in titles or "amendment) act, 2025" in titles


class TestTheCorpusKnowsWhatKindOfThingEachIs:
    def test_amendments_are_typed_as_government_orders(self):
        kinds = {kind for title, kind in DOCUMENTS if "164" in title}
        assert kinds <= {"government_order"}, kinds

    def test_acts_rules_and_orders_are_all_represented(self):
        kinds = {kind for _, kind in DOCUMENTS}
        for expected in ("act", "rule", "government_order"):
            assert expected in kinds, f"no {expected} in {kinds}"


class TestTheCorpusIsMultilingual:
    def test_at_least_one_tamil_document_is_indexed(self):
        """A corpus that is entirely English makes every Tamil citizen depend
        on cross-language retrieval for everything. Tamil documents exist and
        should be indexed as themselves."""
        import re

        tamil = re.compile("[஀-௿]")
        tamil_titles = [t for t, _ in DOCUMENTS if tamil.search(t)]
        assert tamil_titles, (
            "no Tamil-titled document is indexed; a Tamil citizen can only "
            "ever reach English text")


class TestWhatIsDeliberatelyNotClaimed:
    def test_the_corpus_holds_both_the_base_rule_and_its_amendment(self):
        """CONSOLIDATION IS NOT AUTOMATIC and is not claimed.

        The service does not merge an amendment into the base text — no
        retrieval system does that reliably, and inventing consolidated
        wording would be exactly the fabrication this layer prevents. Both
        instruments are indexed so an officer sees the amendment beside the
        rule and applies it themselves.
        """
        titles = _titles()
        assert "Rules, 2023" in titles
        assert "164" in titles
