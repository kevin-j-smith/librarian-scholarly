"""One search function per API. Each returns SearchResults in the API's own
relevance order, with the link most likely to be readable: an open-access
copy where the API knows one, else the DOI, else the API's own page."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional

from librarian.research.providers import SearchResult

from . import http
from .config import settings

_TAG = re.compile(r"<[^>]+>")
_SNIPPET_CHARS = 600


def _clean(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", _TAG.sub(" ", text or "")).strip()


def _snippet(year, venue, abstract) -> str:
    head = " · ".join(str(x) for x in (year, venue) if x)
    body = _clean(abstract)[:_SNIPPET_CHARS]
    return f"{head} — {body}" if head and body else (head or body)


def _result(url: str, title: str, snippet: str) -> SearchResult:
    return SearchResult(url=url, title=_clean(title) or url, snippet=snippet, kind="science")


# ─── OpenAlex ──────────────────────────────────────────────────────────────

def _abstract(inverted: Optional[dict]) -> str:
    """OpenAlex stores abstracts as {word: [positions]}."""
    if not inverted:
        return ""
    words = sorted((pos, word) for word, positions in inverted.items() for pos in positions)
    return " ".join(word for _, word in words)


def openalex(query: str, count: int, cache=None) -> list[SearchResult]:
    params = {"search": query, "per-page": min(count, 50),
              "select": "id,doi,display_name,publication_year,primary_location,best_oa_location,"
                        "abstract_inverted_index"}
    if settings.mailto:
        params["mailto"] = settings.mailto
    secret = dict(params)
    if settings.openalex_api_key:
        secret["api_key"] = settings.openalex_api_key
    data = http.get("openalex", "https://api.openalex.org/works", secret, cache=cache, cache_params=params)
    out = []
    for w in data.get("results", []):
        oa = w.get("best_oa_location") or {}
        primary = w.get("primary_location") or {}
        url = oa.get("pdf_url") or oa.get("landing_page_url") or w.get("doi") or w.get("id")
        venue = ((primary.get("source") or {}).get("display_name"))
        if url:
            out.append(_result(url, w.get("display_name") or "",
                               _snippet(w.get("publication_year"), venue,
                                        _abstract(w.get("abstract_inverted_index")))))
    return out


# ─── Crossref ──────────────────────────────────────────────────────────────

def crossref(query: str, count: int, cache=None) -> list[SearchResult]:
    params = {"query": query, "rows": min(count, 50),
              "select": "DOI,title,URL,published,container-title,abstract,type"}
    if settings.mailto:
        params["mailto"] = settings.mailto
    data = http.get("crossref", "https://api.crossref.org/works", params, cache=cache)
    out = []
    for item in (data.get("message") or {}).get("items", []):
        title = (item.get("title") or [""])[0]
        doi = item.get("DOI")
        url = f"https://doi.org/{doi}" if doi else item.get("URL")
        year = (((item.get("published") or {}).get("date-parts") or [[None]])[0] or [None])[0]
        venue = (item.get("container-title") or [None])[0]
        if url and title:
            out.append(_result(url, title, _snippet(year, venue, item.get("abstract"))))
    return out


# ─── arXiv ─────────────────────────────────────────────────────────────────

_ATOM = {"a": "http://www.w3.org/2005/Atom"}


def _arxiv_query(query: str) -> str:
    # Every word in any field: arXiv's own search treats a bare phrase as
    # one field match and misses most papers.
    words = [w for w in re.findall(r"[\w-]+", query) if len(w) > 1]
    return " AND ".join(f"all:{w}" for w in words) or f"all:{query}"


def arxiv(query: str, count: int, cache=None) -> list[SearchResult]:
    params = {"search_query": _arxiv_query(query), "start": 0, "max_results": min(count, 50),
              "sortBy": "relevance"}
    data = http.get("arxiv", "https://export.arxiv.org/api/query", params, as_text=True, cache=cache)
    root = ET.fromstring(data["text"])
    out = []
    for entry in root.findall("a:entry", _ATOM):
        abs_url = (entry.findtext("a:id", default="", namespaces=_ATOM) or "").strip()
        abs_url = re.sub(r"^http://", "https://", abs_url)
        abs_url = re.sub(r"v\d+$", "", abs_url)
        year = (entry.findtext("a:published", default="", namespaces=_ATOM) or "")[:4]
        if abs_url:
            out.append(_result(abs_url, entry.findtext("a:title", default="", namespaces=_ATOM),
                               _snippet(year, "arXiv",
                                        entry.findtext("a:summary", default="", namespaces=_ATOM))))
    return out


# ─── PubMed (NCBI E-utilities) ─────────────────────────────────────────────

def _ncbi_params(extra: dict) -> tuple[dict, dict]:
    params = {"tool": "librarian-scholarly", **extra}
    if settings.mailto:
        params["email"] = settings.mailto
    secret = dict(params)
    if settings.ncbi_api_key:
        secret["api_key"] = settings.ncbi_api_key
    return secret, params


def pubmed(query: str, count: int, cache=None) -> list[SearchResult]:
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    secret, params = _ncbi_params({"db": "pubmed", "term": query, "retmax": min(count, 50),
                                   "retmode": "json", "sort": "relevance"})
    ids = (http.get("pubmed", f"{base}/esearch.fcgi", secret, cache=cache, cache_params=params)
           .get("esearchresult") or {}).get("idlist") or []
    if not ids:
        return []
    secret, params = _ncbi_params({"db": "pubmed", "id": ",".join(ids), "retmode": "json"})
    summary = http.get("pubmed", f"{base}/esummary.fcgi", secret, cache=cache,
                       cache_params=params).get("result") or {}
    out = []
    for pmid in ids:
        doc = summary.get(pmid) or {}
        pmc = next((a["value"] for a in doc.get("articleids", []) if a.get("idtype") == "pmc"), None)
        # A PubMed Central copy is the full text, open; PubMed itself is the abstract.
        url = (f"https://pmc.ncbi.nlm.nih.gov/articles/{pmc}/" if pmc
               else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
        authors = ", ".join(a.get("name", "") for a in (doc.get("authors") or [])[:3])
        if doc.get("title"):
            out.append(_result(url, doc["title"], _snippet((doc.get("pubdate") or "")[:4],
                                                           doc.get("source"), authors)))
    return out


# ─── Semantic Scholar ──────────────────────────────────────────────────────

def semanticscholar(query: str, count: int, cache=None) -> list[SearchResult]:
    params = {"query": query, "limit": min(count, 50),
              "fields": "title,abstract,url,externalIds,year,venue,openAccessPdf"}
    headers = {"x-api-key": settings.semantic_scholar_api_key} if settings.semantic_scholar_api_key else None
    data = http.get("semanticscholar", "https://api.semanticscholar.org/graph/v1/paper/search", params,
                    headers=headers, cache=cache)
    out = []
    for p in data.get("data") or []:
        ids = p.get("externalIds") or {}
        url = ((p.get("openAccessPdf") or {}).get("url")
               or (f"https://arxiv.org/abs/{ids['ArXiv']}" if ids.get("ArXiv") else None)
               or (f"https://doi.org/{ids['DOI']}" if ids.get("DOI") else None)
               or p.get("url"))
        if url and p.get("title"):
            out.append(_result(url, p["title"], _snippet(p.get("year"), p.get("venue"), p.get("abstract"))))
    return out


SOURCES = {"openalex": openalex, "crossref": crossref, "arxiv": arxiv, "pubmed": pubmed,
           "semanticscholar": semanticscholar}
