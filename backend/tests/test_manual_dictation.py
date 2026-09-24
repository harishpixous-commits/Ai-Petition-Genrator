"""Manual dictation transport cannot submit a workflow answer."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import dictation
from app.services.asr import Transcript


class Stream:
    def __init__(self):
        self.results = asyncio.Queue()
        self.received = []

    async def send_audio(self, chunk):
        self.received.append(chunk)
        await self.results.put(Transcript('My street', False, 1))
        await self.results.put(Transcript('My street has no water.', True, 1))

    async def stop(self):
        await self.results.put(Transcript('Please repair it.', True, 2))
        await self.results.put(None)

    async def close(self):
        pass

    async def __aiter__(self):
        while (item := await self.results.get()) is not None:
            yield item


@pytest.fixture
def setup(monkeypatch):
    app = FastAPI()
    app.include_router(dictation.router)
    workflow = SimpleNamespace(snapshot=AsyncMock(return_value={'language':'ta'}), invoke=AsyncMock())
    app.state.workflow = workflow
    monkeypatch.setattr(dictation, 'citizen_scope', lambda _: None)
    monkeypatch.setattr(dictation.asr, 'choose_provider', lambda _: 'deepgram')
    stream = Stream()
    monkeypatch.setattr(dictation.asr, 'open_stream', AsyncMock(return_value=stream))
    return TestClient(app), workflow, stream


def test_live_results_stop_and_no_workflow_submission(setup):
    client, workflow, stream = setup
    with client.websocket_connect('/ws/dictation/test') as socket:
        assert socket.receive_json()['type'] == 'dictation.ready'
        socket.send_json({'type':'answer.confirm','text':'Do not submit this'})
        socket.send_bytes(bytes(640))
        assert socket.receive_json() == {'type':'stt.partial','segment':'1','text':'My street'}
        assert socket.receive_json()['type'] == 'stt.final'
        socket.send_json({'type':'dictation.stop'})
        assert socket.receive_json()['text'] == 'Please repair it.'
        assert socket.receive_json()['type'] == 'dictation.stopped'
    assert len(stream.received) == 1
    workflow.invoke.assert_not_called()


def test_batch_partial_and_manual_final_preserve_audio(setup, monkeypatch):
    client, workflow, _ = setup
    monkeypatch.setattr(dictation.asr,'choose_provider',lambda _: 'sarvam')
    received=[]
    async def transcribe(wav, language, settings):
        received.append((len(wav), language))
        return 'எங்கள் பகுதியில் தண்ணீர் வரவில்லை.'
    monkeypatch.setattr(dictation.asr,'transcribe',transcribe)
    with client.websocket_connect('/ws/dictation/test') as socket:
        rate=socket.receive_json()['sample_rate']
        socket.send_bytes(bytes(rate*2*2))
        assert socket.receive_json()['type']=='stt.partial'
        socket.send_json({'type':'dictation.stop'})
        assert socket.receive_json()['type']=='stt.final'
        assert socket.receive_json()['type']=='dictation.stopped'
    assert received[0]==received[1]
    assert received[0][1]=='ta'
    workflow.invoke.assert_not_called()


def test_unavailable_and_disconnect_do_not_mutate(setup, monkeypatch):
    client, workflow, _ = setup
    monkeypatch.setattr(dictation.asr,'choose_provider',lambda _: None)
    with client.websocket_connect('/ws/dictation/test') as socket:
        assert socket.receive_json()['type']=='error'
    workflow.invoke.assert_not_called()


def test_provider_failure_is_reported(setup, monkeypatch):
    client, workflow, stream = setup
    async def failed(_):
        raise RuntimeError('provider error')
    stream.send_audio=failed
    with client.websocket_connect('/ws/dictation/test') as socket:
        socket.receive_json()
        socket.send_bytes(bytes(640))
        assert socket.receive_json()['type']=='error'
    workflow.invoke.assert_not_called()


def test_cross_origin_denied(setup):
    client, _, _=setup
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect), client.websocket_connect('/ws/dictation/test',headers={'origin':'https://other.example'}):
        pass


# ---------------------------------------------------------------------------
# A dictated number reaches the box as a number
# ---------------------------------------------------------------------------

SPOKEN_NUMBER = ("\u0ba4\u0bca\u0ba3\u0bcd\u0ba3\u0bc2\u0bb1\u0bcd\u0bb1\u0bbf \u0bae\u0bc2\u0ba9\u0bcd\u0bb1\u0bc1 \u0ba8\u0bbe\u0bb1\u0bcd\u0baa\u0ba4\u0bcd\u0ba4\u0bbf \u0ba8\u0bbe\u0bb2\u0bc1 \u0baa\u0ba4\u0bbf\u0ba9\u0bc7\u0bb4\u0bc1 "
                 "\u0ba8\u0bbe\u0bb1\u0bcd\u0baa\u0ba4\u0bcd\u0ba4\u0bbf \u0b8f\u0bb4\u0bc1 \u0b90\u0bae\u0bcd\u0baa\u0ba4\u0bcd\u0ba4\u0bbf \u0b87\u0bb0\u0ba3\u0bcd\u0b9f\u0bc1")


class TestASpokenNumberIsWrittenAsFigures:
    """REPORTED FROM A TAMIL SESSION. Asked for their mobile number the
    citizen said it the way it is printed \u2014 in pairs \u2014 and the text box
    filled with Tamil number words.

    The form understands those now. The citizen still could not check them:
    the whole point of dictating into the text box is that they read it back
    before pressing Send, and nobody can verify their own phone number
    spelled out in words.

    Converted on the socket rather than in the page so there is ONE number
    parser. Tamil cardinals, English cardinals, digit-by-digit, "double
    seven", figures already \u2014 all of it is `digits_from_speech`, and a
    second copy in JavaScript is a second copy to drift.
    """

    def test_a_number_field_gets_figures(self):
        assert dictation.as_dictated(SPOKEN_NUMBER, True) == "9344174752"

    def test_english_too(self):
        said = "ninety three forty four seventeen forty seven fifty two"

        assert dictation.as_dictated(said, True) == "9344174752"

    def test_free_text_is_never_touched(self):
        """A grievance that says "for five days" must not come out as "for 5
        days". The citizen's own words are the complaint."""
        said = "\u0b90\u0ba8\u0bcd\u0ba4\u0bc1 \u0ba8\u0bbe\u0b9f\u0bcd\u0b95\u0bb3\u0bbe\u0b95 \u0ba4\u0ba3\u0bcd\u0ba3\u0bc0\u0bb0\u0bcd \u0b87\u0bb2\u0bcd\u0bb2\u0bc8"

        assert dictation.as_dictated(said, False) == said
        assert dictation.as_dictated(SPOKEN_NUMBER, False) == SPOKEN_NUMBER

    def test_a_citizen_can_still_say_they_have_no_number(self):
        """A field that swallows every sentence without four digits in it is
        a field nobody can say no to."""
        for said in ("I do not have a mobile number",
                     "\u0b8e\u0ba9\u0b95\u0bcd\u0b95\u0bc1 \u0bae\u0bca\u0baa\u0bc8\u0bb2\u0bcd \u0b87\u0bb2\u0bcd\u0bb2\u0bc8"):
            assert dictation.as_dictated(said, True) == said, said

    def test_a_sentence_that_merely_mentions_a_number_is_left_alone(self):
        """"I have two numbers" is an answer, not the digit 2."""
        said = "I have two numbers"

        assert dictation.as_dictated(said, True) == said

    def test_only_fields_that_are_digits_all_the_way_through(self):
        """A PAN or an IFSC carries letters, and writing one as digits would
        delete them. The set is deliberately three, not every identifier."""
        assert dictation._DIGIT_FIELDS == frozenset({"mobile", "aadhaar", "pincode"})

    def _socket(self, monkeypatch, fields, said):
        """A dictation socket on a session whose next question is `fields`'
        successor, with the provider returning `said`."""
        class Said(Stream):
            async def send_audio(self, chunk):
                self.received.append(chunk)
                await self.results.put(Transcript(said, True, 1))

            async def stop(self):
                await self.results.put(None)

        app = FastAPI()
        app.include_router(dictation.router)
        app.state.workflow = SimpleNamespace(
            snapshot=AsyncMock(return_value={"language": "ta",
                                             "status": "collecting",
                                             "fields": dict(fields)}),
            invoke=AsyncMock())
        monkeypatch.setattr(dictation, "citizen_scope", lambda _: None)
        monkeypatch.setattr(dictation.asr, "choose_provider", lambda _: "deepgram")
        monkeypatch.setattr(dictation.asr, "open_stream", AsyncMock(return_value=Said()))
        return TestClient(app)

    # Everything before the mobile question, so mobile is what is asked next.
    BEFORE_MOBILE = {"applicant_name": "Ravi Kumar", "age": 45}

    def _close_cleanly(self, socket):
        """Close the way the browser closes, and not the way a test is
        tempted to.

        WHY THIS EXISTS. These two tests used to leave the `with` block
        straight after reading the transcript, which left the handler parked
        in `asyncio.wait` on the next `socket.receive()`. Starlette's
        `WebSocketTestSession.__exit__` then runs its callbacks LIFO:

            close(1000)          queue a disconnect for the app
            portal.call(cs.cancel)   cancel the app's cancel scope
            fut.result()             re-raise whatever the task ended as

        The first two are back to back with no guaranteed window in between,
        so a handler that has not yet noticed the disconnect is simply
        cancelled, the task future ends CANCELLED, and `fut.result()` raises
        `CancelledError` into the test thread. It surfaced roughly once in
        four full-suite runs and never once in fourteen runs of this file
        alone, because the flake needs the machine to be busy.

        IT IS NOT A DEFECT IN THE HANDLER, and that was checked rather than
        assumed: a twenty-line websocket endpoint containing no project code,
        parked the same way, fails at the same rate (12/300), while the same
        endpoint that has already returned fails 0/300. Measured against the
        real handler, closing cleanly is 300/300.

        So nothing in `app/api/dictation.py` was changed. The browser sends
        `dictation.stop` and waits for the acknowledgement, and now so does
        this test — which makes it a more faithful test, not a quieter one.
        """
        socket.send_json({"type": "dictation.stop"})
        while socket.receive_json().get("type") != "dictation.stopped":
            pass

    def test_the_socket_converts_when_the_mobile_number_is_asked(self, monkeypatch):
        client = self._socket(monkeypatch, self.BEFORE_MOBILE, SPOKEN_NUMBER)
        with client.websocket_connect("/ws/dictation/s1") as socket:
            assert socket.receive_json()["type"] == "dictation.ready"
            socket.send_bytes(bytes(320))
            message = socket.receive_json()
            self._close_cleanly(socket)

        assert message["text"] == "9344174752", message

    def test_and_leaves_the_grievance_in_the_citizens_own_words(self, monkeypatch):
        """The same utterance, asked at the grievance instead. Nothing is
        converted: "ஐந்து நாட்களாக" is a complaint, not a number."""
        before_grievance = {**self.BEFORE_MOBILE, "mobile": "9344174752",
                            "address": "12 Gandhi Street, Coimbatore"}
        client = self._socket(monkeypatch, before_grievance, SPOKEN_NUMBER)
        with client.websocket_connect("/ws/dictation/s2") as socket:
            assert socket.receive_json()["type"] == "dictation.ready"
            socket.send_bytes(bytes(320))
            message = socket.receive_json()
            self._close_cleanly(socket)

        assert message["text"] == SPOKEN_NUMBER, message
