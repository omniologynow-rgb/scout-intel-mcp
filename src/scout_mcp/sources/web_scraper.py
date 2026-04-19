"""Intelligent web scraping with httpx + BeautifulSoup."""

import logging
import re
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

from ..config import REQUEST_TIMEOUT, USER_AGENT

logger = logging.getLogger(__name__)

_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
    return _http_client


async def fetch_page(url: str) -> str | None:
    """Fetch a webpage and return its HTML content."""
    try:
        client = _get_client()
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return None


async def scrape_company_website(domain: str) -> dict:
    """Scrape a company website for structured information."""
    url = f"https://{domain}" if not domain.startswith("http") else domain
    html = await fetch_page(url)
    if not html:
        return {}

    soup = BeautifulSoup(html, "lxml")
    info = {}

    # Title / description
    title_tag = soup.find("title")
    if title_tag:
        info["site_title"] = title_tag.get_text(strip=True)

    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc:
        info["meta_description"] = meta_desc.get("content", "")

    # OG tags
    og_desc = soup.find("meta", attrs={"property": "og:description"})
    if og_desc:
        info["og_description"] = og_desc.get("content", "")

    # Find social links
    social_patterns = {
        "twitter": r"twitter\.com/|x\.com/",
        "linkedin": r"linkedin\.com/",
        "github": r"github\.com/",
        "facebook": r"facebook\.com/",
        "youtube": r"youtube\.com/",
        "instagram": r"instagram\.com/",
    }
    social_links = {}
    for link in soup.find_all("a", href=True):
        href = link["href"]
        for platform, pattern in social_patterns.items():
            if re.search(pattern, href) and platform not in social_links:
                social_links[platform] = href
    info["social_links"] = social_links

    # Try to find tech indicators
    tech_hints = set()
    scripts = soup.find_all("script", src=True)
    for s in scripts:
        src = s["src"].lower()
        if "react" in src:
            tech_hints.add("React")
        if "angular" in src:
            tech_hints.add("Angular")
        if "vue" in src:
            tech_hints.add("Vue.js")
        if "jquery" in src:
            tech_hints.add("jQuery")
        if "bootstrap" in src:
            tech_hints.add("Bootstrap")
        if "tailwind" in src:
            tech_hints.add("Tailwind CSS")
        if "next" in src:
            tech_hints.add("Next.js")
        if "gatsby" in src:
            tech_hints.add("Gatsby")
        if "wordpress" in src or "wp-" in src:
            tech_hints.add("WordPress")

    # Check meta generator
    gen = soup.find("meta", attrs={"name": "generator"})
    if gen:
        tech_hints.add(gen.get("content", ""))

    info["tech_stack_hints"] = list(tech_hints)

    # Extract key text sections
    headings = []
    for h in soup.find_all(["h1", "h2"], limit=10):
        text = h.get_text(strip=True)
        if text and len(text) < 200:
            headings.append(text)
    info["key_headings"] = headings

    return info


async def scrape_page_text(url: str, max_chars: int = 5000) -> str:
    """Fetch a page and extract its main text content."""
    html = await fetch_page(url)
    if not html:
        return ""

    soup = BeautifulSoup(html, "lxml")

    # Remove script, style, nav, footer
    for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    # Clean whitespace
    text = re.sub(r'\s+', ' ', text)
    return text[:max_chars]


async def find_pricing_page(domain: str) -> dict:
    """Try to find and scrape a pricing page."""
    base_url = f"https://{domain}" if not domain.startswith("http") else domain
    pricing_paths = ["/pricing", "/plans", "/price", "/packages"]

    for path in pricing_paths:
        url = urljoin(base_url, path)
        html = await fetch_page(url)
        if html:
            soup = BeautifulSoup(html, "lxml")
            # Extract pricing text
            for tag in soup.find_all(["script", "style", "nav", "footer"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)
            text = re.sub(r'\s+', ' ', text)
            if len(text) > 100:
                return {"pricing_url": url, "pricing_text": text[:3000]}

    return {}
