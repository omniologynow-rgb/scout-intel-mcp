"""scout_person tool — Research a public figure (PRO tier only)."""

import logging
from datetime import datetime, timezone

from ..models import PersonIntel, SocialProfile, SourceConfidence, compute_grade
from ..sources import search, news_api, wikipedia_src, social
from ..cache import get_cached, set_cached

logger = logging.getLogger(__name__)


async def scout_person(name: str, company: str | None = None) -> dict:
    """Get intelligence on a public figure. PRO tier only.

    Returns: current role, background, social profiles, recent activity, achievements.
    """
    query_name = f"{name} {company}" if company else name

    cached = get_cached("scout_person", name=name, company=company)
    if cached:
        return cached

    sources_used = []
    sources_failed = []
    intel = PersonIntel(name=name, company=company)
    breakdown: dict[str, SourceConfidence] = {}
    confidence = 0.0

    # 1. Wikipedia for background
    try:
        wiki_data = await wikipedia_src.get_summary(name)
        if wiki_data:
            sources_used.append("wikipedia")
            intel.background_summary = wiki_data.get("summary", "")[:500]

            # Try to extract role and location from summary
            summary = wiki_data.get("summary", "")
            import re

            # Extract role
            role_patterns = [
                rf'{re.escape(name)}\s+is\s+(?:an?\s+)?([^.]+)',
                r'(?:CEO|CTO|CFO|COO|founder|co-founder|president|chairman|director)\s+of\s+([^.]+)',
            ]
            for pattern in role_patterns:
                m = re.search(pattern, summary, re.IGNORECASE)
                if m:
                    intel.current_role = m.group(1).strip()[:200]
                    break

            # Extract notable achievements
            achievements = []
            sentences = summary.split(".")
            for sent in sentences:
                sent = sent.strip()
                if any(w in sent.lower() for w in ["founded", "created", "invented", "awarded",
                                                     "built", "developed", "pioneered", "launched"]):
                    if len(sent) > 20:
                        achievements.append(sent[:200])
            intel.notable_achievements = achievements[:5]
            confidence += 0.25
            breakdown["wikipedia"] = SourceConfidence(
                score=0.9 if achievements else 0.7,
                reason=f"page found, {len(achievements)} achievements"
            )
    except Exception as e:
        logger.warning("Wikipedia failed for '%s': %s", name, e)
        sources_failed.append("wikipedia")
        breakdown["wikipedia"] = SourceConfidence(score=0.0, reason=f"error: {e}")

    # 2. Web search for current info
    try:
        results = await search.search_web(query_name, max_results=5)
        if results:
            sources_used.append("web_search")
            for r in results:
                body = r.get("body", "")
                if body and not intel.current_role:
                    import re
                    role_match = re.search(
                        rf'{re.escape(name)}[,\s]+([A-Z][^.]+?)(?:\.|,|\s+at\s+|\s+of\s+)',
                        body
                    )
                    if role_match:
                        intel.current_role = role_match.group(1).strip()[:200]
                if body and not intel.background_summary:
                    intel.background_summary = body[:500]
            confidence += 0.15
    except Exception as e:
        sources_failed.append("web_search")

    # 3. News for recent activity
    try:
        news_results = await news_api.search_news(query_name, max_results=3)
        ddg_news = await search.search_news_ddg(query_name, max_results=3)

        activities = []
        for n in news_results:
            h = n.get("headline", "")
            if h:
                activities.append(h)
        for n in ddg_news:
            h = n.get("title", "")
            if h and h not in activities:
                activities.append(h)
        intel.recent_activity = activities[:5]
        if activities:
            sources_used.append("news")
            confidence += 0.15
    except Exception as e:
        sources_failed.append("news")

    # 4. Social profiles
    try:
        social_results = await social.find_social_profiles(query_name)
        intel.social_profiles = [SocialProfile(**p) for p in social_results]
        if social_results:
            sources_used.append("social_search")
            confidence += 0.1
    except Exception as e:
        sources_failed.append("social_search")

    if breakdown:
        scores = [sc.score for sc in breakdown.values() if sc.score > 0]
        avg_breakdown = sum(scores) / len(scores) if scores else 0.0
        intel.confidence = round(min(avg_breakdown + confidence * 0.2, 1.0), 2)
    else:
        intel.confidence = min(confidence, 1.0)
    intel.confidence_breakdown = breakdown
    intel.sources_used = list(set(sources_used))
    intel.sources_failed = list(set(sources_failed))
    intel.data_freshness = datetime.now(timezone.utc).isoformat()

    intel.data_quality_grade = compute_grade(intel.confidence)

    result = intel.model_dump()
    set_cached("scout_person", result, name=name, company=company)
    return result
