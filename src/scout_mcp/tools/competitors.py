"""scout_competitors tool — Find and analyze competitors.

Strategy:
1. Multiple targeted search queries to find "alternatives" pages
2. Scrape the top results pages and parse structured competitor lists
3. Cross-reference names across sources (more mentions = higher confidence)
4. Aggressive false-positive filtering via expanded stop-word list
5. Enrich top competitors with per-competitor detail searches
"""

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from ..models import CompetitorIntel, CompetitorEntry, SourceConfidence, compute_grade
from ..sources import search, web_scraper
from ..cache import get_cached, set_cached

logger = logging.getLogger(__name__)

# ── Expanded stop words: sentence-starters, generic verbs, adjectives, etc. ──
_STOP_WORDS = {
    # determiners / pronouns / prepositions
    "the", "and", "for", "with", "from", "this", "that", "they", "their",
    "have", "has", "had", "been", "were", "was", "are", "not", "but", "what",
    "which", "when", "where", "who", "how", "can", "will", "just", "more",
    "also", "than", "other", "some", "its", "all", "one", "two", "three",
    "new", "top", "best", "free", "most", "here", "like", "over", "into",
    "about", "each", "only", "very", "well", "back", "our", "you", "your",
    "both", "many", "much", "own", "why", "get", "use", "make", "see",
    "try", "let", "say", "any", "may", "find", "take", "want", "give",
    "first", "last", "great", "high", "old", "big", "small", "large",
    "good", "right", "look", "think", "still", "should", "could", "would",
    "every", "under", "need", "between", "another", "however", "without",
    # tech / article / listicle words
    "compare", "comparison", "review", "reviews", "alternative", "alternatives",
    "competitor", "competitors", "versus", "list", "article", "blog", "post",
    "read", "learn", "guide", "help", "tool", "tools", "software", "platform",
    "service", "solution", "company", "product", "feature", "features", "pricing",
    "price", "plan", "plans", "year", "month", "day", "time", "people", "team",
    "user", "users", "customer", "customers", "business", "market", "industry",
    "world", "global", "data", "using", "used", "based", "while", "offers",
    "offer", "include", "including", "available", "different", "similar",
    "start", "way", "work", "working", "works", "things", "thing",
    "check", "explore", "detailed", "complete", "full", "overall", "key",
    "main", "major", "popular", "known", "common", "general", "specific",
    "update", "updated", "latest", "current", "today", "now",
    # sentence-starters that get caught by uppercase regex
    "according", "additionally", "although", "because", "before", "below",
    "besides", "certainly", "clearly", "compared", "considering", "despite",
    "during", "essentially", "eventually", "finally", "furthermore",
    "generally", "hence", "importantly", "indeed", "instead", "likewise",
    "meanwhile", "moreover", "nevertheless", "nonetheless", "notably",
    "obviously", "otherwise", "overall", "particularly", "perhaps",
    "previously", "primarily", "rather", "recently", "regardless",
    "similarly", "since", "specifically", "still", "subsequently",
    "therefore", "though", "thus", "typically", "ultimately", "unlike",
    "whereas", "whether", "while",
    # months / days (title-cased in text)
    "january", "february", "march", "april", "june", "july", "august",
    "september", "october", "november", "december",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    # common false-positive words
    "allow", "generated", "client", "content", "design", "development",
    "editor", "essential", "experience", "framework", "integration",
    "management", "manager", "open", "options", "performance", "project",
    "projects", "resource", "resources", "support", "system", "version",
    "website", "workspace", "document", "documents", "note", "notes",
    "task", "tasks", "file", "files", "page", "pages", "view", "views",
    "app", "apps", "web", "cloud", "online", "digital", "smart", "pro",
    "premium", "basic", "standard", "enterprise", "personal", "professional",
    "source", "sources", "report", "reports", "results", "search",
    "click", "sign", "create", "manage", "organize", "share", "edit",
    "built", "build", "running", "run", "set", "setting", "settings",
    "image", "images", "video", "videos", "text", "link", "links",
    # Additional false positives caught in testing
    "paid", "discover", "compare", "visit", "join", "download", "install",
    "browse", "choose", "pick", "select", "switch", "migrate", "consider",
    "rated", "ranked", "listed", "mentioned", "recommended", "featured",
    "suitable", "ideal", "perfect", "great", "excellent", "wonderful",
    "easy", "easier", "easiest", "hard", "harder", "hardest",
    "better", "worse", "faster", "slower", "cheaper", "expensive",
    "overview", "summary", "conclusion", "introduction", "chapter",
    "section", "part", "step", "steps", "method", "methods",
    "here", "there", "being", "done", "having", "making", "getting",
    "keeping", "going", "coming", "becoming", "turning", "looking",
    "showing", "starting", "ending", "adding", "removing", "changing",
    # Single common words that look like product names when capitalized
    "chat", "send", "word", "mail", "call", "note", "meet", "hub",
    "flow", "drive", "wave", "spark", "loop", "dock", "snap",
    "spanish", "english", "french", "german", "chinese", "japanese",
    "channel", "channels", "message", "messages", "thread", "threads",
    "group", "groups", "board", "boards", "space", "spaces",
    "real", "really", "actually", "basically", "simply", "truly",
    "want", "wanted", "wants", "needed", "needs", "likes", "liked",
    # Month abbreviations
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    # More generic words that slip through
    "leading", "plastic", "english", "language", "answer", "question",
    "reply", "comment", "comments", "vote", "votes", "score", "rating",
    "stack", "exchange", "overflow", "forum", "community", "discussion",
    # Tech description words that get captured
    "screen", "private", "office", "mode", "modes", "noise", "lobby",
    "sharing", "server", "servers", "hosting", "hosted", "deploy",
    "mobile", "desktop", "browser", "native", "cross", "single",
    "multiple", "default", "custom", "enable", "disable", "toggle",
    "inside", "outside", "within", "along", "below", "above",
    "direct", "directly", "indirect", "through", "into", "onto",
    "across", "around", "toward", "towards", "among", "against",
    # Pricing & feature descriptors
    "unlimited", "limited", "self", "auto", "manual", "instant",
    "audio", "calls", "calling", "recording", "storage", "backup",
    "sync", "syncing", "notification", "notifications", "alert", "alerts",
    "template", "templates", "widget", "widgets", "plugin", "plugins",
    "extension", "extensions", "addon", "addons", "module", "modules",
    "advanced", "standard", "basic", "premium", "lite", "trial",
    # Too-broad category words (not company names — those would block valid multi-word competitors)
    "email", "emails",
    # Common verbs/adverbs that slip through capitalization
    "maybe", "perhaps", "probably", "possible", "impossible",
    "already", "always", "never", "often", "sometimes", "usually",
    "especially", "particularly", "specifically", "generally",
    "immediately", "recently", "currently", "previously", "formerly",
    "additionally", "furthermore", "moreover", "besides", "otherwise",
    "meanwhile", "nevertheless", "however", "therefore", "consequently",
    # Remaining false positives caught in testing
    "kind", "kinds", "type", "types", "sort", "sorts", "form", "forms",
    "paced", "fast", "slow", "quick", "rapid", "modern", "traditional",
    "simple", "complex", "easy", "easier", "hard", "harder",
    "sized", "style", "level", "tier",
    # UI/nav elements from scraped pages
    "interface", "view", "blog", "apps", "marketplace", "code",
    "tested", "reviewed", "rated", "compared", "verified", "certified",
    "these", "those", "such", "same", "each", "every", "another",
    "powerful", "robust", "flexible", "reliable", "efficient",
    "home", "menu", "header", "footer", "sidebar", "navigation",
    "login", "signup", "register", "subscribe", "follow", "contact",
    # Common tech/description words
    "privacy", "security", "true", "false", "null", "undefined",
    "markdown", "html", "css", "json", "xml", "yaml", "sql",
    "api", "sdk", "cli", "gui", "url", "http", "https",
    "crafted", "designed", "focused", "oriented", "driven",
    # Tech ecosystem words
    "pdf", "git", "github", "reddit", "plus", "minus", "pro", "lite",
    "open", "closed", "local", "remote", "hybrid", "native",
    # Remaining single-word false positives
    "analysis", "buildin", "building", "compare", "comparing",
    "feature", "pricing", "support", "available", "release",
    # Job titles / categories that appear as false positives
    "managers", "manager", "designers", "designer", "developers", "developer",
    "engineers", "engineer", "analysts", "analyst", "consultants", "consultant",
    "freelancers", "freelancer", "founders", "founder",
    # Caught in testing iteration 2
    "autistic", "competely", "completely", "ranking", "rankings",
    "live", "taking", "looking", "going", "coming", "trying",
    "giving", "making", "doing", "seeing", "saying", "thinking",
    "comprehensive", "affordable", "perfect", "ideal", "ultimate",
    "annual", "monthly", "weekly", "daily", "yearly",
    # Platform names
    "mac", "windows", "linux", "ios", "android", "chrome", "firefox", "safari",
    "iphone", "ipad", "tablet", "smartphone", "laptop", "computer",
    # Geographic / legal / nationality words
    "inc", "llc", "corp", "ltd", "gmbh", "corporation", "company",
    "irish", "american", "british", "european", "asian", "african",
    "north", "south", "east", "west", "central", "united", "states",
    "san", "new", "los", "las", "del", "francisco", "york", "angeles",
    "london", "berlin", "paris", "tokyo", "sydney", "toronto",
    "comprehensive", "analysis", "overview", "report", "study",
    # Business/financial terms that look like names
    "payments", "billing", "revenue", "profit", "growth", "market",
    "infrastructure", "platform", "services", "solutions", "global",
    "underdogs", "startup", "startups", "enterprise", "ventures",
}


def _is_valid_competitor(name: str, target: str) -> bool:
    """Strict validation: is this plausibly a real product/company name?"""
    if not name:
        return False
    name = name.strip()
    # Length guards
    if len(name) < 2 or len(name) > 35:
        return False
    # Must not be the target itself (fuzzy)
    if name.lower().replace(" ", "") == target.lower().replace(" ", ""):
        return False
    # Must start with uppercase letter
    if not name[0].isalpha() or not name[0].isupper():
        return False
    # Reject concatenated common words (e.g., "AnalysisThe") but allow product CamelCase (e.g., "ClickUp")
    for word in name.split():
        parts = re.split(r'(?<=[a-z])(?=[A-Z])', word)
        if len(parts) >= 2:
            # Only reject if ALL parts are stop words (= clearly concatenated text, not a brand)
            if all(p.lower() in _STOP_WORDS for p in parts):
                return False
    # ALL words must NOT be stop words (at least one word must be "real")
    words = name.lower().split()
    if all(w in _STOP_WORDS for w in words):
        return False
    # Multi-word: reject if ANY word is a strong disqualifier
    _title_disqualifiers = {"best", "top", "alternative", "alternatives", "competitor",
                            "competitors", "list", "review", "reviews", "guide",
                            "comparison", "compared", "overview", "complete", "ultimate"}
    if len(words) > 1 and any(w in _title_disqualifiers for w in words):
        return False
    # Multi-word: reject if first word is a common verb/UI action
    _verb_prefixes = {"view", "open", "click", "see", "get", "try", "use", "read",
                      "learn", "find", "join", "sign", "log", "compare", "explore",
                      "interface", "blog", "code", "let", "it", "in", "on"}
    if len(words) > 1 and words[0] in _verb_prefixes:
        return False
    # Multi-word: reject if first word is a pronoun
    _pronouns = {"i", "we", "they", "he", "she", "it", "my", "our", "their", "his", "her", "its"}
    if len(words) > 1 and words[0] in _pronouns:
        return False
    # Multi-word: reject if last word is a role/category
    _role_suffixes = {"managers", "designers", "developers", "engineers", "analysts",
                      "consultants", "freelancers", "founders", "professionals"}
    if len(words) > 1 and words[-1] in _role_suffixes:
        return False
    # Reject single-word mega-corp parent names (too broad as competitors)
    _MEGACORP_SINGLE_WORDS = {"microsoft", "google", "apple", "amazon", "facebook",
                              "meta", "oracle", "ibm", "sap", "salesforce", "adobe",
                              "intel", "cisco", "dell", "hp", "samsung", "sony"}
    if len(words) == 1 and words[0] in _MEGACORP_SINGLE_WORDS:
        return False
    # Reject single-char or very short single words
    if len(words) == 1 and len(name) < 3:
        return False
    # Reject if it looks like a URL fragment
    if any(c in name for c in ["http", "www.", ".com", ".org", ".net", "/"]):
        return False
    # Reject pure numbers
    if name.replace(" ", "").isdigit():
        return False
    # Reject if target name is a substring (e.g., "Notion Templates")
    if target.lower() in name.lower():
        return False
    # Reject probable person names: two short words, both starting uppercase,
    # neither word commonly seen in product names
    if len(words) == 2:
        w1, w2 = words
        # If both words are 3-10 chars and purely alphabetic, likely a person name
        if (w1.isalpha() and w2.isalpha() and 3 <= len(w1) <= 10 and 3 <= len(w2) <= 10
                and w1[0].isupper() and w2[0].isupper()):
            # Check if either word is a known product suffix
            product_suffixes = {"ai", "io", "app", "hub", "lab", "labs", "hq", "ly",
                                "ify", "ful", "base", "desk", "pad", "bit", "box",
                                "flow", "stack", "cloud", "ware", "soft", "tech"}
            if not any(w1.lower().endswith(s) or w2.lower().endswith(s) for s in product_suffixes):
                # Check if this appears like a person name (no tech indicators)
                tech_words = {"chat", "mail", "doc", "note", "task", "code", "data",
                              "sync", "meet", "call", "team", "work", "dev", "ops"}
                if not any(w1.lower() in tech_words or w2.lower() in tech_words for _ in [1]):
                    # Final check: if second word looks like a surname
                    if w2.lower() not in _STOP_WORDS:
                        # Likely a person name — skip
                        return False
    return True


def _normalize_name(raw: str) -> str:
    """Clean a raw extracted name."""
    raw = raw.strip().rstrip(".,;:!?")
    # Remove trailing possessives
    if raw.endswith("'s"):
        raw = raw[:-2]
    # Remove leading "the " or "a "
    for prefix in ("The ", "A "):
        if raw.startswith(prefix) and len(raw) > len(prefix) + 2:
            raw = raw[len(prefix):]
    raw = raw.strip()
    # Remove duplicated words (e.g., "Chanty Chanty" -> "Chanty")
    words = raw.split()
    deduped = []
    for w in words:
        if not deduped or w.lower() != deduped[-1].lower():
            deduped.append(w)
    raw = " ".join(deduped)
    # Limit to max 2 words (3+ words are almost always text fragments)
    words = raw.split()
    if len(words) > 2:
        raw = " ".join(words[:2])
    return raw.strip()


def _extract_from_text(text: str, target: str) -> dict[str, int]:
    """Extract candidate competitor names from a text block.

    Returns {name: score} where higher score = more likely real competitor.
    """
    candidates: dict[str, int] = {}
    target_lower = target.lower()

    # ── Pattern 1: "X vs Y" ──
    # Capture what's on the other side of "vs"
    for m in re.finditer(rf'{re.escape(target)}\s+vs\.?\s+([A-Z][\w]+(?:\s+[A-Z][\w]+)?)', text, re.IGNORECASE):
        name = _normalize_name(m.group(1))
        if _is_valid_competitor(name, target):
            candidates[name] = candidates.get(name, 0) + 3  # high confidence

    for m in re.finditer(rf'([A-Z][\w]+(?:\s+[A-Z][\w]+)?)\s+vs\.?\s+{re.escape(target)}', text, re.IGNORECASE):
        name = _normalize_name(m.group(1))
        if _is_valid_competitor(name, target):
            candidates[name] = candidates.get(name, 0) + 3

    # ── Pattern 2: Comma/and-separated lists near "alternatives/competitors" ──
    # e.g., "alternatives include Asana, Monday, ClickUp, and Trello"
    list_pattern = r'(?:alternatives?|competitors?|rivals?|competing\s+(?:products?|tools?|apps?))\s*(?:include|are|like|such\s+as)?[:\s]+([^.]{10,200})'
    for m in re.finditer(list_pattern, text, re.IGNORECASE):
        chunk = m.group(1)
        # Split on commas, "and", semicolons
        parts = re.split(r'[,;]\s*|\s+and\s+|\s+or\s+', chunk)
        for part in parts:
            # Extract capitalized name from each part
            name_m = re.match(r'([A-Z][\w]*(?:\s+[A-Z][\w]*){0,2})', part.strip())
            if name_m:
                name = _normalize_name(name_m.group(1))
                if _is_valid_competitor(name, target):
                    candidates[name] = candidates.get(name, 0) + 2

    # ── Pattern 3: Numbered/bulleted list items ──
    # "1. Asana" or "• Monday.com" or "- ClickUp"
    # Handle both newline-separated and inline (1. X 2. Y 3. Z) lists
    for m in re.finditer(r'(?:^|\n|\s)(?:\d+[\.\)]\s*)([A-Z][\w]*(?:[.\s][A-Z]?[\w]*){0,2})(?=\s*(?:\d+[\.\)]|\n|$|[,;]))', text):
        name = _normalize_name(m.group(1))
        if _is_valid_competitor(name, target):
            candidates[name] = candidates.get(name, 0) + 2
    # Also match bullet/dash lists
    for m in re.finditer(r'(?:^|\n)\s*[•\-\*]\s+([A-Z][\w]*(?:[.\s][A-Z]?[\w]*){0,2})', text):
        name = _normalize_name(m.group(1))
        if _is_valid_competitor(name, target):
            candidates[name] = candidates.get(name, 0) + 2

    # ── Pattern 4: Bold/header patterns from scraped text ──
    # "Asana — project management tool" or "Monday.com: An alternative..."
    for m in re.finditer(r'([A-Z][\w]*(?:[.\s][A-Z][\w]*){0,2})\s*[—–\-:]\s+(?:an?\s+)?(?:alternative|competitor|rival|project|team|workflow|collaboration|productivity)', text, re.IGNORECASE):
        name = _normalize_name(m.group(1))
        if _is_valid_competitor(name, target):
            candidates[name] = candidates.get(name, 0) + 2

    # ── Pattern 5: "like X" or "such as X" near target ──
    for m in re.finditer(rf'(?:like|such\s+as)\s+([A-Z][\w]+(?:\s+[A-Z][\w]+)?)', text):
        name = _normalize_name(m.group(1))
        if _is_valid_competitor(name, target) and name.lower() != target_lower:
            candidates[name] = candidates.get(name, 0) + 1

    # ── Pattern 6: Title-cased product names near context words (1-2 words only) ──
    context_words = {"alternative", "competitor", "rival", "instead", "switch", "replace", "migrate", "versus", "vs", "better", "similar"}
    text_lower = text.lower()
    if any(w in text_lower for w in context_words):
        for m in re.finditer(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b', text):
            name = _normalize_name(m.group(1))
            if _is_valid_competitor(name, target) and len(name.split()) <= 2:
                candidates[name] = candidates.get(name, 0) + 1

    return candidates


def _merge_candidates(all_candidates: list[dict[str, int]]) -> dict[str, int]:
    """Merge candidate dicts, summing scores and boosting cross-source mentions."""
    merged: dict[str, int] = {}
    # Track which sources mentioned each name
    source_counts: dict[str, int] = {}

    for cand_dict in all_candidates:
        names_in_source = set()
        for name, score in cand_dict.items():
            merged[name] = merged.get(name, 0) + score
            names_in_source.add(name)
        for name in names_in_source:
            source_counts[name] = source_counts.get(name, 0) + 1

    # Boost names that appear in multiple sources
    for name, src_count in source_counts.items():
        if src_count >= 2:
            merged[name] = merged.get(name, 0) + (src_count * 2)

    return merged


async def scout_competitors(company_or_product: str, max: int = 10) -> dict:
    """Find competitors for a company or product.

    Returns: target, list of competitors with positioning, strengths, weaknesses.
    """
    max_results = max  # avoid shadowing built-in max()
    cached = get_cached("scout_competitors", company_or_product=company_or_product, max=max_results)
    if cached:
        return cached

    sources_used = []
    sources_failed = []
    intel = CompetitorIntel(target=company_or_product)
    breakdown: dict[str, SourceConfidence] = {}

    # ── Phase 1: Gather search results from targeted queries ──
    # Use fewer, more focused queries to stay under rate limits
    queries = [
        f"{company_or_product} alternatives",
        f"{company_or_product} vs competitors",
    ]

    all_candidates: list[dict[str, int]] = []
    all_snippets: dict[str, list[str]] = {}  # name -> snippets for positioning
    all_urls: dict[str, list[str]] = {}  # name -> urls for domain extraction

    for query in queries:
        try:
            results = await search.search_web(query, max_results=8)
            if results:
                sources_used.append(f"search:{query[:40]}")
                per_query_candidates: dict[str, int] = {}

                for r in results:
                    title = r.get("title", "")
                    body = r.get("body", "")
                    href = r.get("href", "")
                    combined = f"{title}. {body}"

                    extracted = _extract_from_text(combined, company_or_product)
                    for name, score in extracted.items():
                        per_query_candidates[name] = per_query_candidates.get(name, 0) + score
                        if body:
                            all_snippets.setdefault(name, []).append(body[:300])
                        if href:
                            all_urls.setdefault(name, []).append(href)

                all_candidates.append(per_query_candidates)
                breakdown[f"search_{query[:20]}"] = SourceConfidence(
                    score=min(0.4 + len(results) * 0.05, 0.8),
                    reason=f"{len(results)} results for '{query[:30]}'"
                )
            else:
                sources_failed.append(f"search:{query[:40]}")
        except Exception as e:
            logger.warning("Competitor search failed for '%s': %s", query, e)
            sources_failed.append(f"search:{query[:40]}")

    # ── Phase 2: (Disabled — scraping introduces too much noise from nav/UI elements)
    # Instead, use a 3rd search query focused on structured competitor lists
    try:
        list_results = await search.search_web(
            f"top 10 {company_or_product} alternatives list", max_results=8
        )
        if list_results:
            sources_used.append("search:alternatives_list")
            per_query_candidates: dict[str, int] = {}
            for r in list_results:
                title = r.get("title", "")
                body = r.get("body", "")
                combined = f"{title}. {body}"
                extracted = _extract_from_text(combined, company_or_product)
                for name, score in extracted.items():
                    per_query_candidates[name] = per_query_candidates.get(name, 0) + score
                    if body:
                        all_snippets.setdefault(name, []).append(body[:300])
                    href = r.get("href", "")
                    if href:
                        all_urls.setdefault(name, []).append(href)
            all_candidates.append(per_query_candidates)
            breakdown["alternatives_list_search"] = SourceConfidence(
                score=0.6, reason=f"{len(list_results)} list results found"
            )
    except Exception as e:
        logger.warning("Alt list search failed: %s", e)

    # ── Phase 3: Merge & rank ──
    merged = _merge_candidates(all_candidates)

    # Post-filter: Remove names that are substrings of higher-scoring names
    # e.g., "Teams" when "Microsoft Teams" exists — always prefer the longer, more specific name
    names_list = list(merged.keys())
    to_remove = set()
    for short_name in names_list:
        for long_name in names_list:
            if short_name != long_name and len(short_name) < len(long_name):
                if short_name.lower() in long_name.lower():
                    # Always merge into the longer (more specific) name
                    to_remove.add(short_name)
                    merged[long_name] = merged.get(long_name, 0) + merged.get(short_name, 0)
    for name in to_remove:
        merged.pop(name, None)

    # Sort by score descending
    ranked = sorted(merged.items(), key=lambda x: x[1], reverse=True)
    logger.info(
        "Competitor extraction for '%s': %d candidates, top=%s",
        company_or_product,
        len(ranked),
        [(n, s) for n, s in ranked[:15]],
    )

    # ── Phase 4: Enrich top competitors ──
    competitors = []
    for comp_name, score in ranked[:max_results]:
        entry = CompetitorEntry(name=comp_name)

        # Use collected snippets for positioning
        snippets = all_snippets.get(comp_name, [])
        if snippets:
            # Pick the most descriptive snippet (longest that mentions the name)
            best_snippet = sorted(snippets, key=len, reverse=True)[0]
            entry.positioning = best_snippet[:250]

        # Try to extract domain from collected URLs or do a quick search
        urls = all_urls.get(comp_name, [])
        for url in urls:
            parsed = urlparse(url)
            host = parsed.netloc.lower()
            # Skip aggregator sites
            if not any(agg in host for agg in ["g2.com", "capterra", "alternativeto", "slant.co",
                                                  "sourceforge", "bing.com", "google.com",
                                                  "reddit.com", "quora.com", "wikipedia"]):
                entry.domain = host
                break

        # Enrich with a targeted detail search if no good domain yet
        if not entry.domain or not entry.positioning:
            try:
                detail = await search.search_web(f"{comp_name} official site", max_results=2)
                if detail:
                    top = detail[0]
                    if not entry.domain and top.get("href"):
                        entry.domain = urlparse(top["href"]).netloc
                    if not entry.positioning and top.get("body"):
                        entry.positioning = top["body"][:250]
            except Exception:
                pass

        # Extract pricing hint from positioning text
        pos_text = (entry.positioning or "").lower()
        if any(w in pos_text for w in ["free", "$", "pricing", "/mo", "per month", "plan"]):
            # Try to pull out the pricing bit
            price_match = re.search(r'(\$\d+[\d,.]*(?:/\w+)?|free\s*(?:plan|tier|version)?)', pos_text, re.IGNORECASE)
            if price_match:
                entry.pricing = price_match.group(1).strip()

        # Generate strengths from positioning context
        if entry.positioning:
            pos_lower = entry.positioning.lower()
            strength_signals = []
            strength_kw = {
                "fast": "Fast performance",
                "intuitive": "Intuitive interface",
                "open source": "Open source",
                "free": "Free tier available",
                "collaboration": "Strong collaboration features",
                "integration": "Rich integrations",
                "customizable": "Highly customizable",
                "lightweight": "Lightweight",
                "powerful": "Powerful feature set",
                "simple": "Simple and easy to use",
                "secure": "Strong security",
                "scalable": "Scalable architecture",
                "ai": "AI-powered features",
                "automation": "Workflow automation",
                "real-time": "Real-time collaboration",
                "offline": "Offline support",
                "api": "Developer-friendly API",
            }
            for kw, label in strength_kw.items():
                if kw in pos_lower:
                    strength_signals.append(label)
            entry.strengths = strength_signals[:4]

        # Key differentiator = first sentence of positioning
        if entry.positioning:
            first_sentence = entry.positioning.split(".")[0].strip()
            if len(first_sentence) > 15:
                entry.key_differentiator = first_sentence

        competitors.append(entry)

    intel.competitors = competitors

    if competitors:
        breakdown["extraction_quality"] = SourceConfidence(
            score=min(0.3 + len(competitors) * 0.08, 0.9),
            reason=f"{len(competitors)} competitors extracted and enriched"
        )
        top_names = [c.name for c in competitors[:5]]
        intel.market_positioning_summary = (
            f"Found {len(competitors)} competitors for {company_or_product}. "
            f"Top alternatives: {', '.join(top_names)}."
        )

    # Compute weighted confidence — only count sources with data
    scores = [sc.score for sc in breakdown.values() if sc.score > 0]
    intel.confidence = round(sum(scores) / len(scores), 2) if scores else 0.0
    intel.confidence_breakdown = breakdown
    intel.sources_used = list(set(sources_used))
    intel.sources_failed = list(set(sources_failed))
    intel.data_freshness = datetime.now(timezone.utc).isoformat()

    intel.data_quality_grade = compute_grade(intel.confidence)

    result = intel.model_dump()
    set_cached("scout_competitors", result, company_or_product=company_or_product, max=max_results)
    return result
