import json
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    import redis  # type: ignore
except ImportError:  # pragma: no cover
    redis = None


def get_client():
    if not redis or not settings.redis_url:
        return None
    try:
        client = redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        return client
    except Exception as exc:
        logger.info("Redis unavailable; continuing without cache: %s", exc)
        return None


def get_json(key: str) -> Any:
    client = get_client()
    if not client:
        return None
    try:
        value = client.get(key)
        return json.loads(value) if value else None
    except Exception as exc:
        logger.warning("Redis read failed: %s", exc)
        return None


def set_json(key: str, value: Any, ttl: int = 60) -> None:
    client = get_client()
    if not client:
        return
    try:
        client.setex(key, ttl, json.dumps(value, default=str))
    except Exception as exc:
        logger.warning("Redis write failed: %s", exc)


def delete(key: str) -> None:
    client = get_client()
    if not client:
        return
    try:
        client.delete(key)
    except Exception as exc:
        logger.warning("Redis delete failed: %s", exc)


def clear_prefix(prefix: str) -> None:
    client = get_client()
    if not client:
        return
    try:
        keys = list(client.scan_iter(match=f"{prefix}*"))
        if keys:
            client.delete(*keys)
    except Exception as exc:
        logger.warning("Redis prefix delete failed: %s", exc)
