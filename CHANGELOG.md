# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-10-03

### Added

- OpenAlex and Crossref results name their venue (`venue`: the OpenAlex
  source id, ISSN, and name), which librarian 0.6 stores on the ingested
  document for its venue-quality signal. Older librarians ignore it.

## [0.1.0]

First release on PyPI.

- `ScholarlyBackend`, registered under the `librarian.search_backends` entry
  point as `scholarly`, answering the `science` category from the official
  APIs of OpenAlex, Crossref, arXiv, PubMed (NCBI E-utilities), and Semantic
  Scholar (on by default only with a key).
- Per-source pacing, a cooldown for a source that refuses (honoring
  Retry-After), deduplication by DOI, arXiv id, or title, and librarian
  response-cache integration with API keys kept out of the cache.

[Unreleased]: https://github.com/kevin-j-smith/librarian-scholarly/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/kevin-j-smith/librarian-scholarly/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/kevin-j-smith/librarian-scholarly/releases/tag/v0.1.0
