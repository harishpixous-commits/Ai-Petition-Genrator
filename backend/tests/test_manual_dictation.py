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
