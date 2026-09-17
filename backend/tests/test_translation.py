"""Reading a finished petition in another language.

The feature is a convenience. The rule it must not break is not: the citizen's
own text — their name, their address, their grievance — is reproduced exactly
as entered, in whatever language they wrote it. A petition whose complaint has
been reworded is a different petition, and a translator has already been caught
turning Coimbatore into the name of a locality in Chennai. A document naming
the wrong town does not get acted on.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi import FastAPI

from app.api.rest import router
from app.graph.state import new_state
from app.graph.workflow import Workflow
from app.services import translate as translator

TAMIL_LINE = "வீதி விளக்கு மூன்று மாதங்களாக எரியவில்லை."
HINDI_LINE = "स्ट्रीट लाइट तीन महीने से काम नहीं कर रही है।"
GRIEVANCE = "The street light outside my house has not worked for three months."
NAME = "Ravi Kumar"
ADDRESS = "12 Anna Street, Coimbatore"

LETTER = "\n".join([
    "To",
    "    The District Collector",
    "    District Collectorate",
    "",
    "Subject: Petition seeking redressal of a grievance",
    "",
    "Respected Sir/Madam,",
    "",
    GRIEVANCE,
    "",
    "I request that the necessary action be taken at the earliest.",
    "",
    "Yours faithfully,",
    NAME,
    ADDRESS,
])


def _id() -> str:
    return str(uuid.uuid4())


def _ready(session_id: str, text: str = LETTER) -> dict:
    return {
        **new_state(session_id, "en"),
        "fields": {"applicant_name": NAME, "age": 45, "mobile": "9876543210",
                   "aadhaar": "234567890124", "address": ADDRESS,
                   "grievance": GRIEVANCE},
        "status": "ready", "confirmed": True,
        # A genuinely finished session has settled its attachment step. Without
        # these the graph routes the edit back to `attach` and the petition is
        # not ready at the end of it — which is the graph working correctly.
        "attachments_offered": True, "attachments_done": True,
        "letter_text": text,
        "document": {"reference": "PET-2026-0001", "docx": "petition.docx",
                     "generated_at": "2026-09-10T09:00:00+00:00", "version": 1},
        "document_version": 1,
        "verification": {"ok": True},
    }


@pytest.fixture
def workflow(graph):
    return Workflow(graph, None)


@pytest.fixture
async def api(workflow):
    app = FastAPI()
    app.include_router(router)
    app.state.workflow = workflow
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        yield client


async def _persist(workflow, session_id, patch):
    await workflow._compiled.aupdate_state(
        workflow.config(session_id), patch, as_node="verify")


class TestReadingTheDocumentsLanguage:
    """Which language a letter is in has to be answered from the letter."""

    @pytest.mark.parametrize("text,expected", [
        ("The District Collector", "en"),
        ("மாவட்ட ஆட்சியர்", "ta"),
        ("जिला कलेक्टर", "hi"),
        ("AP/2026/34B583", "en"),
        ("", "en"),
    ])
    def test_a_line_is_read_by_its_script(self, text, expected):
        assert translator.script_of(text) == expected

    def test_an_indic_script_wins_over_a_latin_word_inside_it(self):
        """A Tamil line routinely carries a place name or an initial in Latin.
        A genuinely English line carries no Tamil at all."""
        assert translator.script_of("மாவட்ட ஆட்சியர், Coimbatore") == "ta"
        assert translator.script_of("जिला कलेक्टर, Coimbatore") == "hi"

    def test_a_letter_is_read_by_weight_not_by_its_first_line(self):
        assert translator.language_of(LETTER.splitlines()) == "en"
        tamil_letter = [TAMIL_LINE] * 6
        assert translator.language_of(tamil_letter) == "ta"

    def test_a_tamil_grievance_does_not_make_an_english_letter_tamil(self):
        """This is the document working correctly, not a letter needing
        translation: a citizen may write their complaint in Tamil inside an
        English petition, and those are their words either way."""
        mixed = LETTER.replace(GRIEVANCE, TAMIL_LINE).splitlines()
        keep = frozenset({TAMIL_LINE})

        assert translator.language_of(mixed, keep) == "en"

    def test_every_offered_language_has_a_code_and_a_script(self):
        for language in ("en", "ta", "hi"):
            assert language in translator.SARVAM_CODE
            assert language in translator.SCRIPTS


class TestTheCitizensOwnWordsAreNeverTranslated:
    async def test_the_grievance_name_and_address_come_through_verbatim(
        self, api, workflow, monkeypatch,
    ):
        """The translator is replaced with one that mangles EVERYTHING, so the
        only thing keeping the citizen's text intact is the rule itself."""
        async def mangle(lines, target, settings=None, keep=frozenset(), source=None):
            return translator.TranslationResult(
                lines=[line if (line in keep or line.strip() in keep)
                       else (TAMIL_LINE if line.strip() else line)
                       for line in lines],
                engine="test")

        monkeypatch.setattr("app.api.rest.translate_lines", mangle)
        session_id = _id()
        await _persist(workflow, session_id, _ready(session_id))

        response = await api.post(f"/api/sessions/{session_id}/translate",
                                  json={"language": "ta"})

        assert response.status_code == 200, response.text
        letter = response.json()["letter_text"]
        assert GRIEVANCE in letter, "the grievance was translated"
        assert NAME in letter, "the petitioner's name was translated"
        assert ADDRESS in letter, "the address was translated"

    async def test_the_rest_of_the_letter_really_is_translated(
        self, api, workflow, monkeypatch,
    ):
        async def mangle(lines, target, settings=None, keep=frozenset(), source=None):
            return translator.TranslationResult(
                lines=[line if (line in keep or line.strip() in keep or not line.strip())
                       else TAMIL_LINE for line in lines],
                engine="test")

        monkeypatch.setattr("app.api.rest.translate_lines", mangle)
        session_id = _id()
        await _persist(workflow, session_id, _ready(session_id))

        letter = (await api.post(f"/api/sessions/{session_id}/translate",
                                 json={"language": "ta"})).json()["letter_text"]

        assert "The District Collector" not in letter, "nothing was translated at all"


class TestWhatTheEndpointRefuses:
    async def test_a_language_it_cannot_produce(self, api, workflow):
        session_id = _id()
        await _persist(workflow, session_id, _ready(session_id))
        for language in ("fr", "", "en-IN", "ta;hi"):
            response = await api.post(f"/api/sessions/{session_id}/translate",
                                      json={"language": language})
            assert response.status_code == 422, f"{language!r} was accepted"

    async def test_a_petition_that_does_not_exist_yet(self, api, workflow):
        session_id = _id()
        await _persist(workflow, session_id, new_state(session_id, "en"))

        response = await api.post(f"/api/sessions/{session_id}/translate",
                                  json={"language": "ta"})

        assert response.status_code == 409

    async def test_the_language_it_is_already_in_changes_nothing(
        self, api, workflow, monkeypatch,
    ):
        """No new version, no re-render, and the translator never called. A
        version history full of identical entries is a history nobody reads."""
        called = False

        async def never(*args, **kwargs):
            nonlocal called
            called = True
            raise AssertionError("the translator was called for a no-op")

        monkeypatch.setattr("app.api.rest.translate_lines", never)
        session_id = _id()
        await _persist(workflow, session_id, _ready(session_id))

        response = await api.post(f"/api/sessions/{session_id}/translate",
                                  json={"language": "en"})

        assert response.status_code == 200
        assert not called
        assert response.json()["letter_text"] == LETTER

    async def test_a_failed_translation_leaves_the_petition_alone(
        self, api, workflow, monkeypatch,
    ):
        """The citizen keeps the document they had. Half a translation, or a
        petition replaced by an error, is worse than no translation."""
        async def broken(*args, **kwargs):
            raise RuntimeError("no translation engine is available")

        monkeypatch.setattr("app.api.rest.translate_lines", broken)
        session_id = _id()
        await _persist(workflow, session_id, _ready(session_id))

        response = await api.post(f"/api/sessions/{session_id}/translate",
                                  json={"language": "hi"})

        assert response.status_code == 503
        kept = await workflow.snapshot(session_id)
        assert kept["letter_text"] == LETTER
        assert kept["document_version"] == 1, "a failed translation bumped the version"

    async def test_a_translator_that_returns_the_text_unchanged_is_a_failure(
        self, api, workflow, monkeypatch,
    ):
        """Silently handing back the English letter as though it were Hindi is
        the one outcome the citizen cannot detect for themselves."""
        async def useless(lines, target, settings=None, keep=frozenset(), source=None):
            return translator.TranslationResult(lines=list(lines), engine="test")

        monkeypatch.setattr("app.api.rest.translate_lines", useless)
        session_id = _id()
        await _persist(workflow, session_id, _ready(session_id))

        response = await api.post(f"/api/sessions/{session_id}/translate",
                                  json={"language": "hi"})

        assert response.status_code == 503


class TestTheGuardOnTheOutput:
    def test_a_translation_carrying_none_of_the_target_script_is_refused(self):
        """Generalised from a Tamil-only check. Hindi needs the same guard, and
        a target with no script check at all would have none."""
        assert translator.SCRIPTS["hi"].search(HINDI_LINE)
        assert not translator.SCRIPTS["hi"].search(GRIEVANCE)
        assert translator.SCRIPTS["ta"].search(TAMIL_LINE)


class TestTheHistorySaysWhatHappened:
    """A translation takes the same path a hand edit takes. It must not be
    recorded as one: a citizen reading "Manual edit" beside a Hindi petition
    would conclude they typed it themselves."""

    async def test_a_translation_is_recorded_as_a_translation(
        self, api, workflow, monkeypatch,
    ):
        async def into_tamil(lines, target, settings=None, keep=frozenset(), source=None):
            return translator.TranslationResult(
                lines=[line if (line in keep or line.strip() in keep or not line.strip())
                       else TAMIL_LINE for line in lines],
                engine="test")

        monkeypatch.setattr("app.api.rest.translate_lines", into_tamil)
        session_id = _id()
        await _persist(workflow, session_id, _ready(session_id))

        await api.post(f"/api/sessions/{session_id}/translate", json={"language": "ta"})
        history = (await api.get(f"/api/sessions/{session_id}/versions")).json()

        latest = history["versions"][-1]
        assert latest["source"] == "Translation", (
            f"a translation was filed as {latest['source']!r}")
        assert "Tamil" in (latest["summary"] or ""), latest["summary"]

    async def test_a_hand_edit_is_still_recorded_as_one(self, api, workflow):
        """The label is optional, and without it nothing changes."""
        session_id = _id()
        await _persist(workflow, session_id, _ready(session_id))

        await api.post(f"/api/sessions/{session_id}/document/text",
                       json={"text": LETTER + "\n\nI request an early inspection."})
        history = (await api.get(f"/api/sessions/{session_id}/versions")).json()

        assert history["versions"][-1]["source"] == "Manual"
