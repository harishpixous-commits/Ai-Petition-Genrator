"""Reach-check the official source URLs in `corpus/source_registry.yaml`.

WHAT THIS SCRIPT IS, said precisely so a reader of the production log knows.

  * It is a REACHABILITY probe for the catalogue of URLs the brief asked us
    to maintain. HEAD or small-range GET only, polite rate, one request at
    a time, service User-Agent header. The output is a per-source status
    row the curator reads to decide what to re-ingest.

  * It is NOT a crawler. It does not follow links, it does not download
    PDFs, it does not parse index pages. Each of the thirty-plus portals
    has its own JS, encoded parameters, pagination and session handling,
    and automating a bulk fetch across them belongs on the production host
    with per-site code — not in a single discovery pass.

  * It is NOT an ingester. A URL that answers 200 from here is NOT the
    same as a document approved for the corpus. Nothing from this script
    enters `tamil_nadu.yaml` or `var/knowledge.sqlite` without a human
    curator's read of the actual document and a decision on its
    instrument type and legal status.

  * It REFUSES to touch anything marked `access: discovery_only` or
    `tier: tier_6_discovery`. Wikipedia and other discovery sources are
    cross-reference material; the brief forbids citing them.

  * It respects robots.txt on polite sources before issuing any request.

Usage:

    python scripts/discover.py list                   show the catalogue
    python scripts/discover.py check                  HEAD-check every polite
                                                      source, write a report
    python scripts/discover.py check --source <id>    one source
    python scripts/discover.py check --tier tier_1_gazette
    python scripts/discover.py check --dry-run        no network, just report
                                                      which URLs would be hit

Output lives in `var/reports/discovery-<utc-timestamp>.json`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
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

from app.knowledge.source_registry import Registry, Source, registry

#: The service introduces itself. Government portals that log User-Agent
#: can tell this is us, which address to reach, and that it is a reachability
#: probe. Changing this to pretend to be a browser is dishonest and worse —
#: it opts the service out of a conversation with the portal operator about
#: what rate we may use.
USER_AGENT = (
    "CitizenPetitionAssistant/1.0 "
    "(reachability probe; +https://ai-petition.pixoustech.app/)"
)

#: Seconds between polite requests to the SAME host. 3 s on a government
#: portal is well below any sustained rate a real user generates and well
#: above anything a scrape would be happy with.
POLITE_INTERVAL_SECONDS = 3.0

#: Per-request timeout. A government PDF behind an index page can take a
#: long moment on the first byte. Six seconds is enough for the HEAD check,
#: not enough to let a slow endpoint hold the probe open.
REQUEST_TIMEOUT_SECONDS = 6.0


def _write_report(result: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"discovery-{stamp}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    return path


def _filter(reg: Registry, *, source_id: str | None,
            tier: str | None) -> tuple[Source, ...]:
    sources = reg.sources
    if source_id:
        sources = tuple(s for s in sources if s.id == source_id)
    if tier:
        sources = tuple(s for s in sources if s.tier == tier)
    return sources


def _robots_allow(url: str, user_agent: str) -> tuple[bool, str]:
    """May we hit this URL under this UA?

    Reads /robots.txt for the host, polite_only. A fetch failure (no robots,
    unreachable, parse error) is treated as "allowed" — which matches the
    standard interpretation of a missing file. The reason string is kept so
    the report says why a source was skipped.
    """
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False, "malformed url"
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    reader = urllib.robotparser.RobotFileParser()
    reader.set_url(robots_url)
    try:
        reader.read()
    except Exception as exc:  # noqa: BLE001
        return True, f"robots unavailable ({type(exc).__name__})"
    if reader.can_fetch(user_agent, url):
        return True, "robots: allowed"
    return False, "robots: disallowed"


async def _check_one(client: httpx.AsyncClient, source: Source) -> dict:
    """One source, one HEAD + metadata snapshot."""
    row: dict = {
        "id": source.id, "name": source.name, "url": source.url,
        "tier": source.tier, "kind": source.kind, "access": source.access,
    }
    allowed, reason = _robots_allow(source.url, USER_AGENT)
    row["robots"] = reason
    if not allowed:
        row["status"] = "skipped"
        return row
    started = time.perf_counter()
    try:
        response = await client.head(source.url, follow_redirects=True)
        if response.status_code == 405:
            # Some servers refuse HEAD. Fall back to a bounded GET.
            response = await client.get(
                source.url, follow_redirects=True,
                headers={"Range": "bytes=0-1023"})
    except Exception as exc:  # noqa: BLE001
        row["status"] = "unreachable"
        row["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        row["ms"] = round((time.perf_counter() - started) * 1000)
        return row
    row["http_status"] = response.status_code
    row["content_type"] = response.headers.get("content-type", "")
    row["final_url"] = str(response.url)
    row["ms"] = round((time.perf_counter() - started) * 1000)
    row["status"] = "ok" if 200 <= response.status_code < 400 else "error"
    return row


async def _check_all(sources: tuple[Source, ...], *, dry_run: bool) -> list[dict]:
    """Walk the sources once, per host, with polite spacing."""
    rows: list[dict] = []
    if dry_run:
        for source in sources:
            rows.append({
                "id": source.id, "url": source.url, "tier": source.tier,
                "access": source.access, "status": "dry-run",
            })
        return rows

    last_hit: dict[str, float] = {}
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
    ) as client:
        for source in sources:
            if source.access == "discovery_only":
                rows.append({
                    "id": source.id, "url": source.url,
                    "tier": source.tier, "access": source.access,
                    "status": "skipped",
                    "reason": "discovery_only — brief forbids crawling",
                })
                continue
            host = urlparse(source.url).netloc
            previous = last_hit.get(host, 0.0)
            wait = POLITE_INTERVAL_SECONDS - (time.monotonic() - previous)
            if wait > 0:
                await asyncio.sleep(wait)
            row = await _check_one(client, source)
            rows.append(row)
            last_hit[host] = time.monotonic()
    return rows


def _print_list(reg: Registry) -> int:
    print(f"source registry — {len(reg.sources)} entries, "
          f"compiled {reg.compiled_on}\n")
    for tier_id in sorted(reg.tiers, key=lambda t: reg.tiers[t].priority):
        tier = reg.tiers[tier_id]
        print(f"[{tier.priority}] {tier.name}")
        for source in reg.by_tier(tier_id):
            flag = " (DISCOVERY ONLY)" if source.access == "discovery_only" else ""
            print(f"  {source.id:<32} {source.kind:<10} {source.url}{flag}")
        print()
    return 0


def _print_summary(rows: list[dict]) -> None:
    buckets: dict[str, int] = {}
    for row in rows:
        buckets[row["status"]] = buckets.get(row["status"], 0) + 1
    print("summary:",
          ", ".join(f"{status}={count}" for status, count in sorted(buckets.items())))
    for row in rows:
        if row["status"] not in ("ok", "dry-run", "skipped"):
            print(f"  ! {row['id']:<32} {row['status']} "
                  f"{row.get('error') or row.get('http_status') or ''}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="print the registered sources")
    check = sub.add_parser("check", help="reach-check a slice of the registry")
    check.add_argument("--source", help="limit to one source id")
    check.add_argument("--tier", help="limit to one tier")
    check.add_argument("--dry-run", action="store_true",
                       help="skip the network, just report which URLs would be hit")
    check.add_argument("--out",
                       default="var/reports",
                       help="report destination directory")
    args = parser.parse_args(argv)

    reg = registry()
    if args.command == "list":
        return _print_list(reg)

    sources = _filter(reg, source_id=args.source, tier=args.tier)
    if not sources:
        print("no sources matched the filter", file=sys.stderr)
        return 2
    rows = asyncio.run(_check_all(sources, dry_run=args.dry_run))
    result = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "user_agent": USER_AGENT,
        "polite_interval_seconds": POLITE_INTERVAL_SECONDS,
        "dry_run": bool(args.dry_run),
        "rows": rows,
    }
    path = _write_report(result, Path(args.out))
    print(f"\nreport: {path}")
    _print_summary(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
