"""scout_batch tool — Run multiple scout queries in parallel.

Accepts a list of queries and runs them concurrently, returning
a structured comparison table. Perfect for competitive landscape
analysis, market mapping, or bulk research.
"""

import asyncio
import logging
from datetime import datetime, timezone

from .company import scout_company
from .competitors import scout_competitors
from .trends import scout_trends
from .market import scout_market
from .product import scout_product

logger = logging.getLogger(__name__)

# Map tool names to functions
_TOOL_MAP = {
    "company": scout_company,
    "competitors": scout_competitors,
    "trends": scout_trends,
    "market": scout_market,
    "product": scout_product,
}


async def _run_single(tool_name: str, params: dict) -> dict:
    """Run a single scout tool with error handling."""
    func = _TOOL_MAP.get(tool_name)
    if not func:
        return {"error": f"Unknown tool: {tool_name}", "params": params}

    try:
        result = await func(**params)
        return result
    except Exception as e:
        logger.warning("Batch item failed (%s, %s): %s", tool_name, params, e)
        return {
            "error": str(e)[:200],
            "params": params,
            "confidence": 0.0,
            "data_quality_grade": "F",
        }


async def scout_batch(
    queries: list[dict],
    max_parallel: int = 5,
) -> dict:
    """Run multiple scout queries in parallel and return comparison.

    Each query is a dict with:
      - tool: "company" | "competitors" | "trends" | "market" | "product"
      - params: dict of parameters for that tool

    Example:
      queries = [
        {"tool": "company", "params": {"name": "Stripe"}},
        {"tool": "company", "params": {"name": "OpenAI"}},
        {"tool": "company", "params": {"name": "Anthropic"}},
      ]

    Returns:
      - results: list of tool responses (same order as input)
      - summary: comparison table with key fields
      - timing: total seconds and per-query timing
      - overall_grade: worst grade across all results
    """
    start_time = datetime.now(timezone.utc)

    if not queries:
        return {"error": "No queries provided", "results": []}

    # Cap parallel execution
    effective_parallel = min(max_parallel, len(queries), 5)

    # Run queries in parallel batches
    semaphore = asyncio.Semaphore(effective_parallel)

    async def _bounded_run(idx: int, query: dict) -> tuple[int, dict, float]:
        async with semaphore:
            q_start = asyncio.get_event_loop().time()
            tool = query.get("tool", "company")
            params = query.get("params", {})
            result = await _run_single(tool, params)
            q_time = asyncio.get_event_loop().time() - q_start
            return idx, result, q_time

    tasks = [_bounded_run(i, q) for i, q in enumerate(queries)]
    completed = await asyncio.gather(*tasks, return_exceptions=True)

    # Sort results back into original order
    results = [None] * len(queries)
    timings = [0.0] * len(queries)
    for item in completed:
        if isinstance(item, Exception):
            continue
        idx, result, q_time = item
        results[idx] = result
        timings[idx] = round(q_time, 2)

    # Fill in any None results (from exceptions)
    for i in range(len(results)):
        if results[i] is None:
            results[i] = {"error": "Query failed", "confidence": 0.0, "data_quality_grade": "F"}

    # Build comparison summary
    summary = _build_comparison(queries, results)

    # Calculate overall grade (worst across all)
    grades = [r.get("data_quality_grade", "F") for r in results if not r.get("error")]
    grade_order = ["A+", "A", "B", "C", "D", "F"]
    overall_grade = "F"
    if grades:
        overall_grade = min(grades, key=lambda g: -grade_order.index(g) if g in grade_order else 99)

    end_time = datetime.now(timezone.utc)
    total_seconds = (end_time - start_time).total_seconds()

    return {
        "query_count": len(queries),
        "results": results,
        "comparison": summary,
        "overall_grade": overall_grade,
        "timing": {
            "total_seconds": round(total_seconds, 2),
            "per_query_seconds": timings,
            "parallel_efficiency": round(sum(timings) / total_seconds, 2) if total_seconds > 0 else 1.0,
        },
        "data_freshness": end_time.isoformat(),
    }


def _build_comparison(queries: list[dict], results: list[dict]) -> list[dict]:
    """Build a comparison table from batch results."""
    comparison = []

    for query, result in zip(queries, results):
        tool = query.get("tool", "company")
        params = query.get("params", {})
        entry = {
            "tool": tool,
            "query": params.get("name") or params.get("query") or params.get("topic") or params.get("company_or_product") or str(params),
            "grade": result.get("data_quality_grade", "F"),
            "confidence": result.get("confidence", 0.0),
        }

        if result.get("error"):
            entry["status"] = "error"
            entry["error"] = result["error"]
        else:
            entry["status"] = "success"

        # Tool-specific comparison fields
        if tool == "company":
            entry["industry"] = result.get("industry")
            entry["headquarters"] = result.get("headquarters")
            entry["funding"] = result.get("funding", {}).get("total_funding") if isinstance(result.get("funding"), dict) else None
            entry["tech_stack"] = result.get("tech_stack", [])[:5]
            entry["competitors"] = result.get("top_competitors", [])[:3]
        elif tool == "competitors":
            entry["competitor_count"] = len(result.get("competitors", []))
            entry["top_3"] = [c.get("name") for c in result.get("competitors", [])[:3]]
        elif tool == "trends":
            entry["sentiment"] = result.get("sentiment", {}).get("label")
            entry["direction"] = result.get("trending_direction")
            entry["development_count"] = len(result.get("key_developments", []))
        elif tool == "market":
            entry["market_size"] = result.get("market_size")
            entry["cagr"] = result.get("cagr")
            entry["player_count"] = len(result.get("key_players", []))
        elif tool == "product":
            entry["category"] = result.get("category")
            entry["pricing"] = result.get("pricing")
            entry["alternative_count"] = len(result.get("alternatives", []))

        comparison.append(entry)

    return comparison
