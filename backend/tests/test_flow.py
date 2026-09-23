"""The form, the missing-field arithmetic, field matching, and the router.

Together these are the "agentic loop", and none of them involves a model. If
they are right, the conversation is right.
"""

from __future__ import annotations

import pytest
from langgraph.graph import END

from app.domain.letter import verbatim_lines
from app.domain.templates import (
    load_templates,
    match_field,
    missing_fields,
    next_field,
    the_template,
    validate_extracted,
)
from app.graph.routing import route_after_compose, route_after_validate


class TestTheForm:
    def test_one_form_is_installed(self):
        assert [t.id for t in load_templates()] == ["petition"]

    def test_it_is_selected_without_asking(self):
        """With one form there is nothing to choose, so the citizen is never
        asked which document they want."""
        assert the_template().id == "petition"

    def test_the_fields_come_in_the_order_asked(self):
        """Who you are, how to reach you, where you live, then the grievance.

        The grievance is always last: it is the part the citizen came to say,
        and asking it after a run of short factual questions is what lets them
        settle into telling it.

        NO IDENTIFIER. The Aadhaar number was here and was removed — a
        petition asking an office to look at a blocked drain does not need a
        national identity number to do it.
        """
        assert the_template().field_names == (
            "applicant_name", "age", "mobile", "address", "grievance",
        )

    def test_the_form_asks_for_no_identifier_at_all(self):
        """The protections around one stay, because an Aadhaar can still
        arrive inside a grievance or on an attached card. What is gone is the
        step that asked a citizen to hand one over to file a complaint."""
        from app.domain.fields import SENSITIVE_TYPES

        asked = {f.type for f in the_template().fields}
        assert "aadhaar" not in asked
        assert not (asked & SENSITIVE_TYPES) - {"mobile"}, sorted(asked)

    def test_every_field_is_required(self):
        template = the_template()
        assert set(template.required_names) == set(template.field_names)

    def test_both_languages_for_every_prompt_and_label(self):
        for spec in the_template().fields:
            assert spec.prompt.get("en") and spec.prompt.get("ta"), spec.name
            assert spec.label.get("en") and spec.label.get("ta"), spec.name

    def test_the_office_and_subject_come_from_config(self):
        """Requirement: the format is replaceable without touching code."""
        template = the_template()
        assert template.text_for("addressee", "en")
        assert template.text_for("addressee", "ta")
        assert template.text_for("subject", "ta")
        assert template.enclosures_for("ta")


class TestMissingFields:
    def test_everything_is_missing_at_the_start(self):
        assert missing_fields(the_template(), {}) == list(the_template().field_names)

    def test_it_shrinks_as_values_arrive(self):
        assert missing_fields(the_template(), {"applicant_name": "Ravi", "age": 45}) == [
            "mobile", "address", "grievance",
        ]

    def test_nothing_missing_when_complete(self, answers):
        assert missing_fields(the_template(), {**answers, "age": 45}) == []

    def test_next_field_follows_template_order(self):
        assert next_field(the_template(), {}).name == "applicant_name"
        assert next_field(the_template(), {"applicant_name": "Ravi"}).name == "age"

    def test_next_field_is_none_when_complete(self, answers):
        assert next_field(the_template(), dict(answers)) is None


class TestMatchField:
    """Deterministic field naming — what makes the correction flow work offline."""

    def test_plain_english_names(self):
        template = the_template()
        assert match_field(template, "the address is wrong") == "address"
        assert match_field(template, "my age is wrong") == "age"
        assert match_field(template, "change my name") == "applicant_name"
        assert match_field(template, "my phone number is wrong") == "mobile"
        assert match_field(template, "I want to change the grievance") == "grievance"

    def test_tamil_names(self):
        template = the_template()
        assert match_field(template, "முகவரி தவறு", "ta") == "address"
        assert match_field(template, "என் வயது தவறு", "ta") == "age"
        assert match_field(template, "கைபேசி எண் தவறு", "ta") == "mobile"

    def test_aliases_are_matched(self):
        assert match_field(the_template(), "my phone number is wrong") == "mobile"
        assert match_field(the_template(), "the complaint is wrong") == "grievance"

    def test_a_bare_yes_or_no_names_nothing(self):
        """Critical: a plain "no" must fall through to the yes/no reading, not
        be taken as naming a field."""
        for utterance in ("no", "yes", "இல்லை", "ஆம்", "that is wrong"):
            assert match_field(the_template(), utterance) is None, utterance

    def test_longest_alias_wins(self):
        assert match_field(the_template(), "the mobile number is wrong") == "mobile"


class TestValidateExtracted:
    def test_accepts_good_values(self):
        accepted, rejected = validate_extracted(
            the_template(), {"applicant_name": "ravi kumar", "mobile": "9876543210"}
        )
        assert accepted == {"applicant_name": "Ravi Kumar", "mobile": "9876543210"}
        assert rejected == {}

    def test_separates_the_bad_ones(self):
        accepted, rejected = validate_extracted(
            the_template(), {"age": "45", "mobile": "1234"}
        )
        assert accepted == {"age": 45}
        assert rejected["mobile"].code == "mobile.length"

    def test_drops_fields_the_form_does_not_declare(self):
        """A model inventing `father_name` on a form that never asked for one
        must not be able to widen the record."""
        accepted, rejected = validate_extracted(
            the_template(), {"father_name": "Kumar", "age": "45"}
        )
        assert "father_name" not in accepted and "father_name" not in rejected


class TestRouteAfterValidate:
    BASE = {"missing": [], "field_errors": {}, "confirmed": False,
            "status": "collecting", "intent": "provide"}

    def test_missing_fields_go_to_ask(self):
        assert route_after_validate({**self.BASE, "missing": ["age"]}) == "ask"

    def test_errors_outrank_missing_fields(self):
        """The rejected value is the most recent thing that happened; asking
        about something else instead loses the citizen."""
        assert route_after_validate({
            **self.BASE, "missing": ["grievance"],
            "field_errors": {"aadhaar": {"code": "aadhaar.checksum"}},
        }) == "ask"

    def test_complete_but_unoffered_attachments_asks_about_them(self):
        """Every detail is in, and nobody has asked whether anything is
        enclosed. That question comes before the read-back."""
        assert route_after_validate(self.BASE) == "attach"

    def test_complete_but_unconfirmed_goes_to_confirm(self):
        assert route_after_validate(
            {**self.BASE, "attachments_done": True}) == "confirm"

    def test_confirmed_goes_to_compose(self):
        assert route_after_validate({
            **self.BASE, "attachments_done": True, "confirmed": True,
            "status": "generating", "intent": "confirm",
        }) == "compose"

    def test_the_attachment_step_never_outranks_a_rejected_value(self):
        """A detail that was just refused is the most recent thing that
        happened. Asking about attachments instead loses the citizen."""
        assert route_after_validate({
            **self.BASE, "field_errors": {"aadhaar": {"code": "aadhaar.checksum"}},
        }) == "ask"

    def test_a_question_never_advances_the_form(self):
        assert route_after_validate({**self.BASE, "intent": "question"}) == "ask"

    def test_a_rejection_asks_rather_than_repeating(self):
        assert route_after_validate({**self.BASE, "intent": "reject"}) == "ask"

    def test_terminal_states_stop(self):
        for status in ("cancelled", "ready", "failed"):
            assert route_after_validate({**self.BASE, "status": status}) == END

    def test_nothing_is_composed_before_confirmation(self):
        """The one invariant that must never be routed around."""
        assert route_after_validate(self.BASE) != "compose"


class TestRouteAfterCompose:
    def test_english_petition_in_an_english_session_skips_translation(self):
        assert route_after_compose({
            "language": "en", "letter_text": "To: The District Collector\nSub: Petition",
        }) == "render"

    def test_tamil_session_with_an_english_petition_translates(self):
        assert route_after_compose({
            "language": "ta", "letter_text": "To: The District Collector\nSub: Petition",
        }) == "translate"

    def test_tamil_petition_in_a_tamil_session_skips_translation(self):
        assert route_after_compose({
            "language": "ta", "letter_text": "பெறுநர்: மாவட்ட ஆட்சியர்\nபொருள்: மனு",
        }) == "render"

    def test_digits_and_dates_alone_never_trigger_translation(self):
        """A line with no letters has nothing to translate. Reference numbers,
        dates and identifiers must not drag a finished Tamil petition through a
        translator on their own account."""
        assert route_after_compose({
            "language": "ta", "letter_text": "15-03-2020\n2345 6789 0124\n45",
        }) == "render"

    def test_a_failed_compose_still_reaches_render(self):
        assert route_after_compose({"status": "failed", "language": "ta",
                                    "letter_text": "English text"}) == "render"


class TestTheVerbatimGrievanceNeverTriggersTranslation:
    """A citizen may write the complaint in either language, whatever language
    the rest of the petition is in. That is the document working correctly.

    Before this, a Tamil complaint inside an English petition made the finished,
    correct letter look like a half-translated one: it was routed to the
    translator, and with no translator configured the citizen was shown
    "no translation service was available" on a letter that needed none.

    The graver half is what happened when a translator WAS configured — it was
    handed the citizen's own words to reword, which is the one thing the
    petition rules forbid.
    """

    TAMIL_GRIEVANCE = "தெருவிளக்கு மூன்று மாதமாக எரியவில்லை."
    ENGLISH_GRIEVANCE = "The street light has not worked for three months."

    @staticmethod
    def _letter(*lines: str) -> str:
        return "\n".join(lines)

    def test_a_tamil_grievance_does_not_send_an_english_letter_to_the_translator(self):
        state = {
            "language": "en",
            "fields": {"grievance": self.TAMIL_GRIEVANCE},
            "letter_text": self._letter(
                "From,", "    Harish", "",
                "To,", "    The District Collector", "",
                "Respected Sir / Madam,", "",
                "Subject: Street light not working", "",
                "   I respectfully submit this petition for your consideration.", "",
                "   " + self.TAMIL_GRIEVANCE, "",
                "   I request you to arrange an inspection of the spot.",
            ),
        }
        assert route_after_compose(state) == "render"

    def test_an_english_grievance_does_not_send_a_tamil_letter_to_the_translator(self):
        state = {
            "language": "ta",
            "fields": {"grievance": self.ENGLISH_GRIEVANCE},
            "letter_text": self._letter(
                "அனுப்புநர்,", "    ஹரிஷ்", "",
                "பெறுநர்,", "    மாவட்ட ஆட்சியர்", "",
                "மதிப்பிற்குரிய ஐயா / அம்மா,", "",
                "பொருள்: தெருவிளக்கு தொடர்பாக.", "",
                "   தங்களிடம் இந்த மனுவை சமர்ப்பிக்கிறேன்.", "",
                "   " + self.ENGLISH_GRIEVANCE, "",
                "   உரிய நடவடிக்கை எடுக்குமாறு கேட்டுக்கொள்கிறேன்.",
            ),
        }
        assert route_after_compose(state) == "render"

    def test_a_genuinely_wrong_language_letter_still_translates(self):
        """The guard must not disable translation altogether: a Tamil session
        handed an English letter still needs one."""
        state = {
            "language": "ta",
            "fields": {"grievance": self.TAMIL_GRIEVANCE},
            "letter_text": self._letter(
                "To,", "    The District Collector", "",
                "Subject: Street light not working", "",
                "   I respectfully submit this petition for your consideration.", "",
                "   " + self.TAMIL_GRIEVANCE,
            ),
        }
        assert route_after_compose(state) == "translate"

    def test_an_english_name_does_not_send_a_tamil_letter_to_the_translator(self):
        """The case a live Tamil run actually hit. Every word of the petition
        was Tamil except the petitioner's own name and address, which they had
        typed in English — and that put "no translation service was available"
        on a letter that was completely correct."""
        state = {
            "language": "ta",
            "fields": {
                "applicant_name": "Harish",
                "address": "80/33 sidthaputhur, coimbatore",
                "grievance": self.TAMIL_GRIEVANCE,
            },
            "letter_text": self._letter(
                "அனுப்புநர்,", "    Harish", "    80/33 sidthaputhur, coimbatore", "",
                "பெறுநர்,", "    மாவட்ட ஆட்சியர் அவர்கள்", "",
                "மதிப்பிற்குரிய ஐயா / அம்மா,", "",
                "பொருள்: தெருவிளக்கு தொடர்பாக.", "",
                "   தங்களிடம் இந்த மனுவை சமர்ப்பிக்கிறேன்.", "",
                "   " + self.TAMIL_GRIEVANCE, "",
                "இப்படிக்கு,", "", "Harish",
            ),
        }
        assert route_after_compose(state) == "render"

    def test_the_protected_values_cover_every_shape_the_letter_prints_them_in(self):
        """The same value appears indented in the sender block, indented as a
        paragraph, and bare on the signature line. One stripped entry has to
        cover all three, because the callers compare both forms."""
        fields = {
            "applicant_name": "Harish",
            "address": "80/33 sidthaputhur, coimbatore",
            "grievance": "First paragraph.\n\nSecond paragraph.",
        }
        assert verbatim_lines(fields) == frozenset({
            "Harish",
            "80/33 sidthaputhur, coimbatore",
            "First paragraph.",
            "Second paragraph.",
        })

    def test_nothing_entered_protects_nothing(self):
        assert verbatim_lines({}) == frozenset()
        assert verbatim_lines({"grievance": "   "}) == frozenset()

    def test_our_own_wording_is_never_protected(self):
        """The guard must cover the citizen's text and nothing else — protecting
        a line we wrote would silently exempt it from translation."""
        protected = verbatim_lines({"applicant_name": "Harish", "grievance": "Light broken."})
        assert "The District Collector" not in protected
        assert "Respected Sir / Madam," not in protected
        assert "Thank you!" not in protected


class TestTheTranslatorIsNeverGivenTheCitizensWords:
    """The rule is that the grievance is reproduced exactly as entered. A
    translator is a rewording like any other, so even when a letter genuinely
    needs translating, those lines come back untouched."""

    def test_kept_lines_survive_a_translation_that_changed_everything(self):
        from app.services.translate import needs_translation

        original = ["To, The District Collector", "   The light is broken.", "Thank you!"]
        keep = frozenset({"   The light is broken."})
        # Every line needs translating except the protected one...
        assert needs_translation(original, "ta", keep) is True
        # ...and with it removed from consideration the rest still decides.
        assert needs_translation(["   The light is broken."], "ta", keep) is False


class TestAnAliasIsAWordNotASubstring:
    """`match_field` decided which field a citizen was correcting by testing
    whether an alias appeared anywhere in what they said. "age" appears inside
    "shortage", "village", "storage", "message" and "sewage" — so a citizen
    saying "there is a water shortage in my village" was understood to be
    correcting their AGE, and at the read-back that wiped an age they had
    already given."""

    @pytest.mark.parametrize("said", [
        "there is a water shortage in my village",
        "make the subject mention drinking water shortage",
        "the storage tank is damaged",
        "I sent a message to the office",
        "the sewage is overflowing",
        "the drainage has not been cleared",
        "our village panchayat did nothing",
    ])
    def test_a_word_that_merely_contains_an_alias_names_nothing(self, said):
        assert match_field(the_template(), said) is None, said

    @pytest.mark.parametrize("said,expected", [
        ("my age is wrong", "age"),
        ("change my address", "address"),
        ("my phone number is wrong", "mobile"),
        ("my contact number is incorrect", "mobile"),
        ("I want to change the grievance", "grievance"),
        ("my name is spelled wrong", "applicant_name"),
    ])
    def test_a_field_genuinely_named_is_still_matched(self, said, expected):
        assert match_field(the_template(), said) == expected

    @pytest.mark.parametrize("said,expected", [
        ("என் வயது தவறு", "age"),
        ("என் வயதை மாற்று", "age"),
        ("முகவரி தவறு", "address"),
        ("முகவரியை மாற்று", "address"),
        ("பெயரை திருத்து", "applicant_name"),
        ("கைபேசி எண்ணை மாற்று", "mobile"),
        ("கைபேசி எண்ணை மாற்று", "mobile"),
        ("குறையை மாற்ற வேண்டும்", "grievance"),
    ])
    def test_tamil_inflected_forms_are_matched(self, said, expected):
        """Tamil marks case by suffixing. "வயதை மாற்று" — change my age — does
        not begin with the base form "வயது" at all, so the base form alone
        misses most of the ways anyone actually says it in a sentence."""
        assert match_field(the_template(), said, "ta") == expected

    def test_a_bare_yes_or_no_still_names_nothing(self):
        for said in ("no", "yes", "இல்லை", "ஆம்", "that is wrong"):
            assert match_field(the_template(), said) is None, said
