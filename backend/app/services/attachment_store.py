"""Where a citizen's attachments live, and why it is not where the corpus lives.

Two stores, and they must never become one.

    var/knowledge.sqlite      government reference documents. Shared across
                              every citizen, written only by `scripts/ingest.py`,
                              embedded and searchable.

    var/attachments/<session> this citizen's own evidence. One directory per
                              session, never embedded, never searchable, never
                              read by the knowledge layer.

An Aadhaar card, a photograph of a street, a previous petition naming a person
and their complaint — putting any of those into a shared vector index means the
next citizen's grievance can retrieve them. There is no code path from this
module to `app/knowledge`, and `KnowledgeStore` has no writer but ingestion;
`test_knowledge.py` asserts the corpus does not grow across a whole petition.

Everything written here is confined to the session's own directory. Paths are
resolved and checked against it after resolution, not before, so a crafted
filename cannot walk out through a symlink or a `..`.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..config import Settings, get_settings
from ..domain.attachments import (
    ALLOWED_SUFFIXES,
    ALLOWED_TYPES,
    MAX_ATTACHMENTS,
    MAX_BYTES,
    Attachment,
    AttachmentSet,
    sanitise_filename,
)

log = logging.getLogger(__name__)


class AttachmentRejected(ValueError):
    """The file cannot be accepted. The message is shown to the citizen."""


@dataclass
class Stored:
    attachment: Attachment
    path: Path


def session_dir(session_id: str, settings: Settings | None = None) -> Path:
    """This session's own directory, created on demand.

    `session_id` is a UUID the service generated, but it arrives here from a URL
    path, so it is validated as one rather than trusted. A session id that is
    not a UUID cannot name a directory.
    """
    try:
        uuid.UUID(str(session_id))
    except (ValueError, AttributeError, TypeError):
        raise AttachmentRejected("That session id is not valid.") from None
    s = settings or get_settings()
    directory = s.data_dir / "attachments" / str(session_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _inside(path: Path, root: Path) -> bool:
    """Is `path` really under `root`, after every link is resolved?

    Checked after resolution on purpose. A check on the joined string passes for
    a name that becomes an escape only once a symlink in the middle is followed.
    """
    try:
        return path.resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


def save(
    *,
    session_id: str,
    filename: str,
    content: bytes,
    content_type: str = "",
    existing: AttachmentSet | None = None,
    settings: Settings | None = None,
) -> Stored:
    """Write one attachment into this session's directory.

    Refuses rather than truncates, and refuses on the bytes rather than on the
    declared type: a `.pdf` whose content is something else is not a PDF.
    """
    existing = existing or AttachmentSet()
    if len(existing) >= MAX_ATTACHMENTS:
        raise AttachmentRejected(
            f"A petition can carry at most {MAX_ATTACHMENTS} attachments.")
    if not content:
        raise AttachmentRejected("That file is empty.")
    if len(content) > MAX_BYTES:
        raise AttachmentRejected(
            f"That file is larger than {MAX_BYTES // (1024 * 1024)} MB.")

    safe = sanitise_filename(filename)
    suffix = Path(safe).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        suffix = ALLOWED_TYPES.get(content_type.split(";")[0].strip().lower(), "")
        if not suffix:
            raise AttachmentRejected(
                "That kind of file cannot be attached. Please send a PDF, a "
                "photograph, a Word document or a text file.")
        safe = f"{safe}{suffix}"

    # The bytes decide, and an unrecognised header is a refusal rather than a
    # pass. Accepting "unknown" was a hole: a file named `.pdf` whose contents
    # began `MZ` — a Windows executable — was stored as a PDF, because the
    # sniffer did not recognise it and the check only fired on a POSITIVE
    # mismatch. Every allowed type except plain text has a signature, so
    # requiring one costs nothing and closes it.
    suffix = ".jpg" if suffix == ".jpeg" else suffix
    if suffix != ".txt":
        sniffed = _sniff(content)
        if sniffed is None:
            raise AttachmentRejected(
                "That file does not look like the kind of file it is named. "
                "Please attach the original PDF, photograph or document.")
        if sniffed != suffix:
            raise AttachmentRejected(
                f"That file is named '{suffix}' but its contents are "
                f"'{sniffed}'. Please attach the original file.")
    elif b"\x00" in content[:4096]:
        # A "text" file with NUL bytes in it is not one.
        raise AttachmentRejected("That file is not readable text.")

    attachment_id = uuid.uuid4().hex[:16]
    stored_name = f"{attachment_id}{suffix}"
    root = session_dir(session_id, settings)
    path = root / stored_name
    if not _inside(path, root):     # pragma: no cover - stored_name is generated
        raise AttachmentRejected("That filename cannot be stored.")

    path.write_bytes(content)
    attachment = Attachment(
        attachment_id=attachment_id,
        filename=safe,
        stored_name=stored_name,
        content_type=(content_type or "").split(";")[0].strip()
        or _TYPE_FOR.get(suffix, "application/octet-stream"),
        size=len(content),
        uploaded_at=datetime.now(UTC).isoformat(),
    )
    # The citizen's filename is NOT logged: people name files after themselves.
    log.info("attachment.stored",
             extra={"attachment_id": attachment_id, "bytes": len(content),
                    "suffix": suffix})
    return Stored(attachment=attachment, path=path)


_TYPE_FOR = {v: k for k, v in ALLOWED_TYPES.items()}

# Enough of each format's header to tell it apart. Not a full sniffer: the point
# is to catch a mislabelled file, not to identify an arbitrary one.
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", ".pdf"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
)


def _sniff(content: bytes) -> str | None:
    """The real type, from the header, or None when it is not one we allow."""
    for magic, suffix in _MAGIC:
        if content.startswith(magic):
            return suffix
    if content[:4] == b"PK\x03\x04":
        # A zip. DOCX is one; so is a lot else, but within the allowlist it can
        # only be DOCX.
        return ".docx"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return ".webp"
    if content[4:8] == b"ftyp" and any(
            brand in content[8:24] for brand in
            (b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1")):
        return ".heic"
    return None


def path_of(session_id: str, attachment: Attachment,
            settings: Settings | None = None) -> Path | None:
    """The file for an attachment, or None if it is not where it should be."""
    root = session_dir(session_id, settings)
    path = root / attachment.stored_name
    if not _inside(path, root) or not path.is_file():
        return None
    return path


def delete(session_id: str, attachment: Attachment,
           settings: Settings | None = None) -> bool:
    path = path_of(session_id, attachment, settings)
    if path is None:
        return False
    path.unlink(missing_ok=True)
    log.info("attachment.deleted", extra={"attachment_id": attachment.attachment_id})
    return True


def discard_session(session_id: str, settings: Settings | None = None) -> None:
    """Remove every attachment for a session. Used when it is restarted."""
    try:
        root = session_dir(session_id, settings)
    except AttachmentRejected:
        return
    shutil.rmtree(root, ignore_errors=True)
    log.info("attachment.session_discarded")
