"""Wikipedia API integration — free, no key needed."""

import logging
import wikipediaapi

from ..config import WIKI_LANGUAGE, WIKI_USER_AGENT

logger = logging.getLogger(__name__)

_wiki = wikipediaapi.Wikipedia(
    user_agent=WIKI_USER_AGENT,
    language=WIKI_LANGUAGE,
)


async def get_summary(title: str) -> dict | None:
    """Get Wikipedia summary for a given title. Returns dict or None."""
    try:
        page = _wiki.page(title)
        if not page.exists():
            # Try search-friendly variants
            variants = [
                title.replace(" Inc", "").replace(" LLC", "").replace(" Corp", "").strip(),
                f"{title} (company)",
                f"{title} (software)",
                f"{title} (service)",
            ]
            for variant in variants:
                page = _wiki.page(variant)
                if page.exists():
                    break
            else:
                logger.info("Wikipedia: No page found for '%s'", title)
                return None

        summary = page.summary
        # Check for disambiguation pages
        if summary and "may refer to" in summary.lower():
            # Try company-specific page
            page = _wiki.page(f"{title} (company)")
            if not page.exists():
                page = _wiki.page(f"{title} (software)")
            if not page.exists():
                logger.info("Wikipedia: '%s' is a disambiguation page", title)
                return None
            summary = page.summary
        # Extract sections for structured data
        sections = [s.title for s in page.sections if s.title]

        return {
            "title": page.title,
            "summary": summary[:2000] if summary else None,
            "url": page.fullurl,
            "sections": sections[:20],
            "categories": list(page.categories.keys())[:10],
        }
    except Exception as e:
        logger.warning("Wikipedia lookup failed for '%s': %s", title, e)
        return None


async def extract_company_info(title: str) -> dict:
    """Extract structured company info from Wikipedia page."""
    data = await get_summary(title)
    if not data:
        return {}

    info = {"wikipedia_summary": data.get("summary", ""), "wikipedia_url": data.get("url", "")}
    summary_lower = (data.get("summary") or "").lower()

    # Try to extract founded year
    import re
    founded_match = re.search(r'founded\s+(?:in\s+)?(\d{4})', summary_lower)
    if founded_match:
        info["founded"] = founded_match.group(1)

    # Try to extract headquarters
    hq_match = re.search(r'headquartered\s+in\s+([^.,:]+)', summary_lower)
    if not hq_match:
        hq_match = re.search(r'based\s+in\s+([^.,:]+)', summary_lower)
    if hq_match:
        info["headquarters"] = hq_match.group(1).strip().title()

    return info
