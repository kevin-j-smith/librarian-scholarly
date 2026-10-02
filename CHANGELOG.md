# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0]

First release on PyPI.

- `ScholarlyBackend`, registered under the `librarian.search_backends` entry
  point as `scholarly`, answering the `science` category from the official
  APIs of OpenAlex, Crossref, arXiv, PubMed (NCBI E-utilities), and Semantic
  Scholar (on by default only with a key).
- Per-source pacing, a cooldown for a source that refuses (honoring
  Retry-After), deduplication by DOI, arXiv id, or title, and librarian
  response-cache integration with API keys kept out of the cache.

[Unreleased]: https://github.com/kevin-j-smith/librarian-scholarly/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/kevin-j-smith/librarian-scholarly/releases/tag/v0.1.0
