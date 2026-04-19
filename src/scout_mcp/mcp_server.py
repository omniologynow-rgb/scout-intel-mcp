"""Scout MCP — FastMCP Server Entry Point.

This is the main MCP server that registers all 6 intelligence tools
for use by AI agents via Claude Desktop, Cursor, VS Code, etc.
"""

from fastmcp import FastMCP

from .tools.company import scout_company as _scout_company
from .tools.competitors import scout_competitors as _scout_competitors
from .tools.trends import scout_trends as _scout_trends
from .tools.market import scout_market as _scout_market
from .tools.product import scout_product as _scout_product
from .tools.person import scout_person as _scout_person
from .tools.batch import scout_batch as _scout_batch
from .auth import check_rate_limit, is_pro_tier

mcp = FastMCP("Scout MCP")


@mcp.tool()
async def scout_company(name: str, domain: str | None = None) -> dict:
    """Get structured intelligence on any company.

    Returns: industry, funding, tech stack, competitors, recent news, key people.

    Args:
        name: Company name (e.g., "Stripe", "OpenAI")
        domain: Optional company domain (e.g., "stripe.com"). Auto-detected if not provided.
    """
    return await _scout_company(name=name, domain=domain)


@mcp.tool()
async def scout_market(query: str, depth: str = "summary") -> dict:
    """Research any market or industry.

    Returns: market size, growth rate, CAGR, key players, trends, risks.

    Args:
        query: Market/industry to research (e.g., "AI SaaS", "electric vehicles")
        depth: "summary" for quick overview, "detailed" for deeper analysis
    """
    return await _scout_market(query=query, depth=depth)


@mcp.tool()
async def scout_competitors(company_or_product: str, max: int = 10) -> dict:
    """Find and analyze competitors for any company or product.

    Returns: list of competitors with positioning, pricing, strengths, weaknesses.

    Args:
        company_or_product: Name of company or product (e.g., "Notion", "Figma")
        max: Maximum number of competitors to return (default 10)
    """
    return await _scout_competitors(company_or_product=company_or_product, max=max)


@mcp.tool()
async def scout_trends(topic: str, timeframe: str = "7d") -> dict:
    """Track trends and sentiment on any topic.

    Returns: sentiment score, trending direction, key developments, related topics.

    Args:
        topic: Topic to track (e.g., "generative AI", "remote work")
        timeframe: Time window — "1d", "7d", "30d", "1y" (default "7d")
    """
    return await _scout_trends(topic=topic, timeframe=timeframe)


@mcp.tool()
async def scout_product(name: str) -> dict:
    """Get intelligence on any product.

    Returns: category, pricing, ratings, features, alternatives, recent updates.

    Args:
        name: Product name (e.g., "Slack", "Linear", "Vercel")
    """
    return await _scout_product(name=name)


@mcp.tool()
async def scout_person(name: str, company: str | None = None) -> dict:
    """Get intelligence on a public figure. PRO tier only.

    Returns: current role, background, social profiles, recent activity, achievements.

    Args:
        name: Person's name (e.g., "Sam Altman", "Jensen Huang")
        company: Optional company context (e.g., "OpenAI")
    """
    return await _scout_person(name=name, company=company)



@mcp.tool()
async def scout_batch(queries: list[dict], max_parallel: int = 5) -> dict:
    """Run multiple scout queries in parallel. Perfect for competitive
    landscape analysis and bulk research.

    Each query is: {"tool": "company|market|competitors|trends|product", "params": {...}}

    Example:
      queries=[
        {"tool": "company", "params": {"name": "Stripe"}},
        {"tool": "company", "params": {"name": "OpenAI"}},
      ]

    Returns: results array, comparison table, timing, overall grade.

    Args:
        queries: List of {"tool": str, "params": dict} objects
        max_parallel: Max concurrent queries (default 5)
    """
    return await _scout_batch(queries=queries, max_parallel=max_parallel)


# Entry point for: fastmcp dev src/scout_mcp/mcp_server.py
# or: python -m scout_mcp.mcp_server
if __name__ == "__main__":
    mcp.run()
