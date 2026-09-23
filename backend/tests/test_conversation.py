"""End-to-end conversations through the real graph and a real checkpointer.

Every conversation here completes, produces a document and verifies it using
only the deterministic path. The model, when present, improves the opening
paragraph. It is never what makes the service work.
"""

from __future__ import annotations

from pathlib import Path

from app.domain import phrasing
from app.domain.templates import the_template
from app.services.render import extract_docx_text

# --------------------------------------------------------------------------- #
# The five questions
# --------------------------------------------------------------------------- #


class TestEnglishFlow:
    async def test_every_question_then_a_document(self, chat, answers):
        c = chat()

        await c.open()
        assert c.awaiting == "applicant_name"
        assert "name" in c.reply.lower()

        await c.say(answers["applicant_name"])
        assert c.awaiting == "age"

        await c.say(answers["age"])
        assert c.awaiting == "mobile"

        await c.say(answers["mobile"])
        assert c.awaiting == "address"

        await c.say(answers["address"])
        assert c.awaiting == "grievance"

        state = await c.say(answers["grievance"])
        # Everything is in, so the next thing is the attachment offer — not the
        # read-back and certainly not the document.
        assert state["status"] == "attachments"
        assert state["missing"] == []
        assert state.get("document") is None
        assert "attachment" in state["reply"].lower()

        state = await c.say("no, nothing to attach")
        assert state["status"] == "confirming"
        assert state.get("document") is None

        state = await c.say("yes")
        assert state["status"] == "ready", state.get("error")
        assert state["verification"]["ok"] is True
        assert state["verification"]["checked"] == len(answers)
        assert Path(state["document"]["docx"]).exists()

    async def test_the_read_back_shows_every_field(self, chat, answers):
        c = chat()
        await c.answer_all(answers)
        assert c.status == "confirming"
        # Every field the form declares, whatever they are — so adding or
        # removing one changes this test by changing the form.
        for spec in the_template().fields:
            assert spec.label_for("en") in c.reply, spec.name
        # In the printed form, so what is confirmed is what will appear.
        assert "+91 98765 43210" in c.reply

    async def test_the_read_back_has_no_identifier_to_show(self, chat, answers):
        """The Aadhaar was here, printed in its grouping for the citizen to
        check. The form no longer asks for one, so there is nothing to
        check and nothing to leave on a screen in a public office."""
        c = chat()
        await c.answer_all(answers)

        assert "Aadhaar" not in c.reply
        assert "ஆதார்" not in c.reply

    async def test_no_question_is_asked_twice(self, chat, answers):
        c = chat()
        await c.open()
        asked = []
        for value in answers.values():
            asked.append(c.awaiting)
            await c.say(value)
        assert asked == list(answers)


class TestTamilFlow:
    async def test_a_tamil_petition_completes(self, chat, tamil_answers):
        c = chat("ta")
        await c.answer_all(tamil_answers)
        state = await c.say("ஆம்")
        assert state["status"] == "ready", state.get("error")
        assert state["verification"]["ok"] is True

    async def test_a_tamil_opening_switches_the_session(self, chat):
        c = chat("en")
        state = await c.open("எனக்கு ஒரு மனு வேண்டும்")
        assert state["language"] == "ta"
        # The STEM. The question asks for "பெயரை" (accusative), and "பெயர்"
        # with its pulli is not a substring of it — Tamil inflects by suffix,
        # and an assertion on the citation form fails on a correct sentence.
        assert "பெயர" in state["reply"]

    async def test_validation_errors_come_back_in_tamil(self, chat):
        c = chat("ta")
        await c.open()
        await c.say("ரவி குமார்")
        state = await c.say("இருநூறு")   # not a number this service can read
        assert state["awaiting"] == "age"
        assert "வயத" in state["reply"]   # stem: Tamil inflects வயது / வயதை
        assert state["reply"] != phrasing.phrase("not_understood", "ta")

    async def test_the_petition_is_assembled_in_tamil_without_a_translator(
        self, chat, tamil_answers
    ):
        """Requirement: do not translate a finished document because a few
        hard-coded labels were left in English."""
        c = chat("ta")
        await c.answer_all(tamil_answers)
        state = await c.say("ஆம்")
        assert not any("translat" in w.lower() for w in state["warnings"]), state["warnings"]
        assert "அனுப்புநர்," in state["letter_text"]
        assert "பொருள்:" in state["letter_text"]
        assert "மதிப்பிற்குரிய ஐயா / அம்மா," in state["letter_text"]
        assert "From," not in state["letter_text"]


# --------------------------------------------------------------------------- #
# Validation, field by field
# --------------------------------------------------------------------------- #


async def _upto(chat, answers, field: str):
    """Answer everything before `field` and stop there."""
    c = chat()
    await c.open()
    for name, value in answers.items():
        if name == field:
            break
        await c.say(value)
    return c


class TestFieldValidation:
    async def test_a_correct_mobile_is_accepted(self, chat, answers):
        c = await _upto(chat, answers, "mobile")
        state = await c.say("9876543210")
        assert state["fields"]["mobile"] == "9876543210"
        assert state["awaiting"] == "address"

    async def test_a_short_mobile_is_rejected_with_the_count(self, chat, answers):
        """The count matters. "That is not a valid number" tells a citizen
        nothing; "10 digits, I heard 8" tells them what to do."""
        c = await _upto(chat, answers, "mobile")
        state = await c.say("98765 43")
        assert state["awaiting"] == "mobile"
        assert "10 digits" in state["reply"]
        assert "7" in state["reply"]
        assert "mobile" not in state["fields"], "a rejected value is never stored"

    async def test_a_long_mobile_is_rejected(self, chat, answers):
        c = await _upto(chat, answers, "mobile")
        state = await c.say("9876543210123")
        assert state["awaiting"] == "mobile"
        assert "10 digits" in state["reply"]

    async def test_an_impossible_prefix_is_caught_and_can_be_corrected(
        self, chat, answers
    ):
        """An Indian mobile number starts 6, 7, 8 or 9. The point of the test
        is the recovery: the citizen is told, and the next attempt lands."""
        c = await _upto(chat, answers, "mobile")
        state = await c.say("1234567890")
        assert state["awaiting"] == "mobile"
        assert "6, 7, 8" in state["reply"]

        state = await c.say("9876543210")
        assert state["fields"]["mobile"] == "9876543210"

    async def test_invalid_age_is_rejected(self, chat, answers):
        c = await _upto(chat, answers, "age")
        state = await c.say("200")
        assert state["awaiting"] == "age"
        assert "200" in state["reply"]
        assert "age" not in state["fields"]

        state = await c.say("45")
        assert state["fields"]["age"] == 45

    async def test_incomplete_address_is_rejected(self, chat, answers):
        c = await _upto(chat, answers, "address")
        state = await c.say("Coimbatore")
        assert state["awaiting"] == "address"
        assert "street" in state["reply"].lower()
        assert "address" not in state["fields"]

        state = await c.say(answers["address"])
        assert state["fields"]["address"] == answers["address"]

    async def test_three_consecutive_invalid_attempts(self, chat, answers):
        """The attempt counter has to climb, or the rephrase never triggers and
        a citizen whose accent defeats the recogniser hears the same sentence
        for ever."""
        c = await _upto(chat, answers, "mobile")
        for _ in range(3):
            state = await c.say("1234")
        assert state["attempts"]["mobile"] == 3
        assert state["awaiting"] == "mobile"
        assert "mobile" not in state["fields"]

        state = await c.say(answers["mobile"])
        assert state["fields"]["mobile"] == answers["mobile"]
        assert "mobile" not in state["attempts"], "the counter resets on success"


# --------------------------------------------------------------------------- #
# The grievance — never altered
# --------------------------------------------------------------------------- #


class TestGrievancePreserved:
    async def _petition(self, chat, answers, grievance: str) -> dict:
        c = chat()
        await c.answer_all({**answers, "grievance": grievance})
        return await c.say("yes")

    async def test_reproduced_word_for_word_in_the_document(self, chat, answers):
        state = await self._petition(chat, answers, answers["grievance"])
        produced = " ".join(extract_docx_text(Path(state["document"]["docx"])).split())
        assert " ".join(answers["grievance"].split()) in produced

    async def test_punctuation_and_numbers_survive(self, chat, answers):
        grievance = (
            'On 12/03/2026 I paid Rs. 1,500 (receipt no. 44/A-2026) to the office; '
            'no receipt was given. "Come tomorrow," they said - 4 times!'
        )
        state = await self._petition(chat, answers, grievance)
        assert state["fields"]["grievance"] == grievance
        produced = " ".join(extract_docx_text(Path(state["document"]["docx"])).split())
        assert " ".join(grievance.split()) in produced

    async def test_line_breaks_are_kept(self, chat, answers):
        """A citizen who set their complaint out in paragraphs has said
        something with that structure. Running the points together is an edit."""
        grievance = (
            "First, the street light has not worked since January.\n"
            "Second, the drain outside my house is blocked.\n\n"
            "I have complained twice and received no reply."
        )
        state = await self._petition(chat, answers, grievance)
        stored = state["fields"]["grievance"]
        assert stored.count("\n") >= 2
        assert "First, the street light" in stored
        assert "Second, the drain" in stored
        assert "I have complained twice" in stored

    async def test_a_trailing_full_stop_is_not_stripped(self, chat, answers):
        state = await self._petition(chat, answers, "The drain is blocked.")
        assert state["fields"]["grievance"] == "The drain is blocked."

    async def test_a_very_long_grievance_is_carried_whole(self, chat, answers):
        grievance = " ".join(
            f"Point {i}: the drain outside house number {i} has been blocked for months."
            for i in range(1, 60)
        )
        assert len(grievance) > 3000
        state = await self._petition(chat, answers, grievance)
        assert state["fields"]["grievance"] == grievance, "nothing is truncated"
        produced = " ".join(extract_docx_text(Path(state["document"]["docx"])).split())
        assert grievance[-80:] in produced, "including the end of it"

    async def test_an_over_long_grievance_is_refused_not_cut(self, chat, answers):
        """Silently dropping the end of a complaint is the one thing this system
        must never do, so over the limit is an error the citizen can act on."""
        c = await _upto(chat, answers, "grievance")
        state = await c.say("x " * 4000)
        assert state["awaiting"] == "grievance"
        assert "shorten" in state["reply"].lower()
        assert "grievance" not in state["fields"]

    async def test_a_tamil_grievance_is_reproduced_exactly(self, chat, tamil_answers):
        grievance = (
            "எனது வீட்டின் முன் உள்ள சாலையில் மூன்று மாதங்களாக குப்பை அகற்றப்படவில்லை. "
            "நான் இரண்டு முறை புகார் அளித்தேன்."
        )
        c = chat("ta")
        await c.answer_all({**tamil_answers, "grievance": grievance})
        state = await c.say("ஆம்")
        assert state["fields"]["grievance"] == grievance
        produced = " ".join(extract_docx_text(Path(state["document"]["docx"])).split())
        assert " ".join(grievance.split()) in produced


# --------------------------------------------------------------------------- #
# Confirmation and correction
# --------------------------------------------------------------------------- #


class TestConfirmation:
    async def test_yes_generates(self, chat, answers):
        c = chat()
        await c.answer_all(answers)
        state = await c.say("yes")
        assert state["status"] == "ready"

    async def test_no_asks_which_detail_rather_than_repeating(self, chat, answers):
        c = chat()
        await c.answer_all(answers)
        read_back = c.reply

        state = await c.say("no")
        assert state["status"] == "collecting"
        assert state["confirmed"] is False
        assert state["awaiting_correction"] is True
        assert state["reply"] != read_back, "the same list is not read back again"
        assert "which detail" in state["reply"].lower()
        # And the citizen is told what they may say.
        assert "Age" in state["reply"] and "Address" in state["reply"]
        assert state.get("document") is None

    async def test_naming_a_field_re_asks_only_that_field(self, chat, answers):
        c = chat()
        await c.answer_all(answers)
        await c.say("no")

        state = await c.say("the age is wrong")
        assert state["awaiting"] == "age"
        assert "age" not in state["fields"], "only that field was cleared"
        # Everything else stands.
        assert state["fields"]["applicant_name"] == answers["applicant_name"]
        assert state["fields"]["address"] == answers["address"]
        assert state["fields"]["grievance"] == answers["grievance"]

    async def test_the_corrected_value_is_validated_again(self, chat, answers):
        c = chat()
        await c.answer_all(answers)
        await c.say("no")
        await c.say("the age is wrong")

        state = await c.say("500")
        assert state["awaiting"] == "age", "a bad correction is rejected like any answer"
        assert "500" in state["reply"]

        state = await c.say("31")
        assert state["fields"]["age"] == 31
        assert state["status"] == "confirming", "and the read-back comes round again"
        assert "31" in state["reply"]

    async def test_no_and_the_field_in_one_breath(self, chat, answers):
        """"no, the address is wrong" is one turn, not two."""
        c = chat()
        await c.answer_all(answers)
        state = await c.say("no, the address is wrong")
        assert state["awaiting"] == "address"
        assert "address" not in state["fields"]

    async def test_the_correction_is_recorded_with_both_values(self, chat, answers):
        """An officer reading the file sees "45 -> 31", not "45 -> None". The
        entry is opened when the citizen asks to change the field and closed
        when the replacement arrives."""
        c = chat()
        await c.answer_all(answers)
        await c.say("no")
        state = await c.say("the age is wrong")
        open_entry = [e for e in state["corrections"] if e["field"] == "age"]
        assert open_entry and open_entry[0]["to"] is None, "opened, not yet closed"

        state = await c.say("31")
        entries = [e for e in state["corrections"] if e["field"] == "age"]
        assert len(entries) == 1, "one change, one entry"
        assert entries[0]["from"] == 45
        assert entries[0]["to"] == 31

    async def test_an_abandoned_correction_stays_visible(self, chat, answers):
        """A citizen who asks to change a field and then cancels leaves an open
        entry. That is worth seeing rather than tidying away."""
        c = chat()
        await c.answer_all(answers)
        await c.say("no")
        state = await c.say("the address is wrong")
        assert state["corrections"][-1] == {
            "field": "address", "from": answers["address"], "to": None,
            "at": state["corrections"][-1]["at"], "source": "citizen-request",
        }

    async def test_correcting_in_tamil(self, chat, tamil_answers):
        c = chat("ta")
        await c.answer_all(tamil_answers)
        await c.say("இல்லை")
        state = await c.say("வயது தவறு")
        assert state["awaiting"] == "age"
        state = await c.say("50")
        assert state["fields"]["age"] == 50
        assert state["status"] == "confirming"

    async def test_an_unrecognised_answer_re_lists_the_fields(self, chat, answers):
        c = chat()
        await c.answer_all(answers)
        await c.say("no")
        state = await c.say("something else entirely")
        assert state["awaiting_correction"] is True
        assert "which detail" in state["reply"].lower()

    async def test_the_whole_interview_is_never_restarted_by_a_rejection(
        self, chat, answers
    ):
        c = chat()
        await c.answer_all(answers)
        state = await c.say("no")
        assert len(state["fields"]) == len(answers), "every answer is still held"

    async def test_confirmation_is_required_before_any_document(self, chat, answers):
        c = chat()
        state = await c.answer_all(answers)
        assert state["status"] == "confirming"
        assert state.get("document") is None
        assert state.get("letter_text") is None


# --------------------------------------------------------------------------- #
# Cancel, restart, recovery
# --------------------------------------------------------------------------- #


class TestControl:
    async def test_cancel_midway_stops_and_produces_nothing(self, chat, answers):
        c = chat()
        await c.open()
        await c.say(answers["applicant_name"])
        await c.say(answers["age"])

        state = await c.say("cancel")
        assert state["status"] == "cancelled"
        assert state.get("document") is None

    async def test_input_after_cancellation_does_not_resume(self, chat):
        c = chat()
        await c.open()
        await c.say("cancel")
        state = await c.say("Ravi Kumar")
        assert state["status"] == "cancelled"
        assert "applicant_name" not in state["fields"]

    async def test_restart_clears_everything_and_continues(self, chat, answers):
        c = chat()
        await c.open()
        await c.say(answers["applicant_name"])
        await c.say(answers["age"])
        assert c.state["fields"]

        state = await c.say("start over")
        assert state["fields"] == {}
        assert state["corrections"] == []
        assert state["status"] == "collecting"

        state = await c.say("Meena")
        assert state["fields"]["applicant_name"] == "Meena"
        assert state["awaiting"] == "age"

    async def test_restart_after_cancellation_is_allowed(self, chat):
        c = chat()
        await c.open()
        await c.say("cancel")
        state = await c.say("start over")
        assert state["status"] == "collecting"

    async def test_a_new_session_is_independent(self, chat, answers):
        first = chat()
        await first.answer_all(answers)

        second = chat()
        state = await second.open()
        assert state["fields"] == {}
        assert state["awaiting"] == "applicant_name"


class TestRecovery:
    async def test_state_survives_between_invocations(self, graph, chat, answers):
        """A dropped connection costs nothing: every turn is its own invocation
        against a checkpoint, so the next one resumes from the record."""
        c = chat()
        await c.open()
        await c.say(answers["applicant_name"])
        await c.say(answers["age"])

        recovered = await graph.aget_state(c.config)
        assert recovered.values["fields"] == {"applicant_name": "Ravi Kumar", "age": 45}
        assert recovered.values["awaiting"] == "mobile"

    async def test_a_reconnecting_client_carries_on(self, graph, chat, answers):
        from tests.conftest import Conversation

        c = chat()
        await c.open()
        await c.say(answers["applicant_name"])
        await c.say(answers["age"])

        resumed = Conversation(graph)
        resumed.session_id, resumed.config = c.session_id, c.config
        state = await resumed.say(answers["mobile"])
        assert state["fields"]["applicant_name"] == answers["applicant_name"]
        assert state["awaiting"] == "address"


class TestPetitionTitle:
    """The name a petition is listed under, in the sidebar.

    Derived from the petition itself and computed on the server, so both
    languages come from one place and a stored name cannot drift from the
    document it belongs to.
    """

    def test_the_drafted_subject_is_preferred(self):
        from app.api.views import petition_title
        from app.graph.state import new_state

        state = new_state("s", "en")
        state["fields"] = {"grievance": "The street light has not worked."}
        state["composition"] = {"subject": "Non-functioning street light at Peelamedu"}

        assert petition_title(state, "en") == "Non-functioning street light at Peelamedu"

    def test_the_grievance_is_used_before_one_is_drafted(self):
        from app.api.views import petition_title
        from app.graph.state import new_state

        state = new_state("s", "en")
        state["fields"] = {"grievance": "The street light outside my house has not "
                                        "worked for three months."}

        title = petition_title(state, "en")
        assert title.startswith("The street light")
        assert len(title) <= 60

    def test_an_empty_petition_is_named_after_the_form(self):
        from app.api.views import petition_title
        from app.graph.state import new_state

        assert petition_title(new_state("s", "en"), "en") == "Citizen Petition"
        assert petition_title(new_state("s", "ta"), "ta") == "குடிமகன் மனு"

    def test_a_tamil_grievance_gives_a_tamil_title(self):
        from app.api.views import petition_title
        from app.graph.state import new_state

        state = new_state("s", "ta")
        state["fields"] = {"grievance": "எனது வீட்டின் முன் உள்ள தெருவிளக்கு "
                                        "மூன்று மாதங்களாக எரியவில்லை."}

        title = petition_title(state, "ta")
        assert "தெருவிளக்கு" in title
        assert "Citizen" not in title

    def test_it_never_spans_lines(self):
        from app.api.views import petition_title
        from app.graph.state import new_state

        state = new_state("s", "en")
        state["fields"] = {"grievance": "Line one.\nLine two.\nLine three is longer."}

        assert "\n" not in petition_title(state, "en")

    def test_a_long_title_ends_at_a_word(self):
        from app.api.views import _shorten

        cut = _shorten("The drainage channel behind the government school has been "
                       "blocked since the monsoon and overflows onto the road")
        assert cut.endswith("…")
        assert not cut[:-1].endswith(" ")
        assert len(cut) <= 60

    async def test_the_session_view_carries_it(self, chat, answers):
        citizen = chat()
        await citizen.answer_all(answers)

        from app.api.views import session_view

        view = session_view(citizen.state)
        assert view["title"]
        assert view["title"].startswith("The street light")

    async def test_a_petition_carries_no_citizen_identifier_in_its_title(
            self, chat, answers, valid_aadhaar):
        """The sidebar is a list of names on a screen anyone at the terminal can
        see. A name is enough; an identifier is not for a list."""
        from app.api.views import session_view

        citizen = chat()
        await citizen.answer_all(answers)
        title = session_view(citizen.state)["title"]

        assert valid_aadhaar not in title
        assert answers["mobile"] not in title
