"""Regression checks for fresh documents and complete, private spoken replies."""

from __future__ import annotations

import asyncio
import base64
import io
import wave
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.services import render, speech_text, tts

PDF_BYTES = b"%PDF-1.7\nconverter output\n%%EOF\n"


class FakeProcess:
    def __init__(self, *, returncode=0, error=None):
        self.returncode = returncode
        self.error = error
        self.killed = False
        self.communications = 0

    async def communicate(self):
        self.communications += 1
        if self.error is not None:
            error, self.error = self.error, None
            raise error
        return b"", b""

    def kill(self):
        self.killed = True
        self.returncode = -9


def pdf_settings(**kwargs):
    return Settings(_env_file=None, pdf_engine="libreoffice", **kwargs)


def fake_converter(monkeypatch, *, contents=PDF_BYTES, process=None):
    process = process or FakeProcess()
    seen = []

    async def spawn(*args, **kwargs):
        seen.append(args)
        source = Path(args[-1])
        if contents is not None:
            source.with_suffix(".pdf").write_bytes(contents)
        return process

    monkeypatch.setattr(render.shutil, "which", lambda _: "soffice")
    monkeypatch.setattr(render.asyncio, "create_subprocess_exec", spawn)
    return process, seen


class TestFreshPdf:
    async def test_failed_conversion_never_returns_a_previous_pdf(self, tmp_path, monkeypatch):
        source = tmp_path / "petition.docx"
        source.write_bytes(b"updated document")
        previous = source.with_suffix(".pdf")
        previous.write_bytes(PDF_BYTES)
        fake_converter(monkeypatch, contents=None)

        output, error = await render.render_pdf(source, pdf_settings())

        assert output is None and error
        assert previous.read_bytes() == PDF_BYTES
        assert not list(tmp_path.glob(".petition-pdf-*"))

    @pytest.mark.parametrize("contents,returncode", [
        (b"", 0), (b"not a PDF", 0), (b"%PDF-1.7\nunfinished", 0), (PDF_BYTES, 1),
    ])
    async def test_incomplete_or_failed_output_is_withheld(
        self, tmp_path, monkeypatch, contents, returncode
    ):
        source = tmp_path / "petition.docx"
        source.write_bytes(b"document")
        fake_converter(monkeypatch, contents=contents, process=FakeProcess(returncode=returncode))

        output, error = await render.render_pdf(source, pdf_settings())

        assert output is None and error
        assert not source.with_suffix(".pdf").exists()

    async def test_success_publishes_new_output_and_uses_an_isolated_profile(
        self, tmp_path, monkeypatch
    ):
        source = tmp_path / "petition.docx"
        source.write_bytes(b"document")
        _, calls = fake_converter(monkeypatch)

        output, error = await render.render_pdf(source, pdf_settings())

        assert output == source.with_suffix(".pdf") and error is None
        assert output.read_bytes() == PDF_BYTES
        assert any(arg.startswith("-env:UserInstallation=file:") for arg in calls[0])
        assert Path(calls[0][-1]).parent != source.parent
        assert not list(tmp_path.glob(".petition-pdf-*"))

    @pytest.mark.parametrize("error", [TimeoutError(), asyncio.CancelledError()])
    async def test_timeout_and_cancellation_reap_the_converter(self, tmp_path, monkeypatch, error):
        source = tmp_path / "petition.docx"
        source.write_bytes(b"document")
        process, _ = fake_converter(
            monkeypatch, contents=None, process=FakeProcess(returncode=None, error=error)
        )

        if isinstance(error, asyncio.CancelledError):
            with pytest.raises(asyncio.CancelledError):
                await render.render_pdf(source, pdf_settings())
        else:
            output, reason = await render.render_pdf(source, pdf_settings())
            assert output is None and "timed out" in reason

        assert process.killed and process.communications == 2
        assert not list(tmp_path.glob(".petition-pdf-*"))

    async def test_word_quotes_apostrophes_in_document_paths(self, tmp_path, monkeypatch):
        source = tmp_path / "citizen's petition.docx"
        source.write_bytes(b"document")
        seen = []

        async def spawn(*args, **kwargs):
            seen.extend(args)
            source.with_suffix(".pdf").write_bytes(PDF_BYTES)
            return FakeProcess()

        monkeypatch.setattr(render.asyncio, "create_subprocess_exec", spawn)
        output, error = await render._pdf_via_word(source)
        assert output and error is None
        assert "citizen''s petition.docx" in seen[-1]

    async def test_a_missing_reference_withholds_the_document(self, chat, answers, monkeypatch):
        from app.graph import nodes

        extract = render.extract_docx_text

        def without_footer(path):
            return "\n".join(extract(path).splitlines()[:-1])

        monkeypatch.setattr(nodes.render_service, "extract_docx_text", without_footer)
        conversation = chat()
        await conversation.answer_all(answers)
        state = await conversation.say("yes")

        assert state["status"] == "failed"
        assert state["verification"]["missing_values"] == []
        assert state["verification"]["reference_ok"] is False

    async def test_truncating_the_end_of_the_grievance_fails_verification(
        self, chat, answers, monkeypatch
    ):
        extract = render.extract_docx_text
        monkeypatch.setattr(
            render, "extract_docx_text",
            lambda path: extract(path).replace(
                "I have complained twice at the panchayat office and nothing has been done.", ""
            ),
        )
        conversation = chat()
        await conversation.answer_all(answers)
        state = await conversation.say("yes")
        assert state["status"] == "failed"
        assert state["verification"]["missing_values"] == ["grievance"]

    async def test_a_missing_age_cannot_match_digits_inside_an_identifier(
        self, chat, answers, monkeypatch
    ):
        extract = render.extract_docx_text
        monkeypatch.setattr(
            render, "extract_docx_text", lambda path: extract(path).replace("Age: 45", "Age:")
        )
        conversation = chat()
        await conversation.answer_all(answers)
        state = await conversation.say("yes")
        assert state["status"] == "failed"
        assert state["verification"]["missing_values"] == ["age"]


def wav_bytes(*, rate=16000, frames=80):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x01\x00" * frames)
    return buffer.getvalue()


def fake_speech_service(monkeypatch, responses):
    sent = []

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, **kwargs):
            sent.append(kwargs["json"]["text"])
            return responses.pop(0)

    monkeypatch.setattr(tts.httpx, "AsyncClient", Client)
    return sent


def speech_settings():
    return Settings(_env_file=None, tts_provider="auto", sarvam_api_keys="test-key")


class TestPrivateCompleteSpeech:
    @pytest.mark.parametrize("identifier", [
        "ravi@example.com", "ABCDE1234F", "ABC1234567", "2345 6789 0124", "+91 98765 43210",
    ])
    def test_speech_redacts_numeric_and_alphanumeric_identifiers(self, identifier):
        assert identifier not in speech_text.redact_for_speech(f"I recorded {identifier}.")

    async def test_redaction_is_also_applied_at_the_provider_boundary(self, monkeypatch):
        response = httpx.Response(200, json={"audios": [base64.b64encode(wav_bytes()).decode()]})
        sent = fake_speech_service(monkeypatch, [response])
        audio = await tts.speak(
            "Your Aadhaar is 2345 6789 0124, email ravi@example.com.", settings=speech_settings()
        )
        assert audio is not None
        assert "2345" not in sent[0] and "ravi@example.com" not in sent[0]

    @pytest.mark.parametrize("response", [
        httpx.Response(200, content=b"not JSON"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"audios": "not an array"}),
        httpx.Response(200, json={"audios": ["not base64!"]}),
        httpx.Response(200, json={"audios": [base64.b64encode(b"not WAV").decode()]}),
        httpx.Response(503),
    ])
    async def test_bad_provider_responses_degrade_to_text(self, monkeypatch, response):
        fake_speech_service(monkeypatch, [response])
        assert await tts.speak("Please enter your name.", settings=speech_settings()) is None

    async def test_a_partial_reply_is_not_returned_as_complete_audio(self, monkeypatch):
        response = httpx.Response(200, json={"audios": [base64.b64encode(wav_bytes()).decode()]})
        fake_speech_service(monkeypatch, [response, httpx.Response(503)])
        assert await tts.speak("Please listen. " * 45, settings=speech_settings()) is None

    def test_joining_preserves_all_frames(self):
        audio = tts.join_wav([wav_bytes(frames=40), wav_bytes(frames=60)])
        with wave.open(io.BytesIO(audio), "rb") as handle:
            assert handle.getnframes() == 100

    def test_mismatched_and_truncated_clips_are_not_played(self):
        assert tts.join_wav([wav_bytes(rate=16000), wav_bytes(rate=24000)]) is None
        assert tts.join_wav([wav_bytes()[:-10]]) is None
        assert tts.join_wav([wav_bytes(), b"invalid"]) is None

    def test_even_a_single_long_word_is_split_into_valid_chunks(self):
        chunks = tts._chunks("a" * 1000)
        assert all(0 < len(chunk) <= tts._CHUNK for chunk in chunks)
        assert "".join(chunks) == "a" * 1000
