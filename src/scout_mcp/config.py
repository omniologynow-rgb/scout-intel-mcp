"""Configuration and settings for Scout MCP."""

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent.parent.parent
load_dotenv(ROOT_DIR / '.env')

# API Keys
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")
SCOUT_API_KEY = os.environ.get("SCOUT_API_KEY", "")

# Cache settings
CACHE_TTL_SECONDS = 86400  # 24 hours

# Rate limit tiers
TIER_LIMITS = {
    "free": 50,
    "pro": 1000,
    "scale": 10000,
}

TIER_PRICING = {
    "free": "$0/mo",
    "pro": "$29/mo",
    "scale": "$99/mo",
}

# Stripe payment links for upgrade
STRIPE_LINKS = {
    "pro": "https://buy.stripe.com/7sY6oJgFddm9cA8crd4wM02",
    "scale": "https://buy.stripe.com/8x2eVf60z5TH43Cbn94wM03",
}

# HTTP settings
REQUEST_TIMEOUT = 15
MAX_RETRIES = 2
USER_AGENT = "ScoutMCP/1.0 (Business Intelligence Bot)"

# Search settings
MAX_SEARCH_RESULTS = 10
MAX_NEWS_RESULTS = 5
MAX_COMPETITORS = 10

# Wikipedia
WIKI_LANGUAGE = "en"
WIKI_USER_AGENT = "ScoutMCP/1.0 (https://github.com/omniologynow-rgb/scoutMCP)"
