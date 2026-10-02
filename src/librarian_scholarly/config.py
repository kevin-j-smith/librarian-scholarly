"""Settings, from the environment (librarian's .env is already loaded)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

ALL_SOURCES = ("openalex", "crossref", "arxiv", "pubmed", "semanticscholar")


def _sources() -> list[str]:
    raw = os.environ.get("SCHOLARLY_SOURCES", "").strip()
    if raw:
        return [s.strip().lower() for s in raw.split(",") if s.strip().lower() in ALL_SOURCES]
    # Semantic Scholar's shared keyless pool answered 429 on its first
    # request when this was written (2026-09-30), so it is on by default
    # only with a key.
    default = ["openalex", "crossref", "arxiv", "pubmed"]
    if os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip():
        default.append("semanticscholar")
    return default


def _float(name: str, default: str) -> float:
    return float(os.environ.get(name, default))


@dataclass
class Settings:
    sources: list = field(default_factory=_sources)
    # An address for the APIs' "polite" pools (OpenAlex, Crossref) and
    # NCBI's `email`. Optional; recommended by all three.
    mailto: str = field(default_factory=lambda: os.environ.get("SCHOLARLY_MAILTO", "").strip())
    openalex_api_key: str = field(default_factory=lambda: os.environ.get("OPENALEX_API_KEY", "").strip())
    semantic_scholar_api_key: str = field(
        default_factory=lambda: os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip())
    ncbi_api_key: str = field(default_factory=lambda: os.environ.get("NCBI_API_KEY", "").strip())
    # Most results asked of one source per search.
    per_source: int = field(default_factory=lambda: int(os.environ.get("SCHOLARLY_PER_SOURCE", "25")))
    timeout_seconds: float = field(default_factory=lambda: _float("SCHOLARLY_TIMEOUT_SECONDS", "30"))
    # A source that refuses (429, 503) is skipped this long, doubling while
    # it keeps refusing, unless it says how long itself (Retry-After).
    cooldown_seconds: float = field(default_factory=lambda: _float("SCHOLARLY_COOLDOWN_SECONDS", "600"))
    # Seconds between two requests to one source: each API's published
    # limit, or under it. Set SCHOLARLY_<SOURCE>_INTERVAL to change one.
    intervals: dict = field(default_factory=lambda: {
        "openalex": _float("SCHOLARLY_OPENALEX_INTERVAL", "1.0"),
        "crossref": _float("SCHOLARLY_CROSSREF_INTERVAL", "1.0"),
        "arxiv": _float("SCHOLARLY_ARXIV_INTERVAL", "3.0"),
        "pubmed": _float("SCHOLARLY_PUBMED_INTERVAL", "0.4"),
        "semanticscholar": _float("SCHOLARLY_SEMANTICSCHOLAR_INTERVAL", "1.1"),
    })


settings = Settings()
