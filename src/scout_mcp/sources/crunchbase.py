"""Company funding data extraction — multi-source approach.

Since Crunchbase blocks direct scraping (Cloudflare), this module
extracts funding data from multiple free sources:
1. DuckDuckGo search snippets (e.g., "Stripe crunchbase funding")
2. Growjo public profiles (funding amounts, employee counts)
3. News search for funding round announcements
4. Wikipedia funding mentions

All sources are free, no API keys needed.
"""

import logging
import re
import httpx
from bs4 import BeautifulSoup

from ..config import REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


async def _search_funding_snippets(company_name: str) -> dict:
    """Extract funding data from DuckDuckGo search snippets about the company."""
    from .search import search_web

    result = {}
    queries = [
        f"{company_name} total funding raised valuation",
        f"{company_name} series funding round investors",
    ]

    for query in queries:
        try:
            results = await search_web(query, max_results=5)
            for r in results:
                text = f"{r.get('title', '')} {r.get('body', '')}"

                # Extract total funding: "$X billion/million"
                if not result.get("funding_total"):
                    funding_matches = re.findall(
                        r'\$[\d,.]+\s*(?:billion|million|B|M)',
                        text, re.IGNORECASE
                    )
                    if funding_matches:
                        # Pick the largest amount mentioned (likely total funding)
                        result["funding_total"] = funding_matches[0]

                # Extract valuation
                if not result.get("valuation"):
                    val_match = re.search(
                        r'(?:valued?\s+at|valuation\s+(?:of\s+)?)\$?([\d,.]+\s*(?:billion|million|B|M))',
                        text, re.IGNORECASE
                    )
                    if val_match:
                        result["valuation"] = "$" + val_match.group(1).strip()

                # Extract latest round: "Series X"
                if not result.get("last_round"):
                    round_match = re.search(
                        r'(Series\s+[A-Z]\+?(?:\s+(?:funding|round))?)',
                        text, re.IGNORECASE
                    )
                    if round_match:
                        result["last_round"] = round_match.group(1).strip()

                # Extract round amount
                if not result.get("last_round_amount") and result.get("last_round"):
                    amt_match = re.search(
                        rf'{re.escape(result["last_round"])}[^.]*?\$?([\d,.]+\s*(?:billion|million|B|M))',
                        text, re.IGNORECASE
                    )
                    if amt_match:
                        result["last_round_amount"] = "$" + amt_match.group(1).strip()

                # Extract employee count
                if not result.get("employee_range"):
                    emp_match = re.search(
                        r'(\d{1,3}(?:,\d{3})*(?:\s*[-–]\s*\d{1,3}(?:,\d{3})*)?)\s*(?:employees?|staff|people|team members)',
                        text, re.IGNORECASE
                    )
                    if emp_match:
                        result["employee_range"] = emp_match.group(1).strip()

                # Extract investors
                if not result.get("investors"):
                    inv_match = re.search(
                        r'(?:investors?\s+(?:include|are|:)|(?:led|backed)\s+by)\s+([^.]{10,200})',
                        text, re.IGNORECASE
                    )
                    if inv_match:
                        inv_text = inv_match.group(1)
                        investors = [i.strip() for i in re.split(r'[,;]|\s+and\s+', inv_text) if i.strip() and len(i.strip()) > 2]
                        result["investors"] = investors[:8]

        except Exception as e:
            logger.debug("Funding snippet search failed for '%s': %s", query, e)

    return result


async def _scrape_growjo(company_name: str) -> dict:
    """Try to get funding/employee data from Growjo (free, public)."""
    slug = company_name.lower().replace(" ", "-").replace(".", "")
    url = f"https://growjo.com/company/{slug}"
    result = {}

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            })
            if resp.status_code != 200:
                return {}

            soup = BeautifulSoup(resp.text, "lxml")
            text = soup.get_text(separator=" ", strip=True)

            # Extract funding
            funding_match = re.search(r'(?:Total\s+Funding|Funding)[:\s]*\$?([\d,.]+[BMK]?(?:\s*(?:billion|million))?)', text, re.IGNORECASE)
            if funding_match:
                result["funding_total"] = "$" + funding_match.group(1).strip()

            # Extract employees
            emp_match = re.search(r'(?:Employees?|Team\s+Size)[:\s]*([\d,]+(?:\s*[-–]\s*[\d,]+)?)', text, re.IGNORECASE)
            if emp_match:
                result["employee_range"] = emp_match.group(1).strip()

            # Extract revenue estimate
            rev_match = re.search(r'(?:Revenue|Est\.?\s+Revenue)[:\s]*\$?([\d,.]+[BMK]?(?:\s*(?:billion|million))?)', text, re.IGNORECASE)
            if rev_match:
                result["estimated_revenue"] = "$" + rev_match.group(1).strip()

            if result:
                result["source_url"] = url
                logger.info("Growjo: extracted %d fields for '%s'", len(result), company_name)

    except Exception as e:
        logger.debug("Growjo scrape failed for '%s': %s", company_name, e)

    return result


async def _search_funding_news(company_name: str) -> dict:
    """Search news for recent funding announcements."""
    from .news_api import search_news

    result = {}
    try:
        articles = await search_news(f"{company_name} funding round raised", max_results=3, days_back=365)
        for art in articles:
            text = f"{art.get('headline', '')} {art.get('description', '')}"

            if not result.get("last_round"):
                round_match = re.search(r'(Series\s+[A-Z]\+?)', text, re.IGNORECASE)
                if round_match:
                    result["last_round"] = round_match.group(1)

            if not result.get("funding_total"):
                amt_match = re.search(r'(?:raised?|secures?|closes?)\s+\$?([\d,.]+\s*(?:billion|million|B|M))', text, re.IGNORECASE)
                if amt_match:
                    result["last_round_amount"] = "$" + amt_match.group(1).strip()

            if not result.get("recent_funding_headline"):
                if any(w in text.lower() for w in ["funding", "raised", "series", "round", "valuation"]):
                    result["recent_funding_headline"] = art.get("headline", "")

    except Exception as e:
        logger.debug("Funding news search failed for '%s': %s", company_name, e)

    return result


async def get_funding_data(company_name: str) -> dict:
    """Aggregate funding data from all available free sources.

    Returns merged dict with best available data from:
    - Search snippets (most reliable)
    - Growjo (employee/revenue estimates)
    - News articles (latest round info)
    """
    # Run all sources
    snippet_data = await _search_funding_snippets(company_name)
    growjo_data = await _scrape_growjo(company_name)
    news_data = await _search_funding_news(company_name)

    # Merge: snippets take priority, then news, then growjo
    merged = {}
    sources_hit = []

    for key in ["funding_total", "valuation", "last_round", "last_round_amount",
                "employee_range", "investors", "estimated_revenue", "recent_funding_headline"]:
        val = snippet_data.get(key) or news_data.get(key) or growjo_data.get(key)
        if val:
            merged[key] = val

    if snippet_data:
        sources_hit.append("search_snippets")
    if growjo_data:
        sources_hit.append("growjo")
    if news_data:
        sources_hit.append("funding_news")

    merged["_funding_sources"] = sources_hit
    data_points = len([v for k, v in merged.items() if not k.startswith("_") and v])
    merged["_data_points"] = data_points

    logger.info("Funding data for '%s': %d data points from %s", company_name, data_points, sources_hit)
    return merged
