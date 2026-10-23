"""Structured logging.

Every log line that concerns a conversation carries `session_id`, and every graph
node logs its own latency. That pairing is what makes a slow voice turn
diagnosable after the fact: you can see which node spent the time without
reproducing the call.

Citizen text is NEVER logged verbatim. Utterances are logged as a length and a
masked preview, so an operator debugging a stuck session can see the shape of
what arrived without the log becoming a store of personal data with none of the
protections the database has.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_session_id: ContextVar[str | None] = ContextVar("session_id", default=None)
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

_RESERVED = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName",
    "levelname", "levelno", "lineno", "module", "msecs", "message", "msg", "name",
    "pathname", "process", "processName", "relativeCreated", "stack_info",
    "thread", "threadName", "taskName",
}


def _scrub(text: str) -> str:
    """Last line of defence, applied to the finished log line.

    Call sites are careful — citizen text goes through `preview()`, identifiers
    are never put in `extra` — but "careful" is a property of every call site
    that exists today, not of the ones written next year. An exception carrying
    a rejected Aadhaar number in its message would otherwise reach the log
    untouched, so the whole formatted line is scrubbed on the way out.
    """
    from .services.mask import mask_pii

    return mask_pii(text)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        session = _session_id.get()
        if session:
            payload["session_id"] = session
        correlation = _correlation_id.get()
        if correlation:
            payload["correlation_id"] = correlation
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return _scrub(json.dumps(payload, ensure_ascii=False, default=str))


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        session = _session_id.get()
        correlation = _correlation_id.get()
        parts = []
        if correlation:
            parts.append(f"cid={correlation}")
        if session:
            parts.append(f"sid={session[:8]}")
        prefix = ("[" + " ".join(parts) + "] ") if parts else ""
        extras = " ".join(
            f"{k}={v}"
            for k, v in record.__dict__.items()
            if k not in _RESERVED and not k.startswith("_")
        )
        base = f"{self.formatTime(record, '%H:%M:%S')} {record.levelname:<5} {prefix}{record.getMessage()}"
        return _scrub(f"{base}  {extras}".rstrip() if extras else base)


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    # A Windows console defaults to cp1252, which cannot encode Tamil. Every
    # log line carrying a Tamil transcript or grievance preview therefore threw
    # UnicodeEncodeError inside the logging handler and printed a page of
    # traceback in place of the record — noise that buries the real failures an
    # operator is reading the log to find.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):  # pragma: no cover - not a real stream
        pass

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # These are chatty at INFO and say nothing this service needs.
    for noisy in ("httpx", "httpcore", "websockets.client", "websockets.server"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


@contextmanager
def session_context(session_id: str) -> Iterator[None]:
    token = _session_id.set(session_id)
    try:
        yield
    finally:
        _session_id.reset(token)


@contextmanager
def correlation_context(correlation_id: str) -> Iterator[None]:
    """Attach a correlation id to every log line emitted inside the block.

    SRS §10.4 asks for an actor/action/target/outcome/timestamp/correlation
    audit. A correlation id lets an officer follow a reported bug through
    attachment upload → extraction → classification → compose → export, which
    today is impossible: an operator reading the log cannot tell which
    `knowledge.timed_out` matches which citizen's session, because the only
    thread is `session_id` and some operations do not have one yet (anonymous
    `POST /sessions`, `/api/health`).
    """
    token = _correlation_id.set(correlation_id)
    try:
        yield
    finally:
        _correlation_id.reset(token)


def current_correlation_id() -> str | None:
    """The correlation id set by `correlation_context`, or None outside one."""
    return _correlation_id.get()


@contextmanager
def timed(logger: logging.Logger, event: str, **fields: Any) -> Iterator[dict[str, Any]]:
    """Log `event` with its duration, whether or not the block raised."""
    started = time.perf_counter()
    carry: dict[str, Any] = {}
    try:
        yield carry
    except Exception as exc:
        logger.warning(
            event,
            extra={"ms": round((time.perf_counter() - started) * 1000), "ok": False,
                   "error": type(exc).__name__, **fields, **carry},
        )
        raise
    else:
        logger.info(
            event,
            extra={"ms": round((time.perf_counter() - started) * 1000), "ok": True, **fields, **carry},
        )


def preview(text: str, limit: int = 60) -> str:
    """A masked, truncated view of citizen text, safe to put in a log."""
    from .services.mask import mask_pii

    masked = mask_pii(str(text or ""))
    return masked[:limit] + ("…" if len(masked) > limit else "")
