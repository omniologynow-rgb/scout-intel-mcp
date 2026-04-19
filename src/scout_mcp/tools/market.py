"""scout_market tool — Research any market or industry."""

import logging
from datetime import datetime, timezone

from ..models import MarketIntel, SourceConfidence, compute_grade
from ..sources import search, news_api, wikipedia_src
from ..cache import get_cached, set_cached

logger = logging.getLogger(__name__)


async def scout_market(query: str, depth: str = "summary") -> dict:
    """Research any market or industry.

    Returns: market size, growth rate, key players, trends, risks.
    depth="summary" for quick overview, depth="detailed" for deeper analysis.
    """
    cached = get_cached("scout_market", query=query, depth=depth)
    if cached:
        return cached

    sources_used = []
    sources_failed = []
    market_name = query.title()
    intel = MarketIntel(market_name=market_name, query=query, depth=depth)
    breakdown: dict[str, SourceConfidence] = {}
    all_texts = []

    # 1. Search for market size and overview
    search_queries = [
        f"{query} market size 2025 2026",
        f"{query} market growth rate CAGR",
        f"{query} industry key players",
    ]
    if depth == "detailed":
        search_queries.extend([
            f"{query} market risks challenges",
            f"{query} market growth drivers",
            f"{query} market trends forecast",
        ])

    for sq in search_queries:
        try:
            results = await search.search_web(sq, max_results=5)
            if results:
                sources_used.append(f"search")
                for r in results:
                    body = r.get("body", "")
                    title = r.get("title", "")
                    href = r.get("href", "")
                    if body:
                        all_texts.append(f"{title} {body}")
                    if href:
                        intel.source_links.append(href)

                    text = f"{title} {body}"
                    import re

                    # Extract market size (e.g., "$X billion")
                    size_matches = re.findall(
                        r'\$[\d,.]+\s*(?:billion|million|trillion|B|M|T)',
                        text, re.IGNORECASE
                    )
                    if size_matches and not intel.market_size:
                        intel.market_size = size_matches[0]
                        if len(size_matches) > 1:
                            intel.market_size_projections = f"Projected: {size_matches[-1]}"

                    # Extract CAGR
                    cagr_matches = re.findall(
                        r'CAGR\s+(?:of\s+)?(\d+\.?\d*%)',
                        text, re.IGNORECASE
                    )
                    if not cagr_matches:
                        cagr_matches = re.findall(
                            r'(\d+\.?\d*%)\s+CAGR',
                            text, re.IGNORECASE
                        )
                    if cagr_matches and not intel.cagr:
                        intel.cagr = cagr_matches[0]

                    # Extract key players (companies mentioned)
                    company_pattern = r'(?:key players?|major (?:players?|companies)|leading companies?)[\s:]+([^.]+)'
                    player_matches = re.findall(company_pattern, text, re.IGNORECASE)
                    for pm in player_matches:
                        names = re.findall(r'[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*', pm)
                        intel.key_players.extend(names)

                breakdown[f"search_{sq[:20]}"] = SourceConfidence(
                    score=0.5, reason=f"{len(results)} results"
                )
        except Exception as e:
            logger.warning("Market search failed for '%s': %s", sq, e)
            sources_failed.append("search")

    # Deduplicate
    intel.key_players = list(dict.fromkeys(intel.key_players))[:15]
    intel.source_links = list(dict.fromkeys(intel.source_links))[:10]

    # 2. Wikipedia for market background
    try:
        wiki_data = await wikipedia_src.get_summary(f"{query} market")
        if not wiki_data:
            wiki_data = await wikipedia_src.get_summary(query)
        if wiki_data:
            sources_used.append("wikipedia")
            summary = wiki_data.get("summary", "")
            all_texts.append(summary)
            breakdown["wikipedia"] = SourceConfidence(score=0.7, reason="market background found")
    except Exception as e:
        sources_failed.append("wikipedia")
        breakdown["wikipedia"] = SourceConfidence(score=0.0, reason=f"error: {e}")

    # 3. News for recent trends
    try:
        news_results = await news_api.search_news(f"{query} market industry", max_results=5)
        ddg_news = await search.search_news_ddg(f"{query} market trends", max_results=5)

        trend_texts = []
        for n in news_results + ddg_news:
            headline = n.get("headline") or n.get("title", "")
            if headline:
                trend_texts.append(headline)
                all_texts.append(headline)

        if trend_texts:
            sources_used.append("news")
            intel.trends = trend_texts[:8]
            breakdown["news"] = SourceConfidence(
                score=min(0.5 + len(trend_texts) * 0.05, 0.9),
                reason=f"{len(trend_texts)} trend headlines found"
            )
    except Exception as e:
        sources_failed.append("news")
        breakdown["news"] = SourceConfidence(score=0.0, reason=f"error: {e}")

    # 4. Extract growth drivers and risks from collected text
    combined_text = " ".join(all_texts).lower()

    growth_keywords = ["growth driver", "driven by", "fueled by", "growth factor", "opportunity",
                       "increasing demand", "rising adoption", "digital transformation"]
    risk_keywords = ["risk", "challenge", "threat", "concern", "regulation", "competition",
                     "slowdown", "decline", "barrier", "constraint"]

    for text in all_texts:
        sentences = text.split(".")
        for sent in sentences:
            sent_lower = sent.lower().strip()
            if any(kw in sent_lower for kw in growth_keywords) and len(sent.strip()) > 20:
                intel.growth_drivers.append(sent.strip()[:200])
            if any(kw in sent_lower for kw in risk_keywords) and len(sent.strip()) > 20:
                intel.risks.append(sent.strip()[:200])

    intel.growth_drivers = list(dict.fromkeys(intel.growth_drivers))[:8]
    intel.risks = list(dict.fromkeys(intel.risks))[:8]

    # Compute weighted confidence — only count sources with data
    scores = [sc.score for sc in breakdown.values() if sc.score > 0]
    intel.confidence = round(sum(scores) / len(scores), 2) if scores else 0.0
    intel.confidence_breakdown = breakdown
    intel.sources_used = list(set(sources_used))
    intel.sources_failed = list(set(sources_failed))
    intel.data_freshness = datetime.now(timezone.utc).isoformat()

    intel.data_quality_grade = compute_grade(intel.confidence)

    result = intel.model_dump()
    set_cached("scout_market", result, query=query, depth=depth)
    return result
