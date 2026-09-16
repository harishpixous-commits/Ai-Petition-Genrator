"""Getting government documents into the corpus.

    document / URL
       ↓  extract   pypdf, python-docx, lxml, plain text
       ↓  clean     de-hyphenate, drop page furniture, collapse rules
       ↓  chunk     ~1200 chars on section and paragraph boundaries
       ↓  metadata  act, rule, GO number, department, section, page, date
       ↓  embed     whichever provider is configured
       ↓  store     SQLite: FTS5 + sqlite-vec

Two decisions worth stating.

**Chunks break on section boundaries, not on a character count.** A citation
that says "Section 12" has to point at the text of section 12, not at a window
that happens to straddle 11 and 12. Everything downstream — the grounding check
especially — rests on a chunk being a thing a reader can look up.

**Metadata is detected, then overridden.** The regexes below read an Act name or
a G.O. number out of the first page because most departmental PDFs put it there,
and whoever runs ingestion can pass better metadata explicitly. Detection is a
convenience; it is never treated as authoritative, and a failed detection leaves
the field null rather than guessing.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Settings, get_settings
from . import embeddings as embedding_providers
from .store import KnowledgeStore, content_hash, document_id_for

log = logging.getLogger(__name__)

TEXT_SUFFIXES = {".txt", ".md", ".text"}
HTML_SUFFIXES = {".html", ".htm", ".xhtml"}


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #

@dataclass
class Page:
    number: int | None
    text: str


@dataclass
class Extracted:
    pages: list[Page]
    title: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.pages)


def extract(source: str | Path) -> Extracted:
    """Pull text out of whatever was handed over.

    A source that yields no text raises, rather than quietly indexing an empty
    document — a scanned PDF with no text layer is the common case, and it
    needs OCR, not a silent success.
    """
    text_source = str(source)
    if text_source.startswith(("http://", "https://")):
        return _extract_url(text_source)

    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(f"Not a file: {path}")
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        extracted = _extract_pdf(path)
    elif suffix == ".docx":
        extracted = _extract_docx(path)
    elif suffix in HTML_SUFFIXES:
        extracted = _extract_html(path.read_text(encoding="utf-8", errors="replace"))
    elif suffix in TEXT_SUFFIXES or suffix == "":
        raw = path.read_text(encoding="utf-8", errors="replace")
        extracted = Extracted(pages=[Page(number=None, text=raw)])
    else:
        raise ValueError(
            f"Unsupported file type '{suffix}'. Supported: .pdf, .docx, .html, .txt"
        )

    if not extracted.title:
        extracted.title = _title_from(extracted, fallback=path.stem)
    if not extracted.text.strip():
        raise ValueError(
            f"No text could be extracted from {path.name}. "
            "A scanned PDF needs OCR before it can be indexed."
        )
    return extracted


def _extract_pdf(path: Path) -> Extracted:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001  — one bad page must not lose the rest
            log.info("ingest.page_failed",
                     extra={"page": index, "error": str(exc)[:120]})
            text = ""
        if text.strip():
            pages.append(Page(number=index, text=text))

    info = {}
    try:
        raw = reader.metadata or {}
        info = {
            "title": (raw.get("/Title") or "").strip(),
            "date": _pdf_date(raw.get("/CreationDate")),
        }
    except Exception:  # noqa: BLE001
        pass
    return Extracted(pages=pages, title=info.get("title") or "",
                     meta={k: v for k, v in info.items() if v and k != "title"})


def _pdf_date(value: Any) -> str | None:
    match = re.match(r"D:(\d{4})(\d{2})(\d{2})", str(value or ""))
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}" if match else None


def _extract_docx(path: Path) -> Extracted:
    import docx

    document = docx.Document(str(path))
    lines = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        # A heading is marked up as one; keeping the marker lets the chunker
        # split where the document itself says a section starts.
        if (paragraph.style and paragraph.style.name or "").startswith("Heading"):
            lines.append(f"\n## {text}\n")
        else:
            lines.append(text)
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                lines.append(" | ".join(cells))
    return Extracted(pages=[Page(number=None, text="\n".join(lines))])


def _extract_html(html: str, url: str | None = None) -> Extracted:
    from lxml import html as lxml_html

    tree = lxml_html.fromstring(html)
    for tag in tree.xpath("//script|//style|//nav|//footer|//noscript|//header|//form"):
        tag.getparent().remove(tag)

    title = ""
    heads = tree.xpath("//title/text()") or tree.xpath("//h1//text()")
    if heads:
        title = " ".join(str(heads[0]).split())

    # Prefer the page's own main region when it marks one — government sites
    # that do are otherwise 80% navigation.
    main = tree.xpath("//main|//article|//*[@role='main']|//*[@id='content']")
    body = main[0] if main else tree
    lines = []
    for node in body.iter():
        if node.tag in ("h1", "h2", "h3", "h4"):
            text = " ".join(node.text_content().split())
            if text:
                lines.append(f"\n## {text}\n")
        elif node.tag in ("p", "li", "td", "th", "dd", "dt"):
            text = " ".join(node.text_content().split())
            if len(text) > 1:
                lines.append(text)
    if not lines:
        lines = [" ".join(body.text_content().split())]
    return Extracted(pages=[Page(number=None, text="\n".join(lines))],
                     title=title, meta={"source_url": url} if url else {})


def _extract_url(url: str) -> Extracted:
    import httpx

    response = httpx.get(url, timeout=30, follow_redirects=True,
                         headers={"User-Agent": "CitizenPetitionAssistant/1.0 (ingestion)"})
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")

    if "pdf" in content_type or url.lower().endswith(".pdf"):
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            handle.write(response.content)
            temporary = Path(handle.name)
        try:
            extracted = _extract_pdf(temporary)
        finally:
            temporary.unlink(missing_ok=True)
        extracted.meta["source_url"] = url
    else:
        extracted = _extract_html(response.text, url=url)

    if not extracted.title:
        extracted.title = url.rstrip("/").rsplit("/", 1)[-1] or url
    if not extracted.text.strip():
        raise ValueError(f"No text could be extracted from {url}")
    return extracted


def _title_from(extracted: Extracted, fallback: str) -> str:
    for line in extracted.text.splitlines():
        stripped = line.strip(" #\t")
        if 8 <= len(stripped) <= 160:
            return stripped
    return fallback.replace("_", " ").replace("-", " ").strip() or "Untitled document"


# --------------------------------------------------------------------------- #
# Cleaning
# --------------------------------------------------------------------------- #

_HYPHEN_BREAK = re.compile(r"(\w)-\s*\n\s*(\w)")
_RULE = re.compile(r"^[\s._\-–—=*]{4,}$", re.MULTILINE)
_PAGE_FURNITURE = re.compile(
    r"^\s*(?:page\s*)?[-–—\[(]*\s*\d{1,4}\s*(?:of\s*\d{1,4})?\s*[-–—\])]*\s*$",
    re.IGNORECASE | re.MULTILINE)
_BLANK_RUN = re.compile(r"\n{3,}")
_SPACE_RUN = re.compile(r"[ \t ]{2,}")


def clean(text: str) -> str:
    """Repair what extraction breaks.

    PDF text arrives hyphenated across line breaks, decorated with rules, and
    carrying a page number on its own line every page or two. Left in, all
    three end up inside chunks and inside citations.
    """
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("­", "")               # soft hyphen
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    text = _RULE.sub("", text)
    text = _PAGE_FURNITURE.sub("", text)
    text = _SPACE_RUN.sub(" ", text)
    text = _BLANK_RUN.sub("\n\n", text)
    return text.strip()


# --------------------------------------------------------------------------- #
# Metadata detection
# --------------------------------------------------------------------------- #

_ACT = re.compile(
    r"\b((?:The\s+)?[A-Z][A-Za-z().,'\-]*(?:\s+[A-Z(][A-Za-z().,'\-]*){0,9}?"
    r"\s+Act,?\s*\d{4})", re.UNICODE)
_RULES = re.compile(
    r"\b((?:The\s+)?[A-Z][A-Za-z().,'\-]*(?:\s+[A-Z(][A-Za-z().,'\-]*){0,9}?"
    r"\s+Rules,?\s*\d{4})", re.UNICODE)
# G.O. (Ms) No. 123, Revenue (LA) Department, dated 01.02.2020
_GO = re.compile(
    r"\bG\.?\s*O\.?\s*(?:\(?(?:Ms|Rt|D|P|2D|3D)\)?\.?\s*)?(?:No\.?\s*)?(\d+[A-Za-z]?)",
    re.IGNORECASE)
_DEPARTMENT = re.compile(
    r"\b([A-Z][A-Za-z&().,'\-]*(?:\s+[A-Z&(][A-Za-z&().,'\-]*){0,5}\s+Department)\b")
_DATE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b")

# The first line of a section, in the shapes government documents use.
_SECTION = re.compile(
    r"^\s*(?:"
    r"##\s*(?P<md>.{3,120}?)"
    r"|(?:Section|Rule|Clause|Article|Para(?:graph)?|Chapter|Schedule|Part)\s+"
    r"(?P<num>[0-9IVXLC]+[A-Za-z]?(?:\s*\(\w+\))*)\s*[.:\-–—]?\s*(?P<title>.{0,110})"
    r"|(?P<plain>\d{1,3}(?:\.\d{1,3})*)\s*[.)]\s+(?P<ptitle>[A-Z஀-௿].{3,110})"
    r")\s*$",
    re.MULTILINE)


def detect_metadata(text: str, limit: int = 6000) -> dict[str, Any]:
    """Read what the document says about itself, off the first few pages."""
    head = text[:limit]
    found: dict[str, Any] = {}

    if match := _ACT.search(head):
        found["act_name"] = " ".join(match.group(1).split())
    if match := _RULES.search(head):
        found["rule_name"] = " ".join(match.group(1).split())
    if match := _GO.search(head):
        found["government_order_number"] = match.group(1)
        found["document_type"] = "government_order"
    if match := _DEPARTMENT.search(head):
        found["department"] = " ".join(match.group(1).split())
    if match := _DATE.search(head):
        day, month, year = match.groups()
        try:
            found["date"] = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        except ValueError:
            pass

    if "document_type" not in found:
        lowered = head.lower()
        if "act" in found or found.get("act_name"):
            found["document_type"] = "act"
        elif found.get("rule_name"):
            found["document_type"] = "rule"
        elif "circular" in lowered[:600]:
            found["document_type"] = "circular"
        elif "guideline" in lowered[:600]:
            found["document_type"] = "guideline"
    return found


# --------------------------------------------------------------------------- #
# Chunking
# --------------------------------------------------------------------------- #

def _sections(text: str) -> list[tuple[str | None, str]]:
    """Split on headings, keeping the heading with the body it introduces."""
    marks = list(_SECTION.finditer(text))
    if not marks:
        return [(None, text)]

    out: list[tuple[str | None, str]] = []
    if marks[0].start() > 0:
        preamble = text[:marks[0].start()].strip()
        if preamble:
            out.append((None, preamble))
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        body = text[mark.start():end].strip()
        if body:
            out.append((_section_label(mark), body))
    return out


def _section_label(mark: re.Match[str]) -> str | None:
    groups = mark.groupdict()
    if groups.get("md"):
        return " ".join(groups["md"].split())[:120]
    if groups.get("num"):
        head = mark.group(0).strip().lstrip("#").strip()
        return " ".join(head.split())[:120]
    if groups.get("plain"):
        return " ".join(f"{groups['plain']} {groups.get('ptitle') or ''}".split())[:120]
    return None


def _split_long(body: str, size: int, overlap: int) -> list[str]:
    """Break an oversized section on paragraph, then sentence, boundaries."""
    if len(body) <= size:
        return [body]

    pieces: list[str] = []
    buffer = ""
    for paragraph in re.split(r"\n\s*\n", body):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(buffer) + len(paragraph) + 2 <= size:
            buffer = f"{buffer}\n\n{paragraph}" if buffer else paragraph
            continue
        if buffer:
            pieces.append(buffer)
        if len(paragraph) <= size:
            buffer = paragraph
            continue
        # One paragraph longer than a whole chunk: sentence boundaries, and a
        # hard cut only if even those are absent.
        sentence_buffer = ""
        for sentence in re.split(r"(?<=[.।?!])\s+", paragraph):
            if len(sentence_buffer) + len(sentence) + 1 <= size:
                sentence_buffer = f"{sentence_buffer} {sentence}".strip()
            else:
                if sentence_buffer:
                    pieces.append(sentence_buffer)
                sentence_buffer = sentence[:size] if len(sentence) > size else sentence
        buffer = sentence_buffer
    if buffer:
        pieces.append(buffer)

    if overlap > 0 and len(pieces) > 1:
        # A little of the previous chunk's tail, so a definition that ends one
        # chunk is still present where it is used at the start of the next.
        overlapped = [pieces[0]]
        for previous, piece in zip(pieces, pieces[1:], strict=False):
            tail = previous[-overlap:]
            cut = tail.find(" ")
            overlapped.append((tail[cut + 1:] + "\n" + piece) if cut >= 0 else piece)
        pieces = overlapped
    return pieces


def chunk_document(
    extracted: Extracted,
    *,
    size: int = 1200,
    overlap: int = 160,
    document_id: str = "",
) -> list[dict[str, Any]]:
    """Chunks, in document order, each knowing its section and its page."""
    out: list[dict[str, Any]] = []
    ordinal = 0
    for page in extracted.pages:
        cleaned = clean(page.text)
        if not cleaned:
            continue
        for section, body in _sections(cleaned):
            for piece in _split_long(body, size, overlap):
                text = piece.strip()
                if len(text) < 40:      # a heading with no body under it
                    continue
                digest = hashlib.blake2b(
                    f"{document_id}|{ordinal}|{text}".encode(), digest_size=12).hexdigest()
                out.append({
                    "chunk_id": digest,
                    "ordinal": ordinal,
                    "text": text,
                    "section": section,
                    "page_number": page.number,
                })
                ordinal += 1
    return out


# --------------------------------------------------------------------------- #
# The pipeline
# --------------------------------------------------------------------------- #

@dataclass
class IngestResult:
    document_id: str
    title: str
    chunks: int
    skipped: bool = False
    reason: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


class Ingestor:
    """Runs the pipeline. The only writer the corpus has."""

    def __init__(self, store: KnowledgeStore | None = None,
                 provider: Any = None, settings: Settings | None = None) -> None:
        self.s = settings or get_settings()
        self.provider = provider or embedding_providers.build(self.s)
        self.store = store or KnowledgeStore(
            self.s.knowledge_path,
            dimension=getattr(self.provider, "dimension", 512),
            provider=getattr(self.provider, "name", "local"),
        )

    async def ingest(
        self,
        source: str | Path,
        *,
        metadata: dict[str, Any] | None = None,
        force: bool = False,
    ) -> IngestResult:
        origin = str(source)
        document_id = document_id_for(origin)
        try:
            extracted = extract(source)
        except Exception as exc:  # noqa: BLE001
            log.warning("ingest.extract_failed",
                        extra={"origin": origin[:200], "error": str(exc)[:200]})
            return IngestResult(document_id, "", 0, error=str(exc))

        body = clean(extracted.text)
        digest = content_hash(body)
        if not force and not self.store.needs_ingest(document_id, digest):
            return IngestResult(document_id, extracted.title, 0,
                                skipped=True, reason="unchanged")

        detected = detect_metadata(body)
        document = {
            "document_id": document_id,
            "title": extracted.title or origin,
            "origin": origin,
            "content_hash": digest,
            "authority": "unknown",
            **{k: v for k, v in extracted.meta.items() if v},
            **detected,
            **{k: v for k, v in (metadata or {}).items() if v is not None},
        }
        if origin.startswith(("http://", "https://")):
            document.setdefault("source_url", origin)
            document.setdefault("document_type", "webpage")

        # Authenticity is established, not asserted.
        #
        # `authority` decides ranking: an official source outranks an unofficial
        # one, and `required_from_analysis` will only call a document mandatory
        # on an official citation. So "official" cannot be a flag somebody types
        # — it has to be backed by something a reader could check. A URL the
        # document came from, a gazette citation, or the name of the officer who
        # verified the copy all count; nothing at all does not.
        document["authority"], downgrade = _checked_authority(document)
        if downgrade:
            log.warning("ingest.authority_downgraded",
                        extra={"title": str(document.get("title"))[:80],
                               "asked": downgrade, "using": document["authority"],
                               "reason": "no provenance recorded"})

        chunks = chunk_document(
            extracted,
            size=self.s.knowledge_chunk_chars,
            overlap=self.s.knowledge_chunk_overlap,
            document_id=document_id,
        )
        if not chunks:
            return IngestResult(document_id, document["title"], 0,
                                error="Nothing survived chunking.")

        vectors = await self._embed([c["text"] for c in chunks])
        self.store.upsert(document=document, chunks=chunks, embeddings=vectors)
        return IngestResult(document_id, str(document["title"]), len(chunks))

    async def _embed(self, texts: Sequence[str]) -> list[list[float]] | None:
        """Vectors, or None — never a half-embedded document.

        If the provider fails partway the document is still indexed lexically,
        which is a corpus that answers slightly worse rather than a corpus with
        a hole in it.
        """
        try:
            out: list[list[float]] = []
            batch = 32
            for start in range(0, len(texts), batch):
                out.extend(await self.provider.embed(list(texts[start:start + batch])))
            return out
        except Exception as exc:  # noqa: BLE001
            log.warning("ingest.embed_failed",
                        extra={"error": str(exc)[:200], "chunks": len(texts)})
            return None

    async def ingest_many(
        self,
        sources: Iterable[str | Path],
        *,
        metadata: dict[str, Any] | None = None,
        force: bool = False,
    ) -> list[IngestResult]:
        results = []
        for source in sources:
            results.append(await self.ingest(source, metadata=metadata, force=force))
        return results

    async def reindex(self) -> int:
        """Re-embed everything already stored, without re-reading the sources.

        What you run after changing the embedding provider. Text and citations
        are untouched; only the vectors are rebuilt.
        """
        rows = list(self.store.all_chunks())
        if not rows:
            return 0
        by_document: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_document.setdefault(row["document_id"], []).append(row)

        total = 0
        for document_id, chunks in by_document.items():
            stored = {d["document_id"]: d for d in self.store.documents(limit=10000)}
            document = stored.get(document_id)
            if not document:
                continue
            chunks.sort(key=lambda c: c["ordinal"])
            vectors = await self._embed([c["text"] for c in chunks])
            document = dict(document)
            document["content_hash"] = content_hash(
                "".join(c["text"] for c in chunks))
            self.store.upsert(document=document, chunks=chunks, embeddings=vectors)
            total += len(chunks)
        log.info("knowledge.reindexed", extra={"chunks": total})
        return total



def _checked_authority(document: dict[str, Any]) -> tuple[str, str | None]:
    """The authority a document may actually carry, and what was refused.

    Returns `(authority, downgraded_from)`. A document asking to be official or
    departmental keeps that only if its origin is recorded — `provenance`, a
    `source_url`, or a `government_order_number`, which is itself a citation an
    officer can look up. Otherwise it falls back to `unknown`, which still
    retrieves and still cites; it simply stops outranking everything else and
    stops being able to make a document mandatory.
    """
    asked = str(document.get("authority") or "unknown").lower()
    if asked not in ("official", "departmental"):
        return (asked if asked in ("external", "unknown") else "unknown"), None

    evidence = any(str(document.get(k) or "").strip()
                   for k in ("provenance", "source_url", "government_order_number"))
    if evidence:
        return asked, None
    return "unknown", asked


def collect(target: str | Path) -> list[Path]:
    """Every ingestible file under a path, or the file itself."""
    path = Path(target)
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    suffixes = {".pdf", ".docx"} | TEXT_SUFFIXES | HTML_SUFFIXES
    return sorted(p for p in path.rglob("*")
                  if p.is_file() and p.suffix.lower() in suffixes)
