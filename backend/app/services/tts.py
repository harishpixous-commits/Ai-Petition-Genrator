"""Speaking the assistant's replies.

Optional by design. When no TTS provider is configured the API returns the reply
text and nothing else, and the client speaks it with the browser's own voice or
simply shows it. A citizen who can read the question is not blocked by a missing
credential.

Sarvam is preferred for Tamil for the same reason it is preferred for
translation: it is Indic-first, and a Tamil sentence read by a generic
multilingual voice is hard to follow at a counter with background noise.
"""

from __future__ import annotations

import base64
import io
import logging
import wave
from collections.abc import AsyncIterator

import httpx

from ..config import Settings, get_settings
from .speech_text import redact_for_speech

log = logging.getLogger(__name__)

# Sarvam rejects long inputs; the replies this service produces are short, but a
# confirmation read-back can run long and must be split rather than truncated.
_CHUNK = 450


class TTSUnavailable(RuntimeError):
    """Speech could not be completed; the visible reply remains available."""


def configured(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    if (s.tts_provider or "auto").lower() == "off":
        return False
    return bool(s.sarvam_key_list)


def status(settings: Settings | None = None) -> dict:
    s = settings or get_settings()
    if not configured(s):
        return {
            "ok": False,
            "provider": None,
            "egress": False,
            "note": "Spoken replies are not configured. The client may use the browser's own voice.",
        }
    return {
        "ok": True,
        "provider": "Sarvam",
        "model": s.sarvam_tts_model,
        "egress": True,
        "note": "Reply text is sent to a hosted service to be spoken. Citizen identifiers are not spoken.",
    }


def _chunks(text: str) -> list[str]:
    words, out, current = str(text or "").split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > _CHUNK:
            if current:
                out.append(current)
                current = ""
            while len(word) > _CHUNK:
                out.append(word[:_CHUNK])
                word = word[_CHUNK:]
        current = f"{current} {word}".strip()
    if current:
        out.append(current)
    return out


def join_wav(parts: list[bytes]) -> bytes | None:
    """Join several WAV clips into one playable clip.

    Concatenating the bytes does not work and used to be what this did: every
    clip carries its own 44-byte RIFF header, so the result is one valid file
    followed by rubbish, and every decoder worth the name plays the first
    sentence and stops. For a one-line prompt that is invisible; for a read-back
    listing six fields the citizen hears the first few words and silence.
    """
    frames, params = [], None
    for part in parts:
        if not part:
            return None
        try:
            with wave.open(io.BytesIO(part), "rb") as handle:
                clip_params = handle.getparams()
                if params is None:
                    params = clip_params
                elif (params.nchannels, params.sampwidth, params.framerate, params.comptype) != (
                    clip_params.nchannels, clip_params.sampwidth,
                    clip_params.framerate, clip_params.comptype,
                ):
                    return None
                data = handle.readframes(handle.getnframes())
                expected = handle.getnframes() * handle.getnchannels() * handle.getsampwidth()
                if not data or len(data) != expected:
                    return None
                frames.append(data)
        except (wave.Error, EOFError):
            return None
    if params is None or not frames:
        return None

    out = io.BytesIO()
    with wave.open(out, "wb") as handle:
        handle.setnchannels(params.nchannels)
        handle.setsampwidth(params.sampwidth)
        handle.setframerate(params.framerate)
        handle.writeframes(b"".join(frames))
    return out.getvalue()


async def stream(
    text: str, language: str = "en", settings: Settings | None = None
) -> AsyncIterator[bytes]:
    """Yield the reply as playable clips, sentence group by sentence group.

    Streaming matters more here than anywhere else in the service. A citizen
    waiting in silence for a whole paragraph to be synthesised believes the
    thing is broken; hearing the first clause a few hundred milliseconds in,
    they believe it is listening. The caller can also stop consuming the moment
    the citizen interrupts, which is what makes barge-in feel immediate rather
    than merely eventual.
    """
    s = settings or get_settings()
    text = redact_for_speech(text)
    if not configured(s) or not text:
        return

    keys = s.sarvam_key_list
    payload_base = {
        "target_language_code": "ta-IN" if language == "ta" else "en-IN",
        "model": s.sarvam_tts_model,
        "speaker": s.sarvam_tts_speaker,
    }

    active = 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        for chunk in _chunks(text):
            encoded = None
            for offset in range(len(keys)):
                key = keys[(active + offset) % len(keys)]
                try:
                    response = await client.post(
                        "https://api.sarvam.ai/text-to-speech",
                        headers={"api-subscription-key": key, "Content-Type": "application/json"},
                        json={**payload_base, "text": chunk},
                    )
                except httpx.HTTPError as exc:
                    raise TTSUnavailable("Speech service could not be reached.") from exc
                if response.status_code < 400:
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise TTSUnavailable("Speech service returned invalid audio.") from exc
                    audios = payload.get("audios") if isinstance(payload, dict) else None
                    encoded = audios[0] if isinstance(audios, list) and audios else None
                    active = (active + offset) % len(keys)
                    break
                # Only a credential or quota problem is worth another key.
                if response.status_code not in (401, 402, 403, 429):
                    raise TTSUnavailable(f"Speech service returned HTTP {response.status_code}.")
            if not isinstance(encoded, str) or not encoded:
                raise TTSUnavailable("Speech service produced no audio.")
            try:
                clip = base64.b64decode(encoded, validate=True)
            except ValueError as exc:
                raise TTSUnavailable("Speech service returned invalid audio.") from exc
            if join_wav([clip]) is None:
                raise TTSUnavailable("Speech service returned incomplete audio.")
            yield clip


async def speak(text: str, language: str = "en", settings: Settings | None = None) -> bytes | None:
    """Render `text` to one WAV clip, or None when TTS is unavailable.

    Returns None rather than raising: a failed voice is a degraded experience,
    not a failed turn, and the caller has already sent the text.
    """
    try:
        parts = [part async for part in stream(text, language, settings)]
    except TTSUnavailable as exc:
        log.info("tts.unavailable", extra={"reason": str(exc)})
        return None
    return join_wav(parts) if parts else None
