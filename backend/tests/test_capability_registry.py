"""The advisory capability seam, exercised rather than assumed.

`extensions/registry.py` states a contract for anything that attaches to it:
it is ADVISORY, it is OPTIONAL, and its output is marked unverified and
attributed. `Registry.register()` had a test. `Registry.enrich()` — the twenty
lines that run capabilities concurrently, cap each one, swallow failures and
attribute what comes back — had none, and had never been executed by any code
path either: the graph calls the knowledge service directly, on a longer budget
and several turns earlier, which is the right thing for that one capability and
the reason nothing reached this method.

That is a bad thing to ship to a department. The first person to build
`scheme_eligibility` or `case_status` would be the first person to find out
whether the timeout works, and they would find out in front of a citizen.

So every clause of the contract is tested here, by behaviour: a slow capability
is cut off, a broken one is isolated, and neither can stop the others or reach
the petition.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.extensions.registry import Registry

PETITION = {"grievance": "no water for ten days", "subject": "Water supply"}


class Fixed:
    """A capability that returns the same thing every time."""

    def __init__(self, name: str, value) -> None:
        self.name = name
        self._value = value
        self.seen: list[dict] = []

    async def enrich(self, petition):
        self.seen.append(petition)
        return self._value


class Slow:
    """A capability that takes longer than it is allowed to."""

    def __init__(self, name: str, seconds: float) -> None:
        self.name = name
        self.seconds = seconds
        self.finished = False

    async def enrich(self, petition):
        await asyncio.sleep(self.seconds)
        self.finished = True
        return {"late": True}


class Broken:
    """A capability that raises, which the contract says must not propagate."""

    name = "broken"

    async def enrich(self, petition):
        raise RuntimeError("this capability is having a bad day")


class TestWhatComesBack:
    async def test_nothing_registered_is_not_an_error(self):
        """Every deployment starts here, and most stay here."""
        assert await Registry().enrich(PETITION) == {}

    async def test_findings_are_attributed_and_marked_unverified(self):
        """The contract's third clause, and the one an officer depends on.

        A petition carries what a citizen said. Anything a system added has to
        be distinguishable from it on sight, or the officer is reading a
        document that mixes evidence with inference.
        """
        registry = Registry()
        registry.register(Fixed("scheme_eligibility", {"scheme": "old age pension"}))

        result = await registry.enrich(PETITION)

        assert result == {
            "scheme_eligibility": {
                "findings": {"scheme": "old age pension"},
                "verified": False,
                "source": "scheme_eligibility",
            }
        }

    async def test_a_capability_with_nothing_to_say_is_left_out(self):
        """None is not an empty finding. A capability that has no opinion must
        not put an empty section on an officer's screen."""
        registry = Registry()
        registry.register(Fixed("quiet", None))
        registry.register(Fixed("loud", {"found": 1}))

        result = await registry.enrich(PETITION)

        assert "quiet" not in result
        assert "loud" in result

    async def test_the_petition_handed_in_is_not_modified(self):
        """The first clause: advisory. It may add to a petition; it may never
        change a validated value. A capability receiving the live dict could
        rewrite a citizen's address and nothing here would notice."""
        registry = Registry()
        probe = Fixed("probe", {"ok": True})
        registry.register(probe)
        before = dict(PETITION)

        await registry.enrich(PETITION)

        assert PETITION == before
        assert probe.seen and probe.seen[0] == before


class TestWhenOneMisbehaves:
    """The second clause: optional. Every caller must work when a capability is
    absent, broken or slow — so none of those may take the others with it."""

    async def test_one_that_raises_is_dropped_and_the_others_survive(self):
        registry = Registry()
        registry.register(Broken())
        registry.register(Fixed("working", {"found": 1}))

        result = await registry.enrich(PETITION)

        assert "broken" not in result
        assert result["working"]["findings"] == {"found": 1}

    async def test_one_that_raises_does_not_propagate(self):
        """Stated twice because it matters twice: the citizen is waiting on a
        document, and an advisory lookup may never be the reason it fails."""
        registry = Registry()
        registry.register(Broken())

        assert await registry.enrich(PETITION) == {}

    async def test_one_that_overruns_its_timeout_is_cut_off(self):
        registry = Registry()
        registry.timeout_seconds = 0.1
        slow = Slow("slow", 5.0)
        registry.register(slow)
        registry.register(Fixed("quick", {"found": 1}))

        start = time.perf_counter()
        result = await registry.enrich(PETITION)
        elapsed = time.perf_counter() - start

        assert "slow" not in result, "a capability outran its cap and still reported"
        assert result["quick"]["findings"] == {"found": 1}
        assert not slow.finished, "the slow capability was allowed to finish"
        assert elapsed < 1.0, (
            f"the cap did not hold: {elapsed:.2f}s against a 0.1s timeout")

    async def test_the_cap_is_a_ceiling_on_the_whole_call(self):
        """Three slow capabilities must cost one timeout, not three. If they
        ran in sequence the citizen would wait fifteen seconds for findings
        that were discarded."""
        registry = Registry()
        registry.timeout_seconds = 0.2
        for index in range(3):
            registry.register(Slow(f"slow{index}", 5.0))

        start = time.perf_counter()
        result = await registry.enrich(PETITION)
        elapsed = time.perf_counter() - start

        assert result == {}
        assert elapsed < 1.0, (
            f"capabilities were capped in sequence, not together: {elapsed:.2f}s")


class TestTheyRunTogether:
    async def test_capabilities_do_not_wait_for_each_other(self):
        """Four capabilities, each sleeping 200ms. In sequence that is 800ms.

        Timed rather than asserted on `asyncio.gather` being present, because
        the thing that matters is the wall clock a citizen experiences.
        """
        registry = Registry()
        registry.timeout_seconds = 5.0

        class Napping:
            def __init__(self, name):
                self.name = name

            async def enrich(self, petition):
                await asyncio.sleep(0.2)
                return {"ok": True}

        for index in range(4):
            registry.register(Napping(f"nap{index}"))

        start = time.perf_counter()
        result = await registry.enrich(PETITION)
        elapsed = time.perf_counter() - start

        assert len(result) == 4
        assert elapsed < 0.6, (
            f"four 200ms capabilities took {elapsed:.2f}s — they ran in sequence")


class TestRegistration:
    def test_the_same_name_cannot_be_registered_twice(self):
        """Two capabilities under one name would silently replace each other,
        and the officer would never know which one answered."""
        registry = Registry()
        registry.register(Fixed("duplicate", {}))

        with pytest.raises(ValueError, match="already registered"):
            registry.register(Fixed("duplicate", {}))

    def test_names_are_listed_in_a_stable_order(self):
        registry = Registry()
        for name in ("case_status", "act_identification", "scheme_eligibility"):
            registry.register(Fixed(name, {}))

        assert registry.names == [
            "act_identification", "case_status", "scheme_eligibility"]


class TestTheOneCapabilityThatExists:
    """`act_identification` is registered at startup by `main.py`.

    It is the only one, and the graph does NOT reach it through this registry:
    `nodes.py` calls the knowledge service directly, because the analysis has
    to start several turns before it is needed and the five-second cap here is
    less than a cold analysis takes. That is deliberate and it is the right
    choice for this capability — but it means the seam below it must be known
    to work by test rather than by use.
    """

    async def test_it_satisfies_the_capability_contract(self):
        from app.knowledge.capability import ActIdentification

        capability = ActIdentification()
        assert capability.name == "act_identification"

        registry = Registry()
        registry.register(capability)
        # With no corpus and no model configured — the state this suite runs
        # in — it must return nothing rather than raise.
        assert await registry.enrich(PETITION) == {}
