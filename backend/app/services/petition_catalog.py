"""A safe, searchable projection of the existing persisted petition sessions.

The checkpoint database remains the source of truth. No new session store is
created: this index is rebuilt from persisted checkpoints after a restart and
then consumes only new checkpoints. Only one small metadata record per session
is retained; citizen identifiers, transcripts and document bodies are discarded.
"""

from __future__ import annotations

import asyncio
import math
import re
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import quote

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from ..domain.templates import the_template
from .mask import mask_pii

_BATCH_SIZE = 128
_SUBJECT = re.compile(r"^\s*(?:Subject|பொருள்)\s*[:：–—-]\s*(.+)$", re.IGNORECASE)
_DRAFT_STATUSES = {"collecting", "attachments", "confirming"}


def _display(value: Any, limit: int = 240) -> str:
    """Flat, bounded display text with identifiers removed at the list boundary."""
    return mask_pii(" ".join(str(value or "").split()))[:limit]


def _finding(analysis: dict, key: str) -> str:
    value = analysis.get(key)
    return _display(value.get("value")) if isinstance(value, dict) else ""


def _version(state: dict, document: dict) -> int:
    try:
        return max(1, int(document.get("version") or state.get("document_version") or 1))
    except (TypeError, ValueError):
        return 1


def _metadata(state: dict, session_id: str, checkpoint_time: str = "") -> dict:
    fields = state.get("fields") or {}
    document = state.get("document") or {}
    analysis = state.get("analysis") or {}
    composition = state.get("composition") or {}
    verification = state.get("verification") or {}
    subject = ""
    # Manual and chat edits share letter_text. Prefer its current subject over
    # the older composition object, which may predate a manual edit.
    for line in (state.get("letter_text") or "").splitlines():
        if match := _SUBJECT.match(line):
            subject = _display(match.group(1))
            break
    subject = subject or _display(composition.get("subject"))
    ready = (
        state.get("status") == "ready" and bool(document.get("docx"))
        and not state.get("field_errors")
        and (verification.get("ok") or verification.get("hand_edited"))
    )
    session_path = quote(session_id, safe="")
    return {
        "session_id": session_id,
        "reference": _display(state.get("petition_reference") or document.get("reference"), 100),
        "petitioner_name": _display(fields.get("applicant_name"), 100),
        # Never use the raw grievance as the fallback list title.
        "subject": subject,
        "department": _finding(analysis, "department"),
        "category": _finding(analysis, "petition_category"),
        "created_at": state.get("created_at") or checkpoint_time,
        "updated_at": state.get("updated_at") or checkpoint_time,
        "generated_at": document.get("generated_at"),
        "status": state.get("status") or "collecting",
        "language": state.get("language") if state.get("language") in ("en", "ta") else "en",
        "version": _version(state, document),
        "document": ({
            "docx_url": f"/api/sessions/{session_path}/document.docx",
            "pdf_url": f"/api/sessions/{session_path}/document.pdf" if document.get("pdf") else None,
        } if ready else None),
        "verification": {"ok": bool(verification.get("ok"))},
        "attention_required": bool(state.get("field_errors")) or state.get("status") == "failed"
        or bool(verification and not verification.get("ok")),
    }


def _generated_metadata(state: dict, session_id: str, checkpoint_time: str) -> dict | None:
    current = _metadata(state, session_id, checkpoint_time)
    if current["document"]:
        return current
    # Versions also preserve the saved petition when checkpoint history has
    # been compacted or the current working copy is waiting for correction.
    for version in reversed(state.get("document_versions") or []):
        if not isinstance(version, dict):
            continue
        snapshot = _metadata({
            **state, **version, "status": "ready", "field_errors": {},
            "updated_at": version.get("updated_at") or state.get("updated_at"),
            "document_version": version.get("version"),
        }, session_id, checkpoint_time)
        if snapshot["document"]:
            return snapshot
    return None


def _timestamp(value: Any) -> float:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC).timestamp() if parsed.tzinfo is None else parsed.timestamp()
    except (ValueError, TypeError, OverflowError):
        return 0.0


class PetitionCatalog:
    """Incremental metadata index backed exclusively by the session checkpointer."""

    def __init__(self, saver: Any) -> None:
        self._saver = saver
        self._lock = asyncio.Lock()
        self._cursor = ""
        self._latest: dict[str, tuple[str, dict]] = {}
        self._generated: dict[str, tuple[str, dict]] = {}

    def _record(self, session_id: str, checkpoint_id: str, checkpoint: dict) -> None:
        state = checkpoint.get("channel_values") or {}
        if not isinstance(state, dict) or not state.get("session_id"):
            return
        checkpoint_time = checkpoint.get("ts") or ""
        previous = self._latest.get(session_id)
        if previous is None or checkpoint_id > previous[0]:
            self._latest[session_id] = (checkpoint_id, _metadata(state, session_id, checkpoint_time))
        generated = _generated_metadata(state, session_id, checkpoint_time)
        previous_generated = self._generated.get(session_id)
        if generated and (previous_generated is None or checkpoint_id > previous_generated[0]):
            self._generated[session_id] = (checkpoint_id, generated)

    async def _refresh_sqlite(self) -> None:
        """Read bounded batches without holding the checkpointer lock while decoding.

        The existing SQLite checkpoint schema and serializer are used directly
        so listing does not deserialize pending writes/transcripts a second time
        or repeatedly rescan years of checkpoint history.
        """
        saver = self._saver
        await saver.setup()
        async with saver.lock, saver.conn.execute(
            "SELECT MAX(checkpoint_id) FROM checkpoints WHERE checkpoint_ns = ''"
        ) as cursor:
            row = await cursor.fetchone()
        high_water = row[0] if row else None
        if not high_water or high_water <= self._cursor:
            return

        while self._cursor < high_water:
            async with saver.lock, saver.conn.execute(
                "SELECT thread_id, checkpoint_id, type, checkpoint FROM checkpoints "
                "WHERE checkpoint_ns = '' AND checkpoint_id > ? AND checkpoint_id <= ? "
                "ORDER BY checkpoint_id ASC LIMIT ?",
                (self._cursor, high_water, _BATCH_SIZE),
            ) as cursor:
                rows = await cursor.fetchall()
            if not rows:
                break
            for session_id, checkpoint_id, checkpoint_type, blob in rows:
                checkpoint = saver.serde.loads_typed((checkpoint_type, blob))
                self._record(session_id, checkpoint_id, checkpoint)
                self._cursor = checkpoint_id
            await asyncio.sleep(0)

    async def _refresh(self) -> None:
        if isinstance(self._saver, AsyncSqliteSaver):
            await self._refresh_sqlite()
            return
        # The test/in-memory checkpointer does not guarantee cross-session
        # ordering. Process entries by their IDs, never by iteration position.
        async for saved in self._saver.alist(None):
            config = saved.config.get("configurable") or {}
            if config.get("checkpoint_ns", ""):
                continue
            session_id = str(config.get("thread_id") or "")
            checkpoint_id = str(config.get("checkpoint_id") or saved.checkpoint.get("id") or "")
            self._record(session_id, checkpoint_id, saved.checkpoint)

    def _items(self) -> list[dict]:
        template = the_template()
        items = []
        for session_id, (_, generated) in self._generated.items():
            latest = self._latest.get(session_id, ("", generated))[1]
            item = dict(latest)
            for key in ("reference", "petitioner_name", "subject", "department", "category",
                        "created_at", "generated_at"):
                item[key] = item.get(key) or generated.get(key)
            item["version"] = max(item["version"], generated["version"])
            language = item["language"]
            item["subject"] = item["subject"] or template.text_for("subject", language)
            item["department"] = item["department"] or template.text_for("department", language)
            item["category"] = item["category"] or None
            status = item["status"]
            lifecycle = (
                "updated" if status == "ready" and item["version"] > 1 else
                "generated" if status == "ready" else
                "draft" if status in _DRAFT_STATUSES else status
            )
            item["lifecycle"] = lifecycle
            item["status_label"] = {
                "generated": "Generated", "updated": "Updated", "draft": "Draft",
                "failed": "Requires attention", "cancelled": "Cancelled",
                "generating": "Preparing",
            }.get(lifecycle, lifecycle.replace("_", " ").title())
            items.append(item)
        return items

    def forget(self, session_ids: list[str]) -> None:
        """Drop deleted petitions from the index.

        The checkpoints they were built from are already gone, and the refresh
        cursor only ever moves forward, so nothing puts them back. Without this
        the listing would keep serving petitions that no longer exist until the
        service restarted.
        """
        for session_id in session_ids:
            self._latest.pop(session_id, None)
            self._generated.pop(session_id, None)

    async def list_petitions(
        self, *, q: str = "", reference: str = "", petitioner_name: str = "",
        date_from: date | None = None, date_to: date | None = None,
        department: str = "", category: str = "", status: str = "", language: str = "",
        sort: str = "newest", page: int = 1, page_size: int = 20,
    ) -> dict:
        async with self._lock:
            await self._refresh()
            items = self._items()
        total_saved = len(items)
        facets = {
            "departments": sorted({item["department"] for item in items if item["department"]}),
            "categories": sorted({item["category"] for item in items if item["category"]}),
            "statuses": sorted({item["lifecycle"] for item in items}),
            "languages": sorted({item["language"] for item in items}),
        }

        def matches(item: dict) -> bool:
            if q.strip().casefold() not in " ".join(str(item[key] or "") for key in (
                "reference", "petitioner_name", "subject", "department", "category",
            )).casefold():
                return False
            for key, expected in (("reference", reference), ("petitioner_name", petitioner_name)):
                if expected.strip().casefold() not in str(item[key] or "").casefold():
                    return False
            for key, expected in (("department", department), ("category", category),
                                  ("language", language)):
                if expected and str(item[key] or "").casefold() != expected.casefold():
                    return False
            if status and status not in (item["status"], item["lifecycle"]):
                return False
            if date_from or date_to:
                try:
                    created_date = datetime.fromtimestamp(_timestamp(item["created_at"]), UTC).date()
                except (ValueError, OSError, OverflowError):
                    return False
                if date_from and created_date < date_from:
                    return False
                if date_to and created_date > date_to:
                    return False
            return True

        filtered = [item for item in items if matches(item)]
        order_key = "updated_at" if sort == "updated" else "created_at"
        filtered.sort(key=lambda item: (_timestamp(item[order_key]), item["session_id"]),
                      reverse=sort != "oldest")
        start = (page - 1) * page_size
        total = len(filtered)
        return {
            "items": filtered[start:start + page_size], "total": total, "total_saved": total_saved,
            "page": page, "page_size": page_size, "pages": math.ceil(total / page_size),
            "has_next": start + page_size < total, "filters": facets,
        }
