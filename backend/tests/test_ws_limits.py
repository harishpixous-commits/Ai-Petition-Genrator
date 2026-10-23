"""Limits on the voice socket, and the thing they must not break.

THE RISK IN THIS FILE IS NOT THAT THE LIMITS FAIL TO FIRE. It is that they
fire on a real citizen. A grievance is dictated, not typed, and somebody
describing a long dispute speaks for minutes with pauses in the middle. A
limit that cuts them off mid-sentence is worse than the abuse it prevents,
because the abuse costs the department money and this costs a citizen their
petition.

So the first class here measures a REALISTIC DICTATION against the configured
limits and asserts it passes with room to spare. The limits are only tested
for firing afterwards.
"""

from __future__ import annotations

import pytest

from app.api import ws_limits
from app.config import get_settings


@pytest.fixture
def limits() -> ws_limits.Limits:
    """The numbers the service actually runs with, not test values."""
    settings = get_settings()
    return ws_limits.Limits(
        max_connections=settings.ws_max_connections,
        max_per_client=settings.ws_max_connections_per_client,
        max_message_bytes=settings.ws_max_message_bytes,
        max_bytes_per_minute=settings.ws_max_bytes_per_minute,
        max_session_seconds=settings.ws_max_session_seconds,
    )


class TestARealCitizenNeverMeetsThese:
    """Every number below is the shape of ordinary use."""

    def test_a_full_minute_of_continuous_speech_fits_easily(self, limits):
        """16 kHz, 16-bit mono is 32,000 bytes a second. A citizen who talks
        without stopping for a whole minute must not be close to the limit."""
        settings = get_settings()
        per_second = settings.asr_sample_rate * 2
        a_minute = per_second * 60

        assert limits.max_bytes_per_minute > a_minute * 3, (
            f"a minute of speech is {a_minute:,} bytes against a limit of "
            f"{limits.max_bytes_per_minute:,} — too little headroom")

    def test_ten_minutes_of_dictation_is_never_cut_off(self, limits):
        """A long grievance, sent frame by frame at the real rate.

        Driven with an explicit clock rather than real time, so the test is
        fast and still exercises the same arithmetic the socket does.
        """
        session = ws_limits.Session(ws_limits.Gate(limits), "citizen")
        frame = 3200          # 100 ms of audio at 16 kHz, 16-bit mono
        now = session.started

        for tick in range(10 * 60 * 10):      # ten minutes of 100 ms frames
            now = session.started + tick * 0.1
            session.check(frame, now=now)

        assert session.frames_seen == 6000
        assert session.bytes_seen == 6000 * frame

    def test_a_long_pause_in_the_middle_is_fine(self, limits):
        """Somebody stops to think for two minutes and carries on. Nothing
        about that is abuse and nothing may close the socket."""
        session = ws_limits.Session(ws_limits.Gate(limits), "citizen")
        session.check(3200, now=session.started)
        session.check(3200, now=session.started + 120.0)
        assert session.frames_seen == 2

    def test_one_citizen_opening_the_page_twice_is_allowed(self, limits):
        """A reloaded tab briefly leaves two connections from one device."""
        gate = ws_limits.Gate(limits)
        gate.acquire("10.0.0.1")
        gate.acquire("10.0.0.1")
        assert gate.open_connections == 2


class TestTheLimitsDoFire:
    def test_an_oversized_frame_is_refused(self, limits):
        session = ws_limits.Session(ws_limits.Gate(limits), "c")
        with pytest.raises(ws_limits.LimitExceeded) as caught:
            session.check(limits.max_message_bytes + 1)
        assert caught.value.code == 1009

    def test_audio_faster_than_speech_is_refused(self, limits):
        """A client streaming as fast as the socket accepts, rather than at
        the speed a person talks."""
        session = ws_limits.Session(ws_limits.Gate(limits), "c")
        now = session.started
        with pytest.raises(ws_limits.LimitExceeded):
            for tick in range(10_000):
                session.check(limits.max_message_bytes, now=now + tick * 0.001)

    def test_a_session_cannot_stay_open_forever(self, limits):
        session = ws_limits.Session(ws_limits.Gate(limits), "c")
        with pytest.raises(ws_limits.LimitExceeded) as caught:
            session.check(100, now=session.started + limits.max_session_seconds + 1)
        # Closed as normal completion, not as an error: the citizen did
        # nothing wrong and their petition is saved.
        assert caught.value.code == 1000

    def test_one_client_cannot_hold_every_slot(self, limits):
        gate = ws_limits.Gate(limits)
        for _ in range(limits.max_per_client):
            gate.acquire("10.0.0.9")
        with pytest.raises(ws_limits.LimitExceeded):
            gate.acquire("10.0.0.9")

    def test_the_process_has_a_ceiling(self):
        gate = ws_limits.Gate(ws_limits.Limits(max_connections=3, max_per_client=3))
        for index in range(3):
            gate.acquire(f"client-{index}")
        with pytest.raises(ws_limits.LimitExceeded) as caught:
            gate.acquire("client-4")
        # 1013 "try again later", not 1008 "policy violation": the client did
        # nothing wrong, the service is simply full.
        assert caught.value.code == 1013

    def test_every_refusal_carries_something_sayable(self, limits):
        """A citizen at a kiosk whose microphone stops has to be told why."""
        gate = ws_limits.Gate(ws_limits.Limits(max_connections=1, max_per_client=1))
        gate.acquire("a")
        with pytest.raises(ws_limits.LimitExceeded) as caught:
            gate.acquire("b")
        assert len(caught.value.reason) > 20
        assert caught.value.reason[0].isupper()


class TestSlotsComeBack:
    def test_a_closed_session_frees_its_slot(self, limits):
        gate = ws_limits.Gate(limits)
        with gate.session("x"):
            gate.acquire("x")
            assert gate.open_connections == 1
        assert gate.open_connections == 0

    def test_a_session_that_raised_still_frees_its_slot(self, limits):
        """The failure mode that matters: an exception inside the socket must
        not leak a slot, or the service degrades one connection at a time
        until it refuses everybody."""
        gate = ws_limits.Gate(limits)
        gate.acquire("x")
        with pytest.raises(RuntimeError), gate.session("x"):
            raise RuntimeError("the socket blew up")
        assert gate.open_connections == 0

    def test_releasing_more_than_was_taken_cannot_go_negative(self, limits):
        gate = ws_limits.Gate(limits)
        gate.release("never-acquired")
        assert gate.open_connections == 0


class TestWhoTheClientIs:
    def test_the_forwarded_address_is_preferred(self):
        class Socket:
            headers = {"x-forwarded-for": "203.0.113.7, 10.0.0.1"}
            client = type("C", (), {"host": "10.0.0.1"})()

        assert ws_limits.client_key(Socket()) == "203.0.113.7"

    def test_the_peer_address_is_used_when_nothing_is_forwarded(self):
        class Socket:
            headers: dict[str, str] = {}
            client = type("C", (), {"host": "198.51.100.4"})()

        assert ws_limits.client_key(Socket()) == "198.51.100.4"

    def test_an_unknown_peer_does_not_crash_the_handshake(self):
        class Socket:
            headers: dict[str, str] = {}
            client = None

        assert ws_limits.client_key(Socket()) == "unknown"
