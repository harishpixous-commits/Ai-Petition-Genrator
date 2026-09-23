"""Deleting a saved petition — everywhere it was kept, not just from a list.

A petition the citizen deletes has to be gone from the machine. It is kept in
four places, and a deletion that misses one leaves a record the citizen
believes they removed:

  * the checkpoint history in the session database, which is the source of
    truth for the petition and everything they typed into it,
  * the generated Word and PDF files under the document directory,
  * anything they uploaded as an attachment,
  * the in-memory index the saved-petition list is drawn from.

There is no undo and no recycle bin, so the work is done in that order — the
authoritative record first, so a half-finished deletion can never leave a
listed petition whose document has already been removed — and every identifier
is validated as a UUID before anything is touched. Paths are confirmed to be
inside the directory they belong to AFTER resolution, which is the same rule
the attachment store applies to uploads, and for the same reason: a name that
is harmless as a string can still escape once a link in the middle is followed.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Settings, get_settings

log = logging.getLogger(__name__)


@dataclass
class Removal:
    """What actually happened, per petition, so the citizen can be told."""

    deleted: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "deleted": self.deleted, "unknown": self.unknown, "failed": self.failed,
            "count": len(self.deleted),
        }


def _valid(session_id: Any) -> str | None:
    """A session id is a UUID this service generated, but it arrives from a
    request body, so it is checked rather than trusted. Anything else names no
    petition and is never allowed near a filesystem path."""
    try:
        return str(uuid.UUID(str(session_id)))
    except (ValueError, AttributeError, TypeError):
        return None


def _inside(path: Path, root: Path) -> bool:
    try:
        return path.resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


def _remove_documents(session_id: str, settings: Settings) -> int:
    """Every rendered file for this petition, all versions of it."""
    root = settings.document_dir
    removed = 0
    if not root.is_dir():
        return 0
    for path in root.glob(f"{session_id}-*"):
        if not path.is_file() or not _inside(path, root):
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            log.warning("petition.document_not_removed")
    return removed


def _remove_attachments(session_id: str, settings: Settings) -> int:
    """What the citizen uploaded. Their own copies, kept only for this session."""
    root = settings.data_dir / "attachments"
    directory = root / session_id
    if not directory.is_dir() or not _inside(directory, root):
        return 0
    try:
        files = sum(1 for path in directory.rglob("*") if path.is_file())
        shutil.rmtree(directory)
        return files
    except OSError:
        log.warning("petition.attachments_not_removed")
        return 0


async def _exists(saver: Any, session_id: str) -> bool:
    """Is there a petition under this id at all?

    Asked so that deleting something already gone is reported as `unknown`
    rather than as a success — a citizen who is told a petition was deleted
    should be able to believe it was there to delete.
    """
    try:
        found = await saver.aget_tuple(
            {"configurable": {"thread_id": session_id, "checkpoint_ns": ""}})
    except Exception:  # noqa: BLE001 - a checkpointer that cannot answer is not proof of absence
        return True
    return found is not None


async def remove_sessions(
    session_ids: list[str], *, saver: Any, catalog: Any = None,
    settings: Settings | None = None,
) -> Removal:
    """Delete these petitions and everything kept with them.

    Returns which ids were deleted, which named nothing, and which could not be
    removed, so the caller can say so rather than reporting a blanket success.
    """
    settings = settings or get_settings()
    result = Removal()
    from .officer_store import forget_petition

    for raw in session_ids:
        session_id = _valid(raw)
        if session_id is None:
            result.unknown.append(str(raw)[:80])
            continue
        if not await _exists(saver, session_id):
            forget_petition(session_id, settings)
            # Still sweep the disk: a petition whose checkpoints were already
            # gone can leave its rendered document behind, and that document is
            # the copy with the citizen's name and address in it.
            _remove_documents(session_id, settings)
            _remove_attachments(session_id, settings)
            if catalog is not None:
                catalog.forget([session_id])
            result.unknown.append(session_id)
            continue
        try:
            await saver.adelete_thread(session_id)
            forget_petition(session_id, settings)
        except Exception:  # noqa: BLE001 - one failure must not abandon the rest
            log.warning("petition.not_deleted")
            result.failed.append(session_id)
            continue
        _remove_documents(session_id, settings)
        _remove_attachments(session_id, settings)
        if catalog is not None:
            catalog.forget([session_id])
        result.deleted.append(session_id)

    # Counts only. A session id is not a name, but there is no reason for a log
    # line to carry a list of them either.
    log.info("petition.removed", extra={
        "deleted": len(result.deleted), "unknown": len(result.unknown),
        "failed": len(result.failed),
    })
    return result
