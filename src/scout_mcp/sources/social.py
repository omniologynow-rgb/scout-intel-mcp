"""Social media profile detection and data extraction."""

import logging
import re

from .search import search_web

logger = logging.getLogger(__name__)


async def find_social_profiles(entity_name: str) -> list[dict]:
    """Find social media profiles for a company or person."""
    profiles = []
    platforms = {
        "linkedin": f"{entity_name} site:linkedin.com",
        "twitter": f"{entity_name} site:twitter.com OR site:x.com",
        "github": f"{entity_name} site:github.com",
        "crunchbase": f"{entity_name} site:crunchbase.com",
    }

    for platform, query in platforms.items():
        try:
            results = await search_web(query, max_results=2)
            if results:
                top = results[0]
                url = top.get("href", "")
                if url:
                    profiles.append({"platform": platform, "url": url})
        except Exception as e:
            logger.debug("Social search failed for %s/%s: %s", entity_name, platform, e)

    return profiles


async def detect_social_from_links(social_links: dict) -> list[dict]:
    """Convert scraped social links dict to standardized profiles."""
    profiles = []
    for platform, url in social_links.items():
        if url and isinstance(url, str):
            if not url.startswith("http"):
                url = f"https://{url}"
            profiles.append({"platform": platform, "url": url})
    return profiles
