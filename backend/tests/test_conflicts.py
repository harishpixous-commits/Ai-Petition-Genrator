"""Two government documents that say different things about the same rule.

A departmental folder is not a consistent snapshot. It holds the 1998 Rules and
the 2019 amendment; a G.O. and its revision; a circular and the notice
withdrawing it. Retrieval returns passages from both, and the failure mode is
not a wrong answer — it is a *tidy* answer assembled across the seam, where an
officer reading "the fee is fifty rupees" has no way to see that the sentence
came from something that stopped being operative years ago.

So there are exactly two permitted outcomes, and this file asserts both:

    preferred_newer   one document is demonstrably current; the other is set
                      aside as evidence but kept on the record
    undetermined      nothing establishes which is in force, so neither is
                      treated as settled and the officer is told so

and one forbidden outcome: silently merging them.

Everything here is TEST DATA, ingested into a temp directory. The "Rules" are
invented and say so on their face.
"""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.knowledge.analyst import Analyst
from app.knowledge.conflicts import resolve, topic_of
from app.knowledge.embeddings import LocalEmbeddings
from app.knowledge.ingest import Ingestor
from app.knowledge.retrieve import Retriever
from app.knowledge.schema import Chunk
from app.knowledge.store import KnowledgeStore

TEST_PROVENANCE = "TEST DATA — fixture, not a real government source"

OLD_RULE = """TEST DATA — Sample Licensing Rules, 1998

Rule 4. Fee payable.
The fee payable for a licence under these rules shall be fifty rupees.
"""
NEW_RULE = """TEST DATA — Sample Licensing Rules, 2019

Rule 4. Fee payable.
The fee payable for a licence under these rules shall be five hundred rupees.
"""
UNDATED_A = """TEST DATA — Sample Procedure Circular

Rule 9. Time limit.
An appeal shall be preferred within thirty days.
"""
UNDATED_B = """TEST DATA — Sample Procedure Circular

Rule 9. Time limit.
An appeal shall be preferred within sixty days.
"""
UNRELATED = """TEST DATA — Sample Water Supply Guidelines

Complaints about drinking water shall be made to the Assistant Engineer.
"""


@pytest.fixture
def make_corpus(tmp_path):
    """Ingest a set of documents into a throwaway store."""
    provider = LocalEmbeddings(dimension=256)
    settings = get_settings()

    async def build(documents):
        store = KnowledgeStore(tmp_path / "k.sqlite", dimension=256, provider="local")
        ingestor = Ingestor(store=store, provider=provider, settings=settings)
        ids = []
        for name, text, metadata in documents:
            path = tmp_path / name
            path.write_text(text, encoding="utf-8")
            result = await ingestor.ingest(
                path, metadata={"provenance": TEST_PROVENANCE, **metadata})
            ids.append(result.document_id)
        return store, Retriever(store, provider, settings), ids

    return build


def _chunk(document_id, title, **kwargs):
    return Chunk(chunk_id=f"{document_id}-1", document_id=document_id,
                 text="Rule 4. The fee shall be paid.", document_title=title, **kwargs)


# --------------------------------------------------------------------------- #
# What counts as the same subject
# --------------------------------------------------------------------------- #

class TestTopic:
    def test_two_documents_on_one_rule_share_a_topic(self):
        first = _chunk("a", "Rules 1998", rule_name="Sample Licensing Rules")
        second = _chunk("b", "Rules 2019", rule_name="Sample Licensing Rules")
        assert topic_of(first) == topic_of(second)

    def test_a_document_with_no_instrument_is_never_compared(self):
        """Better to miss a conflict than to invent one between two circulars
        that merely share a department."""
        assert topic_of(_chunk("a", "Some circular")) is None

    def test_a_government_order_number_is_a_topic(self):
        assert topic_of(_chunk("a", "G.O.", government_order_number="145")) == "go:145"


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #

class TestResolution:
    def test_a_superseded_document_is_set_aside_and_recorded(self):
        live = _chunk("new", "Rules 2019", rule_name="Sample Rules")
        retired = _chunk("old", "Rules 1998", rule_name="Sample Rules", superseded=True)

        kept, conflicts = resolve([live, retired])

        assert [c.document_id for c in kept] == ["new"]
        assert len(conflicts) == 1
        assert conflicts[0].resolution == "preferred_newer"
        assert conflicts[0].superseded_id == "old"
        # Version history survives: the retired one is still on the record.
        assert conflicts[0].older.document_title == "Rules 1998"

    def test_the_later_date_wins(self):
        old = _chunk("a", "Rules 1998", rule_name="Sample Rules", date="1998-01-01")
        new = _chunk("b", "Rules 2019", rule_name="Sample Rules", date="2019-06-01")

        kept, conflicts = resolve([old, new])

        assert [c.document_id for c in kept] == ["b"]
        assert conflicts[0].resolution == "preferred_newer"

    def test_a_year_in_the_title_counts_when_there_is_no_date(self):
        """A corpus built from PDFs often has nothing but the name."""
        old = _chunk("a", "Rules", rule_name="Sample Licensing Rules, 1998")
        new = _chunk("b", "Rules", rule_name="Sample Licensing Rules, 2019")

        kept, conflicts = resolve([old, new])

        assert conflicts[0].resolution == "preferred_newer"
        assert [c.document_id for c in kept] == ["b"]

    def test_undated_documents_are_kept_and_flagged(self):
        first = _chunk("a", "Circular", rule_name="Sample Procedure")
        second = _chunk("b", "Circular", rule_name="Sample Procedure")

        kept, conflicts = resolve([first, second])

        assert {c.document_id for c in kept} == {"a", "b"}, "neither is discarded"
        assert conflicts[0].resolution == "undetermined"
        assert conflicts[0].needs_office_confirmation
        assert "which is currently in force" in conflicts[0].message

    def test_unrelated_documents_produce_no_conflict(self):
        first = _chunk("a", "Licensing", rule_name="Sample Licensing Rules")
        second = _chunk("b", "Water", rule_name="Sample Water Rules")

        kept, conflicts = resolve([first, second])

        assert len(kept) == 2
        assert conflicts == []

    def test_a_single_document_is_never_in_conflict_with_itself(self):
        only = _chunk("a", "Rules", rule_name="Sample Rules")
        kept, conflicts = resolve([only, only])
        assert conflicts == []
        assert len(kept) == 2

    def test_nothing_is_ever_returned_empty(self):
        """Two superseded revisions and no live one: thin evidence, not none."""
        first = _chunk("a", "Rules 1998", rule_name="Sample Rules", superseded=True)
        second = _chunk("b", "Rules 2019", rule_name="Sample Rules", superseded=True)

        kept, _ = resolve([first, second])
        assert kept, "retrieval must not be emptied by conflict resolution"


# --------------------------------------------------------------------------- #
# End to end, through the analyst
# --------------------------------------------------------------------------- #

class TestThroughTheAnalyst:
    async def test_the_newer_rule_is_the_one_reported(self, make_corpus):
        store, retriever, _ = await make_corpus([
            ("old.txt", OLD_RULE, {"authority": "official",
                                   "rule_name": "Sample Licensing Rules",
                                   "date": "1998-01-01"}),
            ("new.txt", NEW_RULE, {"authority": "official",
                                   "rule_name": "Sample Licensing Rules",
                                   "date": "2019-01-01"}),
        ])
        analysis = await Analyst(retriever, get_settings()).analyse("licence fee payable")

        excerpts = " ".join(s.excerpt for s in analysis.sources)
        assert "five hundred rupees" in excerpts
        assert "fifty rupees" not in excerpts, "the 1998 wording must not be cited"
        assert len(analysis.conflicts) == 1
        # Resolved, so it is recorded but not warned about.
        assert analysis.warnings == []

    async def test_an_unresolvable_conflict_warns_and_shows_both(self, make_corpus):
        store, retriever, _ = await make_corpus([
            ("a.txt", UNDATED_A, {"authority": "official",
                                  "rule_name": "Sample Procedure Circular"}),
            ("b.txt", UNDATED_B, {"authority": "official",
                                  "rule_name": "Sample Procedure Circular"}),
        ])
        analysis = await Analyst(retriever, get_settings()).analyse(
            "time limit for an appeal")

        assert analysis.warnings, "an unresolved conflict must be said out loud"
        excerpts = " ".join(s.excerpt for s in analysis.sources)
        assert "thirty days" in excerpts
        assert "sixty days" in excerpts, "both must be visible, not merged"

    async def test_identical_titles_do_not_collapse_into_one_source(self, make_corpus):
        """Two different documents sharing a title were deduplicated into one,
        which hid half of every conflict."""
        store, retriever, _ = await make_corpus([
            ("a.txt", UNDATED_A, {"authority": "official",
                                  "rule_name": "Sample Procedure Circular"}),
            ("b.txt", UNDATED_B, {"authority": "official",
                                  "rule_name": "Sample Procedure Circular"}),
        ])
        analysis = await Analyst(retriever, get_settings()).analyse(
            "time limit for an appeal")

        ids = {s.document_id for s in analysis.sources}
        assert len(ids) == 2, "both documents must appear in the source list"

    async def test_an_unrelated_corpus_produces_no_conflicts(self, make_corpus):
        store, retriever, _ = await make_corpus([
            ("a.txt", OLD_RULE, {"authority": "official",
                                 "rule_name": "Sample Licensing Rules"}),
            ("b.txt", UNRELATED, {"authority": "official",
                                  "rule_name": "Sample Water Rules"}),
        ])
        analysis = await Analyst(retriever, get_settings()).analyse("licence fee")

        assert analysis.conflicts == []
        assert analysis.warnings == []

    async def test_a_conflict_warning_reaches_the_officer_panel(self, make_corpus):
        from app.api.views import analysis_view

        store, retriever, _ = await make_corpus([
            ("a.txt", UNDATED_A, {"authority": "official",
                                  "rule_name": "Sample Procedure Circular"}),
            ("b.txt", UNDATED_B, {"authority": "official",
                                  "rule_name": "Sample Procedure Circular"}),
        ])
        analysis = await Analyst(retriever, get_settings()).analyse(
            "time limit for an appeal")

        view = analysis_view(analysis.model_dump(), "en")
        assert view["warnings"], "the panel must show what could not be resolved"


# --------------------------------------------------------------------------- #
# Provenance: official is earned, not asserted
# --------------------------------------------------------------------------- #

class TestProvenance:
    async def test_official_without_provenance_is_downgraded(self, tmp_path):
        store = KnowledgeStore(tmp_path / "p.sqlite", dimension=256, provider="local")
        ingestor = Ingestor(store=store, provider=LocalEmbeddings(dimension=256),
                            settings=get_settings())
        path = tmp_path / "claim.txt"
        path.write_text(OLD_RULE, encoding="utf-8")

        await ingestor.ingest(path, metadata={"authority": "official"})

        assert store.documents()[0]["authority"] == "unknown"
        assert store.stats()["official_documents"] == 0

    @pytest.mark.parametrize("evidence", [
        {"provenance": "Tamil Nadu Government Gazette, Part III, 12 June 2019"},
        {"source_url": "https://example.tn.gov.in/rules.pdf"},
        {"government_order_number": "145"},
    ])
    async def test_evidence_of_origin_earns_it(self, tmp_path, evidence):
        store = KnowledgeStore(tmp_path / "p.sqlite", dimension=256, provider="local")
        ingestor = Ingestor(store=store, provider=LocalEmbeddings(dimension=256),
                            settings=get_settings())
        path = tmp_path / "claim.txt"
        path.write_text(OLD_RULE, encoding="utf-8")

        await ingestor.ingest(path, metadata={"authority": "official", **evidence})

        assert store.documents()[0]["authority"] == "official"

    async def test_a_downgraded_document_is_still_searchable(self, tmp_path):
        """It stops outranking things. It does not stop existing."""
        store = KnowledgeStore(tmp_path / "p.sqlite", dimension=256, provider="local")
        provider = LocalEmbeddings(dimension=256)
        ingestor = Ingestor(store=store, provider=provider, settings=get_settings())
        path = tmp_path / "claim.txt"
        path.write_text(OLD_RULE, encoding="utf-8")
        await ingestor.ingest(path, metadata={"authority": "official"})

        found = await Retriever(store, provider, get_settings()).search("licence fee")
        assert found.chunks
        assert found.chunks[0].authority == "unknown"

    async def test_an_unofficial_document_cannot_make_anything_mandatory(self):
        """`required` is the one place a suggestion becomes an instruction."""
        from app.domain.attachments import required_from_analysis

        analysis = {
            "required_documents": [
                {"value": "Encumbrance certificate",
                 "sources": [{"authority": "unknown", "document_title": "A summary"}]},
                {"value": "Patta copy",
                 "sources": [{"authority": "external", "document_title": "A blog"}]},
            ]
        }
        assert required_from_analysis(analysis) == []

    async def test_an_official_source_can(self):
        from app.domain.attachments import required_from_analysis

        analysis = {
            "required_documents": [
                {"value": "Patta copy",
                 "sources": [{"authority": "official", "document_title": "TEST DATA Act",
                              "section": "Rule 3", "source_url": ""}]},
            ]
        }
        required = required_from_analysis(analysis)
        assert len(required) == 1
        assert required[0]["value"] == "Patta copy"
        assert "TEST DATA Act" in required[0]["source"]


# ---------------------------------------------------------------------------
# Operator-panel conflict reporting is REGISTRY-AWARE.
#
# THE INCIDENT behind these tests. The operator status page on 2026-10-22
# reported 2 "active conflicts" for 18 indexed documents. One group named
# the Tamil Nadu ULB Rules 2023 and all five of its declared amendments
# (G.O. 104, 162, 164, 433, 480) as "7 live documents cover the same
# instrument. None of them carries a date or version that establishes
# which is in force." That is wrong: the amendments ARE declared in
# `corpus/legal_relationships.yaml`, each with Gazette evidence, and the
# whole point of the relationships registry is to say which document
# modifies which. The other group named the TN Combined Development and
# Building Rules 2019 beside the TN Town and Country Planning Act 1971,
# because the Rules doc carries its parent Act's name in `act_name`
# metadata — picking Act name before Rule name grouped a Rules doc with
# an unrelated Act.
# ---------------------------------------------------------------------------


class TestTopicOfPrefersTheMoreSpecificField:
    def test_rule_name_wins_when_both_are_set(self):
        """A Rules doc that carries its parent Act's name in act_name is
        still a Rules doc. Grouping by Act name conflates the Rules with
        the Act they were made under."""
        from app.knowledge.conflicts import topic_of
        from app.knowledge.schema import Chunk
        chunk = Chunk(
            chunk_id="r", document_id="d", text="",
            document_title="Rules under the Act",
            rule_name="TN Combined Development and Building Rules, 2019",
            act_name="TN Town and Country Planning Act, 1971",
            authority="official",
        )
        topic = topic_of(chunk)
        assert topic is not None
        assert "building rules" in topic
        assert "planning act" not in topic


class TestCorpusConflictsAreRegistryAware:
    def test_an_amendment_chain_declared_in_the_registry_is_not_a_conflict(
            self, monkeypatch):
        """Mock the registry to declare three amendments of one root. The
        corpus-level conflict detector must not report the group as a
        conflict — that is the amendment chain working."""
        from app.knowledge import conflicts
        from app.knowledge import legal_status as ls

        class StubChange:
            def __init__(self, source, target):
                self.source = source
                self.target = target
                self.relation = "amends"

        class StubRegistry:
            instruments = {}
            changes = [
                StubChange("amend-104", "rules-2023"),
                StubChange("amend-162", "rules-2023"),
                StubChange("amend-164", "rules-2023"),
            ]

        monkeypatch.setattr(ls, "registry", lambda: StubRegistry())
        monkeypatch.setattr(ls, "manifest_ids_by_url", lambda: {
            "https://x/rules.pdf": "rules-2023",
            "https://x/amend-104.pdf": "amend-104",
            "https://x/amend-162.pdf": "amend-162",
            "https://x/amend-164.pdf": "amend-164",
        })
        monkeypatch.setattr(conflicts, "_manifest_ids_by_url",
                            ls.manifest_ids_by_url)

        docs = [
            {"document_id": "r1", "title": "Rules 2023", "date": "2023-07-11",
             "rule_name": "TN ULB Rules, 2023", "act_name": "", "superseded": 0,
             "source_url": "https://x/rules.pdf"},
            {"document_id": "a1", "title": "Amendment G.O. 104", "date": "2025-06-17",
             "rule_name": "TN ULB Rules, 2023", "act_name": "", "superseded": 0,
             "source_url": "https://x/amend-104.pdf"},
            {"document_id": "a2", "title": "Amendment G.O. 162", "date": "2024-11-06",
             "rule_name": "TN ULB Rules, 2023", "act_name": "", "superseded": 0,
             "source_url": "https://x/amend-162.pdf"},
            {"document_id": "a3", "title": "Amendment G.O. 164", "date": "2026-09-09",
             "rule_name": "TN ULB Rules, 2023", "act_name": "", "superseded": 0,
             "source_url": "https://x/amend-164.pdf"},
        ]
        assert conflicts.corpus_conflicts(docs) == []

    def test_two_undated_live_versions_with_no_declared_relationship_are_still_a_conflict(
            self, monkeypatch):
        """The registry filter must NOT swallow a genuine overlap. If two
        documents claim the same rule name but the registry does not
        declare a relationship between them, the operator panel should
        still see the conflict."""
        from app.knowledge import conflicts
        from app.knowledge import legal_status as ls

        class EmptyRegistry:
            instruments = {}
            changes: list = []

        monkeypatch.setattr(ls, "registry", lambda: EmptyRegistry())
        monkeypatch.setattr(ls, "manifest_ids_by_url", lambda: {})
        monkeypatch.setattr(conflicts, "_manifest_ids_by_url", lambda: {})

        docs = [
            {"document_id": "A", "title": "Fictional Rules, Draft I",
             "rule_name": "Fictional Rules", "superseded": 0,
             "source_url": "https://x/A.pdf"},
            {"document_id": "B", "title": "Fictional Rules, Draft II",
             "rule_name": "Fictional Rules", "superseded": 0,
             "source_url": "https://x/B.pdf"},
        ]
        result = conflicts.corpus_conflicts(docs)
        assert len(result) == 1
        assert result[0]["resolution"] == "undetermined"

    def test_two_docs_on_different_instruments_are_not_a_conflict(self):
        """A Rules doc + its parent Act, after the topic_of fix, go into
        different buckets. The operator panel should see zero conflicts.
        """
        from app.knowledge import conflicts
        docs = [
            {"document_id": "A", "title": "TN Combined Development and Building Rules, 2019",
             "rule_name": "TN Combined Development and Building Rules, 2019",
             "act_name": "TN Town and Country Planning Act, 1971",
             "superseded": 0, "source_url": "https://x/rules.pdf"},
            {"document_id": "B", "title": "TN Town and Country Planning Act, 1971",
             "rule_name": "", "act_name": "TN Town and Country Planning Act, 1971",
             "superseded": 0, "source_url": "https://x/act.pdf"},
        ]
        assert conflicts.corpus_conflicts(docs) == []
