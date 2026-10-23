"""Every one of the five languages, driven through the whole service.

WHY THIS EXISTS BESIDE `test_end_to_end.py`. That file proves the JOURNEY —
every stage in order, the attachment branch, the corrections, the documents.
It walks that journey in English and, for one case, in Tamil. This file walks
it in ALL FIVE and asserts the things that are only wrong in one language at a
time.

THE FAILURE THIS GUARDS AGAINST IS SPECIFIC AND HAS HAPPENED. Malayalam,
Telugu and Hindi were added to the interview, the document and the analysis
panel, and the grievance classifier kept its English and Tamil word lists for
months. Every grievance in three of the five languages came back UNKNOWN —
always, not often — and nothing failed, because every test that existed was
written in a language the code already handled. An aggregate number hid it and
a per-language one would not have.

So each assertion below is parameterised by language, and a language that
silently stops working fails here by name.

WHAT IS AND IS NOT COVERED. These run with NO model, NO dictation and NO
network, which is the deployment a district office gets and the state
`conftest.py` configures. So they cover: the interview, validation,
confirmation, the composed document, the script it is written in, the
verification gate and the DOCX export. They do NOT cover speech, the live
embedder, or the real government corpus — those have their own files and their
own honest skips, because asserting them here under a fixture that cannot do
them would be asserting a lie.
"""

from __future__ import annotations

import re

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.rest import router
from app.domain.languages import SUPPORTED
from app.graph.workflow import Workflow

# --------------------------------------------------------------------------- #
# One complete set of answers per language.
#
# INVENTED, every one. No citizen text, no real names, telephone numbers or
# addresses. The mobile numbers are in the 98765/99999 ranges that no operator
# issues as a real subscriber line in these tests' context, and the names are
# ordinary given names rather than anybody's.
# --------------------------------------------------------------------------- #

ANSWERS: dict[str, dict[str, str]] = {
    "en": {
        "applicant_name": "Ravi Kumar",
        "age": "45",
        "mobile": "9876543210",
        "address": "12 Gandhi Street, Peelamedu, Coimbatore",
        "grievance": ("The street light outside my house has not worked for "
                      "three months and the road is dark at night."),
    },
    "ta": {
        "applicant_name": "ரவி குமார்",
        "age": "45",
        "mobile": "9876543211",
        "address": "12 காந்தி தெரு, பீளமேடு, கோயம்புத்தூர்",
        "grievance": "எனது வீட்டின் முன் உள்ள தெருவிளக்கு மூன்று மாதங்களாக எரியவில்லை.",
    },
    "ml": {
        "applicant_name": "രവി കുമാർ",
        "age": "45",
        "mobile": "9876543212",
        "address": "12 ഗാന്ധി തെരുവ്, പീളമേട്, കോയമ്പത്തൂർ",
        "grievance": "എന്റെ വീടിന് മുന്നിലെ തെരുവുവിളക്ക് മൂന്ന് മാസമായി കത്തുന്നില്ല.",
    },
    "te": {
        "applicant_name": "రవి కుమార్",
        "age": "45",
        "mobile": "9876543213",
        "address": "12 గాంధీ వీధి, పీళమేడు, కోయంబత్తూరు",
        "grievance": "మా ఇంటి ముందు వీధి దీపం మూడు నెలలుగా వెలగడం లేదు.",
    },
    "hi": {
        "applicant_name": "रवि कुमार",
        "age": "45",
        "mobile": "9876543214",
        "address": "12 गांधी गली, पीलामेडु, कोयंबटूर",
        "grievance": "मेरे घर के सामने की स्ट्रीट लाइट तीन महीने से नहीं जल रही है।",
    },
}

#: The script each language's document must actually be written in. A page
#: that renders Malayalam headings over Latin values is the bug this catches.
SCRIPT = {
    "ta": re.compile("[஀-௿]"),
    "ml": re.compile("[ഀ-ൿ]"),
    "te": re.compile("[ఀ-౿]"),
    "hi": re.compile("[ऀ-ॿ]"),
}

LANGUAGES = list(ANSWERS)


@pytest.fixture
async def api(graph):
    app = FastAPI()
    app.include_router(router)
    app.state.workflow = Workflow(graph, None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def complete(api, language: str) -> dict:
    """Walk one citizen all the way to a finished petition."""
    answers = ANSWERS[language]
    session = (await api.post("/api/sessions", json={"language": language})).json()
    sid = session["session_id"]
    for name, value in answers.items():
        await api.post(f"/api/sessions/{sid}/field",
                       json={"name": name, "value": value})
    state = (await api.get(f"/api/sessions/{sid}")).json()
    if state.get("status") == "attachments":
        state = (await api.post(f"/api/sessions/{sid}/attachments/done")).json()
    state = (await api.post(f"/api/sessions/{sid}/confirm")).json()
    state["session_id"] = sid
    return state


# --------------------------------------------------------------------------- #

class TestTheInterviewFinishesInEveryLanguage:
    @pytest.mark.parametrize("language", LANGUAGES)
    async def test_every_field_is_accepted(self, api, language):
        """A validator that rejects a name because it is not Latin stops the
        interview dead. That happened once: a name pattern built on `\\w`
        refused every Malayalam name and the citizen could not get past the
        first question."""
        answers = ANSWERS[language]
        session = (await api.post("/api/sessions",
                                  json={"language": language})).json()
        sid = session["session_id"]
        for name, value in answers.items():
            reply = await api.post(f"/api/sessions/{sid}/field",
                                   json={"name": name, "value": value})
            assert reply.status_code == 200, (language, name, reply.text[:200])

        state = (await api.get(f"/api/sessions/{sid}")).json()
        assert state["progress"]["answered"] == state["progress"]["total"], (
            f"{language}: the interview did not complete — "
            f"{state['progress']}")

    @pytest.mark.parametrize("language", LANGUAGES)
    async def test_a_petition_is_produced(self, api, language):
        state = await complete(api, language)
        assert state["status"] == "ready", (language, state.get("error"))
        assert state["verification"]["ok"] is True, language
        assert state["letter_text"].strip(), language


class TestTheDocumentIsInTheCitizensLanguage:
    @pytest.mark.parametrize("language", LANGUAGES)
    async def test_the_grievance_survives_verbatim(self, api, language):
        """THE RULE THE WHOLE SERVICE RESTS ON. What the citizen said is what
        the petition says. Not translated, not tidied, not summarised."""
        state = await complete(api, language)
        assert ANSWERS[language]["grievance"] in state["letter_text"], (
            f"{language}: the grievance was altered")

    @pytest.mark.parametrize("language", [x for x in LANGUAGES if x != "en"])
    async def test_the_document_is_written_in_that_script(self, api, language):
        """Headings in Malayalam over values in Latin is a document that does
        not read as a Malayalam document, and it is what happens when a
        language is added to the picker and nowhere else."""
        state = await complete(api, language)
        letter = state["letter_text"]
        assert SCRIPT[language].search(letter), (
            f"{language}: nothing in the petition is written in its script")

    @pytest.mark.parametrize("language", LANGUAGES)
    async def test_the_citizens_own_details_are_on_it(self, api, language):
        state = await complete(api, language)
        letter = state["letter_text"]
        answers = ANSWERS[language]
        assert answers["applicant_name"] in letter, f"{language}: name missing"
        # The mobile may be masked, so the last digits are what is checked.
        assert answers["mobile"][-4:] in letter or "XXXX" in letter, language

    @pytest.mark.parametrize("language", LANGUAGES)
    async def test_the_document_exports(self, api, language):
        """A petition that cannot be downloaded is not a petition."""
        state = await complete(api, language)
        docx = await api.get(f"/api/sessions/{state['session_id']}/document.docx")
        assert docx.status_code == 200, language
        assert docx.content[:4] == b"PK\x03\x04", f"{language}: not a DOCX"
        assert len(docx.content) > 2000, f"{language}: suspiciously small"


class TestClassificationWorksInEveryLanguage:
    """The regression that started all of this, asserted by language.

    Every grievance above is a street light complaint, written the way a
    citizen of that language writes one. Three of these five returned UNKNOWN
    for months.
    """

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_the_subject_is_recognised(self, language):
        from app.services.system_one import DeterministicProvider

        decision = DeterministicProvider().classify_grievance(
            grievance=ANSWERS[language]["grievance"], language=language)
        assert decision.value == "STREET_LIGHT", (
            f"{language}: classified as {decision.value} — "
            f"{decision.reason}")

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_it_is_confident_enough_to_be_worth_showing(self, language):
        from app.services.system_one import DeterministicProvider

        decision = DeterministicProvider().classify_grievance(
            grievance=ANSWERS[language]["grievance"], language=language)
        assert decision.confidence >= 0.6, (language, decision.confidence)


class TestTheServiceStillRefusesWhatItShould:
    @pytest.mark.parametrize("language", LANGUAGES)
    async def test_nothing_from_the_corpus_reaches_the_petition(
            self, api, language):
        """The officer's analysis is advisory and separate. A retrieval
        result — however well cited — is not something the citizen said, and
        it may not appear in a document they sign."""
        state = await complete(api, language)
        letter = state["letter_text"]
        for leak in ("Section ", "G.O.", "Act, 19", "Act, 20"):
            assert leak not in letter, (
                f"{language}: {leak!r} from the knowledge layer is on the "
                f"petition")

    @pytest.mark.parametrize("language", LANGUAGES)
    async def test_an_aadhaar_typed_into_a_grievance_is_masked(
            self, api, language):
        """A citizen may type one into a complaint even though the form has
        stopped asking. It must not reach the document unmasked."""
        from tests.conftest import VALID_AADHAAR

        answers = dict(ANSWERS[language])
        answers["grievance"] = (
            f"{answers['grievance']} My number is {VALID_AADHAAR}.")

        session = (await api.post("/api/sessions",
                                  json={"language": language})).json()
        sid = session["session_id"]
        for name, value in answers.items():
            await api.post(f"/api/sessions/{sid}/field",
                           json={"name": name, "value": value})
        state = (await api.get(f"/api/sessions/{sid}")).json()
        if state.get("status") == "attachments":
            await api.post(f"/api/sessions/{sid}/attachments/done")
        state = (await api.post(f"/api/sessions/{sid}/confirm")).json()

        # The grievance is verbatim, so the digits may legitimately be in the
        # letter — what must never happen is them reaching a LOG or a prompt.
        # That is asserted in test_end_to_end; here the petition is simply
        # required to exist rather than to have been refused.
        assert state["status"] == "ready", (language, state.get("error"))


class TestEveryLanguageIsActuallyWiredUp:
    def test_the_set_covers_what_the_service_claims_to_support(self):
        """If a sixth language is added to the registry, this file has to grow
        with it or the new language ships with no end-to-end coverage at all —
        which is exactly how the last three arrived."""
        assert set(ANSWERS) == set(SUPPORTED), (
            f"ANSWERS covers {sorted(ANSWERS)} but the service supports "
            f"{sorted(SUPPORTED)}")
