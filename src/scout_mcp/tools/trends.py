"""scout_trends tool — Track trends and sentiment on any topic."""

import logging
from datetime import datetime, timezone

from ..models import TrendIntel, TrendDevelopment, SourceConfidence, compute_grade
from ..sources import search, news_api
from ..cache import get_cached, set_cached

logger = logging.getLogger(__name__)

TIMEFRAME_MAP = {
    "1d": "d",
    "7d": "w",
    "30d": "m",
    "1m": "m",
    "1y": "y",
}


def _simple_sentiment(texts: list[str]) -> dict:
    """Basic sentiment analysis using keyword matching."""
    positive_words = {
        "growth", "surge", "gain", "profit", "success", "innovation", "breakthrough",
        "boost", "rise", "improve", "strong", "record", "best", "leading", "expand",
        "partnership", "launch", "milestone", "opportunity", "positive", "bullish",
        "promising", "exciting", "impressive", "outstanding", "excellent",
    }
    negative_words = {
        "decline", "loss", "crash", "fail", "risk", "concern", "downturn", "cut",
        "layoff", "struggle", "weak", "trouble", "lawsuit", "scandal", "drop",
        "crisis", "threat", "bearish", "warning", "bankrupt", "fraud", "hack",
        "breach", "controversy", "negative", "slowdown", "recession",
    }

    pos_count = 0
    neg_count = 0
    total_words = 0

    for text in texts:
        words = text.lower().split()
        total_words += len(words)
        for w in words:
            clean = w.strip(".,!?;:'\"()[]")
            if clean in positive_words:
                pos_count += 1
            elif clean in negative_words:
                neg_count += 1

    if pos_count + neg_count == 0:
        return {"score": 0.5, "label": "neutral"}

    score = pos_count / (pos_count + neg_count)
    if score > 0.65:
        label = "positive"
    elif score < 0.35:
        label = "negative"
    else:
        label = "mixed"

    return {"score": round(score, 2), "label": label}


async def scout_trends(topic: str, timeframe: str = "7d") -> dict:
    """Track trends and sentiment on any topic.

    Returns: sentiment, trending direction, key developments, related topics.
    """
    cached = get_cached("scout_trends", topic=topic, timeframe=timeframe)
    if cached:
        return cached

    sources_used = []
    sources_failed = []
    intel = TrendIntel(topic=topic, timeframe=timeframe)
    breakdown: dict[str, SourceConfidence] = {}
    all_texts = []

    ddg_timelimit = TIMEFRAME_MAP.get(timeframe, "w")

    # 1. DuckDuckGo News
    try:
        ddg_news = await search.search_news_ddg(topic, max_results=10, timelimit=ddg_timelimit)
        if ddg_news:
            sources_used.append("duckduckgo_news")
            for item in ddg_news:
                headline = item.get("title", "")
                if headline:
                    all_texts.append(headline)
                    body = item.get("body", "")
                    if body:
                        all_texts.append(body)
                    # Determine impact level
                    impact = "medium"
                    h_lower = headline.lower()
                    if any(w in h_lower for w in ["breaking", "major", "record", "crisis", "surge"]):
                        impact = "high"
                    elif any(w in h_lower for w in ["minor", "small", "slight", "update"]):
                        impact = "low"

                    intel.key_developments.append(TrendDevelopment(
                        headline=headline,
                        date=item.get("date"),
                        impact_level=impact,
                        source=item.get("source"),
                        url=item.get("url"),
                    ))
            breakdown["duckduckgo_news"] = SourceConfidence(
                score=min(0.5 + len(ddg_news) * 0.05, 0.9),
                reason=f"{len(ddg_news)} news articles found"
            )
        else:
            sources_failed.append("duckduckgo_news")
            breakdown["duckduckgo_news"] = SourceConfidence(score=0.0, reason="no results")
    except Exception as e:
        logger.warning("DDG news failed for '%s': %s", topic, e)
        sources_failed.append("duckduckgo_news")
        breakdown["duckduckgo_news"] = SourceConfidence(score=0.0, reason=f"error: {e}")

    # 2. NewsAPI
    days_map = {"1d": 1, "7d": 7, "30d": 30, "1m": 30, "1y": 365}
    days_back = days_map.get(timeframe, 7)
    try:
        news_results = await news_api.search_news(topic, max_results=5, days_back=days_back)
        if news_results:
            sources_used.append("newsapi")
            for item in news_results:
                headline = item.get("headline", "")
                if headline:
                    all_texts.append(headline)
                    desc = item.get("description", "")
                    if desc:
                        all_texts.append(desc)
                    # Avoid duplicates
                    existing = {d.headline.lower() for d in intel.key_developments}
                    if headline.lower() not in existing:
                        intel.key_developments.append(TrendDevelopment(
                            headline=headline,
                            date=item.get("date"),
                            impact_level="medium",
                            source=item.get("source"),
                            url=item.get("url"),
                        ))
            breakdown["newsapi"] = SourceConfidence(
                score=min(0.5 + len(news_results) * 0.1, 0.9),
                reason=f"{len(news_results)} articles found"
            )
        else:
            sources_failed.append("newsapi")
            breakdown["newsapi"] = SourceConfidence(score=0.0, reason="no articles")
    except Exception as e:
        logger.warning("NewsAPI failed for '%s': %s", topic, e)
        sources_failed.append("newsapi")
        breakdown["newsapi"] = SourceConfidence(score=0.0, reason=f"error: {e}")

    # 3. Web search for broader context
    try:
        web_results = await search.search_web(f"{topic} trends {timeframe}", max_results=5)
        if web_results:
            sources_used.append("web_search")
            for r in web_results:
                body = r.get("body", "")
                if body:
                    all_texts.append(body)
            breakdown["web_search"] = SourceConfidence(
                score=0.5, reason=f"{len(web_results)} web results for context"
            )
    except Exception as e:
        sources_failed.append("web_search")
        breakdown["web_search"] = SourceConfidence(score=0.0, reason=f"error: {e}")

    # 4. Find related topics
    try:
        related_results = await search.search_web(f"{topic} related topics trends", max_results=5)
        related = set()
        for r in related_results:
            title = r.get("title", "")
            # Extract capitalized multi-word terms
            import re
            terms = re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', title)
            for t in terms:
                if t.lower() != topic.lower() and len(t) > 3:
                    related.add(t)
        intel.related_topics = list(related)[:10]
    except Exception:
        pass

    # 5. Sentiment analysis
    intel.sentiment = _simple_sentiment(all_texts)

    # 6. Determine trending direction
    if intel.key_developments:
        recent_sentiment = _simple_sentiment(
            [d.headline for d in intel.key_developments[:5]]
        )
        if recent_sentiment["score"] > 0.6:
            intel.trending_direction = "up"
        elif recent_sentiment["score"] < 0.4:
            intel.trending_direction = "down"
        else:
            intel.trending_direction = "stable"

    intel.key_developments = intel.key_developments[:10]

    # Compute weighted confidence — only count sources with data
    _weights = {"duckduckgo_news": 2, "newsapi": 3, "web_search": 1}
    total_w = sum(_weights.get(s, 1) for s in breakdown if breakdown[s].score > 0)
    weighted = sum(breakdown[s].score * _weights.get(s, 1) for s in breakdown if breakdown[s].score > 0)
    intel.confidence = round(weighted / total_w, 2) if total_w > 0 else 0.0
    intel.confidence_breakdown = breakdown
    intel.sources_used = list(set(sources_used))
    intel.sources_failed = list(set(sources_failed))
    intel.data_freshness = datetime.now(timezone.utc).isoformat()

    intel.data_quality_grade = compute_grade(intel.confidence)

    result = intel.model_dump()
    set_cached("scout_trends", result, topic=topic, timeframe=timeframe)
    return result
