# librarian-scholarly

A **scholarly search backend** for [librarian](https://github.com/kevin-j-smith/librarian)'s
research loop. It answers librarian's `science` category from the official
APIs of OpenAlex, Crossref, arXiv, PubMed (NCBI E-utilities), and Semantic
Scholar, instead of scraping them through a metasearch.

```
librarian research loop ──► ScholarlyBackend ──► OpenAlex · Crossref · arXiv · PubMed · Semantic Scholar
                                  │
                 one source at a time · each paced to its limit · cached · cooldown on refusal
```

Why: in librarian's measurements, 4 of the 5 requests a research iteration
sends to SearXNG are science pages, and the science engines are the ones
that rate-limit. These APIs are free, documented, and meant for this.

## Install

Install **into the same environment as librarian**, then route the
`science` category to it beside your web backend:

```bash
uv pip install librarian-scholarly
```

```ini
# librarian's .env
RESEARCH_SEARCH_ROUTES=web: searxng; video: searxng; science: scholarly, searxng
SCHOLARLY_MAILTO=you@example.org     # optional: OpenAlex/Crossref polite pools, NCBI contact
```

With more than one backend installed, librarian needs `RESEARCH_SEARCH_ROUTES`
(or `RESEARCH_SEARCH_BACKEND`); it refuses to guess.

## Settings

| Setting | Default | What it does |
|---|---|---|
| `SCHOLARLY_SOURCES` | `openalex,crossref,arxiv,pubmed` (+ `semanticscholar` with a key) | Sources asked, in this order |
| `SCHOLARLY_MAILTO` | empty | Contact address sent to OpenAlex, Crossref, and NCBI |
| `OPENALEX_API_KEY` | empty | OpenAlex key (a free key raises its daily allowance) |
| `SEMANTIC_SCHOLAR_API_KEY` | empty | Semantic Scholar key; the keyless pool is shared and often refuses |
| `NCBI_API_KEY` | empty | Raises PubMed's limit from 3 to 10 requests a second |
| `SCHOLARLY_PER_SOURCE` | 25 | Most results asked of one source per search |
| `SCHOLARLY_<SOURCE>_INTERVAL` | arXiv 3.0, PubMed 0.4, others 1.0–1.1 | Seconds between two requests to one source |
| `SCHOLARLY_COOLDOWN_SECONDS` | 600 | How long a refusing source is left out (doubling, unless it sends Retry-After) |
| `SCHOLARLY_TIMEOUT_SECONDS` | 30 | Per request |

Keys are sent to their API and never written to librarian's search cache.

## What it returns

Each source's results in its own relevance order, interleaved, one result
per paper (by DOI, arXiv id, or title: one paper often arrives as an open copy from one API and a DOI from another), with the link most likely to be readable:
an open-access copy where the API knows one (OpenAlex's best OA location,
a PubMed Central article, Semantic Scholar's open PDF), else the DOI, else
the API's own page. Filtering, ranking, and caps are librarian's, as for
every backend.

## What the APIs said on September 30, 2026

- **OpenAlex** prices requests: a search cost $0.001, and the keyless
  allowance was $0.10 a day (its `X-RateLimit-*` headers say so).
- **Crossref**'s public pool allowed 1 request a second.
- **arXiv** asks for one request every 3 seconds.
- **PubMed** allowed 3 requests a second without a key.
- **Semantic Scholar** refused the first keyless request (429), which is why
  it's on by default only with a key.

A source that refuses (429 or 503) is left out of searches for a cooldown and
reported to librarian as degraded; the other sources still answer.

## The services' terms

This package's license covers its code, not the services it calls. What
they return is subject to each one's terms, which you accept when you use
them. Semantic Scholar's API license asks you to attribute "Semantic
Scholar" wherever its data appears in what you publish. arXiv's API terms
ask you not to present a project as endorsed by arXiv.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
