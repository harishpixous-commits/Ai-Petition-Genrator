"""Load verified government documents into the knowledge base.

    python scripts/ingest.py inspect <file|url>          read it, index nothing
    python scripts/ingest.py preview <file|url>          show the chunks it makes
    python scripts/ingest.py add     <file|folder|url> [...]  [--official ...]
    python scripts/ingest.py show    <document-id>       what is actually indexed
    python scripts/ingest.py list
    python scripts/ingest.py remove  <document-id>
    python scripts/ingest.py supersede <document-id> [--by <document-id>]
    python scripts/ingest.py reindex
    python scripts/ingest.py status

The onboarding order that works:

    1  inspect  — see what metadata the file yields, and correct what is wrong
    2  preview  — read the chunks; a citation points at one of these
    3  add      — index it, with provenance
    4  show     — confirm what went in is what you meant

Re-running `add` on the same source does nothing unless the file has changed,
so this can be put on a schedule against a folder that a department syncs into.
`--force` re-reads and re-indexes regardless.

Authority is a decision, not a guess, and it has to be backed by something.
A document is marked `official` or `departmental` only because whoever ran this
said so AND recorded where the copy came from (`--provenance`, a source URL, or
a G.O. number). Without that it is indexed as `unknown`: still searchable, still
cited, but it no longer outranks anything and can never make a document
mandatory for a citizen. The pipeline infers none of this from a filename.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# The Windows console defaults to cp1252, which turns every Tamil document
# title into a row of replacement characters — and a department indexing its own
# Tamil circulars cannot read the confirmation that they were indexed.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from app.config import get_settings  # noqa: E402
from app.knowledge import embeddings as embedding_providers  # noqa: E402
from app.knowledge.ingest import Ingestor, collect  # noqa: E402
from app.knowledge.store import KnowledgeStore  # noqa: E402

DOCUMENT_TYPES = ("act", "rule", "government_order", "circular", "guideline",
                  "procedure", "faq", "webpage", "other")


def _build() -> tuple[Ingestor, KnowledgeStore]:
    settings = get_settings()
    provider = embedding_providers.build(settings)
    store = KnowledgeStore(settings.knowledge_path, dimension=provider.dimension,
                           provider=provider.name)
    return Ingestor(store=store, provider=provider, settings=settings), store


def _authority(args: argparse.Namespace) -> str | None:
    return ("official" if args.official
            else "departmental" if args.departmental
            else "external" if args.external else None)


def _refuse_unprovenanced(args: argparse.Namespace, sources: list) -> bool:
    """Official rank requires evidence of origin, and the CLI says so up front.

    The pipeline already downgrades a document that claims official rank with
    nothing behind it. Downgrading silently is the wrong shape for an operator
    tool: somebody loading a department's gazette copies should be told they
    are about to index fifty documents at the wrong rank BEFORE it happens,
    not find out from a log line afterwards.
    """
    if _authority(args) not in ("official", "departmental"):
        return False
    if args.provenance:
        return False
    urls = [s for s in sources if str(s).startswith(("http://", "https://"))]
    if urls and len(urls) == len(sources):
        return False        # the URL is itself the provenance
    print(
        "\nRefusing to index at official rank without provenance.\n\n"
        "  Authority decides ranking, and it is the only thing that can tell a\n"
        "  citizen a document is mandatory. It has to be backed by something a\n"
        "  reader could check.\n\n"
        "  Add one of:\n"
        '    --provenance "Tamil Nadu Government Gazette, Part III, 12 June 2019"\n'
        '    --provenance "Verified against the portal copy by <officer>, <date>"\n'
        "    (or ingest the URL directly, which records itself)\n\n"
        "  Or drop --official/--departmental to index it as unknown: still\n"
        "  searchable and still cited, it simply outranks nothing.\n")
    return True


async def add(args: argparse.Namespace) -> int:
    ingestor, _ = _build()
    metadata = {
        "authority": _authority(args),
        "department": args.department,
        "document_type": args.type,
        "provenance": args.provenance,
        "act_name": args.act,
        "version": args.version,
        "date": args.date,
    }

    sources: list = []
    for target in args.sources:
        if str(target).startswith(("http://", "https://")):
            sources.append(target)
        else:
            found = collect(target)
            if not found:
                print(f"  ! nothing ingestible at {target}")
            sources.extend(found)

    if not sources:
        print("Nothing to ingest.")
        return 1

    if _refuse_unprovenanced(args, sources):
        return 2

    added = skipped = failed = 0
    for source in sources:
        result = await ingestor.ingest(source, metadata=metadata, force=args.force)
        if result.error:
            failed += 1
            print(f"  ! {Path(str(source)).name}: {result.error}")
        elif result.skipped:
            skipped += 1
            print(f"  = {result.title}  (unchanged)")
        else:
            added += 1
            print(f"  + {result.title}  [{result.document_id}]  {result.chunks} chunks")

    print(f"\n{added} indexed, {skipped} unchanged, {failed} failed.")
    return 1 if failed and not added else 0


def _readable(key: str, value):
    """Epoch seconds are a storage detail, not something to read off a screen."""
    if key == "ingested_at":
        from datetime import UTC, datetime

        try:
            return datetime.fromtimestamp(float(value), UTC).strftime(
                "%Y-%m-%d %H:%M UTC")
        except (TypeError, ValueError):
            return value
    if key == "superseded":
        return "yes" if value else "no"
    return value


def _describe(source, extracted, detected, body) -> None:
    print(f"\n  source      {source}")
    print(f"  title       {extracted.title}")
    print(f"  pages       {len(extracted.pages) or 1}")
    print(f"  characters  {len(body):,}")
    print("\n  metadata read off the document:")
    if not detected:
        print("    (nothing detected — pass it explicitly on `add`)")
    for key in ("document_type", "act_name", "rule_name",
                "government_order_number", "department", "date"):
        if detected.get(key):
            print(f"    {key:24} {detected[key]}")


async def inspect(args: argparse.Namespace) -> int:
    """Read a document and show what it yields. Indexes nothing.

    The step that stops a folder of fifty circulars going in with the wrong Act
    name on every one of them.
    """
    from app.knowledge.ingest import clean, detect_metadata, extract

    try:
        extracted = extract(args.source)
    except Exception as exc:  # noqa: BLE001
        print(f"  ! {exc}")
        return 1

    body = clean(extracted.text)
    detected = detect_metadata(body)
    _describe(args.source, extracted, detected, body)

    chunks = _chunks_for(extracted, args.source)
    print(f"\n  would produce {len(chunks)} chunk(s). "
          f"Run `preview` to read them.")
    print("\n  Nothing was indexed.")
    return 0


def _chunks_for(extracted, source):
    from app.knowledge.ingest import chunk_document
    from app.knowledge.store import document_id_for

    settings = get_settings()
    return chunk_document(extracted, size=settings.knowledge_chunk_chars,
                          overlap=settings.knowledge_chunk_overlap,
                          document_id=document_id_for(str(source)))


async def preview(args: argparse.Namespace) -> int:
    """Print the chunks a document would produce.

    A citation points at one of these. If the chunk boundaries are wrong — a
    section split down the middle, a table flattened into noise — the citation
    will point at something a reader cannot follow, and this is where that is
    caught rather than in front of an officer.
    """
    from app.knowledge.ingest import extract

    try:
        extracted = extract(args.source)
    except Exception as exc:  # noqa: BLE001
        print(f"  ! {exc}")
        return 1

    chunks = _chunks_for(extracted, args.source)
    print(f"{len(chunks)} chunk(s) from {args.source}\n")
    for chunk in chunks[:args.limit]:
        head = f"[{chunk['ordinal']}]"
        where = " · ".join(str(x) for x in
                           (chunk.get("section"), chunk.get("page_number")) if x)
        print(f"{head} {where or '(no section)'}")
        print(f"    {chunk['text'][:args.chars].strip()}"
              f"{'…' if len(chunk['text']) > args.chars else ''}\n")
    if len(chunks) > args.limit:
        print(f"… {len(chunks) - args.limit} more. Use --limit to see them.")
    return 0


async def show(args: argparse.Namespace) -> int:
    """What is actually indexed for one document, as retrieval sees it."""
    _, store = _build()
    row = next((d for d in store.documents(limit=10000)
                if d["document_id"] == args.document_id), None)
    if row is None:
        print(f"No document with id {args.document_id}.")
        return 1

    for key in ("document_id", "title", "document_type", "authority", "department",
                "act_name", "source_url", "provenance", "version", "superseded",
                "chunk_count", "ingested_at"):
        if key in row and row[key] not in (None, ""):
            print(f"  {key:16} {_readable(key, row[key])}")
    if not row.get("provenance"):
        print("  provenance       (none recorded)")
    if row["authority"] in ("official", "departmental") and not row.get("provenance"):
        print("\n  NOTE: ranked official on a source URL or G.O. number rather "
              "than a written provenance.")

    chunks = [c for c in store.all_chunks() if c["document_id"] == args.document_id]
    print(f"\n  {len(chunks)} indexed chunk(s):")
    for chunk in chunks[:args.limit]:
        where = chunk.get("section") or "(no section)"
        print(f"    [{chunk['ordinal']}] {where}")
        print(f"        {chunk['text'][:160].strip()}…")
    if len(chunks) > args.limit:
        print(f"    … {len(chunks) - args.limit} more")
    return 0


async def listing(_: argparse.Namespace) -> int:
    _, store = _build()
    rows = store.documents()
    if not rows:
        print("The knowledge base is empty.")
        return 0
    print(f"{'id':26} {'auth':13} {'prov':5} {'chunks':>6}  title")
    for row in rows:
        mark = " (superseded)" if row["superseded"] else ""
        # Whether the rank is backed by anything, at a glance.
        backed = "yes" if (row.get("provenance") or row.get("source_url")) else "--"
        print(f"{row['document_id']:26} {row['authority']:13} {backed:5} "
              f"{row['chunk_count']:>6}  {row['title'][:58]}{mark}")
    print(f"\n{len(rows)} document(s). `show <id>` for what is indexed.")
    return 0


async def remove(args: argparse.Namespace) -> int:
    _, store = _build()
    if store.delete(args.document_id):
        print(f"Deleted {args.document_id}.")
        return 0
    print(f"No document with id {args.document_id}.")
    return 1


async def supersede(args: argparse.Namespace) -> int:
    _, store = _build()
    if store.mark_superseded(args.document_id, args.by):
        print(f"{args.document_id} marked superseded.")
        return 0
    print(f"No document with id {args.document_id}.")
    return 1


async def reindex(_: argparse.Namespace) -> int:
    ingestor, _store = _build()
    print(f"Re-embedded {await ingestor.reindex()} chunks.")
    return 0


async def status(_: argparse.Namespace) -> int:
    _, store = _build()
    stats = store.stats()
    for key in ("path", "documents", "live_documents", "superseded",
                "official_documents", "chunks", "vector_search",
                "indexed_provider", "indexed_dimension", "ready"):
        print(f"{key:20} {stats.get(key)}")
    if stats.get("by_type"):
        print("by type            ", stats["by_type"])
    if not stats.get("ready"):
        print("\nNothing is indexed yet. The analysis panel will say so rather "
              "than guess.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="index files, folders or URLs")
    p_add.add_argument("sources", nargs="+")
    p_add.add_argument("--official", action="store_true",
                       help="a gazette, Act, Rule or Government Order")
    p_add.add_argument("--departmental", action="store_true",
                       help="a circular, SOP or departmental guideline")
    p_add.add_argument("--external", action="store_true",
                       help="not a government source; ranked lowest and marked")
    p_add.add_argument("--department")
    p_add.add_argument(
        "--provenance",
        help="Where this copy came from and how it was verified — a gazette "
             "citation, a portal URL, or the officer who checked it. REQUIRED "
             "for --official and --departmental unless the file already "
             "carries a source URL or a G.O. number; without it the document "
             "is indexed as 'unknown' and does not outrank anything.")
    p_add.add_argument("--type", choices=DOCUMENT_TYPES)
    p_add.add_argument("--act", help="Act name, if the document does not state it")
    p_add.add_argument("--version")
    p_add.add_argument("--date", help="YYYY-MM-DD")
    p_add.add_argument("--force", action="store_true", help="re-index unchanged files")
    p_add.set_defaults(run=add)

    p_inspect = sub.add_parser(
        "inspect", help="read a document and show its metadata; index nothing")
    p_inspect.add_argument("source")
    p_inspect.set_defaults(run=inspect)

    p_preview = sub.add_parser(
        "preview", help="print the chunks a document would produce")
    p_preview.add_argument("source")
    p_preview.add_argument("--limit", type=int, default=8)
    p_preview.add_argument("--chars", type=int, default=400)
    p_preview.set_defaults(run=preview)

    p_show = sub.add_parser("show", help="what is indexed for one document")
    p_show.add_argument("document_id")
    p_show.add_argument("--limit", type=int, default=6)
    p_show.set_defaults(run=show)

    sub.add_parser("list", help="what is indexed").set_defaults(run=listing)

    p_remove = sub.add_parser("remove", help="delete a document and its chunks")
    p_remove.add_argument("document_id")
    p_remove.set_defaults(run=remove)

    p_sup = sub.add_parser("supersede", help="retire a document without deleting it")
    p_sup.add_argument("document_id")
    p_sup.add_argument("--by", help="id of the document that replaces it")
    p_sup.set_defaults(run=supersede)

    sub.add_parser("reindex", help="re-embed everything after a provider change"
                   ).set_defaults(run=reindex)
    sub.add_parser("status", help="corpus statistics").set_defaults(run=status)

    args = parser.parse_args()
    return asyncio.run(args.run(args))


if __name__ == "__main__":
    raise SystemExit(main())
