"""The voice WebSocket: one live conversation, over the same workflow as text.

    browser mic --(16 kHz PCM)--> VAD --> end of speech --> STT
                                                            |
                              the SAME graph a typed turn uses
                                                            |
                          reply --> what may be spoken --> TTS --> browser

The socket is a TRANSPORT, not a second implementation. A settled transcript is
handed to exactly the same `workflow.invoke` the REST endpoint calls, so a
citizen can answer one question by speaking and the next by typing, and the
petition cannot tell the difference. There is no voice petition state. There is
the petition state.

What this file owns is turn-taking: when the citizen has started speaking, when
they have finished, and what happens when they speak over the assistant. What
it must never own is what to ask next, whether an answer is acceptable, or what
goes in the document.

Protocol, client to server:
    binary frames                 16-bit little-endian PCM at the advertised rate
    {"type":"voice.start"}        begin hands-free listening
    {"type":"voice.end"}          stop listening; the petition is untouched
    {"type":"voice.interrupt"}    the citizen spoke over the assistant
    {"type":"stop"}               finalise the current utterance now
    {"type":"text","text":…}      a typed turn on the same socket
    {"type":"cancel"}             abandon the petition

Server to client:
    {"type":"voice.ready", …}     what is configured, and the frame format
    {"type":"voice.state", …}     one of the states in `Phase`
    {"type":"stt.final", …}       a settled transcript, with its turn number
    {"type":"state", …}           the session view, after the graph has run
    {"type":"tts.start", …}       the text about to be spoken
    {"type":"tts.audio"}          followed by one binary frame of WAV
    {"type":"tts.end"}            nothing more for this reply
    {"type":"voice.interrupted"}  the assistant stopped because it was spoken over
    {"type":"voice.discarded", …} something was heard and judged not to be an
                                  answer, with the measurements it was judged
                                  on — never a transcript. Drives the developer
                                  diagnostics panel; the citizen sees nothing.
    {"type":"voice.ended", …}     listening has stopped; why
    {"type":"error", …}           something failed; the socket may still be usable

A long silence is not an event. The assistant simply says something — "I am
listening" — through the ordinary `tts.start` path, because a nudge the citizen
can hear is the whole point of one.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
from enum import StrEnum

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import get_settings
from ..domain.fields import read_boolean
from ..domain.phrasing import phrase
from ..domain.templates import the_template
from ..logging_setup import preview, session_context
from ..services import asr, speech_text, tts
from ..services.commit_guard import SpeechCommitGuard, Verdict
from ..services.voice import EndOfSpeech, Speech, VadSettings, VoiceActivityDetector
from .views import session_view

log = logging.getLogger(__name__)
router = APIRouter()

# Said after the petition exists. Deliberately small and literal: this is the
# only place the voice layer acts on words itself, so it acts on very few.
#
# The word boundaries matter and are easy to lose. An earlier revision of this
# file reached disk with a literal backspace character where each boundary
# should have been, so neither pattern matched anything in English and only
# the Tamil alternatives worked — saying "stop" did nothing at all. The
# tests pin both directions now.
_READ_ALOUD = re.compile(
    r"\b(read|aloud|go ahead)\b"
    r"|படி|வாசி|வாசிக்க|படிக்க",
    re.I,
)
_STOP_READING = re.compile(
    r"\b(stop|enough|quiet)\b"
    r"|நிறுத்து|போதும்|வேண்டாம்",
    re.I,
)


# How often a running turn is checked for having reached composition. Short
# enough that the panel opens while the citizen is still waiting for a reply,
# long enough to be nothing next to a turn measured in tens of seconds.
_PROGRESS_POLL_S = 0.4


# The steps where a plain "yes" or "no" is the answer to the question on the
# table, rather than the sound a transcription service makes out of silence.
_CONFIRMATION_STATUSES = {"attachments", "confirming", "ready"}


def expects_confirmation(state: dict | None) -> bool:
    """Is a bare yes or no an answer right now?

    Asked of the workflow's own state, never guessed from the words. At the
    review step the assistant asks "Shall I prepare your petition?" and there
    is no longer answer to give; while details are being collected the same
    word is what a service returns when it heard nothing.
    """
    values = state or {}
    return (str(values.get("status") or "") in _CONFIRMATION_STATUSES
            or bool(values.get("awaiting_correction")))


class Phase(StrEnum):
    """The live session's state, named once and sent to the page as-is.

    A single value rather than a handful of booleans. `isListening` and
    `isSpeaking` and `isProcessing` can all be true at once by accident, and
    when they are, the page shows a microphone that is listening to a citizen
    the server has stopped hearing.
    """

    IDLE = "idle"
    LISTENING = "listening"
    USER_SPEAKING = "user_speaking"
    TRANSCRIBING = "transcribing"
    PROCESSING = "processing"
    GENERATING = "generating"
    ASSISTANT_SPEAKING = "assistant_speaking"
    ERROR = "error"


@router.websocket("/ws/voice/{session_id}")
async def voice(websocket: WebSocket, session_id: str, language: str = "en") -> None:
    await websocket.accept()
    settings = get_settings()
    workflow = getattr(websocket.app.state, "workflow", None)

    if workflow is None:  # pragma: no cover
        await websocket.send_json({"type": "error", "message": "The service is still starting."})
        await websocket.close()
        return

    with session_context(session_id):
        state = await workflow.snapshot(session_id)
        if not state:
            await websocket.send_json(
                {"type": "error", "message": "That session was not found. Start a new one."}
            )
            await websocket.close()
            return

        language = state.get("language", language)
        template = the_template()
        confirmation_expected = expects_confirmation(state)

        # ---------------------------------------------------------------- #
        # Session state. One phase, one lock, one cancellable speech task.
        # ---------------------------------------------------------------- #
        phase = Phase.IDLE
        listening = False
        turn_lock = asyncio.Lock()
        speaking: asyncio.Task | None = None
        last_voice_at = time.monotonic()
        nudges = 0
        # How much of the utterance being collected overlapped the assistant's
        # own speech. The microphone stays open during playback so the citizen
        # can interrupt; this is what tells an interruption from the speaker
        # being heard by the microphone.
        playback_overlap_ms = 0

        # Set while the citizen has asked the assistant to stop reading, so a
        # read already under way abandons its remaining sections.
        reading_cancelled = asyncio.Event()

        guard = SpeechCommitGuard(
            min_voiced_ms=settings.voice_min_voiced_ms,
            min_voiced_ratio=settings.voice_min_voiced_ratio,
            min_modulation=settings.voice_min_modulation,
        )

        vad = VoiceActivityDetector(VadSettings(
            sample_rate=settings.asr_sample_rate,
            threshold=settings.voice_vad_threshold,
            onset_ms=settings.voice_onset_ms,
            hangover_ms=settings.voice_silence_ms,
        ))

        async def set_phase(next_phase: Phase, **extra) -> None:
            nonlocal phase
            if phase == next_phase and not extra:
                return
            phase = next_phase
            with contextlib.suppress(Exception):
                await websocket.send_json({"type": "voice.state", "state": phase.value, **extra})

        async def stop_speaking(*, interrupted: bool) -> None:
            """Silence the assistant immediately.

            Cancelling the task stops the NEXT clip being sent; the clip already
            in the browser is stopped by the page on the same signal. Both are
            needed: cancelling here alone leaves a second of audio still
            playing, which is exactly long enough to feel like being ignored.
            """
            nonlocal speaking
            task, speaking = speaking, None
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            if interrupted:
                with contextlib.suppress(Exception):
                    await websocket.send_json({"type": "voice.interrupted"})

        async def say(text: str) -> None:
            """Speak one reply, clip by clip, until told not to.

            Runs as its own task so that a citizen speaking over it cancels it
            mid-sentence rather than after it.
            """
            if not text.strip() or not tts.configured(settings):
                if listening:
                    await set_phase(Phase.LISTENING)
                return
            await set_phase(Phase.ASSISTANT_SPEAKING, text=text)
            with contextlib.suppress(Exception):
                await websocket.send_json({"type": "tts.start", "text": text})
            first_at = None
            try:
                async for clip in tts.stream(text, language, settings):
                    if first_at is None:
                        first_at = time.monotonic()
                    await websocket.send_json({"type": "tts.audio", "bytes": len(clip)})
                    await websocket.send_bytes(clip)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                # A failed voice is a degraded experience, never a failed turn:
                # the text is already on the page.
                #
                # The TYPE is recorded as well as the message, because the most
                # common one here has no message at all: a citizen who closes
                # the tab mid-sentence raises WebSocketDisconnect, whose str()
                # is empty. Five of those in a day's log read as five silent
                # failures of the speech service, which is not what happened
                # and is not something to go looking for.
                log.info("tts.stream.failed", extra={
                    "kind": type(exc).__name__,
                    "error": str(exc)[:160] or "(no message)",
                    "listener_gone": isinstance(exc, WebSocketDisconnect)})
            finally:
                with contextlib.suppress(Exception):
                    await websocket.send_json({"type": "tts.end"})
            if listening:
                await set_phase(Phase.LISTENING)

        async def announce_generation() -> None:
            """Say that the petition is being written, while it is being written.

            A turn is a single invoke that returns only once it has finished,
            so a citizen who confirmed by voice watched an unchanged review
            screen for as long as composition took — two and a half minutes in
            the report that prompted this, with nothing on the page to say the
            work had even started. Typing Confirm never had the problem: that
            button knows what it just asked for.

            Nothing here decides that work is under way. The confirm node
            records `generating` in the checkpoint before it routes to compose,
            and this reads that and passes it on unchanged; the page already
            knows what a generating state means and has a panel for it. A turn
            that is something else — a correction, a question — never reaches
            that status, so nothing is sent and nothing is claimed.

            The phase moves too, and not only the panel. PROCESSING and
            GENERATING are both "the assistant is busy", but they are not the
            same wait: answering a question takes a second or two, and writing
            the petition took two and a half minutes in the report above. A
            citizen told "Thinking..." for two and a half minutes concludes it
            has hung. Saying which wait they are in is the whole difference.
            """
            try:
                while True:
                    await asyncio.sleep(_PROGRESS_POLL_S)
                    values = await workflow.peek(session_id)
                    if (values or {}).get("status") == "generating":
                        await set_phase(Phase.GENERATING)
                        await websocket.send_json(
                            {"type": "state", "state": session_view(values)})
                        return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                # Progress is a courtesy. A turn must never fail for it.
                log.info("voice.progress.unavailable", extra={"error": str(exc)[:120]})

        async def run_turn(text: str, *, via: str) -> dict | None:
            """One turn through the workflow. The only way in, for both modes."""
            async with turn_lock:
                log.info("turn.received", extra={"via": via, "chars": len(text),
                                                 "preview": preview(text)})
                await set_phase(Phase.PROCESSING)
                started = time.monotonic()
                progress = asyncio.create_task(announce_generation())
                try:
                    result = await workflow.invoke(session_id, {"utterance": text})
                except Exception as exc:  # noqa: BLE001
                    log.exception("turn.failed")
                    await set_phase(Phase.ERROR)
                    with contextlib.suppress(Exception):
                        await websocket.send_json(
                            {"type": "error", "message": phrase("turn_failed", language),
                             "detail": str(exc)[:200]}
                        )
                    return None
                finally:
                    progress.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await progress
                log.info("voice.turn_latency_ms",
                         extra={"ms": int((time.monotonic() - started) * 1000), "via": via})

                await websocket.send_json({"type": "state", "state": session_view(result)})
                return result

        async def respond(result: dict) -> None:
            """Say whatever the workflow decided, in the form fit to be said."""
            nonlocal language
            if result is None:
                return
            nonlocal confirmation_expected
            language = result.get("language", language)
            confirmation_expected = expects_confirmation(result)
            view = session_view(result)
            reply = result.get("reply") or ""
            spoken = speech_text.speech_for(
                display_text=reply,
                view=view,
                template=template,
                language=language,
                allow_spoken_identifiers=settings.voice_spoken_identifiers,
            )
            if listening and spoken:
                await start_speaking(spoken)

        async def start_speaking(text: str) -> None:
            nonlocal speaking
            await stop_speaking(interrupted=False)
            speaking = asyncio.create_task(say(text))

        # ---------------------------------------------------------------- #
        # Utterance -> transcript -> the workflow
        # ---------------------------------------------------------------- #

        async def read_petition_aloud() -> None:
            """Read the finished document, section by section, interruptibly.

            Reading is PRESENTATION, not a petition action: nothing here
            touches the record, the document or the workflow. It is the only
            thing the voice layer does that the typed path cannot, and it does
            it strictly read-only.

            Identifiers are described rather than recited on the way out —
            the document on screen carries the Aadhaar, the room does not need
            to hear it.
            """
            current = await workflow.snapshot(session_id)
            sections = speech_text.readable_sections((current or {}).get("letter_text") or "")
            if not sections:
                await start_speaking(speech_text.phrase("ready_no_read", language))
                return
            await start_speaking(speech_text.phrase("reading", language))
            for section in sections:
                # Each section is its own utterance, so the citizen speaking
                # over it cancels the rest rather than being read the whole
                # petition before anyone listens to them.
                if speaking is not None:
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await speaking
                if not listening or reading_cancelled.is_set():
                    await start_speaking(speech_text.phrase("read_stopped", language))
                    return
                await start_speaking(section)
            if speaking is not None:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await speaking
            if listening and not reading_cancelled.is_set():
                await start_speaking(speech_text.phrase("read_done", language))

        async def handle_finished_command(text: str) -> bool:
            """Act on what a citizen says AFTER the petition exists.

            Returns True when the utterance was handled here, so it is not then
            offered to a workflow that has already finished and would silently
            drop it.
            """
            current = await workflow.snapshot(session_id)
            if not current or current.get("status") != "ready":
                return False

            answer = read_boolean(text)
            wants_read = answer is True or _READ_ALOUD.search(text or "")
            wants_stop = answer is False or _STOP_READING.search(text or "")

            if wants_stop:
                reading_cancelled.set()
                await stop_speaking(interrupted=False)
                await start_speaking(speech_text.phrase("read_stopped", language))
                return True
            if wants_read:
                reading_cancelled.clear()
                asyncio.create_task(read_petition_aloud())
                return True
            return False

        async def send_discarded(reason: str, evidence, *, sent: bool) -> None:
            """Say that something was thrown away, and on what measurements.

            Carries no transcript and no value — only why. The citizen sees
            nothing; a developer tuning a noisy room sees everything they need.
            """
            with contextlib.suppress(Exception):
                await websocket.send_json({
                    "type": "voice.discarded", "reason": reason, "sent_to_stt": sent,
                    "voiced_ms": evidence.voiced_ms,
                    "voiced_ratio": round(evidence.voiced_ratio, 2),
                    "modulation": round(evidence.modulation, 3),
                    "peak_snr": round(evidence.peak_snr, 1),
                })

        async def on_utterance(utterance) -> None:
            """One settled utterance: measure, transcribe, then decide.

            The order matters. The evidence is taken from the audio BEFORE a
            transcription service ever sees it, so the decision to commit rests
            on what was heard rather than on the service having produced
            characters — which it will do for a fan, a keyboard and for
            silence.
            """
            nonlocal last_voice_at, nudges
            last_voice_at = time.monotonic()
            nudges = 0

            evidence = vad.evidence()
            evidence.during_playback_ms = playback_overlap_ms
            vad.clear_evidence()
            turn = guard.turn

            # Cheapest gate first: audio that carries no speech is never sent
            # anywhere. Nothing leaves the building, nothing is billed, and
            # nothing can come back to be mistaken for an answer.
            probe = guard.judge("...", evidence, language=language, turn=turn)
            if probe.verdict in (Verdict.TOO_SHORT, Verdict.NO_SPEECH_EVIDENCE):
                log.info("voice.discarded", extra={
                    "reason": probe.verdict.value, "voiced_ms": evidence.voiced_ms,
                    "ratio": round(evidence.voiced_ratio, 2),
                    "modulation": round(evidence.modulation, 3),
                    "snr": round(evidence.peak_snr, 1), "sent_to_stt": False})
                await send_discarded(probe.verdict.value, evidence, sent=False)
                if listening:
                    await set_phase(Phase.LISTENING)
                return

            await set_phase(Phase.TRANSCRIBING)
            started = time.monotonic()
            try:
                text, confidence = await asr.transcribe_with_confidence(
                    asr._wav(utterance.audio, settings.asr_sample_rate), language, settings
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("asr.transcribe.failed", extra={"error": str(exc)[:200]})
                await set_phase(Phase.LISTENING if listening else Phase.IDLE)
                with contextlib.suppress(Exception):
                    # Which message depends on what actually happened. The
                    # phase above is the tell: still listening means one
                    # utterance was lost and the next one will be heard, so
                    # "dictation has stopped" is simply untrue — and it is the
                    # kind of untrue that costs something, because it sends a
                    # citizen to the keyboard when saying it again would have
                    # worked.
                    await websocket.send_json(
                        {"type": "error",
                         "message": phrase(
                             "dictation_failed" if listening else "dictation_stopped", language),
                         "detail": str(exc)[:200], "recoverable": True}
                    )
                return
            log.info("voice.stt_latency_ms",
                     extra={"ms": int((time.monotonic() - started) * 1000),
                            "seconds": round(utterance.seconds, 2)})

            decision = guard.judge(
                text, evidence, language=language, turn=turn,
                confidence=confidence, min_confidence=settings.voice_min_confidence,
                during_playback=playback_overlap_ms > 0,
                expecting_confirmation=confirmation_expected,
            )
            if not decision.ok:
                # Never say what was rejected — it is either nothing or a
                # citizen's words — only why.
                log.info("voice.discarded", extra={
                    "reason": decision.verdict.value, "voiced_ms": evidence.voiced_ms,
                    "ratio": round(evidence.voiced_ratio, 2),
                    "modulation": round(evidence.modulation, 3),
                    "snr": round(evidence.peak_snr, 1), "chars": len(text or ""),
                    "sent_to_stt": True})
                await send_discarded(decision.verdict.value, evidence, sent=True)
                # TOO_SHORT is in this list now. It used to fall through to
                # silence, and silence after somebody speaks reads as a broken
                # microphone — so they say it again, louder, into a void. The
                # brief utterances reaching here are overwhelmingly real
                # speech that was simply short.
                if listening and decision.verdict in (
                        Verdict.FILLER_ONLY, Verdict.WRONG_SCRIPT,
                        Verdict.LOW_CONFIDENCE, Verdict.TOO_SHORT):
                    # Heard something, could not make an answer of it. Saying so
                    # is better than silence, which reads as a broken
                    # microphone and makes people repeat into a void.
                    await start_speaking(speech_text.phrase("not_caught", language))
                elif listening:
                    await set_phase(Phase.LISTENING)
                return

            guard.begin_turn()
            await websocket.send_json(
                {"type": "stt.final", "text": decision.text, "turn": utterance.turn})

            # A finished petition is a terminal state in the workflow: the
            # router stops at `ready`, so anything said now would vanish. The
            # assistant has just offered to read the document aloud, and an
            # offer nothing can act on is worse than no offer.
            if await handle_finished_command(decision.text):
                return

            result = await run_turn(decision.text, via="voice")
            if result is not None:
                await respond(result)

        eos = EndOfSpeech(on_utterance=on_utterance,
                          max_seconds=settings.voice_max_utterance_s,
                          sample_rate=settings.asr_sample_rate)

        async def handle_audio(chunk: bytes) -> None:
            """One buffer from the browser: classify it, keep it at most once.

            The detector reports on every 32 ms FRAME, and a browser buffer is
            several frames long. Adding the buffer once per verdict — which is
            what this did — stored each buffer four times over, and the speech
            service transcribed exactly that: "My name is Harish" came back as
            "Ni Ni Ni Ni Mi Mi Mi Mi" for three hundred words. The buffer is
            the unit of storage; the frames only decide what to do with it.
            """
            nonlocal last_voice_at
            if not listening:
                return

            # Held before it is classified: if this buffer turns out to be
            # where a word began, the one before it carries the beginning.
            eos.remember(chunk)

            verdicts = vad.feed(chunk)
            started = Speech.STARTED in verdicts
            ended = Speech.ENDED in verdicts

            if started:
                last_voice_at = time.monotonic()
                playback_overlap_ms = 0
                # Barge-in. The assistant stops the moment the citizen starts,
                # not when it reaches the end of its sentence.
                if settings.voice_barge_in and speaking is not None:
                    await stop_speaking(interrupted=True)
                await set_phase(Phase.USER_SPEAKING)
                eos.begin()

            # Kept whenever this buffer belongs to the utterance — including
            # the one the turn opened in, whose first frames are the start of
            # the word, and the one it closed in, whose first frames are the
            # end of it.
            if started or ended or vad.speaking:
                eos.add(chunk)
                if phase is Phase.ASSISTANT_SPEAKING or speaking is not None:
                    playback_overlap_ms += int(len(chunk) / 2 / settings.asr_sample_rate * 1000)

            if ended:
                await eos.finish()
            elif eos.open and eos.seconds > settings.voice_max_utterance_s:
                await eos.finish()

        async def watchdog() -> None:
            """Nudge, then ask, then stop — without touching the petition."""
            nonlocal nudges, listening
            try:
                while True:
                    await asyncio.sleep(2.0)
                    if not listening or phase in (Phase.PROCESSING, Phase.TRANSCRIBING,
                                                  Phase.ASSISTANT_SPEAKING):
                        continue
                    quiet = time.monotonic() - last_voice_at
                    finished = (await workflow.snapshot(session_id) or {}).get("status")
                    if finished in ("ready", "cancelled", "failed"):
                        # Nothing is outstanding. Keep listening — "read it to
                        # me" is still worth hearing — but stop prompting for
                        # an answer that nobody is waiting for.
                        if quiet > settings.voice_idle_timeout_s:
                            listening = False
                            await stop_speaking(interrupted=False)
                            eos.abandon()
                            await set_phase(Phase.IDLE)
                            with contextlib.suppress(Exception):
                                await websocket.send_json(
                                    {"type": "voice.ended", "reason": "idle"})
                            return
                        continue
                    if quiet > settings.voice_idle_timeout_s:
                        listening = False
                        await stop_speaking(interrupted=False)
                        eos.abandon()
                        await set_phase(Phase.IDLE)
                        with contextlib.suppress(Exception):
                            await websocket.send_json(
                                {"type": "voice.ended", "reason": "idle"})
                        return
                    if quiet > settings.voice_ask_after_s and nudges < 2:
                        nudges = 2
                        await start_speaking(speech_text.phrase("still_there", language))
                    elif quiet > settings.voice_nudge_after_s and nudges < 1:
                        nudges = 1
                        await start_speaking(speech_text.phrase("still_listening", language))
            except asyncio.CancelledError:
                return

        watchdog_task: asyncio.Task | None = None

        # ---------------------------------------------------------------- #

        await websocket.send_json({
            "type": "voice.ready",
            "dictation": asr.status(settings),
            "spoken_replies": tts.status(settings),
            "sample_rate": settings.asr_sample_rate,
            "barge_in": settings.voice_barge_in,
            "diagnostics": settings.voice_diagnostics,
            "thresholds": {
                "vad_multiple": settings.voice_vad_threshold,
                "onset_ms": settings.voice_onset_ms,
                "silence_ms": settings.voice_silence_ms,
                "min_voiced_ms": settings.voice_min_voiced_ms,
                "min_modulation": settings.voice_min_modulation,
            },
            "spoken_identifiers": settings.voice_spoken_identifiers,
            "enabled": settings.voice_enabled and asr.status(settings)["ok"],
        })

        try:
            while True:
                message = await websocket.receive()

                if message.get("type") == "websocket.disconnect":
                    break

                if (chunk := message.get("bytes")) is not None:
                    await handle_audio(chunk)
                    continue

                raw = message.get("text")
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except ValueError:
                    continue
                kind = payload.get("type")

                if kind == "voice.start":
                    if not settings.voice_enabled or not asr.status(settings)["ok"]:
                        await websocket.send_json(
                            {"type": "error", "recoverable": False,
                             "message": phrase("dictation_stopped", language)})
                        continue
                    listening = True
                    nudges = 0
                    last_voice_at = time.monotonic()
                    vad.reset()
                    eos.reset()
                    await set_phase(Phase.LISTENING)
                    if watchdog_task is None:
                        watchdog_task = asyncio.create_task(watchdog())
                    # Greet with the question that is actually outstanding,
                    # asked by the workflow rather than invented here.
                    current = await workflow.snapshot(session_id)
                    if current:
                        await respond(current)

                elif kind == "voice.end":
                    listening = False
                    await stop_speaking(interrupted=False)
                    eos.abandon()
                    vad.reset()
                    await set_phase(Phase.IDLE)
                    await websocket.send_json({"type": "voice.ended", "reason": "requested"})

                elif kind == "voice.interrupt":
                    # The page heard speech before the server did. Believe it.
                    await stop_speaking(interrupted=True)
                    if listening:
                        await set_phase(Phase.LISTENING)

                elif kind == "stop":
                    # Push-to-talk: finalise now rather than waiting for silence.
                    if eos.open:
                        await eos.finish()

                elif kind == "text" and str(payload.get("text") or "").strip():
                    # A typed turn mid-voice-session. Same door, same workflow,
                    # and the assistant answers out loud if it was speaking.
                    typed = str(payload["text"])
                    await stop_speaking(interrupted=False)
                    eos.abandon()
                    if await handle_finished_command(typed):
                        continue
                    result = await run_turn(typed, via="ws-text")
                    if result is not None:
                        await respond(result)
                    elif listening:
                        await set_phase(Phase.LISTENING)

                elif kind == "cancel":
                    listening = False
                    await stop_speaking(interrupted=False)
                    eos.abandon()
                    await run_turn("cancel", via="ws")
                    break

        except WebSocketDisconnect:
            # Nothing is lost: the checkpoint already holds everything the
            # citizen said, and they resume by reopening the session.
            log.info("ws.disconnected")
        finally:
            listening = False
            if watchdog_task is not None:
                watchdog_task.cancel()
            await stop_speaking(interrupted=False)
            eos.abandon()
