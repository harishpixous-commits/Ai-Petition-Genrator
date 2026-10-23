"""Reading a finished petition in another language.

The feature is a convenience. The rule it must not break is that the citizen's
identity and complaint survive intact. Name and address display formatting may
change capitalization or script; translation must never rewrite them, and the
grievance is reproduced word for word. A translator has already been caught
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
from app.services import translate
from app.services import translate as translator

TAMIL_LINE = "வீதி விளக்கு மூன்று மாதங்களாக எரியவில்லை."
HINDI_LINE = "स्ट्रीट लाइट तीन महीने से काम नहीं कर रही है।"
GRIEVANCE = "The street light outside my house has not worked for three months."
NAME = "Ravi Kumar"
RAW_ADDRESS = "12 anna street, coimbatore"
ADDRESS = "12, Anna Street, Coimbatore"

LETTER = "\n".join([
    "Date: 22-10-2026",
    "Place: Coimbatore",
    "",
    "From,",
    f"    {NAME}",
    f"    {ADDRESS}",
    "    Age: 45",
    "    Mobile number: +91 98765 43210",
    "",
    "To,",
    "    The District Collector,",
    "    District Collectorate,",
    "    Coimbatore District, Tamil Nadu.",
    "",
    "Subject: Petition seeking redressal of a grievance",
    "",
    "Respected Sir / Madam,",
    "",
    GRIEVANCE,
    "",
    "I request that the necessary action be taken at the earliest.",
    "",
    "Thanking you,",
    "",
    "Yours faithfully,",
    "",
    "",
    f"(Signature) / {NAME}",
    "",
    "Enclosures: Nil",
    "",
    "Note: This petition was prepared based on the information provided by the petitioner. Please verify all details before signing or submitting it.",
])


def _id() -> str:
    return str(uuid.uuid4())


def _ready(session_id: str, text: str = LETTER) -> dict:
    return {
        **new_state(session_id, "en"),
        "fields": {"applicant_name": NAME, "age": 45, "mobile": "9876543210",
                   "aadhaar": "234567890124", "address": RAW_ADDRESS,
                   "grievance": GRIEVANCE},
        "status": "ready", "confirmed": True,
        # A genuinely finished session has settled its attachment step. Without
        # these the graph routes the edit back to `attach` and the petition is
        # not ready at the end of it — which is the graph working correctly.
        "attachments_offered": True, "attachments_done": True,
        "letter_text": text,
        "document": {"reference": "AP/2026/TEST001", "docx": "petition.docx",
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
    async def test_the_name_and_address_come_through_verbatim(
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
        assert NAME in letter, "the petitioner's name was translated"
        assert ADDRESS in letter, "the address was translated"
        # The grievance IS translated now, with the rest of the letter, so the
        # document reads as one language. The record still holds what the
        # citizen typed; this is about the page, not the evidence.
        assert GRIEVANCE not in letter, (
            "the grievance was left in its original language, so the petition "
            "is still a mixture")

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


# --------------------------------------------------------------------------- #
# Five languages
# --------------------------------------------------------------------------- #

# Real words, as escapes, so no encoding between here and the runner can
# quietly change what is being asserted.
_SAMPLES = {
    "ta": "\u0BAA\u0BC1\u0BA4\u0BBF\u0BAF \u0BAE\u0BA9\u0BC1",
    "ml": "\u0D2A\u0D41\u0D24\u0D3F\u0D2F \u0D2A\u0D30\u0D3E\u0D24\u0D3F",
    "te": "\u0C15\u0C4A\u0C24\u0C4D\u0C24 \u0C35\u0C3F\u0C28\u0C24\u0C3F",
    "hi": "\u0928\u0908 \u092A\u094D\u0930\u093E\u0930\u094D\u0925\u0928\u093E",
    "en": "a new petition",
}


class TestTheTranslatorKnowsFiveLanguages:
    def test_every_script_it_can_name_is_one_it_can_ask_for(self):
        """The invariant that keeps a document in the language it is already in.

        `language_of` feeds its answer straight to SARVAM_CODE. The moment
        script_of can return a code SARVAM_CODE has no entry for, that document
        is announced to the provider as en-IN and translated out of itself.
        """
        assert set(translate.SCRIPTS) == set(translate.SARVAM_CODE)
        for code, sample in _SAMPLES.items():
            assert translate.script_of(sample) == code
            assert translate.script_of(sample) in translate.SARVAM_CODE

    @pytest.mark.parametrize("code", ["ta", "ml", "te", "hi", "en"])
    def test_a_finished_document_is_not_sent_back_to_the_translator(self, code):
        """The infinite loop this group exists to prevent.

        Before Malayalam and Telugu were added to the script table, a finished
        Malayalam letter carried no script the translator recognised. It was
        saved only by `has_letters` returning False — remove that accident on
        its own and every line comes back "not yet Malayalam", for ever.
        """
        lines = [_SAMPLES[code], _SAMPLES[code]]
        assert translate.needs_translation(lines, code) is False

    @pytest.mark.parametrize("code", ["ta", "ml", "te", "hi"])
    def test_text_in_any_of_these_scripts_counts_as_translatable(self, code):
        assert translate.has_letters(_SAMPLES[code]) is True

    def test_something_with_no_language_is_still_left_alone(self):
        for noise in ("", "   ", "9344174752", "AP/2026/00a1b2", "12.09.2026"):
            assert translate.has_letters(noise) is False


class TestPinnedRepairsStayInTheirOwnLanguage:
    def test_tamil_still_has_its_repairs(self):
        assert len(translate.PINNED["ta"]) == 5

    @pytest.mark.parametrize("target", ["ml", "te", "hi"])
    def test_a_tamil_repair_never_reaches_another_language(self, target):
        """Every pinned replacement is a Tamil string.

        The old guard was `if target != "ta": return`. Reading that as "this
        gate is two-language, widen it" would splice Tamil words into a Hindi
        petition — a worse fault than the mistranslation it repairs.
        """
        source = "The certificate was issued in Coimbatore, Tamil Nadu."
        for term in translate.PINNED["ta"]:
            out = translate.apply_pinned(source, term.correct, target)
            assert out == term.correct, "a Tamil repair was applied to " + target

    @pytest.mark.parametrize("target", ["ml", "te", "hi"])
    def test_nothing_is_pinned_for_a_language_nobody_has_checked(self, target):
        assert translate.PINNED[target] == ()

    def test_every_language_the_translator_serves_has_an_entry(self):
        assert set(translate.PINNED) == set(translate.SARVAM_CODE) - {"en"}


class TestATranslationIsNeverMadeFromATranslation:
    """A citizen read their petition in four languages and got back a ruin.

    Each translation was made from whatever was on screen, so the fourth was a
    translation of a translation of a translation. Measured on a real petition:

        Place: theni              ->  Location: Honey
        From,                     ->  Since the beginning,
        "the supply of water has  ->  "with the water they have become
         become insufficient"          a mirage"

    Their town became another word and a structural label — one that
    `render.py` matches on to rebuild the document — became a sentence.
    """

    @staticmethod
    def _marking(tag):
        """A translator that marks every line it touches, so compounding shows.

        A line translated twice carries two marks. That is the whole fault,
        made countable.
        """
        async def translate(lines, target, settings=None, keep=frozenset(), source=None):
            structural_starts = (
                "Date:", "Place:", "From,", "To,", "Subject:", "Respected ",
                "Sir / Madam", "Thanking you", "Thank you", "Yours faithfully",
                "Yours sincerely", "Enclosures:", "Note:",
            )
            return translator.TranslationResult(
                lines=[line if (not line.strip() or line in keep or line.strip() in keep
                               or line.strip().startswith(structural_starts))
                       else f"{tag}{line}"
                       for line in lines],
                engine="test")
        return translate

    async def test_each_language_is_translated_from_the_original(
        self, api, workflow, monkeypatch,
    ):
        monkeypatch.setattr("app.api.rest.translate_lines", self._marking("<>"))
        session_id = _id()
        await _persist(workflow, session_id, _ready(session_id))

        letters = []
        for target in ("ta", "hi"):
            response = await api.post(f"/api/sessions/{session_id}/translate",
                                      json={"language": target})
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["status"] == "ready", payload.get("verification")
            letters.append(payload["letter_text"])

        for letter in letters:
            worst = max((line.count("<>") for line in letter.split("\n")), default=0)
            assert worst == 1, (
                f"a line was translated {worst} times — the second translation "
                f"was made from the first instead of from the original")

    async def test_going_back_returns_the_original_exactly(
        self, api, workflow, monkeypatch,
    ):
        """Reading a petition in another language and coming home is a VIEW.

        A citizen who returns to the language they approved should get the
        words they approved, to the character — not a translation of a
        translation that happens to be in the right language.
        """
        monkeypatch.setattr("app.api.rest.translate_lines", self._marking("<>"))
        session_id = _id()
        await _persist(workflow, session_id, _ready(session_id))

        before = (await api.get(f"/api/sessions/{session_id}")).json()["letter_text"]

        for target in ("ta", "hi", "ta"):
            response = await api.post(f"/api/sessions/{session_id}/translate",
                                      json={"language": target})
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "ready", response.json().get("verification")

        home = await api.post(f"/api/sessions/{session_id}/translate",
                              json={"language": "en"})
        assert home.status_code == 200, home.text
        after = home.json()["letter_text"]

        assert after.strip() == before.strip(), (
            "coming back to the original language did not return the original text")
        assert "<>" not in after, "the restored petition still carries translation marks"
