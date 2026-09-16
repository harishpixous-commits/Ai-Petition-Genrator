"""The government knowledge layer.

Retrieval over indexed government documents, reported with citations, and the
refusal sentence when nothing can be cited. Advisory throughout: it never writes
a word of the petition and the petition is produced whether it answers or not.

    ingest    documents and URLs into the corpus
    retrieve  hybrid lexical + vector search over it
    analyst   a bounded agent, then a grounding check that drops inventions
    capability the seam it attaches to, and the once-per-grievance cache

See `docs/knowledge-layer-decision.md` for why it is shaped this way.
"""

from .schema import UNVERIFIED, UNVERIFIED_TA, Chunk, Finding, PetitionAnalysis, Source

__all__ = [
    "UNVERIFIED",
    "UNVERIFIED_TA",
    "Chunk",
    "Finding",
    "PetitionAnalysis",
    "Source",
]
