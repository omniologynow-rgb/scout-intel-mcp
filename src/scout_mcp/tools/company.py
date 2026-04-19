"""scout_company tool — Structured intelligence on any company."""

import logging
from datetime import datetime, timezone

from ..models import CompanyIntel, FundingInfo, NewsItem, SocialProfile, KeyPerson, SourceConfidence, compute_grade
from ..sources import search, news_api, wikipedia_src, web_scraper, social
from ..sources import crunchbase, github_api, opencorporates
from ..cache import get_cached, set_cached

logger = logging.getLogger(__name__)


async def scout_company(name: str, domain: str | None = None) -> dict:
    """Get structured intelligence on any company.

    Returns: industry, funding, tech stack, competitors, recent news, key people.
    """
    # Check cache
    cached = get_cached("scout_company", name=name, domain=domain)
    if cached:
        return cached

    sources_used = []
    sources_failed = []
    intel = CompanyIntel(name=name, domain=domain)
    breakdown: dict[str, SourceConfidence] = {}

    # 1. Web search for company info
    try:
        search_results = await search.search_web(f"{name} company", max_results=8)
        if search_results:
            sources_used.append("duckduckgo_search")
            # Extract domain if not provided
            if not domain and search_results:
                for r in search_results:
                    href = r.get("href", "")
                    if href and name.lower().replace(" ", "") in href.lower():
                        from urllib.parse import urlparse
                        parsed = urlparse(href)
                        domain = parsed.netloc
                        intel.domain = domain
                        break
            # Extract description from search snippets
            snippets = [r.get("body", "") for r in search_results if r.get("body")]
            if snippets:
                intel.description = snippets[0][:500]
            breakdown["duckduckgo"] = SourceConfidence(
                score=0.6 if len(search_results) >= 5 else 0.4,
                reason=f"{len(search_results)} results found"
            )
        else:
            sources_failed.append("duckduckgo_search")
            breakdown["duckduckgo"] = SourceConfidence(score=0.0, reason="no results")
    except Exception as e:
        logger.warning("Search failed for %s: %s", name, e)
        sources_failed.append("duckduckgo_search")

    # 2. Scrape company website
    if domain:
        try:
            site_data = await web_scraper.scrape_company_website(domain)
            if site_data:
                sources_used.append("company_website")
                if site_data.get("meta_description"):
                    intel.description = site_data["meta_description"]
                elif site_data.get("og_description"):
                    intel.description = site_data["og_description"]
                intel.tech_stack = site_data.get("tech_stack_hints", [])
                # Social profiles from website
                social_links = site_data.get("social_links", {})
                profiles = await social.detect_social_from_links(social_links)
                intel.social_profiles = [SocialProfile(**p) for p in profiles]
                data_points = sum(1 for v in [site_data.get("meta_description"), site_data.get("og_description"), site_data.get("tech_stack_hints")] if v)
                breakdown["company_website"] = SourceConfidence(
                    score=min(0.3 + data_points * 0.2, 0.9),
                    reason=f"scraped {domain}, {data_points} data points extracted"
                )
        except Exception as e:
            logger.warning("Website scrape failed for %s: %s", domain, e)
            sources_failed.append("company_website")
            breakdown["company_website"] = SourceConfidence(score=0.0, reason=f"scrape failed: {e}")

    # 3. Wikipedia for background
    try:
        wiki_data = await wikipedia_src.extract_company_info(name)
        if wiki_data:
            sources_used.append("wikipedia")
            if wiki_data.get("wikipedia_summary"):
                if not intel.description or len(wiki_data["wikipedia_summary"]) > len(intel.description):
                    intel.description = wiki_data["wikipedia_summary"][:500]
            if wiki_data.get("founded"):
                intel.founded = wiki_data["founded"]
            if wiki_data.get("headquarters"):
                intel.headquarters = wiki_data["headquarters"]
            has_extra = bool(wiki_data.get("founded") or wiki_data.get("headquarters"))
            breakdown["wikipedia"] = SourceConfidence(
                score=0.9 if has_extra else 0.7,
                reason=f"page found, {'structured data extracted' if has_extra else 'summary only'}"
            )
        else:
            sources_failed.append("wikipedia")
            breakdown["wikipedia"] = SourceConfidence(score=0.0, reason="no page found")
    except Exception as e:
        logger.warning("Wikipedia failed for %s: %s", name, e)
        sources_failed.append("wikipedia")
        breakdown["wikipedia"] = SourceConfidence(score=0.0, reason=f"error: {e}")

    # 4. News via NewsAPI + DuckDuckGo News
    try:
        news_results = await news_api.search_news(name, max_results=3)
        ddg_news = await search.search_news_ddg(f"{name} company", max_results=3)

        all_news = []
        seen_headlines = set()
        for n in news_results:
            h = n.get("headline", "")
            if h and h not in seen_headlines:
                seen_headlines.add(h)
                all_news.append(NewsItem(
                    headline=h, source=n.get("source"), url=n.get("url"), date=n.get("date")
                ))
        for n in ddg_news:
            h = n.get("title", "")
            if h and h not in seen_headlines:
                seen_headlines.add(h)
                all_news.append(NewsItem(
                    headline=h, source=n.get("source"), url=n.get("url"), date=n.get("date")
                ))
        intel.recent_news = all_news[:5]
        if all_news:
            sources_used.append("news_api")
            breakdown["newsapi"] = SourceConfidence(
                score=min(0.5 + len(all_news) * 0.1, 0.9),
                reason=f"{len(all_news)} articles found"
            )
        else:
            sources_failed.append("news_api")
            breakdown["newsapi"] = SourceConfidence(score=0.0, reason="no articles found")
    except Exception as e:
        logger.warning("News search failed for %s: %s", name, e)
        sources_failed.append("news_api")
        breakdown["newsapi"] = SourceConfidence(score=0.0, reason=f"error: {e}")

    # 4b. Funding data — multi-source (search snippets + Growjo + news)
    try:
        funding_data = await crunchbase.get_funding_data(name)
        data_points = funding_data.get("_data_points", 0)
        if data_points > 0:
            sources_used.append("funding_intelligence")
            if funding_data.get("funding_total") or funding_data.get("last_round"):
                intel.funding = FundingInfo(
                    total_funding=funding_data.get("funding_total"),
                    last_round=funding_data.get("last_round"),
                    last_round_amount=funding_data.get("last_round_amount"),
                    valuation=funding_data.get("valuation"),
                )
            if funding_data.get("employee_range") and not intel.employee_range:
                intel.employee_range = funding_data["employee_range"]
            funding_sources = funding_data.get("_funding_sources", [])
            breakdown["funding_intelligence"] = SourceConfidence(
                score=min(0.4 + data_points * 0.1, 0.9),
                reason=f"{data_points} funding data points from {', '.join(funding_sources)}"
            )
        else:
            breakdown["funding_intelligence"] = SourceConfidence(score=0.0, reason="no funding data found")
    except Exception as e:
        logger.warning("Funding intelligence failed for %s: %s", name, e)
        breakdown["funding_intelligence"] = SourceConfidence(score=0.0, reason=f"error: {e}")

    # 4c. GitHub — org info, repos, tech stack
    try:
        gh_data = await github_api.search_org(name)
        if gh_data:
            sources_used.append("github")
            # Merge tech stack from GitHub languages
            if gh_data.get("github_languages"):
                existing = set(intel.tech_stack)
                for lang in gh_data["github_languages"]:
                    if lang not in existing:
                        intel.tech_stack.append(lang)
            # Add GitHub URL to social profiles
            if gh_data.get("github_url"):
                has_gh = any(p.platform == "github" for p in intel.social_profiles)
                if not has_gh:
                    intel.social_profiles.append(SocialProfile(platform="github", url=gh_data["github_url"]))
            if gh_data.get("github_description") and not intel.description:
                intel.description = gh_data["github_description"][:500]
            repos = gh_data.get("github_public_repos", 0)
            breakdown["github"] = SourceConfidence(
                score=min(0.5 + (min(repos, 50) / 50) * 0.4, 0.9),
                reason=f"org found, {repos} public repos, {len(gh_data.get('github_languages', []))} languages"
            )
        else:
            breakdown["github"] = SourceConfidence(score=0.0, reason="no org found")
    except Exception as e:
        logger.warning("GitHub failed for %s: %s", name, e)
        breakdown["github"] = SourceConfidence(score=0.0, reason=f"error: {e}")

    # 4d. OpenCorporates — legal registration data
    try:
        oc_data = await opencorporates.search_company(name)
        if oc_data:
            sources_used.append("opencorporates")
            if oc_data.get("incorporation_date") and not intel.founded:
                intel.founded = oc_data["incorporation_date"]
            if oc_data.get("registered_address") and not intel.headquarters:
                intel.headquarters = oc_data["registered_address"][:100]
            if oc_data.get("status"):
                pass  # could add to model later
            fields = sum(1 for k in ["legal_name", "jurisdiction", "incorporation_date", "company_type", "status"] if oc_data.get(k))
            breakdown["opencorporates"] = SourceConfidence(
                score=min(0.4 + fields * 0.1, 0.8),
                reason=f"registered in {oc_data.get('jurisdiction', '?')}, {fields} fields"
            )
        else:
            breakdown["opencorporates"] = SourceConfidence(score=0.0, reason="no registration found")
    except Exception as e:
        logger.warning("OpenCorporates failed for %s: %s", name, e)
        breakdown["opencorporates"] = SourceConfidence(score=0.0, reason=f"error: {e}")


    # 5. Find competitors — extract from search results + wikipedia + focused query
    try:
        from .competitors import _extract_from_text, _is_valid_competitor
        comp_candidates: dict[str, int] = {}
        
        # Extract from existing search results (step 1)
        if search_results:
            for r in search_results:
                text = f"{r.get('title', '')}. {r.get('body', '')}"
                extracted = _extract_from_text(text, name)
                for cname, score in extracted.items():
                    comp_candidates[cname] = comp_candidates.get(cname, 0) + score
        
        # Extract company names mentioned in Wikipedia summary (strict: use _extract_from_text)
        if intel.description:
            extracted = _extract_from_text(intel.description, name)
            for cname, score in extracted.items():
                comp_candidates[cname] = comp_candidates.get(cname, 0) + score
        
        # Focused competitor search
        comp_results = await search.search_web(f"{name} competitors alternatives", max_results=5)
        if comp_results:
            for r in comp_results:
                text = f"{r.get('title', '')}. {r.get('body', '')}"
                extracted = _extract_from_text(text, name)
                for cname, score in extracted.items():
                    comp_candidates[cname] = comp_candidates.get(cname, 0) + score
        
        ranked = sorted(comp_candidates.items(), key=lambda x: x[1], reverse=True)
        # Only include competitors with score >= 2 (mentioned in at least 2 contexts)
        intel.top_competitors = [n for n, s in ranked if s >= 2][:5]
        if intel.top_competitors:
            breakdown["competitor_extraction"] = SourceConfidence(
                score=min(0.4 + len(intel.top_competitors) * 0.1, 0.8),
                reason=f"{len(intel.top_competitors)} competitors identified"
            )
    except Exception as e:
        logger.warning("Competitor search failed for %s: %s", name, e)
        breakdown["competitor_extraction"] = SourceConfidence(score=0.0, reason=f"error: {e}")

    # 6. Find key people
    try:
        people_results = await search.search_web(f"{name} CEO founder leadership team", max_results=3)
        people = []
        import re
        cxo_patterns = [
            r'(?:CEO|Chief Executive Officer)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)',
            r'([A-Z][a-z]+ [A-Z][a-z]+)[\s,]+(?:CEO|Chief Executive|founder|co-founder)',
            r'(?:CTO|Chief Technology Officer)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)',
            r'([A-Z][a-z]+ [A-Z][a-z]+)[\s,]+(?:CTO|Chief Technology)',
            r'(?:CFO|Chief Financial Officer)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)',
        ]
        for r in people_results:
            text = f"{r.get('title', '')} {r.get('body', '')}"
            for pattern in cxo_patterns:
                matches = re.findall(pattern, text)
                for m in matches:
                    if m.lower() != name.lower() and len(m.split()) >= 2:
                        role = "Leadership"
                        if "CEO" in pattern or "founder" in pattern:
                            role = "CEO/Founder"
                        elif "CTO" in pattern:
                            role = "CTO"
                        elif "CFO" in pattern:
                            role = "CFO"
                        people.append(KeyPerson(name=m, role=role))
        # Deduplicate
        seen = set()
        unique_people = []
        for p in people:
            if p.name not in seen:
                seen.add(p.name)
                unique_people.append(p)
        intel.key_people = unique_people[:5]
        if unique_people:
            breakdown["people_search"] = SourceConfidence(
                score=min(0.4 + len(unique_people) * 0.15, 0.8),
                reason=f"{len(unique_people)} key people identified"
            )
    except Exception as e:
        logger.warning("People search failed for %s: %s", name, e)

    # 7. Social profiles (if not found from website)
    if not intel.social_profiles:
        try:
            social_results = await social.find_social_profiles(name)
            intel.social_profiles = [SocialProfile(**p) for p in social_results]
            if social_results:
                sources_used.append("social_search")
                breakdown["social_profiles"] = SourceConfidence(
                    score=min(0.5 + len(social_results) * 0.1, 0.8),
                    reason=f"{len(social_results)} profiles found"
                )
        except Exception as e:
            logger.warning("Social search failed for %s: %s", name, e)

    # Determine industry from description
    if intel.description:
        desc_lower = intel.description.lower()
        industry_keywords = {
            "software": "Software & Technology",
            "fintech": "Financial Technology",
            "healthcare": "Healthcare",
            "e-commerce": "E-Commerce",
            "ecommerce": "E-Commerce",
            "artificial intelligence": "Artificial Intelligence",
            "ai": "Artificial Intelligence",
            "saas": "SaaS",
            "cloud": "Cloud Computing",
            "cybersecurity": "Cybersecurity",
            "biotechnology": "Biotechnology",
            "automobile": "Automotive",
            "automotive": "Automotive",
            "media": "Media & Entertainment",
            "education": "Education Technology",
            "real estate": "Real Estate",
            "food": "Food & Beverage",
            "energy": "Energy",
            "retail": "Retail",
            "logistics": "Logistics & Supply Chain",
            "telecommunications": "Telecommunications",
            "gaming": "Gaming",
            "social media": "Social Media",
            "blockchain": "Blockchain & Crypto",
            "crypto": "Blockchain & Crypto",
        }
        for keyword, industry in industry_keywords.items():
            if keyword in desc_lower:
                intel.industry = industry
                break

    # Compute overall confidence — only count sources that returned data (score > 0)
    # Failed sources appear in breakdown for transparency but don't drag down the grade
    _weights = {"wikipedia": 3, "company_website": 2, "newsapi": 2, "duckduckgo": 1,
                "funding_intelligence": 3, "github": 2, "opencorporates": 1,
                "competitor_extraction": 1, "people_search": 1, "social_profiles": 1}
    total_weight = 0
    weighted_sum = 0.0
    for src, sc in breakdown.items():
        if sc.score > 0:  # Only count sources that returned data
            w = _weights.get(src, 1)
            total_weight += w
            weighted_sum += sc.score * w
    intel.confidence = round(weighted_sum / total_weight, 2) if total_weight > 0 else 0.0
    intel.confidence_breakdown = breakdown
    intel.sources_used = sources_used
    intel.sources_failed = sources_failed
    intel.data_freshness = datetime.now(timezone.utc).isoformat()

    intel.data_quality_grade = compute_grade(intel.confidence)

    result = intel.model_dump()
    set_cached("scout_company", result, name=name, domain=domain)
    return result
