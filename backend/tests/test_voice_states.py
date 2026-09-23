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
