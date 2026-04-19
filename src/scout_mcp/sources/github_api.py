"""GitHub API integration — free, no key required for public data.

Fetches public organization/company data:
- Repo count, primary language
- Description, location, website
- Member count, created date
- Top repositories with stars/forks
"""

import logging
import httpx

from ..config import REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

_GH_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "ScoutMCP/0.1",
    "X-GitHub-Api-Version": "2022-11-28",
}


async def get_org(org_name: str) -> dict:
    """Fetch public GitHub organization data.

    Returns dict with: name, description, location, blog, public_repos,
    followers, created_at, avatar_url, html_url.
    """
    url = f"https://api.github.com/orgs/{org_name}"
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers=_GH_HEADERS) as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                logger.info("GitHub: org '%s' not found", org_name)
                return {}
            if resp.status_code != 200:
                logger.info("GitHub: %d for org '%s'", resp.status_code, org_name)
                return {}

            data = resp.json()
            result = {
                "github_org": data.get("login"),
                "github_name": data.get("name"),
                "github_description": data.get("description"),
                "github_location": data.get("location"),
                "github_blog": data.get("blog"),
                "github_public_repos": data.get("public_repos"),
                "github_followers": data.get("followers"),
                "github_created_at": data.get("created_at"),
                "github_url": data.get("html_url"),
                "github_avatar": data.get("avatar_url"),
            }
            # Filter out None values
            result = {k: v for k, v in result.items() if v is not None}
            logger.info("GitHub: found org '%s' with %d public repos", org_name, data.get("public_repos", 0))
            return result

    except Exception as e:
        logger.warning("GitHub org lookup failed for '%s': %s", org_name, e)
        return {}


async def get_top_repos(org_name: str, limit: int = 5) -> list[dict]:
    """Fetch top public repos for an org, sorted by stars.

    Returns list of {name, description, stars, forks, language, url}.
    """
    url = f"https://api.github.com/orgs/{org_name}/repos"
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers=_GH_HEADERS) as client:
            resp = await client.get(url, params={"sort": "pushed", "per_page": 30, "type": "public"})
            if resp.status_code != 200:
                return []

            repos = resp.json()
            if not isinstance(repos, list):
                return []

            # Sort by stars descending
            repos.sort(key=lambda r: r.get("stargazers_count", 0), reverse=True)

            result = []
            for repo in repos[:limit]:
                result.append({
                    "name": repo.get("name"),
                    "description": (repo.get("description") or "")[:200],
                    "stars": repo.get("stargazers_count", 0),
                    "forks": repo.get("forks_count", 0),
                    "language": repo.get("language"),
                    "url": repo.get("html_url"),
                })
            logger.info("GitHub: %d top repos for '%s'", len(result), org_name)
            return result

    except Exception as e:
        logger.warning("GitHub repos lookup failed for '%s': %s", org_name, e)
        return []


async def search_org(company_name: str) -> dict:
    """Search for a company's GitHub org and return combined data.

    Tries common slug patterns: lowercase, no spaces, hyphenated.
    """
    # Try common slug variations
    slugs = [
        company_name.lower().replace(" ", ""),
        company_name.lower().replace(" ", "-"),
        company_name.lower(),
    ]
    # Remove duplicates while preserving order
    seen = set()
    unique_slugs = []
    for s in slugs:
        if s not in seen:
            seen.add(s)
            unique_slugs.append(s)

    for slug in unique_slugs:
        org_data = await get_org(slug)
        if org_data:
            # Also get top repos
            repos = await get_top_repos(slug, limit=5)
            if repos:
                org_data["top_repos"] = repos
                # Extract tech stack from repo languages
                languages = set()
                for repo in repos:
                    lang = repo.get("language")
                    if lang:
                        languages.add(lang)
                org_data["github_languages"] = list(languages)
            return org_data

    logger.info("GitHub: no org found for '%s' (tried: %s)", company_name, unique_slugs)
    return {}
