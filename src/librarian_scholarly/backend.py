"""`ScholarlyBackend`: librarian's search-backend interface over the
scholarly APIs. Registered under the `librarian.search_backends` entry point
as "scholarly"; it answers the `science` category only, so it is meant to be
routed beside a web backend:

    RESEARCH_SEARCH_ROUTES="web: searxng; video: searxng; science: scholarly, searxng"

A search asks each enabled source in turn (each paced to its own limit),
interleaves their results in each source's own order, and drops repeats of
one paper by DOI, arXiv id, or title. Ranking, the topical gate, and the caps are
librarian's (research/gather.py), as for every backend. A source that fails
or is cooling down is reported as degraded; the others still answer.
"""
from __future__ import annotations

import logging
import re
from contextlib import nullcontext
from typing import Optional

from librarian.research.backends import BACKEND_API_VERSION, SearchResponse
from librarian.research.providers import document_key
from librarian.research.search_cache import CachePolicy

from . import http
from .config import settings
from .sources import SOURCES

logger = logging.getLogger("librarian_scholarly")


def _title_key(title: str) -> str:
    words = re.findall(r"\w+", (title or "").casefold())
    # Short titles ("Introduction", "Editorial") name many papers.
    return "title:" + " ".join(words) if len(words) >= 4 else ""


class ScholarlyBackend:
    name = "scholarly"
    api_version = BACKEND_API_VERSION
    categories = frozenset({"science"})

    def __init__(self, sources: Optional[list[str]] = None):
        self.sources = [s for s in (sources or settings.sources) if s in SOURCES]

    def search(self, query: str, count: int, category: str = "science", *,
               cache: Optional[CachePolicy] = None) -> SearchResponse:
        if category not in self.categories:
            raise ValueError(f"scholarly backend has no category {category!r}")
        per_source = max(1, min(count, settings.per_source))
        lists, degraded = [], []
        for name in self.sources:
            try:
                lists.append(SOURCES[name](query, per_source, cache=cache))
            except http.SourceUnavailable as e:
                degraded.append((name, str(e)))
            except Exception as e:      # noqa: BLE001 - one API's failure narrows the pool
                logger.warning("scholarly source %s failed for %r: %s", name, query, e)
                degraded.append((name, f"failed: {e}"[:200]))
        merged, seen = [], set()
        for rank in range(max((len(r) for r in lists), default=0)):
            for results in lists:
                if rank < len(results):
                    r = results[rank]
                    # One paper reaches here as an open-access landing page
                    # from one API and a DOI from another, two different
                    # URLs; its title is the same. Measured live: 2 of a
                    # topic's top 5 were repeats by title.
                    keys = {document_key(r.url), _title_key(r.title)} - {""}
                    if not keys & seen:
                        seen |= keys
                        merged.append(r)
        return SearchResponse(merged[:count], degraded)

    def session(self):
        return nullcontext(self)

    def diagnose(self, category: str = "science") -> dict:
        """Sources cooling down after refusing. Makes no request."""
        refusing = [(name, f"cooling down ({left:.0f}s left)") for name in self.sources
                    if (left := http.cooling(name))]
        return {"refusing": refusing, "silent": []}
