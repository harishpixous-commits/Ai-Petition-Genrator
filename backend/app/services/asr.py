"""Live speech to text.

    microphone -> browser WS -> this service -> streaming ASR -> partial text
                                                             -> final transcript

The browser never sees the ASR credential. Both providers sit behind this one
module, so replacing them with an on-premise engine for a departmental rollout is
a server-side change the client never notices.

Honest note, carried into the API response and meant to reach the screen: audio
DOES leave this machine while a hosted provider is configured. That is stated,
not buried.

The Deepgram model default is load-bearing and cost a demonstration in the Node
service: `nova-2-general` answers HTTP 400 "No such model/language/tier
combination found" for Tamil, and Tamil is the default on the intake screen. Every
Tamil dictation failed while the status endpoint cheerfully reported the service
as available. `nova-3` has Tamil.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import math
import time
import wave
from collections.abc import AsyncIterator
from dataclasses import dataclass
from urllib.parse import urlencode

import websockets

from ..config import Settings, get_settings

log = logging.getLogger(__name__)


@dataclass
class Transcript:
    text: str
    final: bool
    turn: int = 0


# What each provider is available for, in the order `auto` prefers them.
#
# Sarvam and Groq are BATCH engines: they read a finished recording rather than
# a live stream, so the citizen gets no running transcript and one settled
# result when they stop speaking. That is the right trade here. Dictation on
# this form is a person reading out a name, a number, or a complaint and then
# stopping — not a continuous conversation — and the engines that do Tamil
# properly are the batch ones.
_PROVIDERS = ("sarvam", "groq", "deepgram", "assemblyai")

_LABELS = {
    "sarvam": "Sarvam saarika",
    "groq": "Groq Whisper",
    "deepgram": "Deepgram streaming",
    "assemblyai": "AssemblyAI streaming",
}

# Which providers can be trusted with Tamil. AssemblyAI's streaming model is
# English-only, so offering it on a Tamil form would be offering silence.
_TAMIL = {"sarvam", "groq", "deepgram"}

BATCH_PROVIDERS = ("sarvam", "groq")


def _configured(provider: str, s: Settings) -> bool:
    if provider == "sarvam":
        return bool(s.sarvam_key_list)
    if provider == "groq":
        return bool(s.groq_key_list)
    if provider == "deepgram":
        return bool(s.deepgram_api_key)
    return bool(s.assemblyai_api_key)


def available_providers(settings: Settings | None = None) -> list[str]:
    """Every configured provider, best first. More than one means failover."""
    s = settings or get_settings()
    forced = (s.stream_asr_provider or "auto").lower()
    if forced == "off":
        return []
    if forced in _PROVIDERS:
        # A named provider is a named provider. If the operator pinned one, a
        # silent fall through to another is not a kindness — it sends audio
        # somewhere they did not choose.
        return [forced] if _configured(forced, s) else []
    return [p for p in _PROVIDERS if _configured(p, s)]


def choose_provider(settings: Settings | None = None) -> str | None:
    providers = available_providers(settings)
    return providers[0] if providers else None


def status(settings: Settings | None = None) -> dict:
    s = settings or get_settings()
    providers = available_providers(s)
    if not providers:
        return {
            "ok": False,
            "provider": None,
            "egress": False,
            "languages": [],
            "note": "Live dictation is not configured. The citizen can type instead.",
        }
    primary = providers[0]
    fallbacks = [_LABELS[p] for p in providers[1:]]
    note = (
        "Audio is sent to a hosted service while dictation runs. Nothing is "
        "stored here until the petition is saved. For a departmental rollout, "
        "point this at an on-premise engine."
    )
    if fallbacks:
        note += " If it does not answer, dictation falls back to " + ", ".join(fallbacks) + "."
    return {
        "ok": True,
        "provider": _LABELS[primary],
        "providers": [_LABELS[p] for p in providers],
        "mode": "batch" if primary in BATCH_PROVIDERS else "streaming",
        "egress": True,
        "sample_rate": s.asr_sample_rate,
        "max_seconds": s.asr_max_seconds,
        "languages": ["ta", "en"] if primary in _TAMIL else ["en"],
        "note": note,
    }


# --------------------------------------------------------------------------- #
# Provider adapters
# --------------------------------------------------------------------------- #


class _Adapter:
    """One upstream ASR socket, normalised to `Transcript` objects."""

    def __init__(self, socket: websockets.WebSocketClientProtocol) -> None:
        self.socket = socket

    async def send_audio(self, chunk: bytes) -> None:
        await self.socket.send(chunk)

    async def stop(self) -> None:  # pragma: no cover - provider specific
        raise NotImplementedError

    def read(self, message: dict) -> Transcript | None:  # pragma: no cover
        raise NotImplementedError

    async def close(self) -> None:
        try:
            await self.socket.close()
        except Exception:  # noqa: BLE001
            pass

    async def __aiter__(self) -> AsyncIterator[Transcript]:
        async for raw in self.socket:
            if isinstance(raw, bytes):
                continue
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            if message.get("error") or message.get("type") == "Error":
                raise RuntimeError(str(message.get("error") or message.get("message"))[:200])
            result = self.read(message)
            if result is not None:
                yield result


class _Deepgram(_Adapter):
    """Interim and final results arrive on one socket, keyed by `is_final`."""

    def read(self, message: dict) -> Transcript | None:
        if message.get("type") != "Results":
            return None
        alternatives = (message.get("channel") or {}).get("alternatives") or [{}]
        text = alternatives[0].get("transcript") or ""
        if not text.strip():
            return None
        return Transcript(text=text, final=bool(message.get("is_final")),
                          turn=int(message.get("start") or 0))

    async def stop(self) -> None:
        await self.socket.send(json.dumps({"type": "CloseStream"}))


class _AssemblyAI(_Adapter):
    """v3 `Turn` objects carry the running text for a `turn_order`."""

    def read(self, message: dict) -> Transcript | None:
        if message.get("type") != "Turn":
            return None
        text = message.get("transcript") or ""
        if not text.strip():
            return None
        # `turn_is_formatted` is always true when format_turns=true, so it says
        # nothing about completeness. `end_of_turn` is the only real marker.
        return Transcript(text=text, final=message.get("end_of_turn") is True,
                          turn=int(message.get("turn_order") or 0))

    async def stop(self) -> None:
        await self.socket.send(json.dumps({"type": "Terminate"}))


# --------------------------------------------------------------------------- #
# Batch dictation — Sarvam, then Groq Whisper
# --------------------------------------------------------------------------- #


def _wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap raw 16-bit mono PCM in a RIFF header.

    The browser sends headerless PCM because that is what an AudioWorklet
    produces. Both batch engines want a file, and a WAV header is 44 bytes.
    """
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)
    return buffer.getvalue()


def sarvam_locale(language: str) -> str:
    """The session's language, as Sarvam names it."""
    return {"ta": "ta-IN", "en": "en-IN", "hi": "hi-IN"}.get(language, "en-IN")


async def _sarvam_stt(client, *, key: str, audio: bytes, model: str, language: str,
                      timeout: float) -> tuple[str, float | None]:
    """One Sarvam transcription, in the language the citizen chose.

    This used to send `language_code=unknown` and let the service detect the
    language, to avoid a trap: asked to read Tamil audio as `en-IN`, Sarvam
    does not fail — it returns a fluent ENGLISH TRANSLATION. On a form whose
    grievance is reproduced word for word that would have the citizen signing a
    paraphrase of their own complaint.

    Auto-detect turned out to be the worse of the two. Detection is a guess,
    and on audio with no words in it the guess is arbitrary: a keyboard click
    came back as the English "Okay" with language confidence 0.765, and a burst
    of noise in a Tamil session came back as Bengali. The citizen has already
    told us which language they are using — on screen, in the language
    selector — and the trap only springs when the locale disagrees with the
    speech, which is precisely what using their own choice avoids.

    The remaining case, a citizen speaking Tamil in an English session, is
    handled where it belongs: the commit guard checks the script, and the
    citizen can switch the selector.
    """
    response = await client.post(
        "https://api.sarvam.ai/speech-to-text",
        headers={"api-subscription-key": key},
        files={"file": ("dictation.wav", audio, "audio/wav")},
        data={"model": model, "language_code": sarvam_locale(language)},
        timeout=timeout,
    )
    response.raise_for_status()
    body = response.json() or {}
    # Sarvam returns `language_probability` only in auto-detect mode, so there
    # is no per-transcript confidence to read here. The evidence gate and the
    # commit guard carry the weight instead.
    return str(body.get("transcript") or "").strip(), None


async def _groq_stt(client, *, key: str, audio: bytes, model: str, language: str,
                    timeout: float) -> tuple[str, float | None]:
    """One Groq Whisper transcription, with a quality figure.

    Whisper takes a language hint rather than translating, so passing the
    session language here is safe — and `/audio/transcriptions` never
    translates, unlike the sibling `/audio/translations` endpoint, which is
    why this must not be pointed at that one.

    `verbose_json` costs nothing and returns per-segment `no_speech_prob` and
    `avg_logprob`, which is the only real confidence signal either provider
    offers. Whisper invents words from silence as readily as anything else —
    it produced a sentence from a clip of digital silence — but it says so in
    the numbers when it does, and those are worth reading.
    """
    response = await client.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {key}"},
        files={"file": ("dictation.wav", audio, "audio/wav")},
        data={"model": model, "language": "ta" if language == "ta" else "en",
              "response_format": "verbose_json"},
        timeout=timeout,
    )
    response.raise_for_status()
    body = response.json() or {}
    text = str(body.get("text") or "").strip()

    segments = body.get("segments") or []
    if not segments:
        return text, None
    # The worst segment decides. A transcript is only as trustworthy as the
    # least trustworthy part of it, and a single confident clause does not
    # vouch for the rest.
    no_speech = max(float(s.get("no_speech_prob") or 0.0) for s in segments)
    logprob = min(float(s.get("avg_logprob") or 0.0) for s in segments)
    # Map to 0..1, where the observed hallucinations sat around 0.2-0.45 and
    # real speech well above. Deliberately coarse: it is one input to the
    # guard, not a verdict on its own.
    confidence = max(0.0, min(1.0, (1.0 - no_speech) * min(1.0, math.exp(logprob))))
    return text, confidence


async def transcribe_with_confidence(
    audio: bytes, language: str, settings: Settings | None = None
) -> tuple[str, float | None]:
    """One finished recording to text, over every configured engine in turn.

    Bounded twice: `stt_timeout_ms` per request and `stt_budget_ms` for the
    whole thing. A citizen who has stopped speaking is watching a spinner, and
    a dictation that never comes back is worse than one that says it failed.
    """
    import httpx

    s = settings or get_settings()
    providers = [p for p in available_providers(s) if p in BATCH_PROVIDERS]
    if not providers:
        raise RuntimeError("Live dictation is not configured.")

    per_call = s.stt_timeout_ms / 1000
    deadline = time.monotonic() + s.stt_budget_ms / 1000
    errors: list[str] = []

    async with httpx.AsyncClient() as client:
        for provider in providers:
            keys = s.sarvam_key_list if provider == "sarvam" else s.groq_key_list
            for index, key in enumerate(keys):
                left = deadline - time.monotonic()
                if left < 2.0:
                    errors.append("time budget exhausted")
                    break
                # Reserve time for the provider behind this one. Measured on a
                # live DNS dropout: four Sarvam keys each spent ~20s failing to
                # resolve, the 75s budget was gone, and Groq Whisper — which
                # was configured, healthy and would have answered — was never
                # called at all. A fallback that only runs when the primary
                # fails quickly is not a fallback.
                if provider != providers[-1] and left < s.stt_timeout_ms / 1000:
                    errors.append(f"{provider}: gave up to leave time for the fallback")
                    break
                try:
                    if provider == "sarvam":
                        text, confidence = await _sarvam_stt(
                            client, key=key, audio=audio, model=s.sarvam_stt_model,
                            language=language, timeout=min(per_call, left))
                    else:
                        text, confidence = await _groq_stt(
                            client, key=key, audio=audio, model=s.groq_stt_model,
                            language=language, timeout=min(per_call, left))
                    if text:
                        log.info("asr.transcribed",
                                 extra={"provider": provider, "key_index": index,
                                        "chars": len(text),
                                        "confidence": (round(confidence, 3)
                                                       if confidence is not None else None)})
                        return text, confidence
                    # An empty transcript is an answer, not a failure: the
                    # citizen pressed stop without saying anything.
                    return "", confidence
                except httpx.TransportError as exc:
                    # DNS, connect and read failures are about the network or
                    # the host, not the credential. Working through the other
                    # keys just repeats the same failure at the same cost, so
                    # this provider is abandoned and the next one gets a turn.
                    errors.append(f"{provider}: {exc}"[:160])
                    break
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{provider}: {exc}"[:160])

    raise RuntimeError("Dictation failed. " + " | ".join(errors[:4]))


async def transcribe(audio: bytes, language: str, settings: Settings | None = None) -> str:
    """Just the text, for callers that have no use for the quality figure."""
    text, _ = await transcribe_with_confidence(audio, language, settings)
    return text


class _BatchAdapter(_Adapter):
    """Buffer the whole utterance, transcribe it when the citizen stops.

    Presents the same interface as a streaming adapter so the socket, the
    graph, and the page cannot tell the difference — apart from the absence of
    a running partial transcript, which these engines do not offer.
    """

    def __init__(self, language: str, settings: Settings) -> None:
        self.language = language
        self.settings = settings
        self.socket = None  # no upstream socket; `close` is overridden
        self._chunks: list[bytes] = []
        self._size = 0
        self._turn = 0
        self._results: asyncio.Queue = asyncio.Queue()
        # 16-bit mono: two bytes per sample.
        self._limit = settings.asr_max_seconds * settings.asr_sample_rate * 2
        self._truncated = False

    async def send_audio(self, chunk: bytes) -> None:
        if self._size >= self._limit:
            # Cut off rather than grow without bound. Whatever was said in the
            # first two minutes is still transcribed when they stop.
            if not self._truncated:
                self._truncated = True
                log.info("asr.recording_capped",
                         extra={"seconds": self.settings.asr_max_seconds})
            return
        self._chunks.append(chunk)
        self._size += len(chunk)

    async def stop(self) -> None:
        pcm = b"".join(self._chunks)
        self._chunks.clear()
        self._size = 0
        self._truncated = False

        # Under a fifth of a second is a misclick, not an utterance.
        if len(pcm) < self.settings.asr_sample_rate // 5 * 2:
            return

        self._turn += 1
        text = await transcribe(_wav(pcm, self.settings.asr_sample_rate),
                                self.language, self.settings)
        if text:
            await self._results.put(Transcript(text=text, final=True, turn=self._turn))

    async def __aiter__(self) -> AsyncIterator[Transcript]:
        while True:
            item = await self._results.get()
            if item is None:
                return
            yield item

    async def close(self) -> None:
        await self._results.put(None)


async def open_stream(language: str, settings: Settings | None = None) -> _Adapter:
    """Open an upstream ASR session for `language`."""
    s = settings or get_settings()
    provider = choose_provider(s)
    if not provider:
        raise RuntimeError("Live dictation is not configured.")

    if provider in BATCH_PROVIDERS:
        return _BatchAdapter(language, s)

    if provider == "deepgram":
        query = urlencode(
            {
                "model": s.deepgram_model,
                "language": "ta" if language == "ta" else "en" if language == "en" else "multi",
                "encoding": "linear16",
                "sample_rate": str(s.asr_sample_rate),
                "channels": "1",
                "interim_results": "true",
                "punctuate": "true",
                "smart_format": "true",
                "endpointing": "600",
            }
        )
        socket = await websockets.connect(
            f"wss://api.deepgram.com/v1/listen?{query}",
            additional_headers={"Authorization": f"Token {s.deepgram_api_key}"},
            max_size=None,
        )
        return _Deepgram(socket)

    # AssemblyAI issues a short-lived token; the browser still never sees the key.
    import httpx

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            "https://streaming.assemblyai.com/v3/token",
            params={"expires_in_seconds": 300},
            headers={"authorization": s.assemblyai_api_key},
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Could not start dictation ({response.status_code}).")
    token = (response.json() or {}).get("token")
    if not token:
        raise RuntimeError("Dictation service returned no token.")

    socket = await websockets.connect(
        f"wss://streaming.assemblyai.com/v3/ws?sample_rate={s.asr_sample_rate}"
        f"&encoding=pcm_s16le&format_turns=true&token={token}",
        max_size=None,
    )
    return _AssemblyAI(socket)
