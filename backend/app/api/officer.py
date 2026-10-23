"""Authenticated office review over existing petition and attachment records."""

from __future__ import annotations

import logging
import re
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

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/officer", tags=["officer"])
STATUSES = Literal[
    "New / Pending", "Acknowledged", "Routed to Department", "Under Review",
    "Field Inspection Scheduled", "Resolved", "Rejected",
    # Accepted for older clients and records written before the lifecycle
    # panel was introduced. The UI offers the normalized lifecycle names.
    "New", "Pending", "Needs Review",
]
PRIORITIES = Literal["Normal", "High Priority", "Urgent / Essential Utility"]
SLA_TARGETS = Literal["15 Days", "7 Days", "48 Hours"]


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


def _dedup_sources(sources):
    """Collapse per-finding sources that cite the same provision.

    Two sources sharing (document_title, section head, page_number) are
    the same statute's text re-chunked around a page break. The brief and
    SRS §8.5 ask for the finding to be EXPOSED, not for the officer to
    read the same section twice; the first chunk is kept and the rest are
    quietly folded in.

    `section` is compared on its leading 60 characters so a chunk whose
    section header runs long ("136 Provision for lighting public streets
    - PUBLIC DRAINAGE") does not count as different from a second chunk
    whose header starts the same way.
    """
    seen: set[tuple[str, str, int | None]] = set()
    kept: list[dict] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        key = (
            (source.get("document_title") or "").strip(),
            " ".join(((source.get("section") or "")[:60]).split()).lower(),
            source.get("page_number"),
        )
        if key in seen:
            continue
        seen.add(key)
        kept.append(source)
    return kept


def grounded(analysis):
    """Only retain findings supported by official, quoted evidence; conflicts stay visible.

    SRS §8.5 says a conflict must be EXPOSED, not disappear the whole
    recommendation set. The earlier rule withheld every grounded finding
    the moment ANY `undetermined` conflict was present — which meant a
    single Act↔Rules timing conflict (two instruments that genuinely both
    apply, both honestly retrieved) hid the ULB Act §118, the District
    Municipalities Act §136 for lighting of public streets, the ULB Rules
    2023 chunks AND the municipality authority. The officer saw "Not
    identified in verified sources" everywhere and had no way to tell the
    retrieval was working.

    Now: the conflict warning rides on top of every finding, the officer
    still sees the two sides, and nothing is silently dropped behind a
    single abstention flag.
    """
    analysis = analysis or {}
    #
    # WARNINGS, DEDUPED. The analyst already emits a specific, named
    # "'TN ULB Rules, 2023' and 'TN ULB Act, 1998' both cover this"
    # paragraph for each unresolved conflict. Appending a generic
    # "Conflicting sources were found" line on top of that was the second
    # of two warnings the user saw rendered next to each other on the live
    # page — the specific message makes the generic one redundant, so the
    # generic one is dropped here.
    #
    # Also: a warning that is a substring of another, or two warnings whose
    # first six words match, are collapsed. Different retrieval passes
    # occasionally emit the same message twice; the renderer should see one.
    seen_prefix: set[str] = set()
    distinct_warnings: list[str] = []
    for warning in analysis.get("warnings") or []:
        normalised = " ".join(str(warning).split())
        prefix = " ".join(normalised.split()[:6]).lower()
        if prefix in seen_prefix:
            continue
        seen_prefix.add(prefix)
        distinct_warnings.append(normalised)
    result = {"warnings": distinct_warnings}
    for key in (
        "department",
        "jurisdiction",
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
                # Rank the per-finding sources by registry tier: Gazette and
                # signed-PDF citations ahead of repository and department
                # ones. SRS §8.5 — when a finding carries two sources that
                # both ground it, the stronger one should read first. Unknown
                # URLs (ingested before the registry existed) fall to the
                # end, preserving the previous order among themselves.
                try:
                    from ..knowledge.source_registry import rank_findings
                    sources = rank_findings(sources)
                except Exception:  # noqa: BLE001
                    pass
                #
                # SOURCE DEDUP. When ingest.chunk_document crosses a page
                # break mid-section, the same rule can appear as two chunks
                # that share (title, section, page) but have different
                # excerpt tails. For the officer page they are the same
                # citation twice. The user screenshot showed "Rule 312" and
                # "Rule 2" each listed two consecutive times from exactly
                # this cause. Keep the first chunk; a reader opening the
                # source URL sees the whole provision anyway.
                sources = _dedup_sources(sources)
                entry = {"value": finding["value"], "sources": sources}
                if key == "jurisdiction":
                    checked = _check_against_the_directory(finding["value"])
                    if checked is None:
                        continue
                    entry.update(checked)
                accepted.append(entry)
        result[key] = accepted if isinstance(raw, list) else (accepted[0] if accepted else None)
    return result


def _check_against_the_directory(claim: str) -> dict | None:
    """Does this jurisdiction name a body that actually exists?

    THE GAP GROUNDING CANNOT CLOSE. The grounding check asks whether a value
    appears in a cited passage. It catches an invention made from nothing. It
    cannot catch one assembled from text that IS there: a passage mentioning
    Oddanchatram and a passage mentioning a municipality will ground
    "Oddanchatram Municipality" — grammatical, citable, and not a body that
    exists. There is a Town Panchayat and a Panchayat Union of that name and
    no municipality at all.

    The department publishes the list of its own local bodies, so this is
    checkable rather than merely plausible. Returns None to DROP the finding
    when the named body is not in that list.

    When the directory has not been built this returns the finding untouched:
    a missing directory must not silently delete every jurisdiction answer the
    service was already giving.
    """
    from ..domain import local_bodies

    if not local_bodies.available():
        return {}

    answer = local_bodies.validate_claim(claim)
    if answer.resolved:
        return {"directory": {
            "status": "confirmed",
            "body_type": answer.body.body_type,
            "district": answer.body.district,
            "lgd_code": answer.body.lgd_code,
            "source_url": answer.body.source_url,
        }}
    if answer.ambiguous:
        # Several real bodies share the name. The finding is kept, because the
        # place is real, and flagged so an officer chooses rather than the
        # service choosing for them.
        return {"directory": {
            "status": "ambiguous",
            "reason": answer.reason,
            "candidates": [
                {"name": body.name_en, "body_type": body.body_type,
                 "district": body.district, "parent": body.parent}
                for body in answer.candidates[:6]
            ],
        }}
    log.info("officer.jurisdiction_not_in_directory",
             extra={"claim": str(claim)[:80], "reason": answer.reason[:90]})
    return None


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
            "SELECT * FROM officer_reviews WHERE session_id=?", (sid,)
        ).fetchone()
    status = review["status"] if review else "New / Pending"
    if status in ("New", "Pending", "Needs Review"):
        status = "New / Pending"
    metadata.update(
        id=sid,
        status=status,
        department=(review["assigned_department"] if review else "")
        or (analysis.get("department") or {}).get("value", ""),
        category=(analysis.get("petition_category") or {}).get("value", ""),
        assigned_department=(review["assigned_department"] if review else ""),
        assigned_authority=(review["assigned_authority"] if review else ""),
        priority=(review["priority"] if review else "Normal"),
        sla_target=(review["sla_target"] if review else "15 Days"),
        official_reply=(review["reply"] if review else ""),
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
    assigned_department: str = Field(default="", max_length=160)
    assigned_authority: str = Field(default="", max_length=200)
    priority: PRIORITIES = "Normal"
    sla_target: SLA_TARGETS = "15 Days"
    official_reply: str = Field(default="", max_length=4000)


@router.post("/petitions/{sid}/review")
async def review(sid: str, body: Review, request: Request, user: OfficerUser):
    await _require_state(request, sid)
    now = datetime.now(UTC).isoformat()
    status = "New / Pending" if body.status in ("New", "Pending", "Needs Review") else body.status
    with store.database() as db:
        db.execute(
            """INSERT INTO officer_reviews(
                   session_id,status,assigned_department,assigned_authority,
                   priority,sla_target,reply
               ) VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(session_id) DO UPDATE SET
                   status=excluded.status,
                   assigned_department=excluded.assigned_department,
                   assigned_authority=excluded.assigned_authority,
                   priority=excluded.priority,
                   sla_target=excluded.sla_target,
                   reply=excluded.reply""",
            (sid, status, body.assigned_department.strip(), body.assigned_authority.strip(),
             body.priority, body.sla_target, body.official_reply.strip()),
        )
        db.execute(
            "INSERT INTO officer_audit(session_id,status,author,created_at) VALUES(?,?,?,?)",
            (sid, status, user["username"], now),
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


def _reference_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


async def _petition_for_reference(request: Request, reference: str):
    key = _reference_key(reference)
    if not re.fullmatch(r"AP\d{4}[A-Z0-9]{6}", key):
        raise HTTPException(404, "Petition reference not found.")
    catalog = _catalog(request)
    async with catalog._lock:
        await catalog._refresh()
        ids = list(catalog._generated)
    for sid in ids:
        try:
            item, state, _ = await record(request, sid)
        except HTTPException as exc:
            if exc.status_code == 404:
                continue
            raise
        if _reference_key(item.get("reference")) == key:
            return sid, item, state
    raise HTTPException(404, "Petition reference not found.")


class AcknowledgementLookup(BaseModel):
    reference: str = Field(min_length=8, max_length=40)


@router.post("/acknowledgements/lookup")
async def acknowledge_by_reference(
    body: AcknowledgementLookup, request: Request, user: OfficerUser
):
    """Record receipt of a paper petition and return a printable slip."""
    sid, item, _ = await _petition_for_reference(request, body.reference)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    key = _reference_key(item["reference"])
    year = key[2:6]
    suffix = key[6:]
    acknowledgement_ref = f"ACK/{year}/{suffix}"
    with store.database() as db:
        db.execute(
            """INSERT INTO officer_acknowledgements(
                   session_id,reference,acknowledged_by,acknowledged_at
               ) VALUES(?,?,?,?)
               ON CONFLICT(session_id) DO NOTHING""",
            (sid, acknowledgement_ref, user["username"], now),
        )
        saved_ack = db.execute(
            "SELECT reference,acknowledged_by,acknowledged_at "
            "FROM officer_acknowledgements WHERE session_id=?", (sid,),
        ).fetchone()
        db.execute(
            """INSERT INTO officer_reviews(session_id,status)
               VALUES(?, 'Acknowledged')
               ON CONFLICT(session_id) DO UPDATE SET status='Acknowledged'""",
            (sid,),
        )
        db.execute(
            "INSERT INTO officer_audit(session_id,status,author,created_at) "
            "VALUES(?,?,?,?)",
            (sid, "Acknowledged", user["username"], now),
        )
    return {
        "id": sid,
        "reference": saved_ack["reference"],
        "petition_reference": item["reference"],
        "petitioner_name": item["petitioner_name"],
        "subject": item["subject"],
        "department": item.get("department") or "",
        "created_at": saved_ack["acknowledged_at"],
        "status": "Acknowledged",
        "language": item["language"],
        "acknowledged_by": saved_ack["acknowledged_by"],
        "type": "physical_receipt",
    }


@router.get("/acknowledgements")
async def acknowledgements(request: Request, user: OfficerUser):
    items = []
    for p in (await petitions(request, user))["items"]:
        items.extend(await acknowledgements_for(request, p["id"]))
        with store.database() as db:
            received = db.execute(
                "SELECT reference,acknowledged_by,acknowledged_at "
                "FROM officer_acknowledgements WHERE session_id=?", (p["id"],),
            ).fetchone()
        if received:
            items.append({
                "id": p["id"], "reference": received["reference"],
                "petition_id": p["id"], "petition_reference": p["reference"],
                "petitioner_name": p["petitioner_name"], "subject": p["subject"],
                "department": p["department"], "category": p["category"],
                "created_at": received["acknowledged_at"],
                "status": "Acknowledged", "language": p["language"],
                "acknowledged_by": received["acknowledged_by"],
                "type": "physical_receipt",
            })
    return {"items": items}


@router.get("/acknowledgements/{aid}")
async def acknowledgement(aid: str, request: Request, user: OfficerUser):
    sid, sep, _ = aid.partition("~")
    if sep:
        for item in await acknowledgements_for(request, sid):
            if item["id"] == aid:
                return item
    else:
        with store.database() as db:
            received = db.execute(
                "SELECT reference,acknowledged_by,acknowledged_at "
                "FROM officer_acknowledgements WHERE session_id=?", (aid,),
            ).fetchone()
        if received:
            item, _, _ = await record(request, aid)
            return {
                "id": aid, "reference": received["reference"],
                "petition_id": aid, "petition_reference": item["reference"],
                "petitioner_name": item["petitioner_name"], "subject": item["subject"],
                "department": item["department"], "created_at": received["acknowledged_at"],
                "status": "Acknowledged", "language": item["language"],
                "acknowledged_by": received["acknowledged_by"],
                "text": "Physical petition received by the Collectorate.",
                "type": "physical_receipt",
            }
    raise HTTPException(404, "Acknowledgement not found.")


# --------------------------------------------------------------------------- #
# The Phase-2 curator-review API used to live here. Removed from the officer
# surface at Harish's request. The underlying data layer — `app.knowledge.
# quarantine` + `app.knowledge.india_code` + `scripts/ingest_india_code_tn.py`
# — remains importable and tested, so a future UI can be re-added without
# re-writing the backend.
# --------------------------------------------------------------------------- #
