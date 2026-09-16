"""One named test per defect actually found in this codebase.

These duplicate coverage elsewhere on purpose. A behavioural test says what the
system should do; a regression test says what it once did wrong, so that a
future refactor that reintroduces the fault fails against a test whose name
explains the problem rather than against an assertion someone has to decode.

Each test names the symptom, not the fix.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.domain.fields import (
    validate_address,
    validate_age,
    validate_email,
    validate_text,
)
from app.domain.templates import match_field, the_template
from app.graph import nodes
from app.logging_setup import JsonFormatter
from app.services.render import extract_docx_text
from tests.conftest import VALID_AADHAAR


class TestValidatorRegressions:
    def test_a_dictated_email_is_not_rejected(self):
        """The spoken-form conversion ran AFTER spaces were stripped, so
        "ravi at example dot com" had become "raviatexampledotcom" and there was
        no word boundary left for \\bat\\b to match. A working address was
        rejected."""
        assert validate_email("ravi at example dot com").value == "ravi@example.com"

    def test_a_single_word_is_not_a_postal_address(self):
        """"Coimbatore" is ten characters and passed a bare length check. A
        letter addressed to a district name cannot be delivered."""
        assert validate_address("Coimbatore").code == "address.short"
        assert validate_address("12 Gandhi Street, Peelamedu, Coimbatore").ok

    def test_a_spoken_scale_word_does_not_collapse_into_a_plausible_age(self):
        """`digits_from_speech` collects digit words and ignores scale words, so
        "nine hundred" became "9" — an age the citizen never said, on a
        government form, with nothing to signal it was wrong."""
        assert validate_age("nine hundred").code == "age.format"
        assert validate_age("my age is about nine hundred or so").code == "age.format"
        assert validate_age("two lakh").code == "age.format"
        assert validate_age("45").value == 45

    def test_a_date_of_birth_is_not_truncated_into_an_age(self):
        """A citizen answering "age" with a date used to yield the first two
        digits of it."""
        assert validate_age("15-03-1980").code == "age.format"

    def test_free_text_keeps_its_trailing_full_stop(self):
        """`clean_text` strips trailing punctuation — correct for a name, and an
        edit to the citizen's own words when applied to a grievance."""
        assert validate_text("The drain is blocked.").value == "The drain is blocked."

    def test_free_text_keeps_its_line_breaks(self):
        """Whitespace was collapsed wholesale, running separate numbered points
        together into one block."""
        result = validate_text("First point.\nSecond point.\n\nThird point.")
        assert result.value.count("\n") >= 2

    def test_free_text_is_never_silently_truncated(self):
        """The value was cut at 2000 characters with no indication, so the end
        of a long complaint vanished between the citizen saying it and the
        petition being printed."""
        long_text = "x" * 7000
        result = validate_text(long_text)
        assert not result.ok
        assert result.code == "text.long"
        assert result.detail["limit"] == 6000


class TestPrivacyRegressions:
    def test_the_understanding_prompt_carries_no_recorded_value(self, valid_aadhaar):
        """`_understanding_context` wrote "[already recorded: <value>]" into the
        SYSTEM prompt, and `chat_json` masked only the user turn — so a
        validated Aadhaar number travelled to the provider while the citizen's
        sentence beside it was redacted."""
        context = nodes._understanding_context(
            {"fields": {"aadhaar": valid_aadhaar, "applicant_name": "Ravi Kumar"}},
            the_template(), "age",
        )
        assert valid_aadhaar not in context
        assert "Ravi Kumar" not in context
        assert "[already answered]" in context

    async def test_a_rejected_identifier_never_reaches_the_model(self, chat, answers,
                                                                 llm_spy):
        """A malformed Aadhaar used to fall through the fast path into the
        model call, putting the citizen's attempted number on the wire to learn
        what the validator had already established."""
        c = chat()
        await c.open()
        await c.say(answers["applicant_name"])
        await c.say(answers["age"])
        await c.say(answers["mobile"])
        await c.say(answers["address"])
        await c.say("2345 6789 0125")
        assert llm_spy.count == 0, llm_spy.payloads

    def test_a_log_line_cannot_carry_an_identifier_through_extra(self):
        """The formatter serialised `extra` verbatim, so any future call site
        putting a value there would have leaked it."""
        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "verify.failed",
                                   None, None)
        record.value = "2345 6789 0124"
        assert VALID_AADHAAR not in JsonFormatter().format(record)
        assert "2345 6789 0124" not in JsonFormatter().format(record)


class TestConversationRegressions:
    async def test_saying_no_at_the_read_back_does_not_loop(self, chat, answers):
        """"No" set the status back to collecting with nothing missing, so the
        router sent the citizen to `confirm` again and read the identical list
        back — for ever, with no way out."""
        c = chat()
        await c.answer_all(answers)
        read_back = c.reply
        assert "Name of petitioner" in read_back, "this is the list being repeated"

        first = await c.say("no")
        assert first["reply"] != read_back, "the identical list is not read back"
        assert "which detail" in first["reply"].lower()
        assert first["awaiting_correction"] is True

        # Saying "no" again does not advance, but it also does not regress into
        # the read-back: the citizen stays on the question they can answer.
        second = await c.say("no")
        assert second["reply"] != read_back
        assert second["awaiting_correction"] is True

        # And naming a field genuinely escapes the loop.
        third = await c.say("the age is wrong")
        assert third["awaiting"] == "age"
        assert third["awaiting_correction"] is False

    async def test_a_cancelled_session_does_not_resume_on_the_next_utterance(self, chat):
        """`validate` recomputed the status from the new turn, so anything said
        after "cancel" quietly reopened the petition."""
        c = chat()
        await c.open()
        await c.say("cancel")
        state = await c.say("Ravi Kumar")
        assert state["status"] == "cancelled"
        assert state["fields"] == {}

    async def test_restart_does_not_jump_to_the_read_back(self, chat, answers):
        """The restart branch returned `missing: []` on an emptied record, so
        the router went straight to `confirm` and offered to generate a petition
        with no details in it."""
        c = chat()
        await c.open()
        await c.say(answers["applicant_name"])
        state = await c.say("start over")
        assert state["status"] == "collecting"
        assert state["missing"] == list(the_template().field_names)
        assert state["awaiting"] == "applicant_name"

    async def test_a_transient_extraction_does_not_apply_twice(self, chat, answers):
        """`_extracted` lives on the checkpointed state. A turn that set nothing
        used to read the previous turn's extraction and record it again."""
        c = chat()
        await c.open()
        await c.say(answers["applicant_name"])
        state = await c.say("")           # nothing said
        assert state["fields"] == {"applicant_name": answers["applicant_name"]}
        assert state["_extracted"] == {}

    async def test_a_specific_error_survives_the_model_being_unavailable(
        self, chat, answers
    ):
        """With no model reachable, every unparseable answer produced "I did not
        understand" instead of the validator's own message, which is the only
        thing that tells the citizen what to do differently."""
        c = chat()
        await c.open()
        await c.say(answers["applicant_name"])
        state = await c.say("200")
        assert "200" in state["reply"], "the specific reason, not a generic fallback"

    def test_a_bare_yes_or_no_does_not_name_a_field(self):
        """Field matching runs before the yes/no reading at the read-back. If
        "no" matched anything, confirmation would be impossible."""
        for utterance in ("no", "yes", "இல்லை", "ஆம்"):
            assert match_field(the_template(), utterance) is None, utterance


class TestDocumentRegressions:
    async def test_a_tamil_petition_is_not_sent_through_a_translator(
        self, chat, tamil_answers
    ):
        """The letter scaffolding was hard-coded English, so eight words like
        "From:" and "Sub:" made `needs_translation` true and dragged every
        finished Tamil petition through a translator to change them."""
        c = chat("ta")
        await c.answer_all(tamil_answers)
        state = await c.say("ஆம்")
        assert not any("translat" in w.lower() for w in state["warnings"])
        assert "From:" not in state["letter_text"]

    async def test_the_end_of_a_long_grievance_reaches_the_document(self, chat, answers):
        """Truncation happened at the validator, so the document was faithful to
        a value that had already lost its ending."""
        grievance = " ".join(f"Item {i} is unresolved." for i in range(1, 120))
        c = chat()
        await c.answer_all({**answers, "grievance": grievance})
        state = await c.say("yes")
        produced = " ".join(extract_docx_text(Path(state["document"]["docx"])).split())
        assert "Item 119 is unresolved." in produced


class TestRenderingRegressions:
    """Both found by rendering a Tamil PDF and looking at it, which is the only
    way either of them could have been found."""

    async def test_the_pdf_converter_is_given_an_absolute_path(self, tmp_path,
                                                               monkeypatch):
        """External converters resolve paths against their own working
        directory, not this process's. A relative path produced a bare
        COMException from Word and an empty output directory from LibreOffice."""
        from app.config import Settings
        from app.services import render as render_module

        seen: dict = {}

        async def capture(path):
            seen["path"] = path
            return None, "not run"

        monkeypatch.setattr(render_module, "_word_available", lambda: True)
        monkeypatch.setattr(render_module, "_pdf_via_word", capture)
        monkeypatch.setattr(render_module.shutil, "which", lambda name: None)

        monkeypatch.chdir(tmp_path)
        relative = Path("var") / "x.docx"
        relative.parent.mkdir()
        relative.write_bytes(b"source document for mocked conversion")
        await render_module.render_pdf(relative, Settings(pdf_engine="word"))
        assert seen["path"].is_absolute()

    def test_the_sender_block_is_a_heading_not_an_inline_label(self):
        """The old layout put "அனுப்புநர்: <name>" on one line behind a tab
        stop, and at 900 twips the Tamil label overran it so the name printed
        hard against the colon. The standard format makes it a heading with the
        details indented beneath, which has no tab stop to overrun."""
        from app.domain.letter import build_letter_text

        text = build_letter_text(
            template=the_template(),
            fields={"applicant_name": "ரவி குமார்", "age": 45,
                    "address": "12 காந்தி தெரு, பீளமேடு, கோயம்புத்தூர்",
                    "aadhaar": VALID_AADHAAR, "grievance": "தெருவிளக்கு எரியவில்லை."},
            language="ta", composition=None, session_id="abc-123",
        )
        assert "அனுப்புநர்," in text
        assert "அனுப்புநர்: " not in text

    def test_a_grievance_paragraph_is_one_line_not_several(self):
        """The grievance was pre-wrapped to 88 columns, and the DOCX renderer
        treats every line as its own paragraph — so a wrapped sentence became
        several justified paragraphs and its last few words were stranded on a
        line of their own ("…இதுவரை எந்த நடவடிக்கையும் / இல்லை."). Word and
        LibreOffice know the real font metrics and wrap far better than a column
        count can, particularly for Tamil, where a glyph cluster is not one
        character wide."""
        from app.domain.letter import build_letter_text

        paragraph = (
            "I complained twice at the panchayat office and paid one thousand five "
            "hundred rupees for a connection, but no receipt of any kind was issued "
            "to me on either occasion despite my asking for one."
        )
        content = _grievance_lines(build_letter_text(
            template=the_template(),
            fields={"applicant_name": "Ravi Kumar", "age": 45,
                    "address": "12 Gandhi Street, Peelamedu, Coimbatore",
                    "aadhaar": VALID_AADHAAR, "grievance": paragraph},
            language="en", composition=None, session_id="abc-123",
        ))
        assert content == [paragraph], f"one paragraph, one line; got {len(content)}"

    def test_a_multi_paragraph_grievance_keeps_one_line_each(self):
        from app.domain.letter import build_letter_text

        grievance = "First point here.\nSecond point here.\n\nThird point here."
        content = _grievance_lines(build_letter_text(
            template=the_template(),
            fields={"applicant_name": "Ravi", "age": 45,
                    "address": "12 Gandhi Street, Peelamedu, Coimbatore",
                    "aadhaar": VALID_AADHAAR, "grievance": grievance},
            language="en", composition=None, session_id="abc-123",
        ))
        assert content == ["First point here.", "Second point here.", "Third point here."]


def _grievance_lines(letter: str) -> list[str]:
    """The non-blank lines of the verbatim grievance block."""
    opening = "I reside at the address given above"
    body = letter.split(opening)[1].split("I therefore humbly request")[0]
    return [line.strip() for line in body.split("\n") if line.strip()][1:]


class TestGroundingRegressions:
    """The elaboration may reason in words. It may not produce a figure."""

    def test_a_number_the_citizen_never_gave_is_refused(self):
        from app.graph.nodes import _numbers_are_grounded

        grounding = "the street light has not worked since 12/03/2026"
        assert _numbers_are_grounded("dark since 12/03/2026", grounding)
        assert not _numbers_are_grounded("for the past 18 months", grounding)
        assert not _numbers_are_grounded("affecting 40 families", grounding)
        assert not _numbers_are_grounded("under section 133", grounding)

    def test_prose_without_figures_always_passes(self):
        from app.graph.nodes import _numbers_are_grounded

        assert _numbers_are_grounded("the road is dark and unsafe at night", "anything")

    def test_an_ungrounded_field_is_dropped_not_the_whole_composition(self):
        """Partial acceptance: a good subject survives a fabricated figure in
        the representation."""
        from app.graph.nodes import _read_composition

        composition = _read_composition(
            {
                "subject": "Non-functioning street light",
                "introduction": "I reside at the address given above.",
                "background": "This has affected 40 families for 18 months.",
                "request": "I request an inspection.",
            },
            "en",
            grounding="street light not working",
        )
        assert composition.subject == "Non-functioning street light"
        assert composition.background is None, "the invented figures cost it this slot"
        assert composition.request == "I request an inspection."


class TestStructuredLogging:
    """`extra={"name": ...}` raised, and the exception was swallowed.

    Python refuses to let `extra` shadow a LogRecord attribute: it raises
    KeyError rather than dropping the key. `extensions/registry.py` logged
    `extra={"name": capability.name}` from the day it was written, and nothing
    noticed for as long as nothing registered a capability — the first real one
    hit it inside a try/except and the capability silently failed to attach.

    This service logs structurally everywhere, so the check is over the whole
    package rather than that one call.
    """

    # From logging.LogRecord.__init__, plus the two that formatting adds.
    RESERVED = frozenset({
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "taskName", "message", "asctime",
    })

    def test_no_log_call_shadows_a_logrecord_attribute(self):
        import ast
        import pathlib

        import app

        offences = []
        for path in sorted(pathlib.Path(app.__file__).parent.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                for keyword in node.keywords:
                    if keyword.arg != "extra" or not isinstance(keyword.value, ast.Dict):
                        continue
                    for key in keyword.value.keys:
                        if isinstance(key, ast.Constant) and key.value in self.RESERVED:
                            offences.append(f"{path.name}:{node.lineno} extra={key.value!r}")

        assert not offences, "these log calls would raise at runtime: " + ", ".join(offences)

    def test_registering_a_capability_actually_logs(self, caplog):
        """The bug was invisible because the failure was caught. Prove the call
        completes rather than trusting that it no longer raises."""
        import logging

        from app.extensions.registry import Registry

        class Probe:
            name = "probe_capability"

            async def enrich(self, petition):
                return None

        with caplog.at_level(logging.INFO):
            Registry().register(Probe())

        assert any(r.message == "capability.registered" for r in caplog.records)


class TestThePageIsWiredUp:
    """Every button the page declares must be reachable from a loaded script.

    Written after two failures no other test could see.

    The first: a range deletion that removed dead drop-zone code took a block
    of click handlers out with it, because they happened to sit between the two
    anchors. The markup still had the button, the script still had the
    function, and nothing connected them.

    The second was worse. `navigation.js` was written, complete and correct —
    and no <script> tag ever loaded it. It carries the bootstrap, so the page
    opened to a dead composer and never started a session. `node --check`
    passed. The suite passed. Nothing was wrong with any file.

    Static checks, so they run in the same suite as everything else with no
    browser and no network.
    """

    @staticmethod
    def _static():
        from pathlib import Path

        return Path("app/static")

    @classmethod
    def _loaded_scripts(cls) -> list[str]:
        import re

        markup = (cls._static() / "index.html").read_text(encoding="utf-8")
        return re.findall(r'<script src="/static/([^"]+)"', markup)

    @classmethod
    def _sources(cls) -> tuple[str, str]:
        """The page, and every script it actually loads, concatenated."""
        static = cls._static()
        markup = (static / "index.html").read_text(encoding="utf-8")
        body = "\n".join((static / name).read_text(encoding="utf-8")
                          for name in cls._loaded_scripts()
                          if (static / name).is_file())
        return markup, body

    def test_every_script_exists_and_every_script_is_loaded(self):
        """Both directions. A tag pointing at nothing is a 404; a file nothing
        points at is dead code that looks alive."""
        static = self._static()
        loaded = self._loaded_scripts()

        missing = [name for name in loaded if not (static / name).is_file()]
        assert not missing, f"the page loads scripts that do not exist: {missing}"

        unloaded = sorted({p.name for p in static.glob("*.js")} - set(loaded))
        assert not unloaded, f"these scripts exist but nothing loads them: {unloaded}"

    def test_every_button_is_referenced_by_the_script(self):
        import re

        markup, script = self._sources()

        # Buttons the script never needs to touch: they submit a form the
        # script already handles, or they are labels for an input.
        handled_by_form = {"send"}

        orphans = []
        for tag in re.findall(r"<button\b[^>]*>", markup):
            match = re.search(r'id="([^"]+)"', tag)
            if not match:
                continue
            element = match.group(1)
            if element in handled_by_form:
                continue
            if f'"{element}"' not in script:
                orphans.append(element)

        assert not orphans, f"buttons with no script reference: {orphans}"

    def test_every_scripted_element_exists_in_the_markup(self):
        """The other direction: a handler bound to an id the page no longer
        has throws on load and takes every handler after it with it."""
        import re

        markup, script = self._sources()
        declared = set(re.findall(r'id="([^"]+)"', markup))
        # Rows the script builds itself — the "working" bubble, the upload
        # progress lines — are not in the markup and are not meant to be.
        declared |= set(re.findall(r'\.id = "([^"]+)"', script))
        declared |= set(re.findall(r'id="([^"$]*)\$\{', script))

        missing = sorted({
            name for name in re.findall(r'\$\("([A-Za-z][\w-]*)"\)', script)
            if name not in declared
        })
        assert not missing, f"script binds ids the page does not have: {missing}"

    def test_the_controls_that_carry_the_flow_have_handlers(self):
        """Named explicitly, because these are the ones whose failure is
        invisible — the page looks right and the button does nothing."""
        import re

        _, script = self._sources()

        for element in ("attachBtn", "confirm", "new", "restart", "cancel",
                        "reviseBtn", "editSave", "editCancel", "resumeBtn",
                        "petitionsRetry", "clearFilters",
                        # Deletion is irreversible: a Delete button with no
                        # handler is harmless, but one whose confirmation
                        # handler went missing would not be.
                        "deleteSelected", "clearSelection", "selectAllMatching"):
            bound = re.search(
                rf'\$\("{element}"\)\.(onclick|onsubmit)\s*=|'
                rf'\$\("{element}"\)\.addEventListener',
                script)
            assert bound, f"{element} has no handler"

    def test_navigation_routes_are_handled(self):
        """Every `data-route` the page offers must be one `navigate` knows."""
        import re

        markup, script = self._sources()
        offered = set(re.findall(r'data-route="([^"]+)"', markup))

        assert offered, "the header offers no navigation at all"
        for route in offered:
            assert f'"{route}"' in script, f"no handling for route {route!r}"


class TestTheDocumentAppearsWhereTheAnimationPlayed:
    """The drafting panel and the finished petition are one slot, not two.

    Before this, the page had three different layouts: chat beside details
    while the questions were asked, a three-column arrangement with the
    animation in the middle while the petition was written, and then a fourth
    rearrangement when it was ready — the document taking the left column and
    the conversation moving to a narrow one on the right. A citizen watched a
    panel fill in, and then the whole page moved and the document they were
    waiting for was somewhere else.

    Measured in a browser, all three now occupy the same rectangle. These are
    the static guarantees that keep it that way, because a single stray
    `grid-column` in a media query is enough to pull them apart again and
    nothing else would notice.
    """

    @staticmethod
    def _css() -> str:
        from pathlib import Path

        return (Path("app/static") / "app.css").read_text(encoding="utf-8")

    @staticmethod
    def _script() -> str:
        from pathlib import Path

        return (Path("app/static") / "app.js").read_text(encoding="utf-8")

    def test_every_rule_that_places_the_stage_places_the_document_with_it(self):
        """`.genpanel` and `.middle` must be positioned by the SAME rule.

        Sharing a declaration block is what makes them share a cell: two rules
        that happen to agree today drift apart the next time one is edited.
        """
        import re

        orphans = []
        for match in re.finditer(r"(?m)^([^\n{}]*\.genpanel[^\n{}]*)\{([^}]*)\}", self._css()):
            selector, body = match.group(1), match.group(2)
            if "grid-column" not in body and "grid-row" not in body:
                continue
            if ".middle" not in selector:
                orphans.append(selector.strip())

        assert not orphans, (
            "these rules place the drafting panel without placing the document "
            f"in the same cell: {orphans}")

    def test_the_stage_stands_in_front_of_the_document_while_it_works(self):
        """Both live in one cell, so exactly one may be visible at a time.

        This is also what makes a change made AFTER the petition exists play in
        the same place: the panel opens over the document it is about to
        replace, rather than opening somewhere new or not at all.
        """
        assert "main.workspace.generating .middle{display:none}" in self._css()

    def test_the_finished_layout_is_the_drafting_layout(self):
        """One `grid-template-columns` for both states. If they differ, the
        page reflows at the exact moment the citizen starts reading."""
        import re

        css = self._css()
        shared = re.search(
            r"(?m)^main\.workspace\.generating,main\.workspace\.done\{([^}]*)\}", css)
        assert shared, "the two states no longer share a grid definition"
        assert "grid-template-columns" in shared.group(1)

        for state in ("generating", "done"):
            alone = re.search(
                rf"(?m)^main\.workspace\.{state}\{{([^}}]*grid-template-columns[^}}]*)\}}", css)
            assert not alone, (
                f"`.{state}` has a grid of its own again: {alone.group(1) if alone else ''}")

    def test_a_change_made_afterwards_opens_the_same_panel(self):
        """Typed, spoken, edited by hand — three routes into one panel, and
        each one checked where it actually is. A count of the calls is not
        enough: dropping one of four still leaves three."""
        script = self._script()

        # (what opens the work, where to look relative to it)
        routes = [
            ("/api/sessions/${sid}/confirm", "before", "the first draft"),
            ("/api/sessions/${sid}/message", "before", "a typed change"),
            ("/api/sessions/${sid}/document/text", "before", "a hand edit"),
            ('case "stt.final":', "after", "a spoken change"),
        ]
        for anchor, side, what in routes:
            assert anchor in script, f"{what}: {anchor!r} is gone from the page"
            at = script.index(anchor)
            # Wide enough to clear the comment that explains each one.
            window = script[max(0, at - 800):at] if side == "before"                 else script[at:at + 800]
            assert "beginDocumentWork(" in window, (
                f"{what} no longer opens the drafting panel")

    def test_the_panel_never_opens_for_work_that_takes_no_time(self):
        """A question answered instantly must not blank the petition and put it
        straight back, so a change waits a moment before claiming the slot."""
        script = self._script()

        assert "DOC_WORK_DELAY_MS" in script
        assert "docWorkTimer" in script
        # And any render must cancel a pending open, or the panel appears after
        # the answer is already on screen and nothing is left to close it.
        assert '!$("genPanel").hidden || docWorkTimer' in script

    def test_the_revision_wording_exists_in_both_languages(self):
        """A Tamil citizen watching `undefined` scroll past is the failure this
        prevents; the panel is drawn from these keys with no fallback."""
        import re

        script = self._script()

        titles = re.findall(r"reviseTitle: \"([^\"]+)\"", script)
        assert len(titles) == 2, f"expected one title per language, found {titles}"
        assert titles[0] != titles[1], "the Tamil title is still the English one"

        rails = re.findall(r"reviseSteps: \[(.*?)\]", script, re.S)
        assert len(rails) == 2, "expected one rail per language"
        counts = [entry.count('"') // 2 for entry in rails]
        assert counts[0] == counts[1], f"the rails have different lengths: {counts}"

    def test_the_workspace_height_matches_what_sits_above_it(self):
        """Header 78 + intro 150 + stepper 62 = 290, measured in a browser. The
        constant was 281 and every page scrolled by the missing nine pixels."""
        assert "height:calc(100dvh - 290px)" in self._css()
