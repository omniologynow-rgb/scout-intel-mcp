"""DuckDuckGo search integration — free, no API key needed.

Uses the `ddgs` package with exponential backoff on rate limits.
Backs off: 3s → 6s → 12s → 24s → 48s (cap). Resets on success.
Retries once on failure before giving up.
"""

import logging
import time

logger = logging.getLogger(__name__)

# ── Exponential backoff state ──
_last_call_ts = 0.0
_BASE_INTERVAL = 2.0         # starting interval (seconds)
_consecutive_failures = 0     # tracks failures for backoff
_MAX_BACKOFF = 48.0           # cap backoff at 48 seconds
_MAX_RETRIES = 1              # retry once on failure


def _get_interval() -> float:
    """Calculate current throttle interval based on failure count."""
    if _consecutive_failures == 0:
        return _BASE_INTERVAL
    backoff = _BASE_INTERVAL * (2 ** _consecutive_failures)
    return min(backoff, _MAX_BACKOFF)


def _throttle():
    """Adaptive throttle — waits longer after consecutive failures."""
    global _last_call_ts
    now = time.time()
    interval = _get_interval()
    elapsed = now - _last_call_ts
    if elapsed < interval:
        wait = interval - elapsed
        logger.debug("DDG throttle: waiting %.1fs (backoff level %d)", wait, _consecutive_failures)
        time.sleep(wait)
    _last_call_ts = time.time()


def _on_success():
    """Reset backoff on successful call."""
    global _consecutive_failures
    if _consecutive_failures > 0:
        logger.info("DDG backoff reset (was level %d)", _consecutive_failures)
    _consecutive_failures = 0


def _on_failure():
    """Increase backoff level on failure."""
    global _consecutive_failures
    _consecutive_failures = min(_consecutive_failures + 1, 5)
    logger.info("DDG backoff increased to level %d (%.1fs interval)", _consecutive_failures, _get_interval())


def get_backoff_status() -> dict:
    """Return current backoff state for diagnostics."""
    return {
        "consecutive_failures": _consecutive_failures,
        "current_interval_seconds": round(_get_interval(), 1),
        "max_backoff_seconds": _MAX_BACKOFF,
    }


async def search_web(query: str, max_results: int = 10) -> list[dict]:
    """Search the web via DuckDuckGo with exponential backoff + retry.

    Returns list of {title, href, body}.
    """
    from ddgs import DDGS

    for attempt in range(_MAX_RETRIES + 1):
        try:
            _throttle()
            results = list(DDGS().text(query, max_results=max_results))
            logger.info("DDG web: %d results for '%s'", len(results), query)
            _on_success()
            return results
        except Exception as e:
            _on_failure()
            if attempt < _MAX_RETRIES:
                wait = _get_interval()
                logger.info("DDG retry %d/%d for '%s' after %.1fs", attempt + 1, _MAX_RETRIES, query, wait)
                time.sleep(wait)
            else:
                logger.warning("DDG web search failed for '%s' after %d attempts: %s", query, _MAX_RETRIES + 1, e)
                return []


async def search_news_ddg(query: str, max_results: int = 10, timelimit: str = "w") -> list[dict]:
    """Search DuckDuckGo News with exponential backoff + retry.

    Returns list of {title, url, body, date, source}.
    """
    from ddgs import DDGS

    for attempt in range(_MAX_RETRIES + 1):
        try:
            _throttle()
            results = list(DDGS().news(query, max_results=max_results, timelimit=timelimit))
            logger.info("DDG news: %d results for '%s'", len(results), query)
            _on_success()
            return results
        except Exception as e:
            _on_failure()
            if attempt < _MAX_RETRIES:
                wait = _get_interval()
                logger.info("DDG news retry %d/%d for '%s' after %.1fs", attempt + 1, _MAX_RETRIES, query, wait)
                time.sleep(wait)
            else:
                logger.warning("DDG news search failed for '%s' after %d attempts: %s", query, _MAX_RETRIES + 1, e)
                return []
