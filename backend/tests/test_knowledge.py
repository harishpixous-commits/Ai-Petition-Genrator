"""The government knowledge layer.

The tests that matter here are the negative ones. It is easy to build retrieval
that finds the right Act when the right Act is indexed; the reason this layer
needs a test suite is the other case — the grievance nobody has a document for,
the model that names a plausible statute, the corpus that is empty on the day of
the demonstration. Each of those has a test below, and each asserts silence.

Everything runs with no model and no network, as the rest of this suite does.
"""

from __future__ import annotations

import pytest

from app.knowledge.analyst import Analyst, grounded, plan_queries
from app.knowledge.embeddings import LocalEmbeddings
from app.knowledge.ingest import Ingestor, chunk_document, clean, detect_metadata, extract
from app.knowledge.retrieve import Retriever, keywords
from app.knowledge.schema import UNVERIFIED, Chunk, PetitionAnalysis
from app.knowledge.store import KnowledgeStore, document_id_for

# TEST DATA. A document may only be indexed as official when where it came from
# is on the record — see `_checked_authority`. These fixtures say plainly that
# they are fixtures; nothing here is a real gazette citation.
TEST_PROVENANCE = "TEST DATA — fixture, not a real government source"

ENCROACHMENT = """The Tamil Nadu Land Encroachment Act, 1905

Section 3. Liability of persons unauthorisedly occupying land.
Any person who occupies land which is the property of Government without lawful
authority shall be liable to pay assessment and penalty as determined by the
Tahsildar of the taluk in which the land is situated.

Section 5. Procedure for eviction.
The District Collector may, after issuing a notice in writing, order the
eviction of any person unauthorisedly occupying such land. An appeal against
the order lies to the Revenue Divisional Officer within thirty days.
"""

WATER = """Tamil Nadu Water Supply and Drainage Board Guidelines

## Complaints about drinking water supply
A complaint about interruption of drinking water supply shall be made to the
Assistant Engineer of the local section office. The complaint shall be
registered and an acknowledgement issued to the complainant.

## Escalation
Where the Assistant Engineer does not resolve the complaint, the matter shall
be escalated to the Executive Engineer of the division.
"""


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def store(tmp_path):
    return KnowledgeStore(tmp_path / "knowledge.sqlite", dimension=256, provider="local")


@pytest.fixture
def provider():
    return LocalEmbeddings(dimension=256)


@pytest.fixture
def ingestor(store, provider):
    from app.config import get_settings

    return Ingestor(store=store, provider=provider, settings=get_settings())


@pytest.fixture
async def corpus(tmp_path, store, ingestor):
    """A small, real corpus: one Act and one departmental guideline."""
    act = tmp_path / "encroachment-act.txt"
    act.write_text(ENCROACHMENT, encoding="utf-8")
    water = tmp_path / "water-guidelines.txt"
    water.write_text(WATER, encoding="utf-8")

    await ingestor.ingest(act, metadata={"authority": "official",
                                         "department": "Revenue Department",
                                         "document_type": "act",
                                         "provenance": TEST_PROVENANCE})
    await ingestor.ingest(water, metadata={"authority": "departmental",
                                           "document_type": "guideline",
                                           "provenance": TEST_PROVENANCE})
    return store


@pytest.fixture
def retriever(corpus, provider):
    from app.config import get_settings

    return Retriever(corpus, provider, get_settings())


# --------------------------------------------------------------------------- #
# 1. Ingestion
# --------------------------------------------------------------------------- #

class TestIngestion:
    async def test_a_document_is_indexed_with_its_sections(self, tmp_path, ingestor, store):
        path = tmp_path / "act.txt"
        path.write_text(ENCROACHMENT, encoding="utf-8")

        result = await ingestor.ingest(path, metadata={"authority": "official",
                                              "provenance": TEST_PROVENANCE})

        assert result.ok and result.chunks >= 2
        sections = [c["section"] for c in store.all_chunks()]
        assert any(s and "Section 3" in s for s in sections)
        assert any(s and "Section 5" in s for s in sections)

    async def test_ingesting_the_same_file_twice_does_not_duplicate_it(
            self, tmp_path, ingestor, store):
        path = tmp_path / "act.txt"
        path.write_text(ENCROACHMENT, encoding="utf-8")

        first = await ingestor.ingest(path)
        second = await ingestor.ingest(path)

        assert first.chunks > 0
        assert second.skipped and second.reason == "unchanged"
        assert store.stats()["documents"] == 1
        assert store.stats()["chunks"] == first.chunks

    async def test_an_updated_document_replaces_its_old_chunks(
            self, tmp_path, ingestor, store):
        path = tmp_path / "circular.txt"
        path.write_text("## Circular\nThe fee for a copy of the record is ten rupees.",
                        encoding="utf-8")
        await ingestor.ingest(path)

        path.write_text("## Circular\nThe fee for a copy of the record is twenty rupees.",
                        encoding="utf-8")
        await ingestor.ingest(path)

        assert store.stats()["documents"] == 1
        texts = " ".join(c["text"] for c in store.all_chunks())
        assert "twenty rupees" in texts
        # The superseded wording is gone, not sitting beside the new one where
        # retrieval could cite either.
        assert "ten rupees" not in texts

    async def test_a_deleted_document_stops_being_retrievable(
            self, corpus, provider, retriever):
        document_id = document_id_for_title(corpus, "Encroachment")
        assert corpus.delete(document_id)

        found = await retriever.search("encroachment government land eviction")

        assert all("Encroachment" not in c.document_title for c in found.chunks)
        assert corpus.stats()["documents"] == 1

    async def test_reindexing_keeps_the_text_and_the_citations(self, corpus, ingestor):
        before = {c["chunk_id"]: c["text"] for c in corpus.all_chunks()}

        await ingestor.reindex()

        after = {c["chunk_id"]: c["text"] for c in corpus.all_chunks()}
        assert before == after

    async def test_an_empty_file_is_refused_rather_than_indexed(self, tmp_path, ingestor):
        path = tmp_path / "scanned.txt"
        path.write_text("   \n\n  ", encoding="utf-8")

        result = await ingestor.ingest(path)

        assert not result.ok and "No text" in result.error

    def test_cleaning_repairs_what_pdf_extraction_breaks(self):
        raw = "The Dist-\nrict Collector may act.\n\n- 12 -\n\n______\n\nAn appeal lies."

        cleaned = clean(raw)

        assert "District Collector" in cleaned
        assert "- 12 -" not in cleaned
        assert "______" not in cleaned

    def test_metadata_is_read_off_the_document(self):
        found = detect_metadata(
            "G.O. (Ms) No. 145, Revenue and Disaster Management Department, "
            "dated 03.07.2021. Under the Tamil Nadu Land Encroachment Act, 1905 ...")

        assert found["government_order_number"] == "145"
        assert found["document_type"] == "government_order"
        # "the" is lowercase in the source, so it is not part of the name that
        # was read off the page. Detection reports what the document wrote.
        assert found["act_name"] == "Tamil Nadu Land Encroachment Act, 1905"
        assert "Department" in found["department"]
        assert found["date"] == "2021-07-03"

    def test_a_long_section_is_split_without_losing_text(self):
        body = "## Section 9\n" + ("The applicant shall submit the form. " * 200)
        chunks = chunk_document(_extracted(body), size=600, overlap=80, document_id="d")

        assert len(chunks) > 1
        assert all(len(c["text"]) <= 900 for c in chunks)
        assert all(c["section"] and "Section 9" in c["section"] for c in chunks)


# --------------------------------------------------------------------------- #
# 2. Retrieval
# --------------------------------------------------------------------------- #

class TestRetrieval:
    async def test_a_grievance_finds_the_relevant_section(self, retriever):
        found = await retriever.search(
            "someone has occupied government land next to my house and will not leave")

        assert not found.empty
        assert any("Encroachment" in c.document_title for c in found.chunks)

    async def test_an_unrelated_grievance_does_not_find_those_documents(self, retriever):
        found = await retriever.search(
            "my pension payment for the month of March has not been credited")

        titles = {c.document_title for c in found.chunks}
        assert "The Tamil Nadu Land Encroachment Act, 1905" not in titles

    async def test_retrieval_works_with_no_embedding_provider(self, corpus):
        from app.config import get_settings

        # The deployment with no key and no egress. The lexical half carries it.
        found = await Retriever(corpus, None, get_settings()).search(
            "drinking water supply complaint Assistant Engineer")

        assert not found.empty
        assert found.vector_hits == 0
        assert any("Water Supply" in c.document_title for c in found.chunks)

    async def test_a_superseded_document_is_not_returned_while_a_live_one_answers(
            self, tmp_path, ingestor, corpus, retriever):
        old = tmp_path / "old-circular.txt"
        old.write_text("## Drinking water complaints\nComplaints about drinking water "
                       "supply shall be made to the Block Development Officer.",
                       encoding="utf-8")
        result = await ingestor.ingest(
            old, metadata={"authority": "departmental",
                           "provenance": TEST_PROVENANCE})
        corpus.mark_superseded(result.document_id)

        found = await retriever.search("drinking water supply complaint")

        assert not found.empty
        assert not any(c.superseded for c in found.chunks)

    async def test_a_superseded_document_answers_when_nothing_live_does(
            self, tmp_path, ingestor, corpus, provider):
        from app.config import get_settings

        empty = KnowledgeStore(tmp_path / "only-old.sqlite", dimension=256,
                               provider="local")
        lone = Ingestor(store=empty, provider=provider, settings=get_settings())
        path = tmp_path / "repealed.txt"
        path.write_text("## Repealed provision\nThe licence fee for a pawnbroker was "
                        "fixed at fifty rupees under the former rules.", encoding="utf-8")
        result = await lone.ingest(
            path, metadata={"authority": "official",
                            "provenance": TEST_PROVENANCE})
        empty.mark_superseded(result.document_id)

        found = await Retriever(empty, provider, get_settings()).search(
            "pawnbroker licence fee")

        assert found.used_superseded
        assert all(c.superseded for c in found.chunks)

    def test_keywords_survive_tamil(self):
        # Tamil combining marks are not word characters; a `\\w+` tokeniser
        # shreds this into fragments and the query matches nothing.
        words = keywords("எனது வீட்டின் முன் உள்ள தெருவிளக்கு எரியவில்லை")

        assert "தெருவிளக்கு" in words
        assert "எரியவில்லை" in words

    def test_punctuation_in_a_grievance_cannot_break_the_search(self, corpus):
        # FTS5 reads a bare hyphen as NOT. A citizen writing "water - supply"
        # must not silently remove half the corpus from consideration.
        assert corpus.lexical('water - supply "drinking') is not None

    async def test_an_official_source_outranks_an_unofficial_one(
            self, tmp_path, ingestor, corpus, retriever):
        blog = tmp_path / "summary.txt"
        blog.write_text("## Land encroachment explained\nAny person who occupies land "
                        "which is the property of Government without lawful authority "
                        "may be evicted by the Collector.", encoding="utf-8")
        await ingestor.ingest(blog, metadata={"authority": "external"})

        found = await retriever.search(
            "person occupies land property of Government without lawful authority")

        assert found.chunks[0].authority in ("official", "departmental")


# --------------------------------------------------------------------------- #
# 3. Grounding — the tests this layer exists for
# --------------------------------------------------------------------------- #

class TestGrounding:
    @staticmethod
    def _chunk() -> Chunk:
        return Chunk(
            chunk_id="c1", document_id="d1", text=ENCROACHMENT,
            document_title="The Tamil Nadu Land Encroachment Act, 1905",
            act_name="The Tamil Nadu Land Encroachment Act, 1905",
            department="Revenue Department", authority="official")

    def test_a_real_act_is_accepted(self):
        assert grounded("The Tamil Nadu Land Encroachment Act, 1905",
                        [self._chunk()], strict=True)

    def test_an_invented_act_is_rejected(self):
        assert not grounded("The Tamil Nadu Public Grievance Redressal Act, 2019",
                            [self._chunk()], strict=True)

    def test_an_invented_government_order_is_rejected(self):
        assert not grounded("G.O. (Ms) No. 145", [self._chunk()], strict=True)

    def test_an_invented_authority_is_rejected(self):
        assert not grounded("Chief Vigilance Commissioner", [self._chunk()], strict=True)

    def test_a_faithful_paraphrase_is_accepted(self):
        assert grounded("The District Collector may order eviction of the occupant",
                        [self._chunk()], strict=False)

    def test_a_paraphrase_that_invents_a_body_is_rejected(self):
        assert not grounded("Appeal to the Tribunal within thirty days",
                            [self._chunk()], strict=False)

    def test_a_paraphrase_that_changes_a_deadline_is_rejected(self):
        # "ninety" is not a digit, so only the spelled-out-number guard catches
        # this. A wrong deadline on a government form costs a citizen their
        # appeal.
        assert not grounded("Appeal to the Revenue Divisional Officer within ninety days",
                            [self._chunk()], strict=False)
        assert not grounded("The Collector may order eviction after 45 days notice",
                            [self._chunk()], strict=False)

    def test_nothing_is_grounded_without_a_citation(self):
        assert not grounded("The Tamil Nadu Land Encroachment Act, 1905", [], strict=True)


# --------------------------------------------------------------------------- #
# 4. The analyst
# --------------------------------------------------------------------------- #

class TestAnalyst:
    async def test_it_reports_the_refusal_sentence_when_nothing_is_indexed(
            self, tmp_path, provider):
        from app.config import get_settings

        empty = KnowledgeStore(tmp_path / "empty.sqlite", dimension=256, provider="local")
        analyst = Analyst(Retriever(empty, provider, get_settings()), get_settings())

        analysis = await analyst.analyse("The street light outside my house does not work.")

        assert analysis.unverified
        assert analysis.message == UNVERIFIED
        assert not analysis.has_findings
        assert analysis.sources == []

    async def test_with_no_model_it_still_reports_what_the_documents_assert(
            self, retriever):
        # No LLM is configured in this suite. The metadata path is the fallback,
        # and it is grounded by construction: the Act name came off the document.
        analyst = Analyst(retriever)

        analysis = await analyst.analyse(
            "A man has occupied the government land beside my house and refuses to move.")

        assert not analysis.unverified
        assert [f.value for f in analysis.applicable_acts] == [
            "The Tamil Nadu Land Encroachment Act, 1905"]
        assert all(f.sources for f in analysis.applicable_acts)

    async def test_a_model_that_invents_an_act_has_it_removed(self, retriever, monkeypatch):
        async def hallucinate(**kwargs):
            return {
                "applicable_acts": [
                    {"value": "The Tamil Nadu Land Encroachment Act, 1905", "cites": [1]},
                    {"value": "The Tamil Nadu Public Grievance Act, 2019", "cites": [1]},
                ],
                "responsible_authority": {"value": "Chief Secretary", "cites": [1]},
                "government_orders": [{"value": "G.O. (Ms) No. 145", "cites": [1]}],
            }

        monkeypatch.setattr("app.knowledge.analyst.chat_json", hallucinate)
        analysis = await Analyst(retriever).analyse(
            "A man has occupied the government land beside my house.")

        values = [f.value for f in analysis.applicable_acts]
        assert "The Tamil Nadu Land Encroachment Act, 1905" in values
        assert "The Tamil Nadu Public Grievance Act, 2019" not in values
        assert analysis.responsible_authority is None
        assert analysis.government_orders == []

    async def test_a_finding_with_no_citation_is_dropped(self, retriever, monkeypatch):
        async def uncited(**kwargs):
            return {"applicable_acts": [
                {"value": "The Tamil Nadu Land Encroachment Act, 1905", "cites": []}]}

        monkeypatch.setattr("app.knowledge.analyst.chat_json", uncited)
        analysis = await Analyst(retriever).analyse(
            "A man has occupied the government land beside my house.")

        # It falls through to the metadata path, which cites; what it must never
        # do is return the uncited claim as given.
        assert all(f.sources for f in analysis.applicable_acts)

    async def test_the_search_loop_is_bounded(self, retriever, monkeypatch):
        calls = []

        async def always_wants_more(**kwargs):
            calls.append(kwargs)
            return {"need_search": ["more", "and more", "and more again"]}

        monkeypatch.setattr("app.knowledge.analyst.chat_json", always_wants_more)
        await Analyst(retriever).analyse(
            "A man has occupied the government land beside my house.")

        from app.config import get_settings
        assert len(calls) <= get_settings().knowledge_max_steps

    async def test_only_retrieved_excerpts_are_sent_never_a_whole_document(
            self, retriever, monkeypatch):
        seen = {}

        async def capture(**kwargs):
            seen.update(kwargs)
            return {}

        monkeypatch.setattr("app.knowledge.analyst.chat_json", capture)
        await Analyst(retriever).analyse("occupied government land beside my house")

        # The prompt carries numbered excerpts, and no more of them than the
        # context limit allows.
        from app.config import get_settings
        assert "EXCERPTS:" in seen["user"]
        assert seen["user"].count("\n[") <= get_settings().knowledge_context_chunks

    def test_query_planning_needs_no_model(self):
        queries = plan_queries(
            "There has been no drinking water in my street for three weeks.")

        assert queries and all(q.strip() for q in queries)
        assert any("water" in q for q in queries)


# --------------------------------------------------------------------------- #
# 5. Privacy
# --------------------------------------------------------------------------- #

class TestPrivacy:
    async def test_the_corpus_never_receives_citizen_text(self, graph, answers, corpus):
        """A whole petition, and the knowledge base is the size it started."""
        from tests.conftest import Conversation

        before = corpus.stats()
        citizen = Conversation(graph)
        await citizen.answer_all(answers)
        await citizen.say("yes")

        assert corpus.stats()["documents"] == before["documents"]
        assert corpus.stats()["chunks"] == before["chunks"]
        indexed = " ".join(c["text"] for c in corpus.all_chunks())
        assert answers["applicant_name"] not in indexed
        assert answers["mobile"] not in indexed
        assert answers["mobile"] not in indexed
        assert "street light" not in indexed.lower()

    async def test_an_aadhaar_inside_a_grievance_is_masked_before_it_is_sent(
            self, retriever, monkeypatch, valid_aadhaar):
        seen = {}

        async def capture(**kwargs):
            seen.update(kwargs)
            return {}

        monkeypatch.setattr("app.knowledge.analyst.chat_json", capture)
        await Analyst(retriever).analyse(
            f"My land is encroached. My Aadhaar number is {valid_aadhaar} "
            f"and my mobile is 9876543210.")

        assert valid_aadhaar not in seen["user"]
        assert "9876543210" not in seen["user"]

    async def test_embedding_a_query_masks_it_too(self, monkeypatch, valid_aadhaar):
        from app.config import Settings
        from app.knowledge.embeddings import GeminiEmbeddings

        sent = []

        class FakeResponse:
            status_code = 200

            @staticmethod
            def json():
                return {"embedding": {"values": [0.1, 0.2, 0.3]}}

        class FakeClient:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False

            async def post(self, url, headers=None, json=None):
                sent.append(json)
                return FakeResponse()

        monkeypatch.setattr("httpx.AsyncClient", lambda *a, **k: FakeClient())
        settings = Settings(gemini_api_keys="test-key", allow_external_ai=True)
        await GeminiEmbeddings(settings, dimension=3).embed(
            [f"my aadhaar is {valid_aadhaar}"])

        assert sent and valid_aadhaar not in str(sent[0])

    def test_the_analysis_cache_holds_no_citizen_text(self, answers):
        from app.knowledge.capability import KnowledgeService

        service = KnowledgeService()
        key = service._key(answers["grievance"], "")

        assert answers["grievance"] not in key
        assert len(key) == 64 and all(c in "0123456789abcdef" for c in key)


# --------------------------------------------------------------------------- #
# 6. It must not change the petition
# --------------------------------------------------------------------------- #

class TestPetitionIsUnchanged:
    async def test_a_petition_is_produced_when_the_corpus_is_empty(self, graph, answers):
        from tests.conftest import Conversation

        citizen = Conversation(graph)
        await citizen.answer_all(answers)
        state = await citizen.say("yes")

        assert state["status"] == "ready"
        assert state["verification"]["ok"]

    async def test_a_petition_is_produced_when_the_knowledge_layer_explodes(
            self, graph, answers, monkeypatch):
        from tests.conftest import Conversation

        async def explode(*a, **k):
            raise RuntimeError("the knowledge base is on fire")

        monkeypatch.setattr(
            "app.knowledge.capability.KnowledgeService.analyse", explode)
        citizen = Conversation(graph)
        await citizen.answer_all(answers)
        state = await citizen.say("yes")

        assert state["status"] == "ready"
        assert state["verification"]["ok"]

    async def test_no_finding_reaches_the_petition_text(
            self, graph, answers, corpus, monkeypatch):
        from tests.conftest import Conversation

        async def analysis(*a, **k):
            return PetitionAnalysis(
                applicable_acts=[__import__("app.knowledge.schema", fromlist=["Finding"])
                                 .Finding(value="The Tamil Nadu Land Encroachment Act, 1905")],
                unverified=False, message="")

        monkeypatch.setattr(
            "app.knowledge.capability.KnowledgeService.analyse", analysis)
        citizen = Conversation(graph)
        await citizen.answer_all(answers)
        state = await citizen.say("yes")

        assert state["status"] == "ready"
        # The petition says what the citizen said. A retrieval result, however
        # well cited, is not something the citizen said.
        assert "Encroachment Act" not in (state["letter_text"] or "")
        assert answers["grievance"] in (state["letter_text"] or "")

    async def test_the_grievance_is_still_verbatim(self, graph, answers, corpus):
        from tests.conftest import Conversation

        citizen = Conversation(graph)
        await citizen.answer_all(answers)
        state = await citizen.say("yes")

        assert answers["grievance"] in state["letter_text"]


# --------------------------------------------------------------------------- #
# 7. The view the officer sees
# --------------------------------------------------------------------------- #

class TestView:
    def test_an_absent_analysis_renders_nothing(self):
        from app.api.views import analysis_view

        assert analysis_view(None, "en") is None

    def test_findings_become_sections_with_numbered_citations(self):
        from app.api.views import analysis_view
        from app.knowledge.schema import Finding, Source

        source = Source(document_title="The Tamil Nadu Land Encroachment Act, 1905",
                        authority="official", section="Section 5", excerpt="...")
        view = analysis_view(
            PetitionAnalysis(
                applicable_acts=[Finding(value="The Tamil Nadu Land Encroachment Act, 1905",
                                         sources=[source])],
                responsible_authority=Finding(value="District Collector", sources=[source]),
                unverified=False, message="").model_dump(),
            "en")

        assert not view["unverified"]
        keys = [s["key"] for s in view["sections"]]
        assert "applicable_acts" in keys and "responsible_authority" in keys
        # One document, cited twice, listed once.
        assert len(view["sources"]) == 1
        assert all(item["cites"] == [1]
                   for section in view["sections"] for item in section["items"])

    def test_an_empty_analysis_carries_the_refusal_sentence(self):
        from app.api.views import analysis_view

        english = analysis_view(PetitionAnalysis().model_dump(), "en")
        tamil = analysis_view(PetitionAnalysis().model_dump(), "ta")

        assert english["unverified"] and english["message"] == UNVERIFIED
        assert english["sections"] == []
        assert tamil["message"] != english["message"] and tamil["message"]

    def test_the_panel_says_it_is_not_verified(self):
        from app.api.views import analysis_view

        view = analysis_view(PetitionAnalysis().model_dump(), "en")

        assert "verification" in view["note"].lower()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _extracted(text: str):
    from app.knowledge.ingest import Extracted, Page

    return Extracted(pages=[Page(number=1, text=text)])


def document_id_for_title(store: KnowledgeStore, fragment: str) -> str:
    for row in store.documents():
        if fragment.lower() in row["title"].lower():
            return row["document_id"]
    raise AssertionError(f"No indexed document matching {fragment!r}")


def test_document_id_is_stable_for_the_same_source():
    assert document_id_for("/var/docs/act.pdf") == document_id_for("/var/docs/act.pdf")
    assert document_id_for("/var/docs/act.pdf") != document_id_for("/var/docs/rules.pdf")


def test_no_knowledge_module_contains_a_stray_control_character():
    """A regex escape that became a control character, twice.

    `\\b` written through a shell heredoc has arrived in this repository as a
    literal backspace on two separate occasions. The pattern then matches
    nothing, silently — a guard that is switched off while every test around it
    still passes. This catches it at the file level, where it is visible.
    """
    import app.knowledge as package

    root = __import__("pathlib").Path(package.__file__).parent
    for path in sorted(root.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        stray = {hex(ord(c)) for c in text if ord(c) < 32 and c not in "\n\t"}
        assert not stray, f"{path.name} contains control characters: {sorted(stray)}"


def test_extract_refuses_a_file_type_it_cannot_read(tmp_path):
    path = tmp_path / "scan.tiff"
    path.write_bytes(b"\x00\x01")

    with pytest.raises(ValueError, match="Unsupported file type"):
        extract(path)


class TestALocalBodyDirectoryIsAFirstClassDocument:
    """A petition goes to a BODY, and which body depends on where somebody
    lives: a corporation, a municipality, a town panchayat or a village
    panchayat, each with a different officer.

    No list of them is shipped with this service and that is deliberate. Tamil
    Nadu has something over twelve thousand village panchayats; a list written
    from general knowledge would be wrong in ways nobody could check, and a
    confident wrong answer about which office to walk to is the exact failure
    this layer exists to prevent. The department ingests its own directory and
    every answer then carries a citation back to it.
    """

    def test_the_type_can_be_chosen_when_indexing(self):
        """Indexed as "other" it would rank beside a blog post."""
        import typing

        from app.knowledge.schema import DocumentType

        assert "local_body_directory" in typing.get_args(DocumentType)

    def test_the_command_line_offers_it(self):
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent / "scripts" / "ingest.py"
        source = path.read_text(encoding="utf-8")
        assert "local_body_directory" in source, (
            "a type the schema accepts but the CLI cannot pass is unreachable")

    async def test_a_directory_is_indexed_and_found(self, tmp_path, ingestor, retriever):
        directory = tmp_path / "ulb-directory.md"
        directory.write_text(
            "## Local bodies, Theni District\n\n"
            "Theni Allinagaram Municipality covers the Theni and Allinagaram "
            "town areas. The Commissioner, Theni Allinagaram Municipality is "
            "the officer for grievances arising within those limits.\n\n"
            "Bodinayakanur Municipality covers the Bodinayakanur town area.\n",
            encoding="utf-8")
        result = await ingestor.ingest(
            directory,
            metadata={"document_type": "local_body_directory",
                      "authority": "official", "provenance": TEST_PROVENANCE})
        assert result.document_id

        found = await retriever.search("which body covers Theni town")
        assert not found.empty
        assert any("Theni" in c.text for c in found.chunks)


class TestJurisdictionCannotBeInvented:
    """The same bar as an Act or a Government Order number.

    A guessed department wastes a journey to the wrong counter. A guessed
    local body wastes it in a different town.
    """

    @staticmethod
    def _chunk() -> Chunk:
        return Chunk(
            chunk_id="c9", document_id="d9",
            text=("Theni Allinagaram Municipality covers the Theni and "
                  "Allinagaram town areas. The Commissioner is the officer "
                  "for grievances arising within those limits."),
            document_title="Local bodies, Theni District",
            document_type="local_body_directory", authority="official")

    def test_it_is_checked_strictly(self):
        from app.knowledge.analyst import _STRICT_FIELDS

        assert "jurisdiction" in _STRICT_FIELDS, (
            "a jurisdiction checked by overlap could be paraphrased into "
            "another town")

    def test_a_body_the_directory_names_is_accepted(self):
        assert grounded("Theni Allinagaram Municipality", [self._chunk()], strict=True)

    def test_a_body_it_does_not_name_is_rejected(self):
        assert not grounded("Periyakulam Municipality", [self._chunk()], strict=True)
        assert not grounded("Theni Village Panchayat", [self._chunk()], strict=True)

    def test_the_model_is_asked_for_it(self):
        from app.knowledge.analyst import _SCHEMA

        assert "jurisdiction" in _SCHEMA["properties"]

    def test_the_officer_sees_it_only_when_it_is_grounded(self):
        from app.api.officer import grounded as officer_grounded

        source = {"document_title": "Local bodies, Theni District",
                  "excerpt": "Theni Allinagaram Municipality covers...",
                  "authority": "official"}
        kept = officer_grounded({"jurisdiction": {"value": "Theni Allinagaram Municipality",
                                                  "sources": [source]}})
        assert kept.get("jurisdiction", {}).get("value") == "Theni Allinagaram Municipality"

        dropped = officer_grounded({"jurisdiction": {"value": "Somewhere Else",
                                                     "sources": []}})
        assert not dropped.get("jurisdiction")


# --------------------------------------------------------------------------- #
# Queries in the five languages the service serves
# --------------------------------------------------------------------------- #

_GRIEVANCES = {
    "en": "water supply interrupted for several days in my street",
    "ta": "எங்கள் தெருவில் குடிநீர் விநியோகம் பல நாட்களாக தடைபட்டுள்ளது",
    "ml": "ഞങ്ങളുടെ തെരുവിൽ കുടിവെള്ള വിതരണം മുടങ്ങി",
    "te": "మా వీధిలో తాగునీటి సరఫరా ఆగిపోయింది",
    "hi": "हमारी गली में पेयजल आपूर्ति कई दिनों से बाधित है",
}


def _semantic_embedder():
    """A real multilingual embedder, or None when this run has not opted in.

    The suite runs with no egress at all (`conftest.py` sets ALLOW_EXTERNAL_AI
    false), because a department machine with no outbound network is the
    deployment this service has to survive. Cross-language retrieval is the one
    property that cannot be shown that way: matching a Malayalam grievance to an
    English Act needs an embedder that understands both, and the hashed bag of
    words used everywhere else understands nothing, by design.

    So reaching the network is OPT-IN and SCOPED. Setting
    PETITION_LIVE_EMBEDDINGS=1 with a Gemini key makes these four tests — and
    nothing else in the suite — talk to an embedding endpoint. The global flag
    is deliberately left alone: flipping it would let every other test reach the
    network too, which is the opposite of what conftest is for.
    """
    import os

    if os.environ.get("PETITION_LIVE_EMBEDDINGS") != "1":
        return None

    from app.config import get_settings
    from app.knowledge.embeddings import GeminiEmbeddings

    settings = get_settings()
    if not settings.gemini_key_list:
        return None
    return GeminiEmbeddings(settings,
                            dimension=settings.knowledge_embedding_dimension)


@pytest.fixture
async def semantic_corpus(tmp_path):
    """The same two documents, embedded by the provider that will query them.

    THIS IS A SEPARATE CORPUS ON PURPOSE. The ordinary `corpus` fixture embeds
    with LocalEmbeddings at 256 dimensions; a Gemini query vector has 1536.
    Pointing a semantic query at that corpus compares two unrelated coordinate
    spaces, so what a cross-language test needs is a different corpus, not the
    same one asked a different question.
    """
    from app.config import get_settings

    provider = _semantic_embedder()
    if provider is None:
        pytest.skip(
            "no semantic embedder — set PETITION_LIVE_EMBEDDINGS=1 with a "
            "Gemini key to run this. A hashed bag of words cannot match across "
            "languages, and asserting that it does would be asserting a lie.")

    act = tmp_path / "encroachment-act.txt"
    act.write_text(ENCROACHMENT, encoding="utf-8")
    water = tmp_path / "water-guidelines.txt"
    water.write_text(WATER, encoding="utf-8")

    store = KnowledgeStore(tmp_path / "semantic.sqlite",
                           dimension=provider.dimension, provider=provider.name)
    ingestor = Ingestor(store=store, provider=provider, settings=get_settings())
    await ingestor.ingest(act, metadata={"authority": "official",
                                         "department": "Revenue Department",
                                         "document_type": "act",
                                         "provenance": TEST_PROVENANCE})
    await ingestor.ingest(water, metadata={"authority": "departmental",
                                           "document_type": "guideline",
                                           "provenance": TEST_PROVENANCE})
    return store, provider


class TestAQueryInAnyLanguage:
    """A citizen writes their grievance in their own language; the corpus is
    whatever the department has indexed, which is mostly English.

    WHAT CAN AND CANNOT BE TESTED OFFLINE. Matching a Malayalam grievance to an
    English Act needs an embedder that understands both, and the fixture here
    uses LocalEmbeddings — a hashed bag of words with no semantics at all, by
    design, so the suite needs no key and no network. A Malayalam query shares
    no tokens with an English passage, so under that fixture it CANNOT match
    and a test asserting it would be asserting a lie.

    So this is split. The first two run always and hold the properties that do
    not need semantics. The third holds the real behaviour and runs against a
    real embedder whenever PETITION_LIVE_EMBEDDINGS=1 — which is what CI does
    wherever the key secret exists, and what a deployment always has.
    """

    @pytest.mark.parametrize("language", sorted(_GRIEVANCES))
    def test_the_words_survive_being_pulled_out_of_the_grievance(self, language):
        r"""`keywords()` splits on separators rather than on word characters,
        because Python's \w drops Indic combining marks and would hand the
        search a mutilated query."""
        from app.knowledge.retrieve import keywords

        words = keywords(_GRIEVANCES[language])
        assert words, f"{language}: nothing survived"
        joined = "".join(words)
        for mark in ("\u0BCD", "\u0D4D", "\u0C4D", "\u094D"):
            if mark in _GRIEVANCES[language]:
                assert mark in joined, f"{language}: a virama was dropped"

    @pytest.mark.parametrize("language", sorted(_GRIEVANCES))
    async def test_a_query_in_any_script_is_handled_without_error(
            self, retriever, language):
        """The lexical half cannot match across languages and is not expected
        to. What must not happen is a crash, or a query that reaches the
        database malformed."""
        found = await retriever.search(_GRIEVANCES[language])
        assert found is not None
        assert found.query

    @pytest.mark.parametrize("language", ["ta", "ml", "te", "hi"])
    async def test_a_grievance_finds_an_english_document(
            self, semantic_corpus, language):
        """THE REAL PROPERTY, and the one a deployment depends on.

        A citizen complains about drinking water in Tamil, Malayalam, Telugu or
        Hindi; the only document the department has indexed is an English one.
        The right passage has to come back anyway, or the analysis panel is
        empty for four of the five languages this service offers.

        Note what is NOT asserted: a ranking, a score, or a number of chunks.
        The property is that the correct document is reached — the water
        guidelines rather than the encroachment Act — which is what makes the
        difference between a useful panel and a misleading one.
        """
        from app.config import get_settings

        store, provider = semantic_corpus
        found = await Retriever(store, provider, get_settings()).search(
            _GRIEVANCES[language])
        assert not found.empty, f"{language}: found nothing in an English corpus"
        assert any("Water Supply" in c.document_title for c in found.chunks), (
            f"{language}: retrieved something, but not the water document")
