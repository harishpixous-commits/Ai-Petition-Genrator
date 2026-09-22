"""The names the voice session goes by, and the fact that they all mean something.

A voice session is a state machine in two halves. The server owns the half it
can know about — it is listening, it heard something, it is thinking — and
sends each one to the page by name. The page owns the half the server cannot
see: connecting, reconnecting, ended. Neither half is complete, and the page
renders both from one table.

That split is the whole hazard. A state added on the server arrives at a page
that has no word for it and no colour for it, and the failure is silent: the
status line goes blank, the button goes grey, and everything else still works.
Nothing throws. So the tests here are mostly about the seam — that every name
one half can send, the other half can say out loud, in both languages.

The state that prompted the file is GENERATING. PROCESSING already existed and
already meant "busy", so writing the petition reported PROCESSING and the panel
read "Thinking…" for as long as composition took. That is two and a half
minutes in the worst measured case. Two and a half minutes of "Thinking…" is
not a status, it is a hang — and the citizen's only remedy, reloading, is the
one thing that loses the turn.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.api.ws import Phase

STATIC = Path("app/static")


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def block(source: str, opener: str, start: int = 0) -> str:
    """The text between `opener` and its matching close brace."""
    at = source.index(opener, start)
    depth, i = 0, at + len(opener) - 1
    while True:
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[at:i + 1]
        i += 1


def page_states() -> set[str]:
    """Every state the page has a constant for."""
    return set(re.findall(r'"([a-z_]+)"', block(read("app.js"), "const VOICE = {")))


def labels() -> list[dict[str, str]]:
    """The voice status strings, one dictionary per language."""
    source = read("app.js")
    out, at = [], 0
    while True:
        try:
            found = block(source, "voiceState: {", at)
        except ValueError:
            return out
        out.append(dict(re.findall(r"(\w+):\s*\"([^\"]*)\"", found)))
        at = source.index(found, at) + len(found)


class TestTheTwoHalvesAgree:
    def test_more_than_one_language_is_being_checked(self):
        """If the parser silently found one table, every test below that
        compares languages would pass by having nothing to compare."""
        assert len(labels()) >= 2, "the Tamil status strings were not found"

    def test_every_state_the_server_can_send_the_page_knows(self):
        missing = {p.value for p in Phase} - page_states()

        assert not missing, f"the server can report states the page cannot show: {missing}"

    def test_every_state_the_page_knows_it_can_say(self):
        """Including the three the server never sends. `connecting`,
        `reconnecting` and `ended` are the page's own, and a citizen watching a
        reconnection needs the word for it as much as any other."""
        for table in labels():
            missing = page_states() - set(table)
            assert not missing, f"states with no status text: {missing}"

    def test_none_of_the_status_texts_are_empty(self):
        for table in labels():
            blank = [k for k, v in table.items() if not v.strip()]
            assert not blank, f"states with a blank status line: {blank}"

    def test_the_languages_cover_the_same_states(self):
        first, *rest = labels()
        for other in rest:
            assert set(first) == set(other)


class TestTheLongWaitIsNamedApartFromTheShortOne:
    """Composition is not thinking. It takes a hundred times longer."""

    def test_the_server_has_a_state_for_writing_the_petition(self):
        assert Phase.GENERATING.value == "generating"

    def test_it_is_not_the_same_state_as_thinking(self):
        assert Phase.GENERATING is not Phase.PROCESSING

    def test_the_announcer_is_what_sets_it(self):
        """Nothing here decides that composition has started; the confirm node
        records it and the announcer relays it. If the phase is set anywhere
        else it is being guessed at."""
        socket = Path("app/api/ws.py").read_text(encoding="utf-8")
        body = socket[socket.index("async def announce_generation"):]
        body = body[:body.index("async def run_turn")]

        assert "set_phase(Phase.GENERATING)" in body
        # Counts the ASSIGNMENT, not the mention. Counting mentions also
        # caught reads — the watchdog names GENERATING to know it is a busy
        # phase and must not time the session out mid-composition — and a
        # test that fails on a correct read teaches people to delete the
        # test rather than to keep the rule.
        assert socket.count("set_phase(Phase.GENERATING)") == 1, (
            "the generating phase is set somewhere other than the announcer")

    def test_the_two_waits_do_not_read_the_same_to_a_citizen(self):
        """The bug was that they did. Distinct states with identical wording
        would be the same bug with more code."""
        for table in labels():
            # `.get`, not `[]`: a missing label is a different fault with its
            # own test above, and a KeyError here would only bury that one's
            # message under a worse one.
            assert table.get("generating") and table.get("processing")
            assert table["generating"] != table["processing"], table["generating"]


class TestNothingElseTookTheOldStateForGranted:
    """Two guards tested for PROCESSING by name, and composition used to be
    PROCESSING. Both would have gone quiet rather than wrong."""

    def test_the_recovery_poll_stays_off_a_composition(self):
        """It fetches a snapshot that waits on the lock the turn is holding,
        with a fifteen second timeout — so during a composition that is going
        perfectly well it can only report a connection that was never lost."""
        script = read("app.js")
        at = script.index("generationPoll = setTimeout(recover")
        window = script[max(0, at - 900):at]

        assert "voiceTurn" in window
        for state in ("VOICE.PROCESSING", "VOICE.GENERATING"):
            assert state in window, f"the poll no longer spares a {state} turn"

    def test_the_waveform_does_not_pretend_to_hear(self):
        """Nothing is being said or heard while the petition is written. The
        ribbon takes the working pulse; falling through to the default would
        give it the listening motion, which reads as a live microphone."""
        script = read("app.js")
        at = script.index("s === VOICE.TRANSCRIBING")
        line = script[script.rindex("if (", 0, at):script.index("{", at)]

        assert "VOICE.GENERATING" in line, line.strip()


class TestTheButtonRuleMatchesTheStateItNames:
    """The header button's class is `voice-` plus the state value verbatim, so
    a rule named for a state that does not exist is dead CSS — and dead CSS is
    invisible: the button just stays grey. `.voice-speaking` was that, for as
    long as the state has been called `assistant_speaking`."""

    def test_every_state_rule_names_a_real_state(self):
        rules = set(re.findall(r"\.hbtn\.voice-([a-z_]+)", read("app.css")))
        assert rules, "the button state rules have gone"

        unreachable = rules - page_states()
        assert not unreachable, f"CSS for states that cannot occur: {unreachable}"

    @staticmethod
    def _declarations(css: str, state: str) -> str:
        """What the button is styled as in one state.

        Looks the rule up by the SELECTOR it contains rather than by an exact
        string, because states that should look the same are grouped — a
        read-back is the assistant speaking and shares its colour. Pinning
        the spelling instead made grouping two states fail a test about
        whether two OTHER states differ.
        """
        # Comments first. A `/* ... */` above a rule is part of the text
        # between the previous `}` and this `{`, so without this the selector
        # never matches and every rule reads as absent — which looks exactly
        # like the missing-CSS bug these tests exist to catch.
        css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            names = [part.strip() for part in selectors.split(",")]
            if f".hbtn.voice-{state}" in names:
                return body.strip()
        return ""

    def test_the_two_busy_states_are_told_apart(self):
        css = read("app.css")
        speaking = self._declarations(css, "assistant_speaking")
        generating = self._declarations(css, "generating")
        assert speaking, "no rule for the assistant speaking"
        assert generating, "no rule for writing the petition"
        assert speaking != generating, (
            "the two waits look identical, which is the bug the states exist to fix")

    def test_a_read_back_looks_like_the_assistant_speaking(self):
        """Because it is. A separate colour for it would say something
        changed about the session when only the question did."""
        css = read("app.css")
        assert (self._declarations(css, "reading_back")
                == self._declarations(css, "assistant_speaking") != "")

    def test_waiting_for_agreement_still_looks_like_an_open_microphone(self):
        """The citizen can answer by speaking. A neutral button there reads
        as voice having stopped, and they press Start Voice again — which is
        the one thing this whole loop is meant to stop them having to do."""
        css = read("app.css")
        assert (self._declarations(css, "waiting_confirmation")
                == self._declarations(css, "listening") != "")


class TestAFailedUtteranceIsNotAFailedSession:
    """One transcription that did not come back is not dictation stopping.

    The microphone is still open, the session is still running, and the next
    thing the citizen says will be heard. Reporting that as "Dictation has
    stopped. You can type instead." is false, and expensively so: it sends
    someone to the keyboard at the exact moment saying it again would have
    worked. Both sentences still exist, because both situations do.
    """

    @staticmethod
    def _socket() -> str:
        return Path("app/api/ws.py").read_text(encoding="utf-8")

    def test_there_is_a_sentence_for_each_situation(self):
        from app.domain.phrasing import phrase

        for language in ("en", "ta"):
            failed = phrase("dictation_failed", language)
            stopped = phrase("dictation_stopped", language)
            assert failed and stopped
            assert failed != stopped, language

    def test_the_one_for_a_lost_utterance_does_not_say_it_stopped(self):
        from app.domain.phrasing import phrase

        said = phrase("dictation_failed", "en").lower()
        assert "stopped" not in said, said
        assert "again" in said, "it does not tell the citizen to try again"

    def test_the_one_for_a_lost_utterance_still_offers_the_keyboard(self):
        """Recoverable does not mean they have to keep talking."""
        from app.domain.phrasing import phrase

        assert "type" in phrase("dictation_failed", "en").lower()

    def test_which_one_is_sent_depends_on_whether_it_is_still_listening(self):
        socket = self._socket()
        at = socket.index('log.warning("asr.transcribe.failed"')
        window = socket[at:at + 1400]

        assert '"dictation_failed" if listening else "dictation_stopped"' in window, window[:400]

    def test_and_it_is_reported_as_recoverable(self):
        """Marked unrecoverable the page tears the session down and shows the
        hard-failure banner — for one utterance that can simply be repeated."""
        socket = self._socket()
        at = socket.index('log.warning("asr.transcribe.failed"')
        window = socket[at:at + 1400]

        assert '"recoverable": True' in window
