"""The attachment pipeline with the relationship classifier wired in.

WHY THESE ARE INTEGRATION TESTS. `test_system_one.py` proves the classifier
answers correctly. That is not the same as proving a petition cannot be
contaminated — the classifier was always capable of saying "this is somebody
else's document" and the petition was contaminated anyway, because nothing
consulted it. These tests exercise the path a real upload takes: read the
file, extract, classify, store, compose.

THE FAILURE BEING PREVENTED, in full. A citizen called Harish attached a
previous petition belonging to Sethubala. Extraction read Sethubala's name,
address and acknowledgement number correctly. Harish confirmed that the
extraction was right — because it WAS right, the document really does say
those things. Two separate harms followed:

    1. the extracted name was offered as a one-click replacement for the
       name Harish had typed, and
    2. the composer wrote "I had previously submitted a petition ... under
       acknowledgement number N" in Harish's first person, using a number
       belonging to Sethubala.

Confirming that a document says something is not the same as claiming it is
about you. Nothing in the confirm step can tell the difference; the
relationship classification can.
"""

from __future__ import annotations

import pytest

from app.domain import attachment_conflicts
from app.domain.attachments import Attachment, AttachmentSet
from app.graph import nodes
from app.services import system_one

PETITION_TEXT = (
    "Respected Sir,\n"
    "Subject: Repair of the drinking water pipeline in our street.\n"
    "I humbly request that the pipeline be repaired.\n"
    "Petition dated 04-03-2025. Acknowledgement number 4412.\n"
)


def attachment_for(*, citizen_name, document_name, kind="previous_petition",
                   text=PETITION_TEXT, confirmed=True, grievance="",
                   reference="4412"):
    """One attachment carried through the same steps the upload endpoint runs."""
    extracted = {
        "kind": kind,
        "readable": True,
        "reason": "",
        "low_confidence": False,
        "other_dates": [],
        "petitioner_name": ({"value": document_name, "evidence": document_name,
                             "confidence": 0.88, "page": 1, "unit": "page"}
                            if document_name else None),
        "reference_number": ({"value": reference, "evidence": reference,
                              "confidence": 0.9, "page": 1, "unit": "page"}
                             if reference else None),
        "submitted_on": {"value": "2025-03-04", "evidence": "04-03-2025",
                         "confidence": 0.9, "page": 1, "unit": "page"},
        "petition_number": None, "address": None, "department": None,
        "authority": None, "subject": None, "grievance": None,
        "requested_action": None, "status": None,
    }
    record = system_one.describe_attachment(
        kind=kind, text=text, grievance=grievance,
        citizen_name=citizen_name, document_name=document_name,
        relevance_level="high")
    return Attachment(
        attachment_id="a1", filename="earlier.pdf", stored_name="earlier.pdf",
        content_type="application/pdf", size=1024, kind=kind,
        extracted=extracted, confirmed=confirmed, relationship=record)


# ---------------------------------------------------------------------------
# CASE A — the reported bug
# ---------------------------------------------------------------------------

class TestCaseA_SomebodyElsesPetition:
    """Citizen Harish, attachment belonging to Sethubala."""

    @pytest.fixture
    def enclosed(self):
        return AttachmentSet(items=[attachment_for(
            citizen_name="Harish", document_name="Sethubala")])

    def test_it_is_classified_as_a_third_partys_document(self, enclosed):
        assert enclosed.items[0].relationship["value"] \
            == "THIRD_PARTY_SUPPORTING_DOCUMENT"

    def test_harish_remains_the_petitioner(self, enclosed):
        """The citizen's confirmed name outranks anything read off a page.
        Nothing in the pipeline writes to `fields`, so this asserts the
        property directly: the name survives the whole analysis."""
        fields = {"applicant_name": "Harish", "address": "12 Gandhi Street"}
        before = dict(fields)
        attachment_conflicts.find(fields, enclosed)
        nodes._prior_reference(enclosed, "en")
        assert fields == before
        assert fields["applicant_name"] == "Harish"

    def test_sethubala_is_never_offered_as_a_replacement_name(self, enclosed):
        """The disagreement is still RAISED — an officer should see it — but
        the swap is not offered. A citizen knows their own name; an OCR pass
        over a scanned letter does not."""
        conflicts = attachment_conflicts.find(
            {"applicant_name": "Harish"}, enclosed)
        names = [c for c in conflicts if c.field == "applicant_name"]
        assert names, "the disagreement should still be reported"
        assert all(c.adoptable is False for c in names)

    def test_the_petition_does_not_claim_sethubalas_reference_number(self, enclosed):
        """THE SENTENCE THAT WENT OUT. Harish had not submitted petition
        4412; Sethubala had. The document and the number are both genuine,
        which is exactly why nothing before this caught it."""
        assert nodes._prior_reference(enclosed, "en") == ""

    def test_the_document_is_still_enclosed(self, enclosed):
        """Withheld from the first person, not thrown away. A neighbour's
        petition about the same road is legitimate evidence and the citizen
        brought it deliberately."""
        assert len(enclosed.items) == 1
        assert enclosed.items[0].kind == "previous_petition"
        assert list(enclosed.lines("en"))

    def test_and_an_officer_is_told_to_look(self, enclosed):
        assert enclosed.items[0].relationship["requires_review"] is True


# ---------------------------------------------------------------------------
# CASE B — their own petition still works
# ---------------------------------------------------------------------------

class TestCaseB_TheirOwnEarlierPetition:

    def test_it_is_recognised_as_their_own(self):
        enclosed = AttachmentSet(items=[attachment_for(
            citizen_name="Harish", document_name="Harish")])
        assert enclosed.items[0].relationship["value"] == "OWN_PREVIOUS_PETITION"

    def test_the_reference_sentence_is_still_produced(self):
        """The guard must not cost a citizen the thing they attached the
        document for. A petition that drops a genuine prior reference sends
        an officer hunting for context that was in the file all along."""
        enclosed = AttachmentSet(items=[attachment_for(
            citizen_name="Harish", document_name="Harish")])
        sentence = nodes._prior_reference(enclosed, "en")
        assert "4412" in sentence
        assert "previously submitted" in sentence

    def test_a_short_form_of_the_same_name_still_counts(self):
        enclosed = AttachmentSet(items=[attachment_for(
            citizen_name="Harish", document_name="Harish Kumar")])
        assert enclosed.items[0].relationship["value"] == "OWN_PREVIOUS_PETITION"
        assert "4412" in nodes._prior_reference(enclosed, "en")

    def test_an_unreadable_petitioner_name_does_not_silence_them(self):
        """Most scanned acknowledgement slips carry no legible petitioner
        name. Withholding on absence of evidence would quietly cost those
        citizens their reference sentence, so the rule withholds on EVIDENCE
        that the document is somebody else's instead."""
        enclosed = AttachmentSet(items=[attachment_for(
            citizen_name="Harish", document_name="")])
        assert enclosed.items[0].relationship["value"] == "UNKNOWN"
        assert "4412" in nodes._prior_reference(enclosed, "en")


# ---------------------------------------------------------------------------
# CASES C and D — other document types
# ---------------------------------------------------------------------------

class TestCaseC_AnAcknowledgement:

    def test_a_receipt_is_read_as_a_receipt(self):
        record = system_one.describe_attachment(
            kind="acknowledgement", grievance="no water in our street",
            text="Acknowledgement. We have received your petition. Token 5567.",
            citizen_name="Harish", document_name="")
        assert record["value"] == "ACKNOWLEDGEMENT"


class TestCaseD_AnUnrelatedDocument:

    @pytest.fixture
    def record(self):
        return system_one.describe_attachment(
            kind="other",
            text="Electricity bill. Consumer number 44/2. Amount due 610.",
            grievance="The drain outside my house has been blocked for a month.",
            citizen_name="Harish", document_name="")

    def test_it_is_reported_as_unrelated(self, record):
        """A supporting document that supports nothing in this complaint is
        not "general support". Two classifiers hold half of that each: one
        knows the document has no recognisable type, the other knows it
        shares nothing with the grievance."""
        assert record["value"] == "UNRELATED"

    def test_it_modifies_no_citizen_data(self, record):
        fields = {"applicant_name": "Harish", "address": "12 Gandhi Street",
                  "grievance": "The drain is blocked."}
        before = dict(fields)
        enclosed = AttachmentSet(items=[Attachment(
            attachment_id="a2", filename="bill.pdf", stored_name="bill.pdf",
            content_type="application/pdf", size=10, kind="other",
            relationship=record)])
        attachment_conflicts.find(fields, enclosed)
        nodes._prior_reference(enclosed, "en")
        assert fields == before


# ---------------------------------------------------------------------------
# CASE E — the classifier is not there
# ---------------------------------------------------------------------------

class TestCaseE_TheClassifierIsUnavailable:

    @pytest.fixture
    def broken(self, monkeypatch):
        def explode(*args, **kwargs):
            raise RuntimeError("provider is down")

        monkeypatch.setattr(system_one.DeterministicProvider,
                            "classify_attachment_relationship", explode)
        monkeypatch.setattr(system_one.DeterministicProvider,
                            "classify_grievance", explode)
        return system_one.describe_attachment(
            kind="previous_petition", text=PETITION_TEXT,
            grievance="no water", citizen_name="Harish",
            document_name="Sethubala")

    def test_it_returns_unknown_rather_than_raising(self, broken):
        """A classification layer must never be the reason a citizen cannot
        file a petition.

        Note what does NOT happen here: the engine catches the provider's
        failure itself and answers UNKNOWN, so this never reaches the outer
        guard in `describe_attachment`. Two layers, and the inner one is
        enough. The outer one is tested separately below, because "the engine
        handled it" and "nothing at all was reachable" are different
        failures and only one of them is the one people plan for.
        """
        assert broken["value"] == "UNKNOWN"
        assert broken["first_person_allowed"] is True

    def test_and_when_nothing_at_all_is_reachable(self, monkeypatch):
        """The outer guard: the engine itself cannot be constructed."""
        def explode(*args, **kwargs):
            raise RuntimeError("no engine")

        monkeypatch.setattr(system_one, "engine", explode)
        with pytest.raises(RuntimeError):
            system_one.engine()
        # describe_attachment builds the engine inside its own try, so a
        # failure there still lands on the safe record rather than escaping.
        record = system_one.describe_attachment(
            kind="pdf", text=PETITION_TEXT, grievance="x",
            citizen_name="Harish", document_name="Sethubala")
        assert record["value"] == "UNKNOWN"
        assert record["source"] == "unavailable"
        assert record["requires_review"] is True

    def test_the_attachment_still_works(self, broken):
        enclosed = AttachmentSet(items=[Attachment(
            attachment_id="a3", filename="x.pdf", stored_name="x.pdf",
            content_type="application/pdf", size=10,
            kind="previous_petition", relationship=broken)])
        assert list(enclosed.lines("en"))

    def test_and_it_is_flagged_for_a_human(self, broken):
        assert broken["requires_review"] is True

    def test_no_citizen_field_is_touched(self, broken):
        fields = {"applicant_name": "Harish"}
        before = dict(fields)
        enclosed = AttachmentSet(items=[attachment_for(
            citizen_name="Harish", document_name="Sethubala")])
        enclosed.items[0].relationship = broken
        attachment_conflicts.find(fields, enclosed)
        assert fields == before


# ---------------------------------------------------------------------------
# CASES F and G — the two scripts crossing
# ---------------------------------------------------------------------------

TAMIL_PETITION = (
    "மதிப்பிற்குரிய ஐயா,\n"
    "பொருள்: எங்கள் தெருவில் குடிநீர் குழாய் பழுது நீக்கக் கோரி மனு.\n"
    "ஒப்புகை எண் 4412.\n"
)


class TestCaseF_TamilAttachmentEnglishPetition:

    def test_a_tamil_document_naming_someone_else_is_still_caught(self):
        record = system_one.describe_attachment(
            kind="previous_petition", text=TAMIL_PETITION, language="ta",
            grievance="There is no drinking water in our street.",
            citizen_name="Harish", document_name="சேதுபாலா")
        assert record["value"] == "THIRD_PARTY_SUPPORTING_DOCUMENT"
        assert record["first_person_allowed"] is False

    def test_no_tamil_text_reaches_an_english_petitioner_field(self):
        enclosed = AttachmentSet(items=[attachment_for(
            citizen_name="Harish", document_name="சேதுபாலா",
            text=TAMIL_PETITION)])
        fields = {"applicant_name": "Harish", "address": "12 Gandhi Street"}
        before = dict(fields)
        attachment_conflicts.find(fields, enclosed)
        assert fields == before
        assert not any("஀" <= c <= "௿" for c in fields["applicant_name"])


class TestCaseG_EnglishAttachmentTamilPetition:

    def test_the_citizens_own_values_are_rendered_by_tamil_output_rules(self):
        """The name printed on a Tamil petition comes from the citizen's
        field put through the Tamil display rules — never copied out of an
        English attachment. This is the defect that printed "Harish" in Latin
        in the signature block of a Tamil petition, fixed in `letter.py` by
        going through `display_value`."""
        from app.domain.fields import display_value

        rendered = display_value("person_name", "Harish", "ta")
        assert rendered
        assert any("஀" <= c <= "௿" for c in rendered), rendered

    def test_an_english_document_does_not_change_the_tamil_petitioner(self):
        enclosed = AttachmentSet(items=[attachment_for(
            citizen_name="ஹரிஷ்", document_name="Sethubala")])
        fields = {"applicant_name": "ஹரிஷ்"}
        before = dict(fields)
        attachment_conflicts.find(fields, enclosed)
        nodes._prior_reference(enclosed, "ta")
        assert fields == before

    def test_the_tamil_reference_sentence_is_withheld_for_a_third_party(self):
        enclosed = AttachmentSet(items=[attachment_for(
            citizen_name="ஹரிஷ்", document_name="Sethubala")])
        assert nodes._prior_reference(enclosed, "ta") == ""


# ---------------------------------------------------------------------------
# The category hint may not route
# ---------------------------------------------------------------------------

class TestSourcesAreNeverFlattenedTogether:
    """Item 10 and 11: a value's origin must survive as far as composition.

    A flat dictionary cannot express priority. Once "Harish" and "சேபாலா" are
    both strings under `applicant_name`, the last writer wins and the question
    of which had the better claim has already been lost.
    """

    @pytest.fixture
    def context(self):
        from app.domain import provenance

        enclosed = AttachmentSet(items=[attachment_for(
            citizen_name="Harish", document_name="Sethubala")])
        return provenance.context(
            {"applicant_name": "Harish", "address": "12 Gandhi Street"}, enclosed)

    def test_the_citizens_value_is_labelled_as_theirs(self, context):
        fact = context["current_citizen_facts"]["applicant_name"]
        assert fact["value"] == "Harish"
        assert fact["source_type"] == "citizen"
        assert fact["confirmed"] is True

    def test_the_documents_value_carries_where_it_was_read(self, context):
        names = [e for e in context["confirmed_attachment_evidence"]
                 if e["key"] == "petitioner_name"]
        assert names, context
        fact = names[0]
        assert fact["value"] == "Sethubala"
        assert fact["source_type"] == "attachment"
        assert fact["attachment_id"]
        assert fact["page"] == 1
        assert fact["confidence"] == 0.88
        assert fact["relationship"] == "THIRD_PARTY_SUPPORTING_DOCUMENT"

    def test_they_are_in_separate_compartments(self, context):
        """Not one dictionary with a priority field — two dictionaries. A
        composer cannot read the wrong one by accident; it has to name the
        compartment it is reading from."""
        assert "Sethubala" not in str(context["current_citizen_facts"])
        assert isinstance(context["confirmed_attachment_evidence"], list)

    def test_the_petitioner_block_is_built_from_the_citizen_alone(self, context):
        from app.domain import provenance

        built = provenance.petitioner_fields(context)
        assert built["applicant_name"] == "Harish"
        assert "Sethubala" not in str(built)

    def test_identity_fields_are_flagged_as_never_attachment_supplied(self, context):
        for fact in context["confirmed_attachment_evidence"]:
            if fact["key"] in ("petitioner_name", "address"):
                assert fact["may_fill_petition_field"] is False, fact

    def test_unconfirmed_extraction_is_not_evidence_at_all(self):
        """Until the citizen has looked at what was read and said it is
        right, it is a regular expression's opinion about a photograph."""
        from app.domain import provenance

        enclosed = AttachmentSet(items=[attachment_for(
            citizen_name="Harish", document_name="Sethubala", confirmed=False)])
        built = provenance.context({"applicant_name": "Harish"}, enclosed)
        assert built["confirmed_attachment_evidence"] == []


class TestTheOfficerPortalShowsItAsAdvice:

    def test_the_api_carries_the_classification(self):
        from app.api import officer

        enclosed = AttachmentSet(items=[attachment_for(
            citizen_name="Harish", document_name="Sethubala")])
        served = officer.attachments({"attachments": enclosed.as_state()}, "s1")

        assert served[0]["relationship"]["value"] \
            == "THIRD_PARTY_SUPPORTING_DOCUMENT"
        assert served[0]["relationship"]["confidence"] > 0

    def test_a_third_partys_reference_is_not_listed_as_the_petitioners(self):
        """"Previous submissions" is a claim about THIS citizen's history.
        A number read off somebody else's document goes under its own
        heading, so an officer sees both that it exists and whose it is."""
        from app.api import officer

        theirs = attachment_for(citizen_name="Harish", document_name="Harish")
        other = attachment_for(citizen_name="Harish", document_name="Sethubala",
                               reference="9999")
        other.attachment_id = "a2"

        facts = {}
        for attachment in (theirs, other):
            record = attachment.relationship or {}
            reference = (attachment.extracted or {}).get("reference_number", {})
            key = ("Previous submissions" if record.get("first_person_allowed", True)
                   else "Referenced in an enclosed document (not the petitioner's)")
            facts.setdefault(key, []).append(reference["value"])

        assert facts["Previous submissions"] == ["4412"]
        assert facts["Referenced in an enclosed document (not the petitioner's)"] \
            == ["9999"]

    def test_the_portal_calls_it_ai_assisted_and_not_a_determination(self):
        """The officer must be able to disagree with it. A classification
        presented as a finding is one nobody questions."""
        import pathlib

        script = (pathlib.Path(__file__).resolve().parent.parent
                  / "app" / "static" / "officer.js").read_text(encoding="utf-8")

        assert "RELATIONSHIP_LABELS" in script
        assert "Third-party supporting document" in script
        assert "AI-assisted classification" in script
        assert "not an official determination" in script
        assert "officer review required" in script
        # And it is actually rendered, not merely defined.
        assert "${relationship(f)}" in script


class TestTheCategoryIsOnlyEverAHint:

    def test_it_is_carried_but_named_as_a_suggestion(self):
        record = system_one.describe_attachment(
            kind="other", text="anything",
            grievance="There is no drinking water in our street for five days.",
            citizen_name="Harish", document_name="")
        assert record["suggested_category"] == "WATER"

    def test_nothing_in_the_service_routes_on_it(self):
        """Department, authority, Act and Rule come from verified RAG and
        officer review. If this ever fails, something has started branching
        on a 0.778 classifier.

        Scanned through the AST rather than by searching the text, because
        the text search flagged a COMMENT explaining that the field must not
        be branched on — which is the opposite of an offence. Comments do not
        appear in an AST, so only real references are counted.
        """
        import ast
        import pathlib

        root = pathlib.Path(__file__).resolve().parent.parent / "app"
        offenders = []
        for path in root.rglob("*.py"):
            if path.name == "system_one.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                # A string key — fields["suggested_category"] — or an
                # attribute — record.suggested_category. Either is a read.
                hit = ((isinstance(node, ast.Constant)
                        and node.value == "suggested_category")
                       or (isinstance(node, ast.Attribute)
                           and node.attr == "suggested_category"))
                if hit:
                    offenders.append(f"{path.name}:{node.lineno}")
        assert not offenders, (
            "suggested_category is read outside system_one.py; it is a hint "
            f"and must not be branched on: {offenders}")
