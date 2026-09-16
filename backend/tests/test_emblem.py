"""Where the emblem goes, and who decides.

Layout has exactly one correct outcome per instruction: "move the logo to the
right" is right, not probably-right. So it is read from a table of words with no
model involved, and it never reaches the drafting call — moving an emblem must
not risk the wording of a petition coming back different.
"""

from __future__ import annotations

import pytest

from app.domain.emblem import (
    DEFAULT_ALIGN,
    DEFAULT_PAGES,
    Placement,
    describe,
    placement_for,
    read_instruction,
)
from app.graph.nodes import understand, validate
from tests.test_revision import ready_state


class TestTheDefault:
    def test_no_emblem_unless_it_is_asked_for(self):
        """A petition is the citizen's document, not the department's.

        Printing the state emblem on it unasked makes a private representation
        look like something the office issued. `DEFAULT_ALIGN` says where it
        goes when someone does ask for it.
        """
        assert DEFAULT_PAGES == "none"
        assert DEFAULT_ALIGN == "center"
        assert Placement().as_dict() == {"align": "center", "pages": "none"}

    def test_an_unreadable_stored_value_falls_back(self):
        """A session written by an older build, or a hand-edited checkpoint,
        must still render rather than raise."""
        for junk in (None, "left", {}, {"align": "sideways", "pages": "occasionally"}):
            assert Placement.from_state(junk).as_dict() == {"align": "center", "pages": "none"}

    def test_a_session_that_asked_for_it_still_gets_it(self):
        """Turning the default off must not discard a stored choice."""
        assert Placement.from_state({"align": "right", "pages": "all"}).as_dict() == {
            "align": "right", "pages": "all"}


class TestReadingAnInstruction:
    @pytest.mark.parametrize("said,align", [
        ("move the logo to the right", "right"),
        ("put the emblem on the left", "left"),
        ("centre the logo", "center"),
        ("center the seal please", "center"),
        ("சின்னத்தை வலதுபுறம் நகர்த்து", "right"),
        ("இலச்சினையை இடதுபுறம் வை", "left"),
    ])
    def test_position(self, said, align):
        assert read_instruction(said).align == align

    @pytest.mark.parametrize("said,pages", [
        ("show the logo on all pages", "all"),
        ("put the logo on the first page only", "first"),
        ("remove the logo from the second page", "first"),
        ("no logo on page 2", "first"),
        ("remove the logo", "none"),
        ("take the emblem off", "none"),
        ("சின்னம் முதல் பக்கம் மட்டும்", "first"),
        ("சின்னம் இரண்டாம் பக்கத்தில் வேண்டாம்", "first"),
        ("லோகோவை நீக்கு", "none"),
    ])
    def test_pages(self, said, pages):
        assert read_instruction(said).pages == pages

    def test_position_and_pages_together(self):
        got = read_instruction("logo on the right and on every page")
        assert got.as_dict() == {"align": "right", "pages": "all"}

    def test_it_builds_on_what_is_already_set(self):
        """Moving it left must not silently put it back on every page."""
        current = Placement(align="center", pages="first")
        assert read_instruction("move the logo left", current).pages == "first"

    @pytest.mark.parametrize("said", [
        "add the logo",
        "add the government logo at the top",
        "put the emblem on the petition",
        "I want the emblem",
        "include the seal",
        "show the logo",
        "சின்னத்தை சேர்க்கவும்",
        "லோகோ வேண்டும்",
    ])
    def test_asking_for_it_plainly_turns_it_on(self, said):
        """The emblem is off by default, so plain words have to switch it on.

        Without this, the only ways back would be naming a side or saying "all
        pages" — and "add the logo at the top" is how anyone would actually ask.
        """
        assert read_instruction(said, Placement()).pages == "all"

    @pytest.mark.parametrize("said", [
        "I don't want the logo shown",
        "remove the emblem please",
        "take the logo off",
        "no logo",
    ])
    def test_a_removal_is_not_read_as_a_request_to_add(self, said):
        """"I don't want the emblem SHOWN" contains a word from both lists."""
        assert read_instruction(said, Placement(pages="all")).pages == "none"

    def test_asking_for_it_somewhere_brings_it_back(self):
        """"Put it on the right" said to a petition with no emblem means the
        citizen wants one, not that they want one nowhere."""
        gone = Placement(align="center", pages="none")
        assert read_instruction("put the logo on the right", gone).pages == "all"

    @pytest.mark.parametrize("said", [
        "make the closing request firmer",
        "say more about the elderly residents",
        "move it to the right",            # names nothing; could be anything
        "my address is wrong",
        "the storage tank is on the right side of the street",
        "",
    ])
    def test_what_is_not_about_the_emblem_is_left_alone(self, said):
        """Most of what a citizen says after reading their petition is about
        the words. A layout parser that answered "maybe" to those would move
        the emblem every time somebody asked for a firmer paragraph."""
        assert read_instruction(said) is None, said

    def test_both_languages_are_described(self):
        for language in ("en", "ta"):
            for placement in (Placement("left", "all"), Placement("right", "first"),
                              Placement("center", "none")):
                assert describe(placement, language).strip()


class TestThroughTheGraph:
    async def test_an_instruction_is_understood_without_a_model(self):
        result = await understand(ready_state(utterance="move the logo to the right"))
        assert result["intent"] == "emblem"
        assert result["understood_by"] == "deterministic"
        assert result["_emblem"] == {"align": "right", "pages": "all"}

    async def test_it_is_read_before_the_yes_no_reading(self):
        """The bug this ordering exists for: "right" is one of the words that
        means YES, so "move the logo to the right" was read as a confirmation
        and did nothing at all — while every other emblem instruction worked,
        which is what made it look like a one-off."""
        from app.domain.fields import read_boolean

        assert read_boolean("move the logo to the right") is True
        result = await understand(ready_state(utterance="move the logo to the right"))
        assert result["intent"] == "emblem"

    async def test_the_wording_is_not_regenerated(self):
        """`letter_text` survives, so `compose` passes it through and the
        drafting call is never made. Moving an emblem must not risk the
        petition coming back worded differently."""
        state = ready_state(utterance="move the logo left", intent="emblem",
                            _emblem={"align": "left", "pages": "all"})
        result = await validate(state)
        assert result["status"] == "generating"
        assert "letter_text" not in result        # kept, not cleared
        assert result["emblem"] == {"align": "left", "pages": "all"}

    async def test_the_stale_document_is_cleared(self):
        state = ready_state(utterance="remove the logo", intent="emblem",
                            _emblem={"align": "center", "pages": "none"})
        result = await validate(state)
        assert result["document"] is None
        assert result["verification"] is None

    async def test_no_recorded_value_is_touched(self):
        state = ready_state(utterance="move the logo left", intent="emblem",
                            _emblem={"align": "left", "pages": "all"})
        result = await validate(state)
        assert "fields" not in result
        assert "corrections" not in result

    async def test_compose_makes_no_call_for_a_layout_change(self):
        import app.graph.nodes as nodes

        source = open(nodes.__file__, encoding="utf-8").read()
        assert 'if state.get("intent") == "emblem" and state.get("letter_text")' in source


class TestTheEditPanel:
    """The Edit box beside the downloads is the only text input a citizen has
    once the petition exists — the composer closes at `ready`.

    It posts to `/revise`, which used to force `intent: "revise"` and skip
    understanding entirely. An emblem instruction typed there went to the
    drafting model as an instruction about prose: the emblem did not move and
    the wording could come back different for no reason. It mattered more once
    the emblem became off-by-default, because "add the logo" is then the normal
    thing to type.
    """

    @pytest.fixture
    def api_workflow(self, graph):
        from app.graph.workflow import Workflow

        return Workflow(graph, None)

    @pytest.fixture
    async def api(self, api_workflow):
        import httpx
        from fastapi import FastAPI

        from app.api.rest import router

        app = FastAPI()
        app.include_router(router)
        app.state.workflow = api_workflow
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            yield client

    async def _ready(self, api, answers):
        state = (await api.post("/api/sessions", json={"language": "en"})).json()
        sid = state["session_id"]
        for name, value in answers.items():
            state = (await api.post(f"/api/sessions/{sid}/field",
                                    json={"name": name, "value": value})).json()
        # The attachment offer stands between the last detail and the read-back.
        if state["status"] == "attachments":
            state = (await api.post(
                f"/api/sessions/{sid}/attachments/done")).json()
        state = (await api.post(f"/api/sessions/{sid}/confirm")).json()
        assert state.get("status") == "ready", state
        return sid, state

    async def test_the_petition_starts_with_no_emblem(self, api, answers):
        _, state = await self._ready(api, answers)
        assert state["emblem"]["pages"] == "none"

    async def test_asking_for_it_in_the_edit_box_turns_it_on(self, api, answers):
        sid, state = await self._ready(api, answers)
        before = state["letter_text"]

        state = (await api.post(f"/api/sessions/{sid}/revise",
                                json={"instruction": "add the government logo at the top"})).json()

        assert state["emblem"] == {"align": "center", "pages": "all"}
        # A layout change must not rewrite the petition.
        assert state["letter_text"] == before
        assert "emblem" in state["reply"].lower()

    async def test_moving_and_removing_it_from_the_edit_box(self, api, answers):
        sid, _ = await self._ready(api, answers)
        await api.post(f"/api/sessions/{sid}/revise",
                       json={"instruction": "add the logo"})

        state = (await api.post(f"/api/sessions/{sid}/revise",
                                json={"instruction": "move the logo to the right"})).json()
        assert state["emblem"] == {"align": "right", "pages": "all"}

        state = (await api.post(f"/api/sessions/{sid}/revise",
                                json={"instruction": "remove the logo"})).json()
        assert state["emblem"]["pages"] == "none"

    async def test_a_wording_request_is_still_a_wording_request(self, api, answers):
        """The emblem check must not swallow ordinary revisions."""
        sid, _ = await self._ready(api, answers)

        state = (await api.post(
            f"/api/sessions/{sid}/revise",
            json={"instruction": "make the closing request firmer"})).json()

        assert state["emblem"]["pages"] == "none"
        assert state["revisions"] == ["make the closing request firmer"]


class TestTheDeploymentSetting:
    """LETTER_EMBLEM_PAGES has to actually do something.

    It did not. `letter_emblem_align` and `letter_emblem_pages` were declared in
    `config.py` and read by nothing at all — every placement came from the
    hard-coded module default. A `.env` carrying LETTER_EMBLEM_PAGES=all was
    therefore silently ignored, and so would LETTER_EMBLEM_PAGES=none have been.
    Settings that look like controls and are not are worse than no settings.
    """

    @staticmethod
    def _settings(**overrides):
        from app.config import Settings

        return Settings(**overrides)

    def test_the_configured_default_is_used_when_the_session_has_none(self):
        from app.domain.emblem import placement_for

        on = self._settings(letter_emblem_pages="all", letter_emblem_align="left")
        assert placement_for(None, on).as_dict() == {"align": "left", "pages": "all"}

        off = self._settings(letter_emblem_pages="none")
        assert placement_for(None, off).pages == "none"

    def test_the_shipped_default_prints_nothing(self):
        assert placement_for(None, self._settings()).pages == "none"

    def test_what_the_citizen_asked_for_beats_the_setting(self):
        """A department that prints the emblem on every petition must still
        honour a citizen who asked for it removed."""
        on = self._settings(letter_emblem_pages="all")
        assert placement_for({"align": "center", "pages": "none"}, on).pages == "none"
        assert placement_for({"align": "right", "pages": "first"}, on).as_dict() == {
            "align": "right", "pages": "first"}

    def test_a_nonsense_setting_falls_back_rather_than_raising(self):
        bad = self._settings(letter_emblem_pages="sometimes",
                             letter_emblem_align="sideways")
        assert placement_for(None, bad).as_dict() == {"align": "center", "pages": "none"}

    def test_no_settings_at_all_still_works(self):
        """`placement_for(stored)` with no settings is the module default."""
        assert placement_for(None).pages == "none"

    async def test_the_setting_reaches_the_rendered_document(self, monkeypatch, answers):
        """End to end: turn it on in settings, and the DOCX carries an image."""
        import zipfile

        from app.config import get_settings

        def images_in(state):
            with zipfile.ZipFile(state["document"]["docx"]) as archive:
                return [n for n in archive.namelist() if n.startswith("word/media/")]

        from langgraph.checkpoint.memory import InMemorySaver

        from app.graph.workflow import build_graph
        from tests.conftest import Conversation

        settings = get_settings()

        monkeypatch.setattr(settings, "letter_emblem_pages", "none")
        citizen = Conversation(build_graph().compile(checkpointer=InMemorySaver()))
        await citizen.answer_all(answers)
        off_state = await citizen.say("yes")
        assert images_in(off_state) == []

        monkeypatch.setattr(settings, "letter_emblem_pages", "all")
        citizen = Conversation(build_graph().compile(checkpointer=InMemorySaver()))
        await citizen.answer_all(answers)
        on_state = await citizen.say("yes")
        assert len(images_in(on_state)) == 1
