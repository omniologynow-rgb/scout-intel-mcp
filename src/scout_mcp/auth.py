"""API key authentication and tier-based rate limiting for Scout MCP."""

import time
import logging
from typing import Optional

from .config import SCOUT_API_KEY, TIER_LIMITS, STRIPE_LINKS

logger = logging.getLogger(__name__)

# In-memory rate tracking: {api_key: {"count": int, "window_start": float}}
_rate_tracker: dict[str, dict] = {}

# Known API keys -> tier mapping (in production, this would be a database)
# Format: {api_key: tier_name}
_api_keys: dict[str, str] = {}

# Register the server's own key if set
if SCOUT_API_KEY:
    _api_keys[SCOUT_API_KEY] = "scale"


def get_tier(api_key: Optional[str] = None) -> str:
    """Determine the tier for a given API key."""
    if not api_key:
        return "free"
    return _api_keys.get(api_key, "free")


def check_rate_limit(api_key: Optional[str] = None) -> dict:
    """Check and consume a rate limit token. Returns status dict."""
    tier = get_tier(api_key)
    limit = TIER_LIMITS[tier]
    key_id = api_key or "__free__"
    now = time.time()

    if key_id not in _rate_tracker:
        _rate_tracker[key_id] = {"count": 0, "window_start": now}

    tracker = _rate_tracker[key_id]

    # Reset window if 24h has passed
    if now - tracker["window_start"] > 86400:
        tracker["count"] = 0
        tracker["window_start"] = now

    if tracker["count"] >= limit:
        # Include upgrade link based on current tier
        upgrade_link = None
        if tier == "free":
            upgrade_link = STRIPE_LINKS.get("pro")
        elif tier == "pro":
            upgrade_link = STRIPE_LINKS.get("scale")

        result = {
            "allowed": False,
            "tier": tier,
            "limit": limit,
            "remaining": 0,
            "resets_in": int(86400 - (now - tracker["window_start"])),
        }
        if upgrade_link:
            result["upgrade_url"] = upgrade_link
            result["upgrade_message"] = (
                f"Rate limit reached for {tier} tier ({limit}/day). "
                f"Upgrade here: {upgrade_link}"
            )
        return result

    tracker["count"] += 1
    remaining = limit - tracker["count"]

    return {
        "allowed": True,
        "tier": tier,
        "limit": limit,
        "remaining": remaining,
    }


def is_pro_tier(api_key: Optional[str] = None) -> bool:
    """Check if the API key has pro or scale tier access."""
    tier = get_tier(api_key)
    return tier in ("pro", "scale")
