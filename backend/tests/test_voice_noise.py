"""Handling a noisy room, without punishing the citizen standing in one.

THE RULE. Noise changes what the assistant SAYS, never what it accepts. A
government counter has a fan, a queue and a printer in it; a voice interface
that only works in a quiet room does not work. The speech threshold is
already relative to the measured floor, so a loud room raises the bar rather
than closing the door, and the advisory exists for the point where raising
the bar starts to cost a soft-voiced citizen their answer.

The browser's own echo cancellation, noise suppression and gain control are
requested on the page. These tests cover the parts that live here — the
advisory, and the claim the page is allowed to make about that processing.
"""

from __future__ import annotations

import pathlib

from app.services.voice import VadSettings, VoiceActivityDetector


def read(name: str) -> str:
    return pathlib.Path("app/static", name).read_text(encoding="utf-8")




class TestTheAdvisory:

    def test_there_is_a_sentence_for_it_in_both_languages(self):
        from app.services.speech_text import phrase

        assert phrase("noisy_room", "en") == (
            "High background noise detected. Please speak a little closer "
            "to the microphone.")
        assert phrase("noisy_room", "ta") == (
            "பின்னணி சத்தம் அதிகமாக உள்ளது. மைக்ரோஃபோனுக்கு அருகில் பேசுங்கள்.")

    def test_it_is_said_once_and_not_repeated(self):
        """A warning repeated every few seconds in a busy office is noise of
        its own."""
        socket = pathlib.Path("app/api/ws.py").read_text(encoding="utf-8")
        body = socket[socket.index("async def check_the_room"):]
        body = body[:body.index("async def watchdog")]

        assert "if noise_advised" in body
        assert "noise_advised = True" in body

    def test_it_takes_several_agreeing_checks(self):
        """A door slamming is not a noisy room."""
        socket = pathlib.Path("app/api/ws.py").read_text(encoding="utf-8")
        body = socket[socket.index("async def check_the_room"):]
        body = body[:body.index("async def watchdog")]

        assert "voice_noise_advisory_checks" in body
        assert "loud_checks = 0" in body

    def test_nothing_is_rejected_because_of_it(self):
        """THE thing that must never happen. The advisory may speak; it may
        not discard, may not raise a threshold, and may not stop listening."""
        socket = pathlib.Path("app/api/ws.py").read_text(encoding="utf-8")
        body = socket[socket.index("async def check_the_room"):]
        body = body[:body.index("async def watchdog")]

        for forbidden in ("send_discarded", "listening = False", "guard.",
                          "eos.abandon", "Verdict."):
            assert forbidden not in body, forbidden


class TestTheDetectorStillAdaptsToTheRoom:
    """The advisory is a message. THIS is what actually makes a noisy room
    workable, and it is unchanged."""

    def test_the_threshold_follows_the_measured_floor(self):
        quiet = VoiceActivityDetector(VadSettings())
        loud = VoiceActivityDetector(VadSettings())

        # Room tone at two very different levels, long enough to calibrate.
        quiet.feed(bytes(b"\x10\x00" * 8192))
        loud.feed(bytes(b"\x00\x08" * 8192))

        assert loud.noise_floor > quiet.noise_floor
        assert loud.speech_threshold >= quiet.speech_threshold

    def test_a_quiet_room_never_drops_below_the_absolute_floor(self):
        """Otherwise a silent room makes its own hiss significant by
        comparison, and every frame becomes speech."""
        detector = VoiceActivityDetector(VadSettings())
        detector.feed(bytes(8192 * 2))

        assert detector.speech_threshold >= VadSettings().floor_rms




class TestManualCapture:
    def test_processing_constraints_without_vad_rejection(self):
        source=read("app.js")
        capture=source[source.index("async function toggleDictation"):source.index("function stopPlayback")]
        for constraint in ("echoCancellation:true", "noiseSuppression:true", "autoGainControl:true"):
            assert constraint in capture
        assert "floorRms" not in capture
        assert "bargeIn" not in capture

    def test_no_noise_reduction_claim_or_waveform(self):
        html=read("index.html")
        assert 'id="voiceNote"' not in html
        assert 'id="voiceWave"' not in html
