"""Measure retrieval on the real corpus: lexical, dense and hybrid, side by side.

    python -m benchmarks.run_retrieval_eval
    python -m benchmarks.run_retrieval_eval --json var/reports/retrieval.json

WHY THREE MODES. Hybrid retrieval is FTS5 (BM25) plus dense vectors, fused by
reciprocal rank. Reporting only the fused number hides which half is doing the
work — and for a Tamil query against an English corpus the lexical half can
contribute almost nothing, which is precisely the failure that matters and the
one an aggregate conceals.

DOCUMENT-LEVEL, deliberately. The question an officer needs answered is "did
the right instrument come back", and several chunks of one Act are one
answer, not several. Chunks are collapsed to their document, in rank order.

    Recall@k   the share of queries with a gold document in the top k
    MRR        mean of 1/rank of the first gold document (0 when absent)

NEEDS the real corpus (`var/knowledge.sqlite`) and, for the dense and hybrid
columns, a configured semantic embedder. Without one, those columns are
reported as not run — never as zero, which would read as a measurement.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from app.config import get_settings  # noqa: E402
from app.knowledge import embeddings as embedding_providers  # noqa: E402
from app.knowledge.legal_status import manifest_ids_by_url  # noqa: E402
from app.knowledge.retrieve import Retriever, keywords  # noqa: E402
from app.knowledge.store import KnowledgeStore  # noqa: E402
from benchmarks.retrieval_cases import OUT_OF_CORPUS, Query, dataset  # noqa: E402

KS = (1, 3, 5)
DEPTH = 20


def documents_in_order(chunks, url_to_id: dict[str, str]) -> list[str]:
    """Chunks collapsed to manifest ids, first appearance first."""
    out: list[str] = []
    for chunk in chunks:
        manifest_id = url_to_id.get(str(chunk.source_url or ""), "")
        key = manifest_id or f"?{chunk.document_id}"
        if key not in out:
            out.append(key)
    return out


def score(ranked: list[str], expected: frozenset[str]) -> dict[str, float]:
    first = next((i for i, d in enumerate(ranked, 1) if d in expected), None)
    out = {f"r@{k}": 1.0 if first is not None and first <= k else 0.0 for k in KS}
    out["rr"] = 1.0 / first if first else 0.0
    return out


async def run() -> dict:
    settings = get_settings()
    provider = embedding_providers.build(settings)
    store = KnowledgeStore(settings.knowledge_path, dimension=provider.dimension,
                           provider=provider.name)
    retriever = Retriever(store, provider, settings)
    url_to_id = manifest_ids_by_url()
    semantic = bool(getattr(provider, "semantic", False))

    modes = ["lexical"] + (["dense", "hybrid"] if semantic else [])
    rows: list[dict] = []

    async def one(query: Query) -> dict:
        row = {"query": query.text, "language": query.language,
               "intent": query.intent, "expected": sorted(query.expected)}

        started = time.perf_counter()
        lexical = store.lexical(" ".join(keywords(query.text)), limit=DEPTH)
        row["lexical"] = {"ms": (time.perf_counter() - started) * 1000,
                          "ranked": documents_in_order(lexical, url_to_id)}

        if semantic:
            started = time.perf_counter()
            try:
                vector = (await provider.embed([query.text]))[0]
                dense = store.vector(vector, limit=DEPTH)
                row["dense"] = {"ms": (time.perf_counter() - started) * 1000,
                                "ranked": documents_in_order(dense, url_to_id)}
            except Exception as exc:  # noqa: BLE001
                row["dense"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}

            started = time.perf_counter()
            found = await retriever.search(query.text, limit=DEPTH)
            row["hybrid"] = {"ms": (time.perf_counter() - started) * 1000,
                             "ranked": documents_in_order(found.chunks, url_to_id)}

        for mode in modes:
            if "ranked" in row.get(mode, {}):
                row[mode].update(score(row[mode]["ranked"], query.expected))
        return row

    for query in dataset():
        rows.append(await one(query))

    outside = []
    for query in OUT_OF_CORPUS:
        found = await retriever.search(query.text, limit=5)
        outside.append({"query": query.text,
                        "top": documents_in_order(found.chunks, url_to_id)[:3],
                        "top_score": round(found.chunks[0].score, 5) if found.chunks else None})

    return {"modes": modes, "rows": rows, "out_of_corpus": outside,
            "semantic": semantic, "embedder": getattr(provider, "model", provider.name)}


def summarise(result: dict) -> dict:
    table: dict[str, dict[str, dict[str, float]]] = {}
    for mode in result["modes"]:
        groups: dict[str, list[dict]] = defaultdict(list)
        for row in result["rows"]:
            cell = row.get(mode, {})
            if "rr" not in cell:
                continue
            groups[row["language"]].append(cell)
            groups["ALL"].append(cell)
        table[mode] = {
            language: {
                **{f"r@{k}": statistics.mean(c[f"r@{k}"] for c in cells) for k in KS},
                "mrr": statistics.mean(c["rr"] for c in cells),
                "n": len(cells),
                "ms_median": statistics.median(c["ms"] for c in cells),
            }
            for language, cells in groups.items()
        }
    return table


def render(result: dict, table: dict) -> str:
    out = [f"embedder: {result['embedder']}  (semantic={result['semantic']})", ""]
    languages = ["ALL", "en", "ta", "ml", "te", "hi"]
    for mode in result["modes"]:
        out.append(f"== {mode.upper()} ==")
        out.append(f"  {'lang':<5} {'n':>3} {'R@1':>6} {'R@3':>6} {'R@5':>6} "
                   f"{'MRR':>6} {'ms':>8}")
        for language in languages:
            cell = table[mode].get(language)
            if not cell:
                continue
            out.append(f"  {language:<5} {cell['n']:>3} {cell['r@1']:>6.3f} "
                       f"{cell['r@3']:>6.3f} {cell['r@5']:>6.3f} {cell['mrr']:>6.3f} "
                       f"{cell['ms_median']:>8.1f}")
        out.append("")
    if not result["semantic"]:
        out.append("dense and hybrid: NOT RUN — no semantic embedder configured.")
    misses = [r for r in result["rows"]
              if result["semantic"] and r.get("hybrid", {}).get("r@5") == 0.0]
    if misses:
        out.append("hybrid misses at k=5:")
        for row in misses:
            out.append(f"  [{row['language']}] {row['intent']:<18} got "
                       f"{row['hybrid']['ranked'][:3]}")
    out.append("")
    out.append("out of corpus (must lead to a refusal downstream, not a miss):")
    for row in result["out_of_corpus"]:
        out.append(f"  {row['query'][:44]:<44} top={row['top'][:2]} "
                   f"score={row['top_score']}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    result = asyncio.run(run())
    table = summarise(result)
    print(render(result, table))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({"summary": table, **result}, indent=2,
                                        ensure_ascii=False, default=str),
                             encoding="utf-8")
        print(f"\nwritten to {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
