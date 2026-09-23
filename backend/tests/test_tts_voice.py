"""Which voice the assistant speaks in, and why a typo here is expensive.

A wrong speaker name is the worst kind of configuration error: Sarvam
answers HTTP 400, `tts.stream` logs it and yields nothing, and the citizen
gets a service that has quietly stopped talking. Nothing fails, nothing is
red, and the reason is one line in a log nobody is reading.

The name is also CASE-SENSITIVE, while Sarvam's own console displays these
voices capitalised — "Ishita". Choosing a voice there and copying the label
across is the obvious way to set this, and it is exactly the thing the API
rejects. So the value is lowercased on the way out, and that is what most of
this file is about.

These tests make no network calls. The speaker list below was read from the
live API's own error message, which names every speaker it accepts.
"""

from __future__ import annotations

import pytest

from app.config import get_settings

# Verified against api.sarvam.ai for bulbul:v3 — the API lists these itself
# when given a name it does not know. If Sarvam adds a voice and somebody
# picks it, this list is what needs updating, and the failure says so.
BULBUL_V3_SPEAKERS = frozenset({
    "aditya", "ritu", "ashutosh", "priya", "neha", "rahul", "pooja", "rohan",
    "simran", "kavya", "amit", "dev", "ishita", "shreya", "ratan", "varun",
    "manan", "sumit", "roopa", "kabir", "aayan", "shubh", "advait", "anand",
    "tanya", "tarun", "sunny", "mani", "gokul", "vijay", "shruti", "suhani",
    "mohit", "kavitha", "rehan", "soham", "rupali",
})


def shipped_default() -> str:
    """The speaker PRODUCTION uses.

    Not `get_settings().sarvam_tts_speaker`, which on a developer machine is
    whatever `.env` says. The deploy writes app.env from a fixed list that
    does not include this variable, so what actually ships is the field
    default — and a test that read the resolved setting passed happily with
    a typo in the default, because the local .env was covering for it.
    """
    from app.config import Settings

    return str(Settings.model_fields["sarvam_tts_speaker"].default).strip().lower()


def payload_for(speaker: str) -> dict:
    """What `tts.stream` will actually send, for a given configured speaker.

    Calls the real builder. Restating the expression here would keep
    passing while the request changed underneath it.
    """
    from app.services.tts import request_for

    settings = get_settings()
    was = settings.sarvam_tts_speaker
    settings.sarvam_tts_speaker = speaker
    try:
        return request_for("ta", settings)
    finally:
        settings.sarvam_tts_speaker = was


class TestTheConfiguredVoice:

    def test_the_shipped_default_is_a_voice_the_model_actually_has(self):
        """A name the API does not know means silence, not an error the
        citizen ever sees. Checked against the default rather than the
        resolved setting, because the default is what production runs."""
        speaker = shipped_default()

        assert speaker in BULBUL_V3_SPEAKERS, (
            f"{speaker!r} is not a bulbul:v3 voice. The API lists the ones it "
            "accepts in its own 400 response; update BULBUL_V3_SPEAKERS if "
            "Sarvam has added one.")

    def test_the_shipped_default_is_the_voice_that_was_chosen(self):
        assert shipped_default() == "ishita"

    def test_whatever_this_machine_is_set_to_is_also_real(self):
        """A developer .env can override it, and a typo there is the same
        silence on that machine."""
        speaker = (get_settings().sarvam_tts_speaker or "").strip().lower()

        assert speaker in BULBUL_V3_SPEAKERS, speaker

    def test_the_model_is_the_one_those_voices_belong_to(self):
        """The speaker list is per model. bulbul:v2 is retired and answers
        "has been deprecated"; its speakers are not v3 speakers."""
        assert get_settings().sarvam_tts_model == "bulbul:v3"


class TestTheNameIsSentAsTheApiWantsIt:
    """The API is case-sensitive; the console that names these voices is
    not. That mismatch is a silent outage waiting to be configured."""

    @pytest.mark.parametrize("written", ["ishita", "Ishita", "ISHITA", "  Ishita  "])
    def test_every_spelling_of_a_real_voice_reaches_the_api_correctly(self, written):
        assert payload_for(written)["speaker"] == "ishita"

    def test_the_request_the_stream_sends_is_the_one_built_here(self):
        """`stream` must USE `request_for`, or everything above measures a
        function nothing calls."""
        import pathlib

        source = pathlib.Path("app/services/tts.py").read_text(encoding="utf-8")

        assert "payload_base = request_for(language, s)" in source

    @pytest.mark.parametrize("language,expected", [("ta", "ta-IN"), ("en", "en-IN")])
    def test_the_language_goes_with_it(self, language, expected):
        from app.services.tts import request_for

        assert request_for(language)["target_language_code"] == expected


class TestHowFastItSpeaks:
    """`pace` is a deployment decision — a counter serving elderly citizens
    may want 0.8 — and it is also a way to mute the service by accident."""

    def test_the_request_carries_a_pace_and_a_sample_rate(self):
        from app.services.tts import request_for

        sent = request_for("ta")
        assert sent["pace"] == 1.0
        assert sent["speech_sample_rate"] == 22050

    @pytest.mark.parametrize("asked,used", [
        (0.5, 0.5), (0.8, 0.8), (1.0, 1.0), (2.0, 2.0),
        (0.3, 0.5),      # below what bulbul:v3 accepts
        (2.5, 2.0),      # above it
        (0.0, 0.5),
    ])
    def test_a_pace_the_model_refuses_is_held_not_sent(self, asked, used):
        """CLAMPED, not rejected. Outside 0.5-2.0 the API answers HTTP 400,
        `stream` logs it and yields nothing, and the citizen gets an
        assistant that has simply stopped talking. Somebody setting 0.3
        wants slow speech; the slowest the model has serves that, and a
        silent service serves nobody."""
        from app.services.tts import clamped_pace

        assert clamped_pace(asked) == used

    @pytest.mark.parametrize("nonsense", ["fast", None, ""])
    def test_a_pace_that_is_not_a_number_falls_back_to_normal(self, nonsense):
        from app.services.tts import clamped_pace

        assert clamped_pace(nonsense) == 1.0

    def test_the_range_is_the_models_own(self):
        """Read from the API's own 400 message: "For the Bulbul V3 and V4
        models, pace should be between 0.5 and 2.0"."""
        from app.services.tts import PACE_RANGE

        assert PACE_RANGE == (0.5, 2.0)

    def test_the_sample_rate_is_what_the_model_already_returns(self):
        """Sent explicitly so a change to the model's default cannot alter
        the audio underneath us without anyone noticing. Verified against
        the live API: it returns 22050Hz 16-bit mono."""
        assert get_settings().sarvam_tts_sample_rate == 22050
