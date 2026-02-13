from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db as _get_db

# Re-export for FastAPI Depends()
get_db = _get_db

_redis_client: Redis | None = None


async def get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(
            settings.redis_dsn,
            decode_responses=True,
        )
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
