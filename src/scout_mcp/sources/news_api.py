"""NewsAPI.org integration for news aggregation."""

import logging
from datetime import datetime, timedelta, timezone

from ..config import NEWS_API_KEY

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None and NEWS_API_KEY:
        from newsapi import NewsApiClient
        _client = NewsApiClient(api_key=NEWS_API_KEY)
    return _client


async def search_news(query: str, max_results: int = 5, days_back: int = 30) -> list[dict]:
    """Search NewsAPI for articles matching query. Returns normalized list."""
    client = _get_client()
    if not client:
        logger.warning("NewsAPI: No API key configured")
        return []

    try:
        from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
        response = client.get_everything(
            q=query,
            from_param=from_date,
            language="en",
            sort_by="relevancy",
            page_size=max_results,
        )
        articles = response.get("articles", [])
        results = []
        for art in articles:
            results.append({
                "headline": art.get("title", ""),
                "source": art.get("source", {}).get("name", ""),
                "url": art.get("url", ""),
                "date": art.get("publishedAt", ""),
                "description": art.get("description", ""),
            })
        logger.info("NewsAPI: %d articles for '%s'", len(results), query)
        return results
    except Exception as e:
        logger.warning("NewsAPI search failed for '%s': %s", query, e)
        return []


async def get_top_headlines(query: str = None, category: str = None, max_results: int = 5) -> list[dict]:
    """Get top headlines from NewsAPI."""
    client = _get_client()
    if not client:
        return []

    try:
        kwargs = {"language": "en", "page_size": max_results}
        if query:
            kwargs["q"] = query
        if category:
            kwargs["category"] = category

        response = client.get_top_headlines(**kwargs)
        articles = response.get("articles", [])
        return [
            {
                "headline": art.get("title", ""),
                "source": art.get("source", {}).get("name", ""),
                "url": art.get("url", ""),
                "date": art.get("publishedAt", ""),
            }
            for art in articles
        ]
    except Exception as e:
        logger.warning("NewsAPI headlines failed: %s", e)
        return []
