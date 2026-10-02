"""Paced, cached requests to the scholarly APIs, one source at a time.

Each source has its own pace (config.intervals) and its own cooldown: a
source that answers 429 or 503 is left out of searches for its
Retry-After, or SCHOLARLY_COOLDOWN_SECONDS doubling while it keeps
refusing, and reported as degraded with the time left. A successful
response is cached with librarian's search cache (research/search_cache.py),
so a replayed search costs no request and no pace; a failed one is never
cached.

These are fixed API hosts, not URLs from content, so librarian's ingestion
guards (which are for content-supplied URLs) don't apply here; the
results' own URLs are fetched later by librarian's ingestion, behind them.
"""
from __future__ import annotations

import threading
import time
from email.utils import parsedate_to_datetime
from typing import Optional

import httpx

from librarian.research import search_cache

from . import __version__
from .config import settings

USER_AGENT = f"librarian-scholarly/{__version__} (+https://github.com/kevin-j-smith/librarian-scholarly)"
NAMESPACE = "scholarly-v1"

_lock = threading.Lock()
_next_allowed: dict[str, float] = {}
_cooldown_until: dict[str, float] = {}
_strikes: dict[str, int] = {}


class SourceUnavailable(RuntimeError):
    """The source is cooling down or refused this request."""


def cooling(source: str) -> Optional[float]:
    """Seconds left on `source`'s cooldown, or None."""
    left = _cooldown_until.get(source, 0) - time.time()
    return left if left > 0 else None


def _pace(source: str) -> None:
    interval = settings.intervals.get(source, 1.0)
    with _lock:
        now = time.monotonic()
        wait = max(0.0, _next_allowed.get(source, 0.0) - now)
        _next_allowed[source] = max(now, _next_allowed.get(source, 0.0)) + interval
    if wait:
        time.sleep(wait)


def _retry_after(resp: httpx.Response) -> Optional[float]:
    value = resp.headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
        except (TypeError, ValueError):
            return None


def _cool(source: str, resp: httpx.Response) -> float:
    strikes = _strikes.get(source, 0) + 1
    _strikes[source] = strikes
    seconds = _retry_after(resp) or settings.cooldown_seconds * (2 ** (strikes - 1))
    _cooldown_until[source] = time.time() + seconds
    return seconds


def get(source: str, url: str, params: dict, *, headers: Optional[dict] = None, as_text: bool = False,
        cache=None, cache_params: Optional[dict] = None) -> dict:
    """GET `url` for `source`: the JSON body (or {"text": ...} with
    `as_text`), from the cache when it has it. `cache_params` is what keys
    the cache when `params` carries a secret (an API key) that must not."""
    key_params = cache_params if cache_params is not None else params
    hit = search_cache.lookup(url, key_params, NAMESPACE, cache)
    if hit is not None:
        return hit
    left = cooling(source)
    if left:
        raise SourceUnavailable(f"cooling down after refusing ({left:.0f}s left)")
    _pace(source)
    resp = httpx.get(url, params=params, headers={"User-Agent": USER_AGENT, **(headers or {})},
                     timeout=settings.timeout_seconds, follow_redirects=True)
    if resp.status_code in (429, 503):
        seconds = _cool(source, resp)
        raise SourceUnavailable(f"HTTP {resp.status_code}: cooling down {seconds:.0f}s")
    resp.raise_for_status()
    _strikes.pop(source, None)
    payload = {"text": resp.text} if as_text else resp.json()
    search_cache.store(url, key_params, NAMESPACE, payload, cache)
    return payload


def reset() -> None:
    """Forget pace and cooldowns (tests)."""
    _next_allowed.clear()
    _cooldown_until.clear()
    _strikes.clear()
