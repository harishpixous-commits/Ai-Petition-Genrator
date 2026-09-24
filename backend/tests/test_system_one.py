"""System-1: four typed decisions, and the defects that shaped them.

EVERY TEST IN THE FIRST SECTION IS A REGRESSION. None of them was written
from imagination — each one is a case that the benchmark sets caught wrong,
diagnosed, and that the tables or the matcher were changed for. They are here
so the same mistake cannot come back quietly.

THE FOUR TASKS, and what each is allowed to do:

    classify_grievance                 a CANDIDATE category, for RAG to verify
    classify_attachment_relationship   whose document this is
    classify_attachment_relevance      whether it bears on the complaint
    needs_review                       whether a human should look

Not one of them writes anything. They return a Decision and the workflow
decides — which is the whole reason a classification cannot overwrite a
citizen's name, the bug this layer was built after.
"""

from __future__ import annotations

import pytest

from app.services import system_one
from app.services.system_one import UNKNOWN, DeterministicProvider, SystemOneEngine


@pytest.fixture
def provider():
    return DeterministicProvider()


def category(provider, text, language="en"):
    return provider.classify_grievance(grievance=text, language=language).value


# ---------------------------------------------------------------------------
# Regressions: every one of these was measured wrong first
# ---------------------------------------------------------------------------

class TestTheMatcherReadsEachScriptByItsOwnRules:

    def test_a_latin_word_is_not_found_inside_a_longer_word(self, provider):
        """"ration" sits inside "corporation", and substring matching found
        it there — so a rubbish complaint against the corporation was
        classified as a welfare scheme. Half the petitions in this state
        name a corporation."""
        assert category(provider, "The corporation has not lifted the rubbish.") \
            == "SANITATION"

    def test_but_the_word_itself_still_matches(self, provider):
        """The fix must not cost the real word."""
        assert category(provider, "Our ration card has not been renewed.") == "WELFARE"

    @pytest.mark.parametrize("text,want", [
        ("குடிநீரும் வரவில்லை தண்ணீரும் இல்லை", "WATER"),
        ("குப்பையை அகற்றவில்லை.", "SANITATION"),
        ("ஓய்வூதியத்தை நிறுத்திவிட்டார்கள்.", "PENSION"),
        ("மின்சாரத்தை துண்டித்துவிட்டனர்.", "ELECTRICITY"),
    ])
    def test_an_inflected_tamil_noun_is_still_the_noun(self, provider, text, want):
        """A Tamil suffix REPLACES the virama rather than following it, so
        குடிநீர் does not occur as a substring of குடிநீரும். The word for
        drinking water went unmatched in a sentence about drinking water,
        and the sentence was then classified from whatever else was in it."""
        assert category(provider, text, "ta") == want

    def test_the_word_boundary_is_a_real_one(self):
        """This exact escape was corrupted once, by a shell heredoc, into a
        literal backspace character. The module still imported, every Latin
        word silently stopped matching, and four benchmark sets collapsed at
        the same moment. The value is asserted rather than trusted."""
        assert system_one._BOUNDARY == "\\b"
        assert not any(ord(c) < 32 for c in system_one._BOUNDARY)


class TestWhereItHappenedIsNotWhatIsWrong:

    @pytest.mark.parametrize("text,want", [
        ("There is no drinking water supply in our street.", "WATER"),
        ("The street light outside my house has not worked.", "STREET_LIGHT"),
        ("எங்கள் தெருவில் மூன்று நாட்களாக குடிநீர் வரவில்லை.", "WATER"),
        ("எங்கள் தெருவில் குப்பை அள்ளப்படவில்லை.", "SANITATION"),
    ])
    def test_street_is_where_they_live(self, provider, text, want):
        """Almost every grievance in Tamil Nadu contains the word for
        street. Read as a road complaint it tied with water on water and
        with street light on lighting — three benchmark cases at once."""
        language = "ta" if any("஀" <= c <= "௿" for c in text) else "en"
        assert category(provider, text, language) == want

    def test_a_weak_word_loses_to_a_real_subject(self, provider):
        """"Sewage is overflowing onto the main road" is a sanitation
        complaint that happens to contain the word road."""
        assert category(provider, "Sewage is overflowing onto the main road.") \
            == "SANITATION"

    def test_but_still_classifies_when_it_is_all_there_is(self, provider):
        """Weak is not ignored. A complaint whose only noun is the road is
        still a road complaint."""
        assert category(provider, "The road outside my house has never been laid.") \
            == "ROAD"


class TestTwoComplaintsAreNotOneCategory:

    @pytest.mark.parametrize("text,language", [
        ("We need both the drainage cleared and the water pipeline repaired.", "en"),
        ("The pothole is dangerous and the street light is also dead.", "en"),
        ("குப்பையும் சேரவில்லை, தண்ணீரும் வரவில்லை.", "ta"),
    ])
    def test_a_coordinated_pair_is_unknown(self, provider, text, language):
        """Counting nouns can never separate "sewage overflowing onto the
        road" from "both the drain and the pipeline need repair" — the nouns
        are the same shape. What separates them is that the second
        COORDINATES them, and Tamil says so outright with உம் on each noun."""
        assert category(provider, text, language) == UNKNOWN

    def test_two_symptoms_of_one_department_are_not_two_complaints(self, provider):
        """"The drain is blocked and the sewage is standing" is one
        complaint said twice. Sending it to a human would be noise."""
        assert category(provider, "The drain is blocked and the sewage is standing.") \
            == "SANITATION"

    def test_a_near_miss_does_not_trigger_it(self, provider):
        """A near-tie rule once sent anything with a second noun to UNKNOWN.
        It bought one case and cost two: a sewage complaint and a widow
        pension both became UNKNOWN. Caution that misroutes correct work is
        not caution."""
        assert category(provider, "My widow pension allowance has been stopped.") \
            == "PENSION"


# ---------------------------------------------------------------------------
# The bug this layer exists for
# ---------------------------------------------------------------------------

class TestAnAttachmentIsEvidenceNeverIdentity:

    PETITION = "Respected Sir, Subject: repair of the street. I request action."

    def test_a_petition_naming_somebody_else_is_theirs_not_the_citizens(self, provider):
        """THE REPORTED BUG. A citizen called Harish attached a previous
        petition belonging to Sethubala. Nothing classified the
        relationship, the document was treated as his own earlier petition,
        and its details were offered as replacements for his. A petition
        went out under a name belonging to neither of them."""
        answer = provider.classify_attachment_relationship(
            kind="pdf", text=self.PETITION,
            citizen_name="Harish", document_name="Sethubala")

        assert answer.value == "THIRD_PARTY_SUPPORTING_DOCUMENT"
        assert answer.confidence >= 0.8

    def test_an_unsigned_petition_is_not_assumed_to_be_theirs(self, provider):
        """The assumption IS the bug. Absence of a name is not evidence of
        ownership."""
        answer = provider.classify_attachment_relationship(
            kind="pdf", text=self.PETITION, citizen_name="Harish", document_name="")
        assert answer.value == UNKNOWN

    def test_nor_when_the_citizen_has_not_given_a_name_yet(self, provider):
        answer = provider.classify_attachment_relationship(
            kind="pdf", text=self.PETITION, citizen_name="", document_name="Kavitha")
        assert answer.value == UNKNOWN

    @pytest.mark.parametrize("citizen,document,same", [
        ("Harish", "Harish", True),
        ("Harish", "Harish Kumar", True),
        ("Harish Kumar", "Harish", True),
        ("Harish", "Harishkumar", False),
        ("Murugan", "Muruganantham", False),
        ("Lakshmi Priya", "Lakshmi Narayanan", False),
    ])
    def test_a_shared_prefix_is_not_a_shared_person(self, provider, citizen, document, same):
        """"Murugan" and "Muruganantham" are two people. A classifier
        generous about names files a petition under the wrong one."""
        answer = provider.classify_attachment_relationship(
            kind="pdf", text=self.PETITION,
            citizen_name=citizen, document_name=document)
        expected = "OWN_PREVIOUS_PETITION" if same else "THIRD_PARTY_SUPPORTING_DOCUMENT"
        assert answer.value == expected

    def test_a_reply_is_read_as_a_reply_not_as_a_petition(self, provider):
        """A government response quotes the petition it answers and so
        carries every petition marker. Checked in the wrong order it reads
        as the citizen's own petition."""
        answer = provider.classify_attachment_relationship(
            kind="pdf", citizen_name="Harish", document_name="Harish",
            text="With reference to your petition dated 4 March, this office "
                 "has sanctioned the work. Respected Sir, subject: repair.")
        assert answer.value == "GOVERNMENT_RESPONSE"


# ---------------------------------------------------------------------------
# Nothing here is allowed to act
# ---------------------------------------------------------------------------

class TestItDecidesAndNeverWrites:

    def test_every_task_returns_a_value_from_its_own_list(self, provider):
        """A caller cannot branch safely on a sentence. Free-form decision
        text is what the typed Decision exists to prevent."""
        assert category(provider, "The road is full of potholes.") in system_one.CATEGORIES
        assert provider.classify_attachment_relationship(
            kind="pdf", text="anything", citizen_name="A", document_name="B"
        ).value in system_one.RELATIONSHIPS

    def test_an_empty_or_tiny_grievance_is_unknown_not_a_guess(self, provider):
        for text in ("", "   ", "help", "ok"):
            assert category(provider, text) == UNKNOWN

    def test_a_provider_that_raises_does_not_stop_a_petition(self):
        """A classification layer must never be the reason a citizen cannot
        file. A broken provider falls back to the deterministic one."""
        class Broken:
            name = "broken"

            def classify_grievance(self, **kwargs):
                raise RuntimeError("provider is down")

        engine = SystemOneEngine(Broken())
        answer = engine.classify_grievance(
            grievance="There is no drinking water in our street.")
        assert answer.value == "WATER"

    def test_a_low_confidence_answer_is_downgraded_not_used(self):
        class Overconfident:
            name = "overconfident"

            def classify_grievance(self, **kwargs):
                return system_one.Decision("PENSION", 0.1, "a guess")

        engine = SystemOneEngine(Overconfident(), threshold=0.6)
        assert engine.classify_grievance(grievance="anything at all").value == UNKNOWN

    def test_laya_refuses_to_load_rather_than_pretending(self):
        """The seam is kept so the question can be re-asked, and it says so
        instead of silently behaving like the deterministic provider."""
        with pytest.raises(RuntimeError, match="not installed"):
            system_one.LayaProvider()

    def test_the_engine_is_deterministic_unless_configured_otherwise(self):
        assert system_one.engine().provider.name == "deterministic"


# ---------------------------------------------------------------------------
# The benchmark sets, as gates
# ---------------------------------------------------------------------------

class TestTheBenchmarksStayPassed:
    """The floors are set at what was measured, so a regression fails here
    rather than being discovered on a citizen's petition.

    THE SETS ARE NOT EQUAL EVIDENCE, and the docstrings in each say so.
    system_one_cases and holdout/holdout2 have all informed a change and can
    only confirm one now. Held-out #3 measured 0.860 BEFORE the defects it
    exposed were fixed; that is the honest independent figure for this
    engine, and the floor below is the confirmatory number.
    """

    @staticmethod
    def score(module):
        import importlib

        from benchmarks.run_system_one_benchmark import ask

        cases = importlib.import_module(module).dataset()
        provider = DeterministicProvider()
        right = sum(1 for c in cases if ask(provider, c).value == c.want)
        return right, len(cases)

    @pytest.mark.parametrize("module,floor", [
        ("benchmarks.system_one_cases", 61),
        ("benchmarks.system_one_holdout", 35),
        ("benchmarks.system_one_holdout2", 38),
        ("benchmarks.system_one_holdout3", 42),
    ])
    def test_the_set_still_scores_what_it_scored(self, module, floor):
        right, total = self.score(module)
        assert right >= floor, f"{module}: {right}/{total}, floor {floor}"

    def test_no_third_party_petition_is_ever_read_as_the_citizens_own(self):
        """The one that matters most, across every set. This is the failure
        that renamed a petitioner, and it is worth more than the headline
        accuracy: a wrong category is corrected by the officer, a wrong name
        goes out on government paper."""
        import importlib

        from benchmarks.run_system_one_benchmark import ask

        provider = DeterministicProvider()
        missed = []
        for module in ("benchmarks.system_one_cases", "benchmarks.system_one_holdout",
                       "benchmarks.system_one_holdout2", "benchmarks.system_one_holdout3"):
            for case in importlib.import_module(module).dataset():
                if (case.task == "relationship"
                        and case.want == "THIRD_PARTY_SUPPORTING_DOCUMENT"
                        and ask(provider, case).value == "OWN_PREVIOUS_PETITION"):
                    missed.append((module, case.payload.get("document_name")))
        assert not missed, missed
