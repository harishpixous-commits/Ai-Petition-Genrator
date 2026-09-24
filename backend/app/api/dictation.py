"""Manual speech typing. This endpoint can emit text only, never workflow turns."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import get_settings
from ..domain.fields import digits_from_speech
from ..services import asr
from ..services.officer_store import citizen_scope

log = logging.getLogger(__name__)

router = APIRouter()

# Fields whose answer is a run of digits and nothing else.
#
# NOT every identifier. A PAN or an IFSC carries letters, and turning one of
# those into digits would delete them. These three are numbers all the way
# through, so a transcript of number WORDS is a transcript of the answer
# written the long way round.
_DIGIT_FIELDS = frozenset({"mobile", "aadhaar", "pincode"})

# Below this, leave the words alone. A citizen answering "I don't have a
# mobile number" must be able to say so and see it — a field that silently
# swallows every sentence without four digits in it is a field nobody can
# say no to.
_ENOUGH_DIGITS = 4


def as_dictated(text: str, digit_field: bool) -> str:
    """The transcript, with a spoken number written as figures.

    REPORTED FROM A TAMIL SESSION. Asked for their mobile number the citizen
    said it the way it is printed — in pairs — and the box filled with
    "தொண்ணூற்றி மூன்று நாற்பத்தி நாலு ...". The form understands that now, but
    the citizen cannot check it: the whole point of dictating into the text
    box is that they read it back before pressing Send, and nobody can
    verify their own phone number spelled out in words.

    Done HERE rather than in the page so there is one number parser and not
    two. Tamil cardinals, English cardinals, digit-by-digit, "double seven",
    figures already — all of it lives in `digits_from_speech`, and a second
    copy of it in JavaScript is a second copy to drift.
    """
    if not digit_field:
        return text
    digits = digits_from_speech(text)
    return digits if len(digits) >= _ENOUGH_DIGITS else text


@router.websocket("/ws/dictation/{session_id}")
async def dictation(socket: WebSocket, session_id: str):
    allowed = citizen_scope(socket)
    if allowed is not None and session_id not in allowed:
        await socket.close(code=1008)
        return
    origin = socket.headers.get("origin")
    if origin and origin.split("://", 1)[-1].rstrip("/") != socket.headers.get("host"):
        await socket.close(code=1008)
        return
    await socket.accept()
    adapter = None
    tasks = []
    try:
        workflow = getattr(socket.app.state, "workflow", None)
        state = await workflow.snapshot(session_id) if workflow else None
        if not state:
            await socket.send_json({"type": "error", "code": "unavailable"})
            return
        settings = get_settings()
        provider = asr.choose_provider(settings)
        if not provider:
            await socket.send_json({"type": "error", "code": "unavailable"})
            return
        language = state.get("language", "en")
        # Which question is outstanding, asked the way the workflow asks it
        # rather than tracked separately here.
        from ..api.ws import field_on_the_table

        asking = field_on_the_table(state)
        digit_field = bool(asking is not None and asking.type in _DIGIT_FIELDS)
        stopping = asyncio.Event()
        send_lock = asyncio.Lock()

        async def emit(message):
            if message.get("type") in ("stt.partial", "stt.final"):
                message = {**message,
                           "text": as_dictated(message.get("text") or "", digit_field)}
            async with send_lock:
                await socket.send_json(message)

        if provider in asr.BATCH_PROVIDERS:
            # Growing windows give live partials even on batch-only providers.
            # Every byte is retained until committed; silence never submits a turn.
            pending = bytearray()
            changed = asyncio.Event()
            frame_bytes = settings.asr_sample_rate * 2
            segment = 0

            async def batch_results():
                nonlocal segment
                last_size = 0
                while True:
                    if not stopping.is_set():
                        await changed.wait()
                        changed.clear()
                    size = len(pending)
                    final = stopping.is_set() or size >= frame_bytes * 12
                    if size < frame_bytes // 5 and stopping.is_set():
                        return
                    if size == 0:
                        if stopping.is_set():
                            return
                        continue
                    if not final and size - last_size < frame_bytes * 2:
                        continue
                    # Freeze a bounded segment. Later audio waits for the next one.
                    count = min(size, frame_bytes * 12)
                    pcm = bytes(pending[:count])
                    text = await asr.transcribe(
                        asr._wav(pcm, settings.asr_sample_rate), language, settings
                    )
                    # It answered, so whatever was wrong before is not wrong now.
                    asr.note_success()
                    await emit(
                        {
                            "type": "stt.final" if final else "stt.partial",
                            "segment": str(segment),
                            "text": text,
                        }
                    )
                    last_size = count
                    if final:
                        del pending[:count]
                        segment += 1
                        last_size = 0
                    if stopping.is_set() and not pending:
                        return
                    if len(pending) >= frame_bytes * 2:
                        changed.set()

            reader = asyncio.create_task(batch_results())
            tasks.append(reader)

            async def audio(data):
                if len(pending) + len(data) > frame_bytes * 120:
                    raise RuntimeError("Speech service cannot keep up")
                pending.extend(data)
                changed.set()

            async def finish():
                stopping.set()
                changed.set()
                await asyncio.wait_for(reader, 30)
        else:
            adapter = await asyncio.wait_for(asr.open_stream(language, settings), 15)

            async def stream_results():
                async for transcript in adapter:
                    await emit(
                        {
                            "type": "stt.final" if transcript.final else "stt.partial",
                            "segment": str(
                                transcript.segment_id
                                if transcript.segment_id is not None
                                else transcript.turn
                            ),
                            "text": transcript.text,
                        }
                    )

            reader = asyncio.create_task(stream_results())
            tasks.append(reader)

            async def audio(data):
                await adapter.send_audio(data)

            async def finish():
                await adapter.stop()
                await asyncio.wait_for(reader, 15)

        await emit({"type": "dictation.ready", "sample_rate": settings.asr_sample_rate})
        while True:
            incoming = asyncio.create_task(socket.receive())
            tasks.append(incoming)
            done, _ = await asyncio.wait([incoming, reader], return_when=asyncio.FIRST_COMPLETED)
            if reader in done:
                # A provider disappearing must not leave a red, dead microphone.
                reader.result()
                raise RuntimeError("Speech provider disconnected")
            message = incoming.result()
            tasks.remove(incoming)
            if message["type"] == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                data = message["bytes"]
                if len(data) > 131072 or len(data) % 2:
                    raise RuntimeError("Invalid audio frame")
                await audio(data)
            elif message.get("text"):
                command = json.loads(message["text"])
                if command.get("type") == "dictation.stop":
                    await finish()
                    await emit({"type": "dictation.stopped"})
                    break
                # No message/confirm/submit commands are accepted here.
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as exc:  # noqa: BLE001
        # REMEMBERED, not only sent. The citizen is told "voice typing is
        # temporarily unavailable" and that is all anyone could see — the
        # health endpoint went on reporting the subsystem fine throughout,
        # because a key was configured. The reason now reaches /api/health,
        # where whoever is looking for it will look first.
        log.info("dictation.failed", extra={"reason": str(exc)[:160]})
        asr.note_failure(f"{type(exc).__name__}: {exc}")
        with contextlib.suppress(Exception):
            await socket.send_json({"type": "error", "code": "unavailable"})
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if adapter:
            await adapter.close()
        with contextlib.suppress(Exception):
            await socket.close()
