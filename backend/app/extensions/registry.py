"""Where genuinely separate capabilities attach later.

Nothing in the petition flow needs these, and none is implemented. This module
exists so that when one is built it attaches at a defined seam instead of being
threaded through the graph, and so that the reason each one is separate is
written down before anyone is tempted to fold it in.

Each of these is a candidate for its own agent or its own service, and the test
for that is not "is it complicated" but: does it have its own knowledge source
and its own failure modes?

    scheme_eligibility    Reasons over welfare scheme rules with its own retrieval
                          corpus. Fails by being out of date, which looks nothing
                          like a validator failing.
    act_identification    Maps a grievance to the Act, Rules and the authority
                          with jurisdiction. Needs the legal corpus and must cite.
    case_status           Calls external government portals. Fails by timing out
                          or by the portal changing shape.
    knowledge_search      Departmental SOPs and circulars.

Splitting slot-filling from validation would isolate nothing — both need the same
five fields and neither has a knowledge source. Splitting these four DOES isolate
something, which is the whole reason to split anything.

CONTRACT for anything registered here:
  * it is ADVISORY. It may add information to a petition; it may never change a
    validated value, choose a question, or decide whether a document is produced.
  * it is OPTIONAL. Every caller must work when it is absent or times out.
  * its output is marked unverified and attributed, so an officer reading the
    petition can tell what came from a citizen and what came from a system.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

log = logging.getLogger(__name__)


class Capability(Protocol):
    """An advisory capability that can look at a petition and add to it."""

    name: str

    async def enrich(self, petition: dict[str, Any]) -> dict[str, Any]:
        """Return advisory findings. Must not raise; must respect its own timeout."""
        ...


@dataclass
class Registry:
    _capabilities: dict[str, Capability] = field(default_factory=dict)
    # Hard ceiling. A capability that takes longer than this has failed, whatever
    # it thinks it is doing — the citizen is waiting on a document.
    timeout_seconds: float = 5.0

    def register(self, capability: Capability) -> None:
        if capability.name in self._capabilities:
            raise ValueError(f"Capability {capability.name!r} is already registered.")
        self._capabilities[capability.name] = capability
        log.info("capability.registered", extra={"capability": capability.name})

    @property
    def names(self) -> list[str]:
        return sorted(self._capabilities)

    async def enrich(self, petition: dict[str, Any]) -> dict[str, Any]:
        """Run every registered capability concurrently and collect what returned.

        A capability that raises or times out is logged and omitted. It never
        propagates, because none of this is load-bearing for the document.
        """
        if not self._capabilities:
            return {}

        async def run(capability: Capability) -> tuple[str, Any]:
            try:
                result = await asyncio.wait_for(
                    capability.enrich(petition), timeout=self.timeout_seconds
                )
                return capability.name, result
            except Exception as exc:  # noqa: BLE001
                log.warning("capability.failed",
                            extra={"capability": capability.name, "error": str(exc)[:200]})
                return capability.name, None

        results = await asyncio.gather(*(run(c) for c in self._capabilities.values()))
        return {
            name: {"findings": value, "verified": False, "source": name}
            for name, value in results
            if value is not None
        }


registry = Registry()
