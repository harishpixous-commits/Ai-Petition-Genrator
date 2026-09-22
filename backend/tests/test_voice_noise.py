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
import re

from app.services.voice import VadSettings, VoiceActivityDetector


def read(name: str) -> str:
    return pathlib.Path("app/static", name).read_text(encoding="utf-8")


class TestTheBrowserProcessingIsAskedFor:

    def test_all_three_constraints_are_requested(self):
        js = read("app.js")
        call = js[js.index("async function openMicrophone"):]
        call = call[:call.index("voice.ctx = new AudioContext")]

        for constraint in ("echoCancellation: true", "noiseSuppression: true",
                           "autoGainControl: true"):
            assert constraint in call, constraint

    def test_what_was_granted_is_read_back_from_the_track(self):
        """Asked for is not the same as got. These are advisory constraints —
        Firefox applies some, a conference microphone doing its own
        processing may refuse, and none of that fails `getUserMedia`."""
        js = read("app.js")

        assert "getSettings()" in js
        assert "noiseSuppression\" in settings" in js

    def test_the_page_only_claims_it_when_the_track_confirms_it(self):
        """A reassurance the citizen cannot check is worse than none. The
        check is for an explicit `true`, so a browser that reports nothing
        reads as unknown rather than as on."""
        js = read("app.js")
        paint = js[js.index("const note = $(\"voiceNote\")"):]
        paint = paint[:paint.index("// The header button")]

        assert "voice.processing.noise === true" in paint

    def test_the_citizen_is_told_in_both_languages(self):
        js = read("app.js")

        assert "✓ Noise reduction active" in js
        assert "பின்னணி சத்தம் குறைக்கப்படுகிறது" in js

    def test_no_technical_detail_reaches_that_line(self):
        """RMS, thresholds and codecs belong in the developer panel, which is
        off in production. A citizen at a counter is not debugging audio."""
        js = read("app.js")
        block = js[js.index("const note = $(\"voiceNote\")"):]
        block = block[:block.index("// The header button")]

        for leak in ("rms", "snr", "threshold", "dB", "codec"):
            assert leak.lower() not in block.lower(), leak


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


class TestTheWaveformIgnoresTheRoom:
    """Display only. A ribbon driven by raw level sits permanently
    half-height next to a fan, which reads as the microphone hearing someone
    when it is hearing furniture."""

    def test_it_is_driven_by_what_is_above_the_floor(self):
        js = read("app.js")
        drive = js[js.index("function waveDrive"):]
        drive = drive[:drive.index("function drawWave")]

        assert "voiceAboveTheRoom()" in drive
        assert re.search(r"voice\.rms\s*/", drive) is None, (
            "the waveform still reads raw level somewhere")

    def test_the_floor_falls_faster_than_it_rises(self):
        """Rising as fast as it falls would let a long spoken answer teach
        the meter that speech is background, flattening the ribbon in the
        middle of a sentence."""
        js = read("app.js")
        block = js[js.index("// Track the room"):]
        block = block[:block.index("if (voice.playAnalyser)")]
        numbers = [float(n) for n in re.findall(r"0\.\d+", block)]

        assert numbers, block
        assert max(numbers) > min(numbers) * 10

    def test_it_gates_nothing(self):
        """The server decides what was said, on audio this never touches."""
        js = read("app.js")
        send = js[js.index("voice.node.onaudioprocess"):]
        send = send[:send.index("voice.socket.send(pcm.buffer)")]

        assert "floorRms" not in send
        assert "voiceAboveTheRoom" not in send
