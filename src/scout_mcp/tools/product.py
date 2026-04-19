"""scout_product tool — Research any product."""

import logging
from datetime import datetime, timezone

from ..models import ProductIntel, ProductRating, SourceConfidence, compute_grade
from ..sources import search, news_api, web_scraper
from ..cache import get_cached, set_cached

logger = logging.getLogger(__name__)


async def scout_product(name: str) -> dict:
    """Get intelligence on any product.

    Returns: category, pricing, ratings, features, alternatives, recent updates.
    """
    cached = get_cached("scout_product", name=name)
    if cached:
        return cached

    sources_used = []
    sources_failed = []
    intel = ProductIntel(name=name)
    confidence = 0.0
    breakdown: dict[str, SourceConfidence] = {}
    results = []  # store initial search results for reuse

    # 1. Web search for product info
    try:
        results = await search.search_web(f"{name} product", max_results=8)
        if results:
            sources_used.append("web_search")
            # Extract description
            for r in results:
                body = r.get("body", "")
                if body and len(body) > 50:
                    intel.description = body[:500]
                    break
            confidence += 0.15
            breakdown["web_search"] = SourceConfidence(
                score=min(0.4 + len(results) * 0.05, 0.8),
                reason=f"{len(results)} product search results"
            )
    except Exception as e:
        sources_failed.append("web_search")

    # 2. Search for pricing
    try:
        pricing_results = await search.search_web(f"{name} pricing plans cost", max_results=5)
        if pricing_results:
            sources_used.append("pricing_search")
            import re
            for r in pricing_results:
                text = f"{r.get('title', '')} {r.get('body', '')}"
                # Check for free tier
                if any(w in text.lower() for w in ["free tier", "free plan", "free forever", "freemium"]):
                    intel.pricing["free_tier"] = True
                # Extract price
                price_matches = re.findall(r'\$(\d+(?:\.\d+)?)\s*(?:/mo|/month|per month)', text, re.IGNORECASE)
                if price_matches:
                    intel.pricing["paid_from"] = f"${price_matches[0]}/mo"
            confidence += 0.1
    except Exception as e:
        sources_failed.append("pricing_search")

    # 3. Search for reviews/ratings
    try:
        review_results = await search.search_web(f"{name} review rating G2 ProductHunt", max_results=5)
        if review_results:
            sources_used.append("review_search")
            import re
            for r in review_results:
                text = f"{r.get('title', '')} {r.get('body', '')}"
                href = r.get("href", "")

                # G2 rating
                if "g2.com" in href.lower():
                    rating_match = re.search(r'(\d+\.?\d*)\s*/\s*5|(\d+\.?\d*)\s+(?:out of|stars)', text)
                    if rating_match:
                        score = rating_match.group(1) or rating_match.group(2)
                        intel.ratings.append(ProductRating(platform="G2", score=f"{score}/5", url=href))

                # ProductHunt
                if "producthunt.com" in href.lower():
                    intel.ratings.append(ProductRating(platform="Product Hunt", url=href))

                # Capterra
                if "capterra.com" in href.lower():
                    rating_match = re.search(r'(\d+\.?\d*)\s*/\s*5|(\d+\.?\d*)\s+(?:out of|stars)', text)
                    score = ""
                    if rating_match:
                        score = f"{rating_match.group(1) or rating_match.group(2)}/5"
                    intel.ratings.append(ProductRating(platform="Capterra", score=score, url=href))

            confidence += 0.1
    except Exception as e:
        sources_failed.append("review_search")

    # 4. Search for features
    try:
        feature_results = await search.search_web(f"{name} features capabilities", max_results=5)
        if feature_results:
            sources_used.append("feature_search")
            features = set()
            for r in feature_results:
                body = r.get("body", "")
                # Extract feature-like phrases
                sentences = body.split(".")
                for sent in sentences:
                    sent = sent.strip()
                    if len(sent) > 15 and len(sent) < 150:
                        features.add(sent)
            intel.features = list(features)[:10]
            confidence += 0.1
    except Exception as e:
        sources_failed.append("feature_search")

    # 5. Search for alternatives — use competitor extraction engine + existing results
    try:
        from .competitors import _extract_from_text
        alt_candidates: dict[str, int] = {}
        
        # Extract from results we already have
        if results:
            for r in results:
                text = f"{r.get('title', '')}. {r.get('body', '')}"
                extracted = _extract_from_text(text, name)
                for n, score in extracted.items():
                    alt_candidates[n] = alt_candidates.get(n, 0) + score
        
        # Focused alternatives search
        alt_results = await search.search_web(f"best {name} alternatives", max_results=5)
        if alt_results:
            sources_used.append("alternatives_search")
            for r in alt_results:
                text = f"{r.get('title', '')}. {r.get('body', '')}"
                extracted = _extract_from_text(text, name)
                for n, score in extracted.items():
                    alt_candidates[n] = alt_candidates.get(n, 0) + score
        
        ranked = sorted(alt_candidates.items(), key=lambda x: x[1], reverse=True)
        intel.alternatives = [n for n, _ in ranked[:8]]
        if intel.alternatives:
            confidence += 0.1
    except Exception as e:
        sources_failed.append("alternatives_search")

    # 6. Recent news/updates
    try:
        news_results = await news_api.search_news(f"{name} update release", max_results=3)
        ddg_news = await search.search_news_ddg(f"{name} product update", max_results=3)

        updates = []
        for n in news_results:
            h = n.get("headline", "")
            if h:
                updates.append(h)
        for n in ddg_news:
            h = n.get("title", "")
            if h:
                updates.append(h)
        intel.recent_updates = list(dict.fromkeys(updates))[:5]
        if updates:
            sources_used.append("news")
            confidence += 0.1
    except Exception as e:
        sources_failed.append("news")

    # 7. Determine category from description
    if intel.description:
        desc_lower = intel.description.lower()
        categories = {
            "project management": "Project Management",
            "crm": "CRM",
            "marketing": "Marketing",
            "analytics": "Analytics",
            "design": "Design",
            "developer": "Developer Tools",
            "communication": "Communication",
            "collaboration": "Collaboration",
            "security": "Security",
            "database": "Database",
            "cloud": "Cloud Infrastructure",
            "ai": "AI & Machine Learning",
            "automation": "Automation",
            "hr": "Human Resources",
            "accounting": "Accounting & Finance",
            "ecommerce": "E-Commerce",
            "email": "Email",
            "social media": "Social Media",
            "video": "Video",
            "productivity": "Productivity",
        }
        for keyword, cat in categories.items():
            if keyword in desc_lower:
                intel.category = cat
                break

    # 8. Ideal for
    if intel.description and intel.features:
        intel.ideal_for = f"Teams and businesses looking for {intel.category or 'a solution'} with {', '.join(intel.features[:3])}"

    # Compute weighted confidence (combine breakdown + legacy confidence)
    if breakdown:
        scores = [sc.score for sc in breakdown.values() if sc.score > 0]
        avg_breakdown = sum(scores) / len(scores) if scores else 0.0
        intel.confidence = round(min(avg_breakdown + confidence * 0.3, 1.0), 2)
    else:
        intel.confidence = min(confidence, 1.0)
    intel.confidence_breakdown = breakdown
    intel.sources_used = list(set(sources_used))
    intel.sources_failed = list(set(sources_failed))
    intel.data_freshness = datetime.now(timezone.utc).isoformat()

    intel.data_quality_grade = compute_grade(intel.confidence)

    result = intel.model_dump()
    set_cached("scout_product", result, name=name)
    return result
