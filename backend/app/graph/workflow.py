"""Wiring the nodes together, and persisting the result.

The shape is a deterministic skeleton with one agentic node in it:

    understand -> validate -> (ask | confirm | compose | END)
                                             compose -> (translate | render)
                                                        translate -> render
                                                                     render -> verify -> END

`ask` and `confirm` run to `END` rather than blocking on an interrupt. One
citizen utterance is one invocation, the checkpointer holds the state against
`session_id`, and the next utterance starts a fresh invocation from that
checkpoint. A dropped WebSocket therefore costs nothing: the citizen reconnects
and carries on from where the record actually is.
"""

from __future__ import annotations

import asyncio
import logging
import weakref
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from ..config import Settings, get_settings
from ..domain.phrasing import phrase
from . import nodes
from .routing import route_after_compose, route_after_validate
from .state import LetterState

log = logging.getLogger(__name__)


def build_graph() -> StateGraph:
    """The graph, uncompiled. Separated so tests can compile it with their own
    checkpointer (or none) without touching the process-wide one."""
    graph = StateGraph(LetterState)

    graph.add_node("understand", nodes.understand)
    graph.add_node("validate", nodes.validate)
    graph.add_node("ask", nodes.ask)
    graph.add_node("attach", nodes.attach)
    graph.add_node("confirm", nodes.confirm)
    graph.add_node("compose", nodes.compose)
    graph.add_node("translate", nodes.translate)
    graph.add_node("render", nodes.render)
    graph.add_node("verify", nodes.verify)

    graph.add_edge(START, "understand")
    graph.add_edge("understand", "validate")

    graph.add_conditional_edges(
        "validate",
        route_after_validate,
        {"ask": "ask", "attach": "attach", "confirm": "confirm",
         "compose": "compose", END: END},
    )

    # The turn ends here and waits for the citizen.
    graph.add_edge("ask", END)
    graph.add_edge("attach", END)
    graph.add_edge("confirm", END)

    graph.add_conditional_edges(
        "compose",
        route_after_compose,
        {"translate": "translate", "render": "render"},
    )
    graph.add_edge("translate", "render")
    graph.add_edge("render", "verify")
    graph.add_edge("verify", END)

    return graph


class Workflow:
    """Owns the compiled graph and its checkpointer for the life of the process."""

    def __init__(self, compiled: Any, saver: AsyncSqliteSaver) -> None:
        self._compiled = compiled
        self._saver = saver
        # REST and every voice connection share this owner. The checkpointer
        # persists individual graph steps, but does not serialize whole turns.
        # Weak references retain only locks currently held or awaited.
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()

    def _lock(self, session_id: str) -> asyncio.Lock:
        lock = self._locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[session_id] = lock
        return lock

    @staticmethod
    def config(session_id: str) -> dict:
        """LangGraph addresses a conversation by `thread_id`; ours is the session."""
        return {"configurable": {"thread_id": session_id}}

    async def invoke(
        self, session_id: str, patch: dict[str, Any], *,
        guard: Callable[[LetterState | None], bool] | None = None,
    ) -> LetterState:
        """Run one turn, atomically checking any endpoint precondition first.

        A guard may raise a caller-specific error or return False to return the
        existing state unchanged (for example a repeated confirmation).
        """
        async with self._lock(session_id):
            state = await self._snapshot(session_id)
            if guard is not None:
                if not guard(state):
                    if state is None:
                        raise ValueError("A skipped invocation requires an existing session.")
                    return state
            return await self._compiled.ainvoke(patch, config=self.config(session_id))

    async def peek(self, session_id: str) -> LetterState | None:
        """The persisted state WITHOUT taking the session lock.

        For watching a turn that is still running, and for nothing else.

        It is deliberately not `snapshot`: that method owns the lock and treats
        a persisted `generating` as the fingerprint of an interrupted process,
        because no live generation could hold the lock and be read by it. Here
        the opposite is true — a live generation is exactly what is being
        watched, and `generating` is the truth being reported, not a fault to
        be repaired.

        Never make a decision about a session from this. Only report it.
        """
        state = await self._compiled.aget_state(self.config(session_id))
        return getattr(state, "values", None) or None

    async def snapshot(self, session_id: str) -> LetterState | None:
        """The persisted state for a session, or None if there is no checkpoint.

        This is session recovery: a citizen returning after a dropped connection
        is handed the same record, with no replay of the conversation.
        """
        async with self._lock(session_id):
            return await self._snapshot(session_id)

    async def _snapshot(self, session_id: str) -> LetterState | None:
        state = await self._compiled.aget_state(self.config(session_id))
        values = getattr(state, "values", None)
        # This method runs only while owning the session lock. A normal
        # generation holds that same lock until it finishes, so a persisted
        # generating state here belongs to an interrupted request/process.
        if values and values.get("status") == "generating":
            recovery = {
                "status": "failed", "document": None, "verification": None,
                "composition": None, "letter_text": None,
                "error": "Document preparation was interrupted. Please try again.",
                "reply": phrase("render_failed", values.get("language", "en")),
                "updated_at": datetime.now(UTC).isoformat(),
            }
            await self._compiled.aupdate_state(self.config(session_id), recovery)
            values = {**values, **recovery}
            log.warning("workflow.interrupted_generation_recovered")
        return values if values else None

    async def update(self, session_id: str, patch: dict[str, Any]) -> None:
        """Write a patch into a session's checkpoint without running a turn.

        Used for out-of-band edits — a citizen correcting one field in a text UI
        rather than by speaking — so those edits are checkpointed the same way
        conversational ones are.
        """
        async with self._lock(session_id):
            await self._compiled.aupdate_state(self.config(session_id), patch)


@asynccontextmanager
async def workflow_lifespan(settings: Settings | None = None) -> AsyncIterator[Workflow]:
    """Open the checkpoint database for the life of the application."""
    s = settings or get_settings()
    s.ensure_dirs()
    async with AsyncSqliteSaver.from_conn_string(str(s.checkpoint_path)) as saver:
        compiled = build_graph().compile(checkpointer=saver)
        log.info("workflow.ready", extra={"checkpoint": str(s.checkpoint_path)})
        yield Workflow(compiled, saver)
