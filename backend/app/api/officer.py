"""Authenticated office review over existing petition and attachment records."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..domain.attachments import AttachmentSet
from ..services import attachment_store
from ..services import officer_store as store
from ..services.petition_catalog import _metadata
from .catalog import _catalog
from .rest import _document, _require_state

router = APIRouter(prefix="/api/officer", tags=["officer"])
STATUSES = Literal["New", "Pending", "Under Review", "Acknowledged", "Resolved", "Needs Review"]


def same_origin(request: Request):
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Cross-origin requests are not allowed.")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Cross-site requests are not allowed.")


def require_officer(request: Request):
    user = store.identity(request.cookies.get(store.COOKIE))
    if not user:
        raise HTTPException(401, "Please sign in. Your officer session may have expired.")
    if request.method not in ("GET", "HEAD"):
        same_origin(request)
    return user


OfficerUser = Annotated[dict, Depends(require_officer)]


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=256)


@router.post("/login")
def login(body: Login, request: Request, response: Response):
    same_origin(request)
    token, error = store.login(
        body.username.strip(), body.password, request.client.host if request.client else "unknown"
    )
    if error:
        raise HTTPException(
            429 if error == "limited" else 401,
            "Too many attempts. Try again in 15 minutes."
            if error == "limited"
            else "Invalid username or password.",
        )
    old = request.cookies.get(store.COOKIE)
    if old:
        with store.database() as db:
            db.execute("DELETE FROM officer_sessions WHERE token=?", (store.digest(old),))
    response.set_cookie(
        store.COOKIE,
        token,
        max_age=store.TTL,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        path="/",
    )
    return store.identity(token)


@router.get("/me")
def me(user: OfficerUser):
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, user: OfficerUser):
    with store.database() as db:
        db.execute(
            "DELETE FROM officer_sessions WHERE token=?",
            (store.digest(request.cookies[store.COOKIE]),),
        )
    response.delete_cookie(store.COOKIE, path="/")


def grounded(analysis):
    """Only retain findings supported by official, quoted evidence; conflicts stay visible."""
    analysis = analysis or {}
    result = {"warnings": analysis.get("warnings") or []}
    unresolved = any(
        c.get("resolution") == "undetermined"
        for c in analysis.get("conflicts", [])
        if isinstance(c, dict)
    )
    if unresolved:
        result["warnings"] = [
            *result["warnings"],
            "Conflicting sources require verification. Recommendations are withheld.",
        ]
        return result
    for key in (
        "department",
        "responsible_authority",
        "petition_category",
        "applicable_acts",
        "applicable_rules",
        "government_orders",
        "processing_steps",
        "processing_hierarchy",
        "transfer_process",
        "closure_process",
    ):
        raw = analysis.get(key)
        accepted = []
        for finding in raw if isinstance(raw, list) else ([raw] if raw else []):
            if not isinstance(finding, dict):
                continue
            sources = [
                s
                for s in finding.get("sources", [])
                if isinstance(s, dict)
                and s.get("authority") in ("official", "departmental")
                and s.get("excerpt")
                and s.get("document_title")
            ]
            if sources and finding.get("value"):
                accepted.append({"value": finding["value"], "sources": sources})
        result[key] = accepted if isinstance(raw, list) else (accepted[0] if accepted else None)
    return result


async def record(request, sid, *, analyse=False):
    state = await _require_state(request, sid)
    metadata = _metadata(state, sid)
    analysis = state.get("analysis") or {}
    if analyse and not analysis:
        from ..knowledge.capability import service

        findings = await service().analyse(
            (state.get("fields") or {}).get("grievance", ""), subject=metadata["subject"]
        )
        analysis = findings.model_dump() if findings else {}
    analysis = grounded(analysis)
    with store.database() as db:
        review = db.execute(
            "SELECT status FROM officer_reviews WHERE session_id=?", (sid,)
        ).fetchone()
    metadata.update(
        id=sid,
        status=review["status"]
        if review
        else ("Needs Review" if metadata["attention_required"] else "New"),
        department=(analysis.get("department") or {}).get("value", ""),
        category=(analysis.get("petition_category") or {}).get("value", ""),
    )
    if metadata.get("document"):
        metadata["document"] = {
            k: v.replace("/api/sessions/", "/api/officer/petitions/") if v else None
            for k, v in metadata["document"].items()
        }
    return metadata, state, analysis


@router.get("/petitions")
async def petitions(request: Request, user: OfficerUser):
    """Every petition this office may review, newest first.

    A PETITION IS A SESSION THAT PRODUCED A DOCUMENT. `_generated` is the
    catalogue's own index of exactly those, and it is what the citizen's
    list is built from — so the two agree about what the word means.

    This read `_latest` instead, which is every session ever started. On one
    machine that was 412 rows of which 12 were petitions: the other 400 were
    drafts abandoned at the first question, and they arrive with no
    reference, no petitioner and no subject. An officer opening the portal
    saw four hundred blank rows and twelve real ones somewhere among them.

    It was also why the page took seconds to appear. Every one of those
    ids was a full checkpoint load, and four hundred of them were loaded to
    produce nothing worth showing.

    What is deliberately NOT here: a petition somebody is halfway through
    typing. It is not finished, the citizen is still holding it, and there
    is nothing for an office to route.
    """
    catalog = _catalog(request)
    # Read the existing incremental catalogue without creating petition copies.
    async with catalog._lock:
        await catalog._refresh()
        ids = list(catalog._generated)
    items = []
    for sid in ids:
        try:
            item, _, _ = await record(request, sid)
            items.append(item)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
    items.sort(key=lambda p: p.get("created_at") or "", reverse=True)
    return {"items": items}


def attachments(state, sid):
    return [
        {
            "id": a.attachment_id,
            "filename": a.filename,
            "kind": a.kind,
            "url": f"/api/officer/petitions/{quote(sid, safe='')}/attachments/{quote(a.attachment_id, safe='')}",
            "metadata": a.note or "",
            # AI-ASSISTED, and the portal labels it that way. It is a
            # classification for an officer to agree or disagree with, not a
            # determination: nothing downstream branches on it, and the
            # officer's own view of the document governs.
            "relationship": a.relationship or None,
        }
        for a in AttachmentSet.from_state(state.get("attachments")).items
    ]


@router.get("/petitions/{sid}")
async def petition(sid: str, request: Request, user: OfficerUser):
    p, state, analysis = await record(request, sid, analyse=True)
    fields = state.get("fields") or {}
    grievance = fields.get("grievance") or ""
    # An extractive overview preserves stated facts and never invents a requested action.
    import re

    sentences = re.split(r"(?<=[.!?।])\s+", grievance)
    summary = " ".join(sentences if len(sentences) <= 4 else sentences[:2] + sentences[-2:])
    facts = {
        "Issue": p["subject"],
        "Address supplied by citizen": fields.get("address"),
        "Supporting documents": str(len(AttachmentSet.from_state(state.get("attachments")).items)),
    }
    # "Previous submissions" is a claim about THIS citizen's history, so a
    # reference number read off a document belonging to somebody else does not
    # belong in it. Listed under its own heading instead, where an officer can
    # see both that the number exists and that it is not the petitioner's.
    previous, third_party = [], []
    for attachment in AttachmentSet.from_state(state.get("attachments")).items:
        if attachment.confirmed and attachment.kind in ("acknowledgement", "previous_petition"):
            reference = (attachment.extracted or {}).get("reference_number")
            if not (isinstance(reference, dict) and reference.get("value")):
                continue
            relationship = attachment.relationship or {}
            if relationship.get("first_person_allowed", True):
                previous.append(str(reference["value"]))
            else:
                third_party.append(str(reference["value"]))
    if previous:
        facts["Previous submissions"] = ", ".join(previous)
    if third_party:
        facts["Referenced in an enclosed document (not the petitioner's)"] = \
            ", ".join(third_party)
    with store.database() as db:
        notes = [
            dict(n)
            for n in db.execute(
                "SELECT text,author,created_at FROM officer_notes WHERE session_id=? ORDER BY id DESC",
                (sid,),
            )
        ]
    return {
        **p,
        "letter_text": state.get("letter_text") or "",
        "summary": summary,
        "facts": facts,
        "analysis": analysis,
        "attachments": attachments(state, sid),
        "notes": notes,
    }


class Review(BaseModel):
    status: STATUSES
    note: str = Field(default="", max_length=4000)


@router.post("/petitions/{sid}/review")
async def review(sid: str, body: Review, request: Request, user: OfficerUser):
    await _require_state(request, sid)
    now = datetime.now(UTC).isoformat()
    with store.database() as db:
        db.execute(
            "INSERT INTO officer_reviews VALUES(?,?) ON CONFLICT(session_id) DO UPDATE SET status=excluded.status",
            (sid, body.status),
        )
        db.execute(
            "INSERT INTO officer_audit(session_id,status,author,created_at) VALUES(?,?,?,?)",
            (sid, body.status, user["username"], now),
        )
        if body.note.strip():
            db.execute(
                "INSERT INTO officer_notes(session_id,text,author,created_at) VALUES(?,?,?,?)",
                (sid, body.note.strip(), user["name"], now),
            )
    return {"saved": True}


@router.get("/petitions/{sid}/document.{kind}")
async def document(sid: str, kind: Literal["pdf", "docx"], request: Request, user: OfficerUser):
    return await _document(request, sid, kind)


@router.get("/petitions/{sid}/attachments/{aid}")
async def attachment(
    sid: str, aid: str, request: Request, user: OfficerUser, download: bool = False
):
    state = await _require_state(request, sid)
    a = AttachmentSet.from_state(state.get("attachments")).get(aid)
    if not a:
        raise HTTPException(404, "Attachment not found.")
    path = attachment_store.path_of(sid, a)
    if path is None or not path.is_file():
        raise HTTPException(410, "This attachment is no longer available.")
    inline = (
        a.content_type in ("application/pdf", "image/png", "image/jpeg", "image/webp", "text/plain")
        and not download
    )
    return FileResponse(
        path,
        media_type=a.content_type,
        filename=a.filename,
        content_disposition_type="inline" if inline else "attachment",
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )


async def acknowledgements_for(request, sid):
    p, state, _ = await record(request, sid)
    rows = []
    for a in AttachmentSet.from_state(state.get("attachments")).items:
        if a.kind != "acknowledgement":
            continue
        extracted = a.extracted if a.confirmed else {}

        def value(key, extracted=extracted):
            raw = (extracted or {}).get(key)
            return raw.get("value", "") if isinstance(raw, dict) else ""

        rows.append(
            {
                "id": sid + "~" + a.attachment_id,
                "reference": value("reference_number") or "Reference not recorded",
                "petition_id": sid,
                "petition_reference": p["reference"],
                "petitioner_name": p["petitioner_name"],
                "department": value("department"),
                "category": p["category"],
                "created_at": value("submitted_on") or a.uploaded_at,
                "status": "Acknowledged" if a.confirmed else "Needs Review",
                "language": p["language"],
                "url": f"/api/officer/petitions/{sid}/attachments/{a.attachment_id}",
                "text": a.note or "",
                "confirmed": a.confirmed,
            }
        )
    return rows


@router.get("/acknowledgements")
async def acknowledgements(request: Request, user: OfficerUser):
    items = []
    for p in (await petitions(request, user))["items"]:
        items.extend(await acknowledgements_for(request, p["id"]))
    return {"items": items}


@router.get("/acknowledgements/{aid}")
async def acknowledgement(aid: str, request: Request, user: OfficerUser):
    sid, sep, _ = aid.partition("~")
    if sep:
        for item in await acknowledgements_for(request, sid):
            if item["id"] == aid:
                return item
    raise HTTPException(404, "Acknowledgement not found.")
