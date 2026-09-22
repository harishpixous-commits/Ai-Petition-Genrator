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
    {"type":"voice.interrupt"}    the citizen spoke over the assistant.
                                  `reason: "typed"` is always honoured; an
                                  onset heard by the page is honoured only
                                  where barge-in is actually enabled
    {"type":"tts.played","id":n} the audio for reply n has finished PLAYING
    {"type":"dictation.finish"}   a long answer is complete
    {"type":"dictation.restart"}  throw away the long answer so far
    {"type":"answer.read"}        read the captured answer out in full
    {"type":"answer.confirm"}     the answer just read back is right
    {"type":"answer.retry"}       it is not; the citizen will say it again
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
    {"type":"tts.end","id":n}     nothing more for reply n. The audio is in
                                  the page, not yet out of the speaker — the
                                  page answers with `tts.played` when it is
    {"type":"voice.dictation", …} how much of a long answer has been captured
                                  so far, with the full text to show
    {"type":"voice.answer", …}    an answer is being read back for agreement,
                                  with the masked text the page should show
                                  beside its Confirm and Retry buttons
    {"type":"voice.interrupted"}  the assistant stopped because it was spoken over
    {"type":"voice.noise", …}     the room is loud enough to be worth saying
                                  so. Advisory: nothing has been rejected
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
from ..domain.answer_intent import continuation, finished
from ..domain.answer_intent import read as read_intent
from ..domain.fields import MAX_FREE_TEXT, read_boolean
from ..domain.phrasing import phrase
from ..domain.templates import next_field, the_template
from ..logging_setup import preview, session_context
from ..services import asr, speech_text, tts
from ..services.commit_guard import SpeechCommitGuard, Verdict
from ..services.mask import mask_for_display
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


# A long grievance that has not been confirmed yet, kept across a dropped
# connection.
#
# WHY THIS EXISTS. The segments of a narration live on the socket, and a
# socket on a counter's wifi does not last two minutes reliably. Without
# this, a citizen who was ninety seconds into their complaint reconnects to
# an empty panel and is asked to start again — which is the single worst
# thing this feature could do, because the reason they were talking for
# ninety seconds is that they had ninety seconds' worth to say.
#
# NOT the petition. Nothing here has been confirmed, so nothing here belongs
# in the checkpoint; the checkpoint holds answers the citizen agreed to. This
# is a scratch buffer with the same lifetime as the citizen's patience, and
# it is dropped the moment the answer is either committed or abandoned.
#
# Bounded, because it holds citizen text: the oldest drafts are discarded
# once there are more than `_DRAFT_LIMIT` of them, so an abandoned session
# cannot keep a grievance in memory indefinitely.
_DRAFTS: dict[str, list[str]] = {}
_DRAFT_LIMIT = 32


def _keep_draft(session_id: str, segments: list[str]) -> None:
    if not segments:
        _DRAFTS.pop(session_id, None)
        return
    _DRAFTS.pop(session_id, None)          # re-insert, so it is the newest
    _DRAFTS[session_id] = list(segments)
    while len(_DRAFTS) > _DRAFT_LIMIT:
        _DRAFTS.pop(next(iter(_DRAFTS)))


def _take_draft(session_id: str) -> list[str]:
    return list(_DRAFTS.get(session_id) or ())


def _drop_draft(session_id: str) -> None:
    _DRAFTS.pop(session_id, None)


def wav_byte_rate(clip: bytes) -> int:
    """Bytes per second of a RIFF/WAVE clip, from its own header.

    Used to know how long the audio we just sent will take to PLAY, which is
    not the same as how long it took to send. Read from the header rather
    than assumed, because a provider that returns 22 kHz audio would
    otherwise be timed as though it were 16 kHz and the microphone would open
    while the assistant was still talking.

    Zero when the bytes are not a WAV this can read, which the caller treats
    as "unknown" rather than as "instant".
    """
    if len(clip) < 36 or clip[:4] != b"RIFF" or clip[8:12] != b"WAVE":
        return 0
    return int.from_bytes(clip[28:32], "little")


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


def field_on_the_table(state: dict | None):
    """The field the citizen is answering right now, or None.

    Taken from the template and the answers already given — the same call
    the workflow makes to decide what to ask — rather than tracked
    separately here. A voice layer with its own idea of which question is
    outstanding is a voice layer that will eventually disagree with the
    form.
    """
    values = state or {}
    if str(values.get("status") or "") != "collecting":
        return None
    return next_field(the_template(), values.get("fields") or {})


def wants_long_dictation(state: dict | None) -> bool:
    """Is the question on the table one a citizen answers at length?

    Decided from the FIELD TYPE in the template, not from the field's name.
    `text` is the free-text type — today that is the grievance and only the
    grievance — so adding another narrative field to `petition.yaml` gets
    long-form dictation with no change here, which is the rule the format
    lives by.

    A name is three words and 700 ms of silence after it means the citizen
    has finished. A grievance is a story told with pauses, and applying the
    short-answer rule to it hands in half a complaint.
    """
    values = state or {}
    if str(values.get("status") or "") != "collecting" or values.get("awaiting_correction"):
        return False
    spec = next_field(the_template(), values.get("fields") or {})
    return spec is not None and spec.type == "text"


def wants_read_back(state: dict | None) -> bool:
    """Should the next answer be quoted back before it is used?

    Only while details are being COLLECTED — that is, only when the citizen
    is about to supply a VALUE that lands on the petition. At the review step
    the assistant has already asked a yes/no question, and reading "yes" back
    to ask whether "yes" is correct is a loop with no exit.

    Asked of the workflow's state rather than guessed from the words, for the
    same reason `expects_confirmation` is: the voice layer does not know what
    is being collected and must not start deciding.
    """
    values = state or {}
    return (str(values.get("status") or "") == "collecting"
            and not values.get("awaiting_correction"))


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
    # The assistant is quoting the answer it just captured, and then waiting
    # for the citizen to agree with it. Two states rather than one: while it
    # is speaking the microphone is hearing its own voice, and while it is
    # waiting the microphone is hearing the citizen. The waveform and the
    # echo accounting behave differently in each.
    READING_BACK = "reading_back"
    WAITING_CONFIRMATION = "waiting_confirmation"
    # Listening to a grievance rather than to an answer. A separate state
    # because everything about it differs: the pause tolerance, what the page
    # shows, and what the citizen has been asked to do. "Listening" over a
    # two-minute narration reads as though the assistant is waiting for them
    # to finish a sentence.
    LONG_LISTENING = "long_listening"
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
        read_back_wanted = settings.voice_read_back and wants_read_back(state)
        long_mode = wants_long_dictation(state)
        long_introduced = False
        asking = field_on_the_table(state)

        # ---------------------------------------------------------------- #
        # Session state. One phase, one lock, one cancellable speech task.
        # ---------------------------------------------------------------- #
        phase = Phase.IDLE
        listening = False
        turn_lock = asyncio.Lock()
        speaking: asyncio.Task | None = None
        last_voice_at = time.monotonic()
        nudges = 0
        # How many consecutive checks have found the room loud, and whether
        # the citizen has already been told. Told ONCE: a warning repeated
        # every few seconds in a busy office is noise of its own.
        loud_checks = 0
        noise_advised = False
        # How much of the utterance being collected overlapped the assistant's
        # own speech. The microphone stays open during playback so the citizen
        # can interrupt; this is what tells an interruption from the speaker
        # being heard by the microphone.
        playback_overlap_ms = 0

        # Set while the citizen has asked the assistant to stop reading, so a
        # read already under way abandons its remaining sections.
        reading_cancelled = asyncio.Event()

        # Set while the finished petition is being read out.
        #
        # The one place the microphone stays open over the assistant's voice.
        # Reading a petition takes minutes and the assistant says "say stop at
        # any time" before it starts — an invitation the half-duplex gate
        # would silently withdraw. What can be ACTED on while it reads is
        # narrowed to exactly that invitation: stop, and read again. Anything
        # else heard during playback is discarded, so the assistant reciting
        # the citizen's own grievance cannot come back in as a request to
        # revise the petition with it.
        reading_aloud = False

        # The answer that has been read back and is waiting to be agreed with.
        # None means there is nothing outstanding and the next thing heard is
        # a fresh answer.
        #
        # This is the ONLY new piece of session state in this file, and it is
        # deliberately not petition state: it holds a candidate that the
        # workflow has never seen. Nothing reaches `workflow.invoke` from here
        # until the citizen has heard it and said yes, and a dropped socket
        # loses only the candidate — the checkpoint still holds every answer
        # that was actually confirmed.
        pending: str | None = None

        # --- turn-taking ---------------------------------------------------
        # The assistant finishes speaking before the microphone is allowed to
        # produce an answer. `playback_ack` is set by the page when the audio
        # has actually come out of the speaker — the server only knows when it
        # finished SENDING, and the two are seconds apart on a slow link.
        playback_seq = 0
        awaited_playback = 0
        playback_ack = asyncio.Event()
        # Whether this page reports playback at all. An older one does not,
        # and is timed by the measured length of the audio instead of being
        # waited on forever.
        reports_playback = False

        # --- long-form dictation -------------------------------------------
        # The grievance arrives as several utterances with thinking pauses
        # between them. They are kept IN ORDER and joined at the end; nothing
        # is summarised, reordered or dropped on the way.
        #
        # A list rather than a running string so that "say it again" can throw
        # the whole thing away in one move, and so the count can be shown.
        # Anything the citizen had already said before the connection
        # dropped. Empty for a fresh session, which is the ordinary case.
        segments: list[str] = _take_draft(session_id) if long_mode else []
        finish_task: asyncio.Task | None = None

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

        def apply_pace() -> None:
            """How long a silence has to be before the answer is over.

            Two questions of different shapes cannot share one number. This
            is the only thing long-form dictation changes about the detector:
            everything it has learnt about the room survives, and every test
            that decides whether a sound was speech is untouched.
            """
            vad.set_hangover(settings.voice_long_silence_ms if long_mode
                             else settings.voice_silence_ms)

        def assistant_has_the_floor() -> bool:
            """Is the assistant speaking, or about to be heard finishing?

            The phase alone is not enough: `say` is a task, and between it
            being created and its first clip the phase has not moved yet.
            """
            return (phase in (Phase.ASSISTANT_SPEAKING, Phase.READING_BACK)
                    or (speaking is not None and not speaking.done()))

        def resting() -> Phase:
            """The phase to fall back to when the assistant stops speaking.

            Not always LISTENING. After a read-back the assistant is waiting
            for one specific thing — agreement with the value it just quoted
            — and a page that says "Listening" there invites the citizen to
            carry on with the next detail, which is the one thing that must
            not happen until this answer is settled.
            """
            if not listening:
                return Phase.IDLE
            if pending is not None:
                return Phase.WAITING_CONFIRMATION
            return Phase.LONG_LISTENING if long_mode else Phase.LISTENING

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
            # Whatever was being waited on is over: the page has been told to
            # stop the audio. Releasing here stops a cancelled reply holding
            # the microphone shut for the rest of its grace period.
            playback_ack.set()

        async def say(text: str, *, as_phase: Phase = Phase.ASSISTANT_SPEAKING) -> None:
            """Speak one reply, clip by clip, until told not to.

            Runs as its own task so that a citizen speaking over it cancels it
            mid-sentence rather than after it.

            `as_phase` is how this particular speech is described. A read-back
            is still the assistant speaking, but the page draws it differently
            and the citizen is being asked a closed question rather than an
            open one — so it says READING_BACK, and settles into
            WAITING_CONFIRMATION rather than LISTENING when it finishes.
            """
            if not text.strip() or not tts.configured(settings):
                # Without a voice there is nothing to wait for the end of, so
                # the resting phase is reached immediately — which, after a
                # read-back, is WAITING_CONFIRMATION. The Confirm and Retry
                # buttons are on the page either way, so a deployment with no
                # TTS still gets the whole loop, silently.
                release_floor()
                await set_phase(resting())
                return
            await set_phase(as_phase, text=text)
            with contextlib.suppress(Exception):
                await websocket.send_json({"type": "tts.start", "text": text})
            nonlocal playback_seq
            playback_seq += 1
            mine = playback_seq
            first_at = None
            sent_bytes = 0
            byte_rate = 0
            try:
                async for clip in tts.stream(text, language, settings):
                    if first_at is None:
                        first_at = time.monotonic()
                    byte_rate = byte_rate or wav_byte_rate(clip)
                    sent_bytes += len(clip)
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
                    await websocket.send_json({"type": "tts.end", "id": mine})

            # THE RULE THIS KEEPS: the microphone does not open until the
            # assistant has stopped talking. Sending the last clip is not the
            # same moment as the speaker going quiet, and the gap between them
            # is exactly where the assistant hears itself, transcribes itself,
            # and asks the citizen to confirm a sentence it made up.
            await await_playback(mine, sent_bytes, byte_rate)
            # Off by default; see `voice_settle_ms`. Placed BEFORE the floor
            # is handed back, so the pause is spent with the gate still shut
            # rather than with the microphone open and being ignored.
            if settings.voice_settle_ms > 0:
                await asyncio.sleep(settings.voice_settle_ms / 1000)
            release_floor()
            await set_phase(resting())

        async def await_playback(mine: int, sent_bytes: int, byte_rate: int) -> None:
            """Hold until the audio has actually finished coming out.

            The page's own `tts.played` is the signal — a real playback event,
            not a timer. The measured length of the audio is the BACKSTOP, for
            a page that cannot report (an older client, a tab the browser has
            throttled), so that a silent page delays the turn by about the
            length of the clip rather than by a guess or by forever.
            """
            nonlocal awaited_playback
            if sent_bytes <= 0:
                return
            # From the clip's own header. Unknown rates fall back to the
            # format this service asks for, which is what it will be.
            rate = byte_rate or (settings.asr_sample_rate * 2)
            seconds = sent_bytes / max(rate, 1)

            if not reports_playback:
                await asyncio.sleep(seconds)
                return

            awaited_playback = mine
            playback_ack.clear()
            try:
                await asyncio.wait_for(
                    playback_ack.wait(),
                    timeout=seconds + settings.voice_playback_grace_s)
            except TimeoutError:
                # Not an error worth telling the citizen about: the audio has
                # almost certainly finished and the page simply did not say
                # so. Recorded because a session where it happens every turn
                # is a page that has stopped reporting.
                log.info("voice.playback.unreported",
                         extra={"seconds": round(seconds, 1)})
            finally:
                awaited_playback = 0

        def release_floor() -> None:
            """The assistant has stopped. Hand the microphone back.

            `speaking` was only ever cleared by the next reply cancelling the
            last one, which was invisible while barge-in did it on every
            utterance — and would have left the microphone muted for the rest
            of the session once barge-in stopped being the default.
            """
            nonlocal speaking
            task = speaking
            # `task is current` matters: this is normally called BY the speech
            # task as its last act, when it is still running and `done()` is
            # false. Without it the floor was never handed back from inside
            # the reply that finished, the phase said "waiting for you" while
            # the gate was still discarding the citizen's answer, and the
            # first thing they said after every reply was thrown away.
            if task is not None and (task.done() or task is asyncio.current_task()):
                speaking = None
            # A half-frame of the assistant's tail must not become the first
            # frame of the citizen's answer.
            if settings.voice_half_duplex:
                vad.reset()
                eos.reset()

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
            nonlocal confirmation_expected, read_back_wanted, long_mode
            nonlocal long_introduced, asking
            language = result.get("language", language)
            confirmation_expected = expects_confirmation(result)
            # Re-read after every turn. The workflow moves from collecting to
            # review on its own, and a read-back offered at the review step
            # would ask the citizen to confirm their own "yes".
            read_back_wanted = settings.voice_read_back and wants_read_back(result)
            long_mode = wants_long_dictation(result)
            asking = field_on_the_table(result)
            apply_pace()
            view = session_view(result)
            reply = result.get("reply") or ""
            spoken = speech_text.speech_for(
                display_text=reply,
                view=view,
                template=template,
                language=language,
                allow_spoken_identifiers=settings.voice_spoken_identifiers,
            )
            # Said ONCE, on the turn that arrives at the narrative question.
            # A citizen asked for their grievance the way they were asked
            # their age answers in one sentence and stops; being told they
            # may take their time is what produces the complaint they have.
            #
            # Appended to the workflow's own question rather than replacing
            # it: the question belongs to the graph, the pacing advice
            # belongs here.
            if long_mode and spoken and not long_introduced:
                spoken = f"{spoken} {speech_text.phrase('long_intro', language)}"
                long_introduced = True

            if listening and spoken:
                await start_speaking(spoken)
            else:
                # Nothing to say. The phase still has to move: it is sitting
                # at PROCESSING from the turn that just finished, and left
                # there the page shows "Thinking…" over a session that is
                # waiting for the citizen. `say` does this at the end of
                # every reply, so a turn with no reply is the one path where
                # it never happened.
                await set_phase(resting())

        async def start_speaking(
                text: str, *, as_phase: Phase = Phase.ASSISTANT_SPEAKING) -> None:
            nonlocal speaking
            await stop_speaking(interrupted=False)
            speaking = asyncio.create_task(say(text, as_phase=as_phase))

        # ---------------------------------------------------------------- #
        # The read-back loop
        #
        # Between hearing an answer and using it, the assistant says it back
        # and waits to be told it is right. Everything below is that loop,
        # and it is the same three actions whether they arrive as speech or
        # as a button press — `on_utterance` classifies words into one of
        # them, the socket's `answer.confirm` / `answer.retry` messages name
        # two of them directly, and both end up here.
        # ---------------------------------------------------------------- #

        async def announce_pending(spoken: str | None, *, lengthy: bool = False) -> None:
            """Tell the page what is outstanding, so its buttons agree with
            the assistant's voice. Sent on every change, `answer: null`
            included, so a panel can never be left up over nothing.

            `lengthy` says the assistant summarised rather than recited, so
            the page knows to offer "read it to me" — the citizen has been
            asked to check something they have not heard.
            """
            with contextlib.suppress(Exception):
                await websocket.send_json({
                    "type": "voice.answer",
                    "answer": spoken,
                    "awaiting": spoken is not None,
                    "lengthy": lengthy,
                })

        # ---------------------------------------------------------------- #
        # Long-form dictation
        # ---------------------------------------------------------------- #

        def grievance_so_far() -> str:
            """Every segment, in the order it was spoken.

            Joined with a single space and nothing else. No summarising, no
            reordering, no sentence the citizen did not say — this is the
            complaint, and it is reproduced verbatim in the document.
            """
            return " ".join(segments).strip()

        async def announce_segments(*, capturing: bool) -> None:
            """What has been captured so far, for the page to show live.

            Sent on every segment so the citizen can watch their own words
            appear. It is the FULL text, never a truncation: the point of the
            panel is that they can see the whole thing before agreeing to it.
            """
            with contextlib.suppress(Exception):
                await websocket.send_json({
                    "type": "voice.dictation",
                    "capturing": capturing,
                    "segments": len(segments),
                    "text": grievance_so_far(),
                })

        def stop_finish_timer() -> None:
            nonlocal finish_task
            task, finish_task = finish_task, None
            # Never the caller's own task. `close_dictation` calls this as
            # its first act, and when the timer is what called
            # `close_dictation` the cancel landed on the task that was
            # running it — killing the close half-done, at its first await,
            # so the citizen's grievance was collected and then silently
            # never offered for confirmation.
            if (task is not None and not task.done()
                    and task is not asyncio.current_task()):
                task.cancel()

        async def start_finish_timer() -> None:
            """Close the dictation after a long enough quiet.

            Separate from the detector's own end-of-speech, and deliberately
            on top of it: the detector decides when a SEGMENT ended, this
            decides when the citizen has stopped altogether. A citizen who is
            thinking gets both timers; a citizen who has finished gets asked
            to confirm without having to say anything at all.
            """
            nonlocal finish_task
            stop_finish_timer()

            async def _wait() -> None:
                try:
                    # The assistant's own voice is not the citizen being
                    # quiet. Counting through it would close the dictation
                    # while it was still saying "please continue".
                    while assistant_has_the_floor():
                        await asyncio.sleep(0.2)
                    await asyncio.sleep(settings.voice_long_finish_s)
                except asyncio.CancelledError:
                    return
                if listening and long_mode and segments and pending is None:
                    await close_dictation()

            finish_task = asyncio.create_task(_wait())

        async def close_dictation() -> None:
            """Everything has been said. Read it back for agreement."""
            stop_finish_timer()
            combined = grievance_so_far()
            if not combined:
                return
            await announce_segments(capturing=False)
            await offer_answer(combined)

        async def collect_segment(text: str) -> None:
            """One more piece of the grievance, or the end of it."""
            # Checked BEFORE the text is kept, so the word "finished" does
            # not end up printed in the complaint.
            if finished(text, language):
                if segments:
                    await close_dictation()
                    return
                # Nothing said yet. "Finished" cannot end an empty answer;
                # asking again is the only reading that does not file a blank
                # grievance.
                await start_speaking(speech_text.phrase("not_understood", language))
                return

            # A REAL limit, met before anything is lost rather than after.
            # The validator refuses text over this length outright, so an
            # unchecked append would hand the citizen's whole narration to a
            # field that rejects it — and the rejection message is not the
            # place to discover that the last two minutes are gone.
            room = MAX_FREE_TEXT - len(grievance_so_far())
            if len(text) + 1 > room:
                log.info("voice.dictation.full", extra={"segments": len(segments)})
                await announce_segments(capturing=False)
                if segments:
                    # ONE sentence, not two. Saying "this form is full" and
                    # then starting a read-back cancels the first mid-word —
                    # `start_speaking` stops whatever is playing — so the
                    # citizen would be told nothing about why their last
                    # minute of speech is missing.
                    await offer_answer(
                        grievance_so_far(),
                        said=speech_text.phrase("long_full", language))
                else:
                    await start_speaking(speech_text.phrase("long_full", language))
                return

            # A final transcript that arrives twice — a retry, a reconnect, a
            # provider repeating itself — must not double a sentence in
            # somebody's complaint. Only the immediately preceding segment is
            # compared: a citizen who really does say the same sentence twice
            # minutes apart is emphasising, and that is theirs to keep.
            if segments and segments[-1] == text:
                log.info("voice.dictation.duplicate", extra={"index": len(segments)})
                await start_finish_timer()
                return

            segments.append(text)
            _keep_draft(session_id, segments)
            log.info("voice.dictation.segment",
                     extra={"index": len(segments), "chars": len(text)})
            await announce_segments(capturing=True)
            await set_phase(Phase.LONG_LISTENING)
            await start_finish_timer()

        async def offer_answer(answer: str, *, said: str = "") -> None:
            """Read one captured answer back and wait to be told it is right.

            The value is masked for SPEECH only. The page is sent the same
            masked text, because the voice panel sits in the same room as the
            speaker: a citizen at a counter has the full value on the chat
            transcript and on the petition, and neither of those is audible
            from the queue.
            """
            nonlocal pending
            pending = answer
            spoken = mask_for_display(answer)
            lengthy = len(answer) > settings.voice_long_readback_chars
            await announce_pending(spoken, lengthy=lengthy)
            # A two-minute grievance read back word for word is two minutes
            # nobody listens to, and the whole of it is already on screen. A
            # short answer is recited, because hearing it is the only way a
            # citizen who cannot read the screen can check it.
            sentence = said or speech_text.read_back_sentence(
                asking, answer, language, lengthy=lengthy)
            await start_speaking(sentence, as_phase=Phase.READING_BACK)

        async def confirm_pending() -> None:
            """The citizen agreed. NOW the workflow sees the answer.

            This is the only path from speech to the petition, and it is
            reached only after the value has been said back to the person it
            belongs to.
            """
            nonlocal pending
            stop_finish_timer()
            answer, pending = pending, None
            segments.clear()
            # Confirmed: it is the petition's now, not a draft.
            _drop_draft(session_id)
            await announce_pending(None)
            await announce_segments(capturing=False)
            if not answer:
                return
            result = await run_turn(answer, via="voice-confirmed")
            if result is not None:
                await respond(result)
            elif listening:
                await set_phase(Phase.LISTENING)

        async def retry_pending() -> None:
            """The citizen said it is wrong and gave nothing to put in its
            place. Throw the candidate away and ask again.

            The rejected transcript is dropped from the duplicate cache
            first. They are about to say the same words again deliberately,
            and without this the guard would discard the repetition as a
            duplicate — asking them to repeat something and then refusing to
            hear it is the worst failure this loop could have.
            """
            nonlocal pending
            stop_finish_timer()
            answer, pending = pending, None
            if answer:
                guard.forget(answer)
            # Starting again means starting again: the whole narration goes,
            # not the last sentence of it. A citizen who says "say it again"
            # about a grievance is rejecting the grievance.
            for segment in segments:
                guard.forget(segment)
            segments.clear()
            _drop_draft(session_id)
            await announce_pending(None)
            await announce_segments(capturing=False)
            await start_speaking(speech_text.phrase("say_again", language))

        async def resume_dictation(extra: str) -> None:
            """They had more to say. The grievance is REOPENED, not replaced.

            Everything already captured stays exactly where it was; this only
            takes the answer off the table and starts listening again. That
            is the whole difference between "also, the drain is blocked" and
            "no, the drain is blocked" — one adds a sentence to a complaint,
            the other would have thrown the complaint away.
            """
            nonlocal pending
            pending = None
            await announce_pending(None)
            if extra and len(extra) + 1 <= MAX_FREE_TEXT - len(grievance_so_far()):
                segments.append(extra)
                _keep_draft(session_id, segments)
            await announce_segments(capturing=True)
            if not extra:
                await start_speaking(speech_text.phrase("long_continue", language))
            else:
                await set_phase(Phase.LONG_LISTENING)
            await start_finish_timer()

        async def read_pending_aloud() -> None:
            """Read the captured answer out in full, on request.

            The summary the assistant gives for a long grievance says the
            text is on screen. A citizen who cannot read it needs this, and
            it is why the summary is a shortcut rather than a replacement.
            """
            if not pending:
                return
            await start_speaking(mask_for_display(pending), as_phase=Phase.READING_BACK)

        async def replace_pending(candidate: str) -> None:
            """The correction was in the same breath as the refusal.

            "No, twelve Kumar Street" is not a request to start again — the
            new answer is already there, and making them repeat it is asking
            a third time for something they have now said twice. It is read
            back in its turn, so a correction is confirmed exactly as an
            original answer is.
            """
            if pending:
                guard.forget(pending)
            await offer_answer(candidate)

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
            nonlocal reading_aloud
            current = await workflow.snapshot(session_id)
            sections = speech_text.readable_sections((current or {}).get("letter_text") or "")
            if not sections:
                await start_speaking(speech_text.phrase("ready_no_read", language))
                return
            reading_aloud = True
            await start_speaking(speech_text.phrase("reading", language))
            for section in sections:
                # Each section is its own utterance, so the citizen speaking
                # over it cancels the rest rather than being read the whole
                # petition before anyone listens to them.
                if speaking is not None:
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await speaking
                if not listening or reading_cancelled.is_set():
                    reading_aloud = False
                    await start_speaking(speech_text.phrase("read_stopped", language))
                    return
                await start_speaking(section)
            if speaking is not None:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await speaking
            reading_aloud = False
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
                nonlocal reading_aloud
                reading_aloud = False
                reading_cancelled.set()
                await stop_speaking(interrupted=False)
                await start_speaking(speech_text.phrase("read_stopped", language))
                return True
            if wants_read:
                reading_cancelled.clear()
                asyncio.create_task(read_petition_aloud())
                return True
            return False

        async def handle_settled(text: str, *, via: str) -> None:
            """One settled answer, however it arrived.

            Spoken and typed turns run THIS, not two copies of it. The
            difference between them ends at the transcript: a citizen who
            gives up on the microphone halfway through and types the rest is
            answering the same question, and a keyboard that skipped the
            confirmation the microphone enforces would put a different thing
            on the petition depending on which one they reached for.
            """
            if pending is not None:
                # In long-form dictation, "also..." and "I forgot to
                # mention..." mean KEEP GOING. Read the ordinary way they
                # would be a correction, and the citizen's whole narration
                # would be replaced by the afterthought.
                if long_mode:
                    carry = continuation(text, language)
                    if carry is not None:
                        log.info("voice.dictation.resumed",
                                 extra={"brought_more": bool(carry)})
                        await resume_dictation(carry)
                        return
                    if _READ_ALOUD.search(text or ""):
                        await read_pending_aloud()
                        return
                reading = read_intent(text, language)
                log.info("voice.readback.reply", extra={"intent": reading.intent})
                if reading.intent == "confirm":
                    await confirm_pending()
                elif reading.intent == "replace":
                    await replace_pending(reading.replacement)
                else:
                    await retry_pending()
                return

            # Long-form: this is one piece of a longer answer, not the whole
            # of it. It is kept and the microphone stays open.
            if long_mode and listening:
                await collect_segment(text)
                return

            if read_back_wanted and listening:
                await offer_answer(text)
                return

            result = await run_turn(text, via=via)
            if result is not None:
                await respond(result)
            elif listening:
                await set_phase(Phase.LISTENING)

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
                await set_phase(resting())
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
                # While an answer is being confirmed, "yes" and "சரி" are the
                # answer to the question on the table — not the sound a
                # transcription service makes out of silence. This is the
                # context that keeps those words out of the hallucination
                # list instead of blacklisting them everywhere, which would
                # make the citizen unable to agree with anything.
                expecting_confirmation=confirmation_expected or pending is not None,
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
                if listening and decision.verdict is Verdict.EMPTY:
                    # The audio carried speech — it cleared every evidence
                    # test above — and the transcription came back with
                    # nothing in it. That is a different thing from a noise
                    # that produced a filler word, and it deserves its own
                    # words: this one is honest about the machine having
                    # failed rather than implying the citizen mumbled.
                    await start_speaking(speech_text.phrase("not_understood", language))
                elif listening and decision.verdict in (
                        Verdict.FILLER_ONLY, Verdict.WRONG_SCRIPT,
                        Verdict.LOW_CONFIDENCE, Verdict.TOO_SHORT):
                    # Heard something, could not make an answer of it. Saying so
                    # is better than silence, which reads as a broken
                    # microphone and makes people repeat into a void.
                    await start_speaking(speech_text.phrase("not_caught", language))
                elif listening:
                    await set_phase(resting())
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

            # Heard over the assistant reading the petition, and not one of
            # the two things the citizen was invited to say. Far more likely
            # to be the document coming back through the microphone than a
            # new instruction, and the cost of acting on it is a petition
            # revised with a sentence of its own text.
            if reading_aloud:
                log.info("voice.discarded", extra={"reason": "during_reading",
                                                   "sent_to_stt": True})
                await send_discarded("during_reading", evidence, sent=True)
                return

            await handle_settled(decision.text, via="voice")

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
            # `playback_overlap_ms` belongs to the session, not to this call.
            # Without it here, the `+=` below raises UnboundLocalError on any
            # buffer that CONTINUES an utterance while the assistant's last
            # reply is still referenced — which killed the socket outright.
            # It was invisible while barge-in cleared `speaking` on the same
            # buffer that bound the variable, and appeared the moment
            # half-duplex stopped barge-in from running.
            nonlocal last_voice_at, playback_overlap_ms
            if not listening:
                return

            # HALF DUPLEX. While the assistant is speaking, nothing arriving
            # from the microphone is an answer — it is the assistant, coming
            # back in through a laptop speaker a foot away. Discarded before
            # the detector sees it, so it cannot become an utterance, cannot
            # be transcribed, and cannot be billed.
            #
            # This is a deliberate trade against barge-in, which needs the
            # microphone open during playback to work at all. Echo rejection
            # catches most self-transcription; most is not enough for a
            # document a citizen signs, and being unable to interrupt is a
            # smaller harm than a fabricated answer. `voice_half_duplex=false`
            # restores interruption for a deployment using headsets.
            if (settings.voice_half_duplex and assistant_has_the_floor()
                    and not reading_aloud):
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
                if (settings.voice_barge_in and not settings.voice_half_duplex
                        and speaking is not None):
                    await stop_speaking(interrupted=True)
                await set_phase(Phase.USER_SPEAKING)
                eos.begin()

            # Kept whenever this buffer belongs to the utterance — including
            # the one the turn opened in, whose first frames are the start of
            # the word, and the one it closed in, whose first frames are the
            # end of it.
            if started or ended or vad.speaking:
                eos.add(chunk)
                if phase in (Phase.ASSISTANT_SPEAKING, Phase.READING_BACK)                         or speaking is not None:
                    playback_overlap_ms += int(len(chunk) / 2 / settings.asr_sample_rate * 1000)

            if ended:
                await eos.finish()
            elif eos.open and eos.seconds > settings.voice_max_utterance_s:
                await eos.finish()

        async def check_the_room() -> None:
            """Say so if the room is loud enough to cost them their answer.

            ADVISORY, and deliberately nothing more. The speech threshold is
            already relative to the measured floor, so a loud room raises the
            bar rather than closing the door — and rejecting speech for being
            said in a noisy place would fail exactly the citizens this is
            for, who are standing in a government office and not a studio.

            The floor read here is the detector's own, learnt from the room
            during the quiet between utterances, not a fixed guess about what
            a microphone sounds like.
            """
            nonlocal loud_checks, noise_advised
            if noise_advised or not listening or assistant_has_the_floor():
                return
            if vad.noise_floor <= settings.voice_noise_advisory_rms:
                loud_checks = 0
                return
            loud_checks += 1
            if loud_checks < settings.voice_noise_advisory_checks:
                return
            noise_advised = True
            # The measurement, never a transcript: this line exists so an
            # operator can tell a loud counter from a broken microphone.
            log.info("voice.room_is_loud",
                     extra={"floor": round(vad.noise_floor, 1),
                            "threshold": round(vad.speech_threshold, 1)})
            with contextlib.suppress(Exception):
                await websocket.send_json({"type": "voice.noise", "high": True})
            await start_speaking(speech_text.phrase("noisy_room", language))

        async def watchdog() -> None:
            """Nudge, then ask, then stop — without touching the petition."""
            nonlocal nudges, listening
            try:
                while True:
                    await asyncio.sleep(2.0)
                    # WAITING_CONFIRMATION is deliberately NOT in this list.
                    # A citizen who goes quiet after a read-back is exactly
                    # who the nudge exists for — they may not have realised a
                    # question was asked.
                    if not listening or phase in (Phase.PROCESSING, Phase.TRANSCRIBING,
                                                  Phase.GENERATING,
                                                  Phase.READING_BACK,
                                                  Phase.ASSISTANT_SPEAKING):
                        continue
                    await check_the_room()
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
            # The EFFECTIVE value, not the configured one. Half-duplex
            # overrides barge-in, and a page told "barge_in: true" while the
            # server is discarding everything it hears would cut the
            # assistant off on its own echo and then listen to nobody.
            "barge_in": settings.voice_barge_in and not settings.voice_half_duplex,
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
                    # Declared by the page rather than assumed. A page that
                    # cannot report playback is timed by the length of the
                    # audio instead of being waited on until a grace period
                    # expires on every single turn.
                    reports_playback = bool(payload.get("reports_playback"))
                    nudges = 0
                    last_voice_at = time.monotonic()
                    vad.reset()
                    eos.reset()
                    apply_pace()
                    await set_phase(Phase.LISTENING)
                    if watchdog_task is None:
                        watchdog_task = asyncio.create_task(watchdog())
                    # Greet with the question that is actually outstanding,
                    # asked by the workflow rather than invented here.
                    current = await workflow.snapshot(session_id)
                    if current:
                        await respond(current)
                    # What the citizen had already said before the connection
                    # dropped. Sent AFTER the question, so the page draws the
                    # panel back with their words in it and they can see that
                    # the ninety seconds they spent are still there.
                    if segments:
                        log.info("voice.dictation.restored",
                                 extra={"segments": len(segments)})
                        await announce_segments(capturing=True)
                        await start_finish_timer()

                elif kind == "voice.end":
                    listening = False
                    stop_finish_timer()
                    pending = None
                    segments.clear()
                    # Ending the session deliberately is not losing it: the
                    # citizen chose to stop, so the draft goes with it.
                    _drop_draft(session_id)
                    await announce_pending(None)
                    await stop_speaking(interrupted=False)
                    eos.abandon()
                    vad.reset()
                    await set_phase(Phase.IDLE)
                    await websocket.send_json({"type": "voice.ended", "reason": "requested"})

                elif kind == "voice.interrupt":
                    # WHY THIS IS NOT BELIEVED UNCONDITIONALLY ANY MORE.
                    #
                    # The page runs its own onset detector so that an
                    # interruption is instant rather than a round trip late.
                    # It has no echo discrimination: on a counter PC the
                    # loudest thing in the microphone while the assistant is
                    # talking IS the assistant. So the assistant's own voice
                    # cut its own question off mid-sentence and opened the
                    # microphone early — which is the whole failure that
                    # half-duplex exists to prevent, arriving through the
                    # one door that bypassed it.
                    #
                    # A TYPED interrupt is different and is always honoured:
                    # somebody reaching for the keyboard while the assistant
                    # is talking is unambiguous, and no speaker can produce
                    # it.
                    typed = payload.get("reason") == "typed"
                    allowed = typed or (settings.voice_barge_in
                                        and not settings.voice_half_duplex)
                    if not allowed:
                        log.info("voice.interrupt.ignored",
                                 extra={"reason": payload.get("reason") or "microphone"})
                        continue
                    await stop_speaking(interrupted=True)
                    if listening:
                        await set_phase(resting())

                elif kind == "tts.played":
                    # The audio has finished coming out of the speaker. Only
                    # the reply currently being waited on counts: a report
                    # for an older one is a message that overtook an
                    # interruption and must not open the microphone early.
                    if awaited_playback and payload.get("id") == awaited_playback:
                        playback_ack.set()

                elif kind == "dictation.finish":
                    # The page's Finish button. The same call the citizen
                    # makes by saying "finished", and by falling quiet.
                    if long_mode and segments and pending is None:
                        await stop_speaking(interrupted=False)
                        eos.abandon()
                        await close_dictation()

                elif kind == "dictation.restart":
                    # Start the whole narration again, mid-flow. Everything
                    # captured goes; nothing has reached the petition yet.
                    if long_mode:
                        stop_finish_timer()
                        for segment in segments:
                            guard.forget(segment)
                        segments.clear()
                        _drop_draft(session_id)
                        eos.abandon()
                        await announce_segments(capturing=True)
                        await start_speaking(speech_text.phrase("say_again", language))

                elif kind == "answer.read":
                    # "Read it to me." The summary for a long grievance says
                    # the text is on screen; this is for the citizen who
                    # cannot read it.
                    await read_pending_aloud()

                elif kind == "answer.confirm":
                    # The page's Confirm button. Not a second implementation
                    # of confirming — the same call the voice path makes when
                    # it hears "yes", so a citizen can start an answer by
                    # speaking and finish it by tapping.
                    if pending is not None:
                        await stop_speaking(interrupted=False)
                        eos.abandon()
                        await confirm_pending()

                elif kind == "answer.retry":
                    if pending is not None:
                        await stop_speaking(interrupted=False)
                        eos.abandon()
                        await retry_pending()

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
                    # The SAME call the spoken path makes, deliberately.
                    await handle_settled(typed, via="ws-text")

                elif kind == "cancel":
                    listening = False
                    stop_finish_timer()
                    pending = None
                    segments.clear()
                    _drop_draft(session_id)
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
            stop_finish_timer()
            if watchdog_task is not None:
                watchdog_task.cancel()
            await stop_speaking(interrupted=False)
            eos.abandon()
