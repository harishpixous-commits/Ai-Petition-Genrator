"""`/api/health` costs one build per `_HEALTH_TTL` seconds, not one per hit.

WHY THIS MATTERS. The handler reaches `llm.available`, which makes a live HTTP
call to each configured provider — up to five, each with a 6-second timeout.
Before this cache an unauthenticated caller could hold every provider under
probe load by hitting `/api/health` in a loop. The response is also fetched
once at page load by the citizen frontend to colour the status badges, so a
cheap read is wanted — and a stale read for 30 seconds is enough for a kiosk
badge.

These tests do not go to the network. `_build_health` is monkeypatched so the
test can count exactly how many times the heavy work actually runs.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.api import rest


@pytest.fixture(autouse=True)
def _reset_cache():
    rest._health_cache = None
    rest._health_cached_at = 0.0
    yield
    rest._health_cache = None
    rest._health_cached_at = 0.0


@pytest.fixture
def counted_build(monkeypatch):
    """Monkeypatch `_build_health` with a cheap counter."""
    calls = {"n": 0}

    async def fake_build():
        calls["n"] += 1
        return {"ok": True, "build": "test", "call": calls["n"]}

    monkeypatch.setattr(rest, "_build_health", fake_build)
    return calls


class TestWithinTheWindow:
    async def test_one_hit_builds_once(self, counted_build):
        payload = await rest.health()
        assert payload["ok"] is True
        assert counted_build["n"] == 1

    async def test_a_second_hit_within_the_window_reuses_the_cache(self, counted_build):
        first = await rest.health()
        second = await rest.health()
        assert second == first
        assert counted_build["n"] == 1

    async def test_many_concurrent_hits_build_once(self, counted_build):
        """A thundering herd of unauth probes must not multiply provider calls."""
        results = await asyncio.gather(*(rest.health() for _ in range(50)))
        assert all(r == results[0] for r in results)
        assert counted_build["n"] == 1


class TestAfterTheWindow:
    async def test_a_hit_after_the_ttl_rebuilds(self, counted_build, monkeypatch):
        monkeypatch.setattr(rest, "_HEALTH_TTL", 0.01)
        await rest.health()
        time.sleep(0.02)
        await rest.health()
        assert counted_build["n"] == 2
