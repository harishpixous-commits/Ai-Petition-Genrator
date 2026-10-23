"""Build the government corpus from the manifest, repeatably.

    python scripts/fetch_corpus.py list       what the manifest names
    python scripts/fetch_corpus.py verify     check every URL is still reachable
    python scripts/fetch_corpus.py fetch      download into var/corpus/
    python scripts/fetch_corpus.py ingest     download and index
    python scripts/fetch_corpus.py health     what is actually in the corpus

WHY THIS EXISTS BESIDE `scripts/ingest.py`. That one indexes whatever a person
points it at, which is the right tool for a department adding its own circular.
This one rebuilds a KNOWN corpus from a checked-in manifest, so that the
question "what does this service know, and where did it come from" has an
answer that does not depend on anybody's memory.

WHAT `verify` IS FOR. Government URLs rot. A department reorganises its site
and a document that was the basis of an answer last month is a 404 this month.
`verify` is cheap, touches nothing, and is meant to be run on a schedule: it
reports which entries have gone, so the manifest can be corrected before an
officer notices that a citation leads nowhere.

NOTHING HERE FABRICATES. A download that fails is reported as a failure and
the entry is skipped; it is never recorded as ingested, and no placeholder
text is ever written in its place. A corpus with nine documents and a clear
note about the tenth is worth more than ten documents one of which is a lie.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

import yaml  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.knowledge import embeddings as embedding_providers  # noqa: E402
from app.knowledge.ingest import Ingestor  # noqa: E402
from app.knowledge.store import KnowledgeStore  # noqa: E402

MANIFEST = Path(__file__).resolve().parent.parent / "corpus" / "tamil_nadu.yaml"

#: Some government hosts refuse a request with no User-Agent.
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; petition-assistant/1.0)"}
_TIMEOUT = 120


@dataclass
class Entry:
    """One document the manifest names."""

    id: str
    title: str
    url: str
    document_type: str
    authority: str
    department: str
    publisher: str
    language: str
    applies_to: str
    verified: str
    why: str
    government_order_number: str = ""

    @property
    def provenance(self) -> str:
        """Where this copy came from, recorded with the document.

        The pipeline refuses to mark anything `official` without this, which
        is the rule that stops a corpus filling up with documents nobody can
        trace.
        """
        return (f"Downloaded from {self.url} on {self.verified}. "
                f"Published by {self.publisher}.")

    def metadata(self) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "title": self.title,
            "document_type": self.document_type,
            "authority": self.authority,
            "department": self.department,
            "provenance": self.provenance,
            "source_url": self.url,
            "language": self.language,
        }
        if self.government_order_number:
            meta["government_order_number"] = self.government_order_number
        return meta


def load_manifest(path: Path = MANIFEST) -> list[Entry]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    documents = raw.get("documents") or []
    entries: list[Entry] = []
    for item in documents:
        entries.append(Entry(
            id=str(item["id"]),
            title=str(item["title"]),
            url=str(item["url"]),
            document_type=str(item.get("document_type") or "other"),
            authority=str(item.get("authority") or "unknown"),
            department=str(item.get("department") or ""),
            publisher=str(item.get("publisher") or ""),
            language=str(item.get("language") or "en"),
            applies_to=str(item.get("applies_to") or "both"),
            verified=str(item.get("verified") or ""),
            why=" ".join(str(item.get("why") or "").split()),
            government_order_number=str(item.get("government_order_number") or ""),
        ))
    return entries


def corpus_dir() -> Path:
    directory = Path(get_settings().data_dir) / "corpus"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def local_path(entry: Entry) -> Path:
    return corpus_dir() / f"{entry.id}.pdf"


# --------------------------------------------------------------------------- #
# Network
# --------------------------------------------------------------------------- #

def _open(url: str, method: str = "GET"):
    request = urllib.request.Request(url, headers=_HEADERS, method=method)
    return urllib.request.urlopen(request, timeout=_TIMEOUT)  # noqa: S310


def check(entry: Entry) -> tuple[bool, str]:
    """Is this URL still serving a document? Downloads nothing on success."""
    try:
        with _open(entry.url, "HEAD") as response:
            kind = response.headers.get("Content-Type", "")
            length = response.headers.get("Content-Length", "?")
            return True, f"{response.status} {kind} {length}"
    except urllib.error.HTTPError as exc:
        # Several government hosts reject HEAD but serve GET perfectly well.
        # The Rural Development portal serves its Acts through a PHP endpoint
        # that answers HEAD with 400 Bad Request and GET with the document, so
        # a verifier that trusted HEAD alone would report a live Act as dead
        # and somebody would "fix" the manifest by deleting it.
        if exc.code in (400, 403, 405, 501):
            try:
                with _open(entry.url) as response:
                    response.read(2048)
                    return True, f"{response.status} (HEAD refused, GET works)"
            except Exception as inner:  # noqa: BLE001
                return False, f"{type(inner).__name__}: {inner}"
        return False, f"HTTP {exc.code} {exc.reason}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def download(entry: Entry, *, force: bool = False) -> tuple[bool, str]:
    """Fetch the document. Returns (ok, message)."""
    target = local_path(entry)
    if target.exists() and not force:
        return True, f"cached {target.stat().st_size:,} bytes"
    try:
        with _open(entry.url) as response:
            body = response.read()
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"

    if not body:
        return False, "empty response"
    # A portal that has lost a document usually serves its HTML error page with
    # a 200. Indexing that as an Act is worse than not having the Act.
    if body[:5] != b"%PDF-":
        head = body[:120].decode("utf-8", "replace").replace("\n", " ")
        return False, f"not a PDF (starts {head!r})"

    target.write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()[:16]
    return True, f"{len(body):,} bytes  sha256:{digest}"


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #

def cmd_list(entries: list[Entry]) -> int:
    print(f"{len(entries)} documents in {MANIFEST.name}\n")
    for entry in entries:
        print(f"  {entry.id}")
        print(f"      {entry.title}")
        print(f"      {entry.document_type}  |  {entry.authority}  |  "
              f"{entry.language}  |  {entry.applies_to}")
        print(f"      {entry.url}")
        if entry.why:
            print(f"      why: {entry.why[:140]}")
        print()
    return 0


def cmd_verify(entries: list[Entry]) -> int:
    print(f"checking {len(entries)} URLs\n")
    gone = []
    for entry in entries:
        ok, message = check(entry)
        print(f"  {'ok  ' if ok else 'GONE'}  {entry.id:<36} {message}")
        if not ok:
            gone.append((entry, message))
    print()
    if gone:
        print(f"{len(gone)} of {len(entries)} are no longer reachable:")
        for entry, message in gone:
            print(f"  {entry.id}: {message}")
            print(f"      {entry.url}")
        print("\nCorrect the manifest before relying on these citations.")
        return 1
    print(f"all {len(entries)} reachable")
    return 0


def cmd_fetch(entries: list[Entry], force: bool = False) -> int:
    print(f"downloading into {corpus_dir()}\n")
    failed = []
    for entry in entries:
        ok, message = download(entry, force=force)
        print(f"  {'ok  ' if ok else 'FAIL'}  {entry.id:<36} {message}")
        if not ok:
            failed.append(entry.id)
    print()
    print(f"{len(entries) - len(failed)}/{len(entries)} downloaded")
    if failed:
        print(f"failed: {', '.join(failed)}")
        return 1
    return 0


async def cmd_ingest(entries: list[Entry], force: bool = False) -> int:
    settings = get_settings()
    provider = embedding_providers.build(settings)
    store = KnowledgeStore(settings.knowledge_path, dimension=provider.dimension,
                           provider=provider.name)
    ingestor = Ingestor(store=store, provider=provider, settings=settings)

    print(f"embedder: {provider.name} "
          f"(semantic={getattr(provider, 'semantic', False)}, "
          f"dimension={provider.dimension})")
    print(f"corpus  : {settings.knowledge_path}\n")

    indexed = skipped = failed = 0
    for entry in entries:
        ok, message = download(entry)
        if not ok:
            print(f"  FAIL  {entry.id:<36} download: {message}")
            failed += 1
            continue
        result = await ingestor.ingest(local_path(entry),
                                       metadata=entry.metadata(), force=force)
        if result.error:
            print(f"  FAIL  {entry.id:<36} ingest: {result.error[:90]}")
            failed += 1
        elif result.skipped:
            print(f"  --    {entry.id:<36} {result.reason}")
            skipped += 1
        else:
            print(f"  ok    {entry.id:<36} {result.chunks} chunks  "
                  f"{result.title[:46]}")
            indexed += 1

    print()
    print(f"indexed {indexed}, unchanged {skipped}, failed {failed}")
    stats = store.stats()
    print(f"corpus now: {stats.get('documents', 0)} documents, "
          f"{stats.get('chunks', 0)} chunks")
    return 1 if failed else 0


def _vector_coverage(settings) -> tuple[int, int] | None:
    """(vectors, chunks), or None when it cannot be read.

    Read straight from the sqlite-vec shadow tables, because the store's own
    stats do not expose this and the number is the difference between working
    multilingual retrieval and a corpus that only matches words.
    """
    import sqlite3

    path = Path(settings.knowledge_path)
    if not path.exists():
        return None
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        vectors = db.execute("SELECT count(*) FROM chunks_vec_rowids").fetchone()[0]
        chunks = db.execute("SELECT count(*) FROM chunks_fts").fetchone()[0]
        return int(vectors), int(chunks)
    except sqlite3.DatabaseError:
        return None
    finally:
        db.close()


def cmd_health(entries: list[Entry]) -> int:
    settings = get_settings()
    provider = embedding_providers.build(settings)
    store = KnowledgeStore(settings.knowledge_path, dimension=provider.dimension,
                           provider=provider.name)
    stats = store.stats()

    print("corpus health\n")
    for key in ("documents", "live_documents", "official_documents",
                "unverified_documents", "superseded", "chunks",
                "indexed_provider", "indexed_dimension", "vector_search",
                "ready", "last_ingested_at"):
        if key in stats:
            print(f"  {key:<22} {stats[key]}")

    by_type = stats.get("by_type") or {}
    if by_type:
        print("\n  by document type")
        for name, count in sorted(by_type.items()):
            print(f"    {name:<24} {count}")

    # VECTOR COVERAGE, which nothing else reports and which can silently fall.
    #
    # Chunks and their embeddings are written separately, so an ingest that is
    # interrupted — a timeout, a kill, a machine going down — can leave every
    # chunk present and its vector missing. Lexical search still works, so the
    # service looks healthy, and cross-language retrieval quietly stops.
    #
    # Measured, not imagined: a kill during ingestion took this from
    # 8,069/8,069 to 5,559/8,069 and nothing in the service said so.
    coverage = _vector_coverage(settings)
    if coverage is not None:
        vectors, chunks = coverage
        share = (100.0 * vectors / chunks) if chunks else 0.0
        print(f"\n  vectors                {vectors:,} of {chunks:,} chunks "
              f"({share:.1f}%)")
        if chunks and vectors < chunks:
            print("    INCOMPLETE — cross-language retrieval is degraded for "
                  "the remainder.")
            print("    Repair with: python scripts/ingest.py reindex")

    print(f"\n  manifest names {len(entries)} documents")
    missing = [e.id for e in entries if not local_path(e).exists()]
    if missing:
        print(f"  not downloaded: {len(missing)}  ({', '.join(missing[:6])}"
              f"{'...' if len(missing) > 6 else ''})")

    if not stats.get("ready"):
        print("\n  NOT READY: the analysis panel will stay silent. "
              "Run `fetch_corpus.py ingest`.")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",
                        choices=("list", "verify", "fetch", "ingest", "health"))
    parser.add_argument("--force", action="store_true",
                        help="re-download and re-index even if unchanged")
    parser.add_argument("--only", default="",
                        help="comma-separated document ids")
    args = parser.parse_args(argv)

    entries = load_manifest()
    if args.only:
        wanted = {name.strip() for name in args.only.split(",") if name.strip()}
        unknown = wanted - {e.id for e in entries}
        if unknown:
            print(f"unknown document id(s): {', '.join(sorted(unknown))}")
            return 2
        entries = [e for e in entries if e.id in wanted]

    if args.command == "list":
        return cmd_list(entries)
    if args.command == "verify":
        return cmd_verify(entries)
    if args.command == "fetch":
        return cmd_fetch(entries, force=args.force)
    if args.command == "health":
        return cmd_health(entries)
    return asyncio.run(cmd_ingest(entries, force=args.force))


if __name__ == "__main__":
    sys.exit(main())
