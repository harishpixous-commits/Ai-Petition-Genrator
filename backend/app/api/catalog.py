"""Navigation and deletion for petitions already saved in the session database."""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..services.officer_store import citizen_scope
from ..services.petition_catalog import PetitionCatalog
from ..services.removal import remove_sessions

router = APIRouter(prefix="/api", tags=["petitions"])


def _saver(request: Request):
    workflow = getattr(request.app.state, "workflow", None)
    if workflow is None:
        raise HTTPException(503, "The service is still starting.")
    saver = getattr(workflow, "_saver", None) or getattr(workflow._compiled, "checkpointer", None)
    if saver is None:
        raise HTTPException(503, "Saved petitions are temporarily unavailable.")
    return saver


def _catalog(request: Request) -> PetitionCatalog:
    catalog = getattr(request.app.state, "petition_catalog", None)
    if catalog is None:
        catalog = PetitionCatalog(_saver(request))
        request.app.state.petition_catalog = catalog
    return catalog


@router.get("/petitions")
async def list_petitions(
    request: Request,
    q: str = Query(default="", max_length=200),
    reference: str = Query(default="", max_length=100),
    petitioner_name: str = Query(default="", max_length=100),
    date_from: date | None = None,
    date_to: date | None = None,
    department: str = Query(default="", max_length=240),
    category: str = Query(default="", max_length=240),
    status: str = Query(default="", max_length=40),
    language: Literal["", "en", "ta"] = "",
    sort: Literal["newest", "oldest", "updated"] = "newest",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    """List saved petitions; date bounds include both endpoints (UTC creation date)."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "The start date must be on or before the end date.")
    return await _catalog(request).list_petitions(
        q=q, reference=reference, petitioner_name=petitioner_name,
        date_from=date_from, date_to=date_to, department=department, category=category,
        status=status, language=language, sort=sort, page=page, page_size=page_size,
        allowed_ids=citizen_scope(request),
    )


class DeleteRequest(BaseModel):
    """Exactly which petitions to delete — never a filter.

    The list is explicit on purpose. A delete that took the same search and
    filter arguments as the listing would delete whatever those arguments
    happened to match at the moment the request arrived, which is not
    necessarily what the citizen had on screen and ticked.
    """

    session_ids: list[str] = Field(min_length=1, max_length=200)


@router.post("/petitions/delete")
async def delete_petitions(request: Request, body: DeleteRequest) -> dict:
    """Permanently delete saved petitions and everything kept with them.

    Irreversible: the checkpoint history, the generated documents and any
    attachments all go. The response says which ids were deleted, which named
    nothing, and which failed, so the citizen is told what actually happened
    rather than a blanket success.
    """
    allowed = citizen_scope(request)
    if allowed is not None and any(sid not in allowed for sid in body.session_ids):
        raise HTTPException(403, "Only petitions created in this browser can be deleted here.")
    result = await remove_sessions(
        body.session_ids, saver=_saver(request), catalog=_catalog(request))
    if result.failed and not result.deleted:
        raise HTTPException(500, "Those petitions could not be deleted. Try again.")
    return result.as_dict()
