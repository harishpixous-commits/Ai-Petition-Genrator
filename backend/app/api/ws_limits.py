"""Limits on the voice socket, sized so that a real citizen never meets them.

WHY THIS ENDPOINT AND NOT THE OTHERS. `/ws/voice` is the most expensive thing
this service does — it holds a connection open, runs voice activity detection
on every frame, and calls a speech recogniser and a speech synthesiser. It was
also the only endpoint with no throttle at any layer: not in nginx, not in the
application. One client could open connections until the process stopped
answering anybody, and nothing would have refused.

THE HARD PART IS NOT THE LIMIT, IT IS THE NUMBER. A grievance is dictated, not
typed: somebody describing a two-year dispute with a water board speaks for
minutes, pauses to think, starts again. Every limit below is therefore set
from the measured shape of real use and not from a round number:

    audio arrives at `asr_sample_rate` × 2 bytes — 32 KB/s at the default
    16 kHz. A minute of continuous speech is about 1.9 MB.

So `max_bytes_per_minute` is 8 MB: four times the natural rate. A citizen who
talks without stopping for a full minute uses a quarter of their allowance. A
client streaming garbage as fast as the socket accepts it hits it in seconds.

    `max_message_bytes` is 256 KiB against a normal frame of a few KB.
    `max_session_seconds` is thirty minutes against a long interview of ten.
    `max_per_client` is 3 against a citizen who uses one.

WHAT HAPPENS AT THE LIMIT is a close with a reason, never a silent drop. A
citizen whose connection closes must be told, because the alternative is a
person at a kiosk talking to a microphone that stopped listening.

NOT A SECURITY BOUNDARY ON ITS OWN. This bounds resource use by a client that
reaches the application. Authentication is `can_access`, which the endpoint
already applies before accepting, and network-level abuse belongs in nginx.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field


class LimitExceeded(Exception):
    """A limit was reached. Carries the close code and a sayable reason."""

    def __init__(self, reason: str, code: int = 1008) -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = code


@dataclass
class Limits:
    """Sized in `app/config.py`; see the module docstring for each number."""

    max_connections: int = 64
    max_per_client: int = 3
    max_message_bytes: int = 262_144
    max_bytes_per_minute: int = 8_000_000
    max_session_seconds: float = 1800.0


@dataclass
class _Window:
    """Bytes seen in the last minute, as (timestamp, size) pairs."""

    events: deque[tuple[float, int]] = field(default_factory=deque)
    total: int = 0

    def add(self, size: int, now: float) -> int:
        self.events.append((now, size))
        self.total += size
        cutoff = now - 60.0
        while self.events and self.events[0][0] < cutoff:
            _, old = self.events.popleft()
            self.total -= old
        return self.total


class Gate:
    """Who is connected, and how much they have sent.

    One instance per process, held on `app.state`. Deliberately in-process and
    not shared: the service runs a single worker by design (one SQLite file,
    in-process locks), so a process-local count IS the whole count. A
    multi-worker deployment would need this in Redis, and that is written down
    here rather than discovered later.
    """

    def __init__(self, limits: Limits | None = None) -> None:
        self.limits = limits or Limits()
        self._per_client: dict[str, int] = {}
        self._total = 0

    # ------------------------------------------------------------------ #
    # Connections
    # ------------------------------------------------------------------ #

    @property
    def open_connections(self) -> int:
        return self._total

    def acquire(self, client: str) -> None:
        """Take a slot, or raise. Call BEFORE accepting the socket."""
        if self._total >= self.limits.max_connections:
            raise LimitExceeded(
                "The service is handling as many voice sessions as it can. "
                "Please try again in a moment.", code=1013)
        held = self._per_client.get(client, 0)
        if held >= self.limits.max_per_client:
            raise LimitExceeded(
                "Too many voice sessions are already open from this device.",
                code=1008)
        self._per_client[client] = held + 1
        self._total += 1

    def release(self, client: str) -> None:
        """Give the slot back. Must run even when the socket failed."""
        held = self._per_client.get(client, 0)
        if held <= 1:
            self._per_client.pop(client, None)
        else:
            self._per_client[client] = held - 1
        self._total = max(0, self._total - 1)

    def session(self, client: str) -> Session:
        return Session(self, client)


class Session:
    """One connection's budget. Created by `Gate.session`."""

    def __init__(self, gate: Gate, client: str) -> None:
        self.gate = gate
        self.client = client
        self.limits = gate.limits
        self.started = time.monotonic()
        self._window = _Window()
        self.bytes_seen = 0
        self.frames_seen = 0

    def check(self, size: int, *, now: float | None = None) -> None:
        """Account for one inbound frame, or raise `LimitExceeded`."""
        moment = time.monotonic() if now is None else now

        if size > self.limits.max_message_bytes:
            raise LimitExceeded(
                f"A single message was larger than this service accepts "
                f"({size:,} bytes). Audio is sent in small frames.",
                code=1009)

        if moment - self.started > self.limits.max_session_seconds:
            raise LimitExceeded(
                "This voice session has been open for a long time and is "
                "being closed. Your petition is saved — start a new session "
                "to carry on.", code=1000)

        recent = self._window.add(size, moment)
        if recent > self.limits.max_bytes_per_minute:
            raise LimitExceeded(
                "Audio is arriving faster than this service accepts.",
                code=1008)

        self.bytes_seen += size
        self.frames_seen += 1

    def __enter__(self) -> Session:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.gate.release(self.client)


def client_key(websocket: object) -> str:
    """Who this connection is from, for the per-client count.

    The peer address, which behind nginx is the proxy unless it forwards the
    real one. `X-Forwarded-For` is read FIRST because that is what the
    deployment sets; it is spoofable by anyone talking to the application
    directly, which is why this bounds resource use rather than identifying
    anybody.
    """
    headers = getattr(websocket, "headers", None) or {}
    forwarded = ""
    try:
        forwarded = headers.get("x-forwarded-for", "") or ""
    except Exception:  # noqa: BLE001
        forwarded = ""
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = getattr(websocket, "client", None)
    host = getattr(client, "host", None)
    return str(host or "unknown")
