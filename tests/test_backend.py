"""The scholarly backend: each API's reply turned into results, the merge,
pacing, cooldowns, and caching. Replies are shaped like the real ones
recorded on 2026-09-30."""
import json
import time

import httpx
import pytest

from librarian_scholarly import http, sources
from librarian_scholarly.backend import ScholarlyBackend
from librarian_scholarly.config import settings

OPENALEX = {"results": [
    {"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1145/1148170.1148222",
     "display_name": "Finding near-duplicate web pages", "publication_year": 2006,
     "primary_location": {"source": {"display_name": "SIGIR"}},
     "best_oa_location": {"landing_page_url": "http://infoscience.epfl.ch/record/99373", "pdf_url": None},
     "abstract_inverted_index": {"Near-duplicate": [0], "pages": [1], "abound": [2]}},
    {"id": "https://openalex.org/W2", "doi": "https://doi.org/10.1000/xyz123", "display_name": "Paywalled",
     "publication_year": 2020, "primary_location": None, "best_oa_location": None,
     "abstract_inverted_index": None}]}
CROSSREF = {"message": {"items": [
    {"DOI": "10.1000/xyz123", "title": ["Paywalled"], "URL": "https://doi.org/10.1000/xyz123",
     "published": {"date-parts": [[2020]]}, "container-title": ["J"], "abstract": "<jats:p>Text</jats:p>"},
    {"DOI": "10.2139/ssrn.4032279", "title": ["Seed Selection Based Web Crawler"],
     "published": {"date-parts": [[2022]]}, "container-title": [], "abstract": None}]}}
ARXIV = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><id>http://arxiv.org/abs/1305.2686v1</id><published>2013-05-13T00:00:00Z</published>
    <title>Using Exclusive Web Crawlers</title><summary>  Crawlers  revisit pages. </summary></entry>
</feed>"""
ESEARCH = {"esearchresult": {"idlist": ["42808675", "42805352"]}}
ESUMMARY = {"result": {"uids": ["42808675", "42805352"],
                       "42808675": {"title": "Sleep and memory", "source": "Nature", "pubdate": "2026 Sep",
                                    "authors": [{"name": "Doe J"}],
                                    "articleids": [{"idtype": "pmc", "value": "PMC1234567"}]},
                       "42805352": {"title": "Another", "source": "Cell", "pubdate": "2025",
                                    "authors": [], "articleids": []}}}
S2 = {"data": [{"title": "Change rate estimation", "abstract": "We estimate.", "year": 2003, "venue": "TOIT",
                "url": "https://www.semanticscholar.org/paper/abc",
                "externalIds": {"ArXiv": "cs/0301001", "DOI": "10.1145/857166.857170"},
                "openAccessPdf": None}]}


class Reply:
    def __init__(self, status=200, body=None, text=None, headers=None):
        self.status_code, self._body, self.text = status, body, text if text is not None else json.dumps(body)
        self.headers = httpx.Headers(headers or {})

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)


@pytest.fixture
def served(monkeypatch):
    calls = []
    routes = {"api.openalex.org": Reply(body=OPENALEX), "api.crossref.org": Reply(body=CROSSREF),
              "export.arxiv.org": Reply(text=ARXIV),
              "esearch.fcgi": Reply(body=ESEARCH), "esummary.fcgi": Reply(body=ESUMMARY),
              "api.semanticscholar.org": Reply(body=S2)}

    def get(url, params=None, headers=None, timeout=None, follow_redirects=None):
        calls.append({"url": url, "params": params, "headers": headers})
        return next(r for key, r in routes.items() if key in url)
    monkeypatch.setattr(httpx, "get", get)
    return calls, routes


def test_each_source_picks_the_readable_link(served):
    oa = sources.openalex("q", 5)
    assert oa[0].url == "http://infoscience.epfl.ch/record/99373"        # the open copy
    assert oa[0].snippet == "2006 · SIGIR — Near-duplicate pages abound" and oa[0].kind == "science"
    assert oa[1].url == "https://doi.org/10.1000/xyz123"
    cr = sources.crossref("q", 5)
    assert cr[0].snippet == "2020 · J — Text" and cr[1].url == "https://doi.org/10.2139/ssrn.4032279"
    ax = sources.arxiv("web crawler", 5)
    assert ax[0].url == "https://arxiv.org/abs/1305.2686" and ax[0].snippet == "2013 · arXiv — Crawlers revisit pages."
    pm = sources.pubmed("sleep", 5)
    assert [r.url for r in pm] == ["https://pmc.ncbi.nlm.nih.gov/articles/PMC1234567/",
                                   "https://pubmed.ncbi.nlm.nih.gov/42805352/"]
    s2 = sources.semanticscholar("q", 5)
    assert s2[0].url == "https://arxiv.org/abs/cs/0301001"


def test_arxiv_queries_every_word():
    assert sources._arxiv_query("page change, rate") == "all:page AND all:change AND all:rate"


def test_the_backend_interleaves_sources_and_drops_repeats(served):
    resp = ScholarlyBackend(["openalex", "crossref", "arxiv"]).search("q", 10, "science")
    urls = [r.url for r in resp.results]
    # The paywalled DOI arrives from OpenAlex and Crossref: kept once.
    assert urls == ["http://infoscience.epfl.ch/record/99373", "https://doi.org/10.1000/xyz123",
                    "https://arxiv.org/abs/1305.2686", "https://doi.org/10.2139/ssrn.4032279"]
    assert resp.degraded == []
    with pytest.raises(ValueError):
        ScholarlyBackend().search("q", 5, "web")


def test_keys_are_sent_but_never_cached_or_logged_in_the_key(served, monkeypatch, tmp_path):
    from librarian.config import settings as core
    from librarian.research import search_cache
    calls, _ = served
    monkeypatch.setattr(core, "search_cache_enabled", True)
    monkeypatch.setattr(core, "search_cache_dir", str(tmp_path))
    monkeypatch.setattr(settings, "openalex_api_key", "secret-key")
    sources.openalex("q", 5)
    assert calls[0]["params"]["api_key"] == "secret-key"
    cached = list(tmp_path.rglob("*.json"))
    assert len(cached) == 1 and "secret-key" not in cached[0].read_text()
    sources.openalex("q", 5)
    assert len(calls) == 1                                            # served from the cache
    search_cache.reset_cache_stats()


def test_a_refusing_source_cools_down_and_is_reported(served, monkeypatch):
    calls, routes = served
    routes["api.crossref.org"] = Reply(status=429, body={}, headers={"Retry-After": "120"})
    backend = ScholarlyBackend(["openalex", "crossref"])
    resp = backend.search("q", 10, "science")
    assert [r.url for r in resp.results][:1] == ["http://infoscience.epfl.ch/record/99373"]
    assert resp.degraded[0][0] == "crossref" and "429" in resp.degraded[0][1]
    before = len(calls)
    resp = backend.search("q", 10, "science")
    assert len(calls) == before + 1                                   # crossref not asked again
    assert "cooling down" in resp.degraded[0][1]
    assert backend.diagnose()["refusing"][0][0] == "crossref"


def test_cooldown_doubles_without_retry_after(served, monkeypatch):
    _, routes = served
    routes["api.crossref.org"] = Reply(status=503, body={})
    monkeypatch.setattr(settings, "cooldown_seconds", 10.0)
    ScholarlyBackend(["crossref"]).search("q", 5, "science")
    first = http.cooling("crossref")
    http._cooldown_until["crossref"] = 0
    ScholarlyBackend(["crossref"]).search("q", 5, "science")
    assert 9 < first <= 10 and 19 < http.cooling("crossref") <= 20


def test_requests_to_one_source_are_paced(served, monkeypatch):
    monkeypatch.setattr(settings, "intervals", {**settings.intervals, "arxiv": 0.2})
    started = time.monotonic()
    sources.arxiv("a", 1)
    sources.arxiv("b", 1)
    assert time.monotonic() - started >= 0.19


def test_default_sources_leave_out_semantic_scholar_without_a_key(monkeypatch):
    from librarian_scholarly import config
    monkeypatch.delenv("SCHOLARLY_SOURCES", raising=False)
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    assert "semanticscholar" not in config._sources()
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "k")
    assert "semanticscholar" in config._sources()
    monkeypatch.setenv("SCHOLARLY_SOURCES", "arxiv, bogus ,pubmed")
    assert config._sources() == ["arxiv", "pubmed"]


def test_it_is_a_librarian_backend():
    from librarian.research.backends import BACKEND_API_VERSION, SearchBackend
    b = ScholarlyBackend()
    assert isinstance(b, SearchBackend) and b.api_version == BACKEND_API_VERSION
    with b.session() as s:
        assert s is b


def test_one_paper_under_two_urls_is_kept_once_by_title(monkeypatch):
    from librarian.research.providers import SearchResult
    a = [SearchResult(url="https://repo.example/oa/123", title="Change Rate Estimation and Optimal Freshness in Web Page Crawling", kind="science")]
    b = [SearchResult(url="https://doi.org/10.1145/1234567", title="Change rate estimation and optimal freshness in web page crawling.", kind="science"),
         SearchResult(url="https://doi.org/10.1145/7654321", title="Editorial", kind="science"),
         SearchResult(url="https://doi.org/10.1145/7654322", title="Editorial", kind="science")]
    monkeypatch.setitem(sources.SOURCES, "openalex", lambda q, n, cache=None: a)
    monkeypatch.setitem(sources.SOURCES, "crossref", lambda q, n, cache=None: b)
    urls = [r.url for r in ScholarlyBackend(["openalex", "crossref"]).search("q", 10, "science").results]
    assert urls == ["https://repo.example/oa/123", "https://doi.org/10.1145/7654321", "https://doi.org/10.1145/7654322"]
