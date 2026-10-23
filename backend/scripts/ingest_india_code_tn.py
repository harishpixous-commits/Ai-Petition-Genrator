"""Discover Tamil Nadu Acts from India Code into the quarantine store.

Phase 2.1 scope — ONE source only, as the brief insists. The India Code
Tamil Nadu collection at `/handle/123456789/2507` is a DSpace handle page
that lists items; this script reads that listing, visits each item's
metadata page, parses the record and stages a row in `var/quarantine.sqlite`
with `verification_status = 'discovered'`.

NOTHING FROM HERE REACHES THE CORPUS, the analyst, retrieval, the officer
page's recommendations or the compose node. A curator must open each row
in the review screen (SRS §8.2 quarantine/review queue) and press approve
before the row becomes a citable source. The `/api/officer/curator/*`
endpoints and the officer-portal review tab are where that happens.

Usage:

    python scripts/ingest_india_code_tn.py discover
    python scripts/ingest_india_code_tn.py discover --limit 25
    python scripts/ingest_india_code_tn.py discover --dry-run
    python scripts/ingest_india_code_tn.py fetch-pdfs
    python scripts/ingest_india_code_tn.py stats

Respects robots.txt. Introduces itself as the service's own User-Agent.
Waits 3 s between hits to the same host. Caps a run at 100 items unless
`--limit` says otherwise — one unattended run must not try to drain the
whole collection.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import urllib.robotparser
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

import httpx

from app.knowledge import india_code, quarantine
from app.knowledge.source_registry import registry

SOURCE_ID = "indiacode-tn"
DEFAULT_LIMIT = 100
USER_AGENT = (
    "CitizenPetitionAssistant/1.0 "
    "(legal discovery; +https://ai-petition.pixoustech.app/)"
)
POLITE_INTERVAL_SECONDS = 3.0
REQUEST_TIMEOUT_SECONDS = 45.0


def _source() -> object:
    """The registry entry for India Code TN. The brief forbids running
    this against a discovery_only source; `is_citable` enforces that."""
    source = registry().source(SOURCE_ID)
    if source is None:
        raise SystemExit(f"source {SOURCE_ID!r} is not in the registry")
    if not source.is_citable:
        raise SystemExit(
            f"source {SOURCE_ID!r} is non-citable "
            f"({source.tier}/{source.access}); discovery refused")
    return source


def _robots(url: str) -> bool:
    """Does robots.txt allow this URL under our UA?"""
    parsed = urlparse(url)
    reader = urllib.robotparser.RobotFileParser()
    reader.set_url(f"{parsed.scheme}://{parsed.netloc}/robots.txt")
    try:
        reader.read()
    except Exception:  # noqa: BLE001
        return True   # standard: a missing robots.txt is allow-all
    return reader.can_fetch(USER_AGENT, url)


async def _polite_get(client: httpx.AsyncClient, url: str,
                      last_hit: dict[str, float]) -> httpx.Response | None:
    host = urlparse(url).netloc
    wait = POLITE_INTERVAL_SECONDS - (time.monotonic() - last_hit.get(host, 0.0))
    if wait > 0:
        await asyncio.sleep(wait)
    try:
        response = await client.get(url, follow_redirects=True)
    except Exception as exc:  # noqa: BLE001
        print(f"  unreachable {url}  {type(exc).__name__}: {str(exc)[:120]}",
              file=sys.stderr)
        return None
    finally:
        last_hit[host] = time.monotonic()
    return response


async def _discover(limit: int, *, dry_run: bool) -> dict:
    source = _source()
    if not _robots(source.url):
        return {"status": "robots_disallowed", "source": source.url}
    if dry_run:
        return {"status": "dry_run", "source": source.url,
                "limit": limit, "would_fetch": source.url}

    discovered: list[dict] = []
    skipped: list[dict] = []
    errors: list[dict] = []
    last_hit: dict[str, float] = {}
    seen_ids: set[str] = set()

    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"},
    ) as client:
        # Step 1: the collection listing.
        listing_response = await _polite_get(client, source.url, last_hit)
        if listing_response is None:
            return {"status": "unreachable", "source": source.url,
                    "generated_at": datetime.now(UTC).isoformat(timespec="seconds")}
        if listing_response.status_code >= 400:
            print(f"  collection listing status {listing_response.status_code}",
                  file=sys.stderr)
            return {"status": "unreachable", "source": source.url,
                    "http_status": listing_response.status_code,
                    "generated_at": datetime.now(UTC).isoformat(timespec="seconds")}

        item_urls = india_code.parse_collection_listing(
            listing_response.text, base_url=source.url)
        print(f"  listing names {len(item_urls)} items", file=sys.stderr)

        # Step 2: each item page, up to `limit`.
        for item_url in item_urls[:limit]:
            if item_url in seen_ids:
                continue
            seen_ids.add(item_url)
            response = await _polite_get(client, item_url, last_hit)
            if response is None:
                errors.append({"url": item_url, "reason": "network error"})
                continue
            if response.status_code >= 400:
                errors.append({"url": item_url, "http_status": response.status_code})
                continue
            try:
                discovery = india_code.parse_item_page(response.text, item_url)
            except india_code.ParseError as exc:
                errors.append({"url": item_url, "reason": str(exc)})
                continue
            row_id = quarantine.record(discovery)
            discovered.append({"id": row_id, "url": item_url,
                               "title": discovery.title,
                               "act_number": discovery.act_number})

    return {
        "status": "ok",
        "source": source.url,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "discovered": discovered,
        "skipped": skipped,
        "errors": errors,
    }


async def _fetch_pdfs(limit: int) -> dict:
    """Fetch the PDF for every quarantine row still in `discovered` state.

    Writes the bytes to var/quarantine/pdfs/<sha256>.pdf and stamps the row
    with the hash + `pdf_fetched` status. If the PDF URL times out or
    returns 4xx/5xx, the row flips to `unreachable` with the http status
    recorded; the curator can decide whether to retry later or reject.
    """
    pending = [row for row in quarantine.pending()
               if row["verification_status"] == "discovered"
               and row["pdf_url"]][:limit]
    if not pending:
        return {"status": "nothing_to_do", "pending": 0}

    fetched = 0
    failed = 0
    last_hit: dict[str, float] = {}
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*"},
    ) as client:
        for row in pending:
            if not _robots(row["pdf_url"]):
                quarantine.set_status(row["id"], "unreachable")
                failed += 1
                continue
            response = await _polite_get(client, row["pdf_url"], last_hit)
            if response is None or response.status_code >= 400:
                quarantine.set_status(row["id"], "unreachable")
                failed += 1
                continue
            if "pdf" not in (response.headers.get("content-type", "")).lower():
                # A government portal sometimes returns HTML with a 200 when
                # the PDF has been moved. The hash would be meaningless.
                quarantine.set_status(row["id"], "unreachable")
                failed += 1
                continue
            sha256 = quarantine.hash_bytes(response.content)
            quarantine.pdf_destination(sha256).write_bytes(response.content)
            quarantine.set_status(row["id"], "pdf_fetched", pdf_sha256=sha256)
            fetched += 1
    return {"status": "ok", "fetched": fetched, "failed": failed,
            "pending": len(pending)}


def _stats() -> dict:
    buckets: dict[str, int] = {}
    for row in quarantine.all_rows():
        buckets[row["verification_status"]] = buckets.get(
            row["verification_status"], 0) + 1
    return {"by_status": buckets, "total": sum(buckets.values())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    discover = sub.add_parser("discover")
    discover.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                          help="cap on items fetched this run")
    discover.add_argument("--dry-run", action="store_true",
                          help="skip the network entirely")

    fetch = sub.add_parser("fetch-pdfs")
    fetch.add_argument("--limit", type=int, default=50)

    sub.add_parser("stats")
    args = parser.parse_args(argv)

    if args.command == "discover":
        result = asyncio.run(_discover(args.limit, dry_run=args.dry_run))
    elif args.command == "fetch-pdfs":
        result = asyncio.run(_fetch_pdfs(args.limit))
    elif args.command == "stats":
        result = _stats()
    else:  # pragma: no cover
        parser.error(f"unknown command {args.command!r}")

    import json
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
