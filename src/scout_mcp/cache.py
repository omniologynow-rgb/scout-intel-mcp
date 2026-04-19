"""Redis-backed TTL cache for Scout MCP with automatic in-memory fallback.

If REDIS_URL is set → uses Redis (persistent, shared across instances)
If REDIS_URL is not set or Redis is down → falls back to in-memory dict
"""

import hashlib
import json
import os
import time
import logging
from typing import Any

from .config import CACHE_TTL_SECONDS

logger = logging.getLogger(__name__)

# ── Redis connection ──
_redis = None
_redis_checked = False


def _get_redis():
    global _redis, _redis_checked
    if not _redis_checked:
        _redis_checked = True
        redis_url = os.environ.get("REDIS_URL")
        if redis_url:
            try:
                import redis as redis_lib
                _redis = redis_lib.from_url(redis_url, decode_responses=True)
                _redis.ping()
                logger.info("Redis cache connected: %s", redis_url[:30] + "...")
            except Exception as e:
                logger.warning("Redis connection failed, falling back to memory: %s", e)
                _redis = None
        else:
            logger.info("REDIS_URL not set — using in-memory cache")
    return _redis


# ── Fallback in-memory cache ──
_mem_cache: dict[str, dict[str, Any]] = {}


def _make_key(tool_name: str, **kwargs) -> str:
    raw = json.dumps({"tool": tool_name, **kwargs}, sort_keys=True, default=str)
    return f"scout:{hashlib.sha256(raw.encode()).hexdigest()}"


def get_cached(tool_name: str, **kwargs) -> Any | None:
    key = _make_key(tool_name, **kwargs)
    r = _get_redis()

    if r is not None:
        try:
            data = r.get(key)
            if data:
                logger.debug("Redis cache hit: %s", key[:20])
                return json.loads(data)
            return None
        except Exception as e:
            logger.warning("Redis get failed: %s", e)

    # Fallback to memory
    entry = _mem_cache.get(key)
    if entry and time.time() - entry["ts"] <= CACHE_TTL_SECONDS:
        return entry["data"]
    elif entry:
        del _mem_cache[key]
    return None


def set_cached(tool_name: str, data: Any, **kwargs) -> None:
    key = _make_key(tool_name, **kwargs)
    r = _get_redis()

    if r is not None:
        try:
            r.setex(key, CACHE_TTL_SECONDS, json.dumps(data, default=str))
            logger.debug("Redis cached: %s", key[:20])
            return
        except Exception as e:
            logger.warning("Redis set failed: %s", e)

    # Fallback to memory
    _mem_cache[key] = {"data": data, "ts": time.time()}


def clear_cache() -> int:
    r = _get_redis()

    if r is not None:
        try:
            keys = r.keys("scout:*")
            if keys:
                r.delete(*keys)
            return len(keys)
        except Exception as e:
            logger.warning("Redis clear failed: %s", e)

    count = len(_mem_cache)
    _mem_cache.clear()
    return count


def cache_stats() -> dict:
    r = _get_redis()

    if r is not None:
        try:
            keys = r.keys("scout:*")
            info = r.info("memory")
            return {
                "backend": "redis",
                "total_entries": len(keys),
                "memory_used": info.get("used_memory_human", "unknown"),
                "connected": True,
            }
        except Exception as e:
            logger.warning("Redis stats failed: %s", e)

    now = time.time()
    active = sum(1 for v in _mem_cache.values() if now - v["ts"] <= CACHE_TTL_SECONDS)
    return {
        "backend": "memory",
        "total_entries": len(_mem_cache),
        "active_entries": active,
        "connected": False,
    }
