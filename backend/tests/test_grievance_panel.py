"""The grievance uses the existing editable composer, without voice panels."""
from pathlib import Path

import pytest

STATIC = Path("app/static")

@pytest.mark.parametrize("element_id", ["voiceBar", "voiceWave", "dictation", "dictationText", "answerCheck", "grievanceDone"])
def test_removed_voice_panels_are_not_in_the_page(element_id):
    assert f'id="{element_id}"' not in (STATIC / "index.html").read_text(encoding="utf-8")


def test_compact_status_and_existing_composer_remain():
    html=(STATIC / "index.html").read_text(encoding="utf-8")
    for element_id in ("text", "micInline", "send", "dictationStatus"):
        assert f'id="{element_id}"' in html
    assert 'aria-live="polite"' in html


def test_manual_dictation_has_no_submission_or_confirmation_calls():
    source=(STATIC / "app.js").read_text(encoding="utf-8")
    voice=source[source.index("/* Manual dictation"):source.index("/* ------------------------------------------------------------ system panel")]
    for forbidden in ("/message", "answer.confirm", "voice.start", "requestSubmit", "mutate("):
        assert forbidden not in voice
    assert "committedText" in voice and "partialText" in voice


def test_mobile_state_is_confined_to_the_microphone():
    css=(STATIC / "app.css").read_text(encoding="utf-8")
    assert "#micInline.dictating" in css
    assert ".dictation-status" in css

def _app_js():
    return (STATIC / "app.js").read_text(encoding="utf-8")


def _dictation_block():
    source = _app_js()
    return source[source.index("/* Manual dictation"):
                  source.index("/* ------------------------------------------------------------ system panel")]


# ---------------------------------------------------------------------------
# The microphone is the whole feature now
# ---------------------------------------------------------------------------
#
# `test_regressions.py` checks every button is REFERENCED by the script, and
# that is all it checks. Deleting the microphone's click handler left the id
# mentioned in `paintVoice` and the check passed — a button that does nothing,
# in the one place the citizen now starts and stops every recording.

def test_the_microphone_actually_has_a_click_handler():
    import re

    assert re.search(r"""\$\(['"]micInline['"]\)\.onclick\s*=""", _app_js())


def test_it_is_a_toggle():
    """One button, both directions. The brief: click once to start, click
    again to stop — not a second control, and not a hold-to-talk."""
    block = _dictation_block()
    fn = block[block.index("async function toggleDictation"):]
    fn = fn[:fn.index("\nfunction ")]

    assert "typing.phase === 'recording'" in fn
    assert "stopDictation()" in fn


def test_the_assistant_speaking_disables_the_microphone():
    """The only self-transcription guard left, and the only one needed: the
    microphone cannot be opened while the reply is playing out of the
    speaker beside it."""
    block = _dictation_block()

    assert "mic.disabled = typing.speaking" in block


def test_nothing_starts_the_microphone_when_the_assistant_stops_talking():
    """The rule the whole redesign turns on. The old build went from
    TTS_FINISHED to LISTENING on its own; this one goes to idle and waits to
    be asked. `stopPlayback` is what runs when the audio ends."""
    block = _dictation_block()
    fn = block[block.index("function stopPlayback"):]
    fn = fn[:fn.index("\nasync function ")]

    assert "typing.speaking=false" in fn.replace(" ", "")
    for starts_recording in ("toggleDictation", "getUserMedia", "new WebSocket"):
        assert starts_recording not in fn, starts_recording


def test_a_final_segment_is_only_ever_counted_once():
    """Providers repeat finals on a retry or a reconnect. Counted twice, a
    sentence appears twice in somebody's grievance."""
    block = _dictation_block()

    assert "typing.finals.has(id)" in block
    assert "typing.finals.add(id)" in block


def test_a_hand_edit_wins_over_a_transcript_still_in_flight():
    """The citizen corrected a word while a result was already on the wire.
    Applying it would undo the correction in front of them."""
    block = _dictation_block()

    assert "$('text').value !== typing.rendered" in block


def test_starting_again_keeps_what_is_already_in_the_box():
    """Append, never replace — the grievance is built over several
    dictations, and a second press must not wipe the first."""
    block = _dictation_block()
    fn = block[block.index("async function toggleDictation"):]

    # The box is READ into the committed buffer, so whatever is there
    # already survives and the new words land after it.
    assert "typing.committedText=$('text').value" in fn.replace(" ", "")
    # And joined with a space rather than glued on.
    assert "joinDictation" in _dictation_block()


def test_every_way_dictation_ends_keeps_the_text():
    """Permission refused, provider down, socket dropped, length capped —
    `closeDictation` runs for all of them, and it reads the box rather than
    writing to it."""
    block = _dictation_block()
    fn = block[block.index("function closeDictation"):]
    fn = fn[:fn.index("\nfunction stopVoice")]

    assert "typing.committedText = $('text').value" in fn
    assert "$('text').value =" not in fn, "it writes back over what the citizen has"
