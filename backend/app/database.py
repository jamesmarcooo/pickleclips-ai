from typing import AsyncGenerator
import asyncpg
from app.config import settings

_pool: asyncpg.Pool | None = None


async def init_db() -> None:
    global _pool
    _pool = await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10)


async def close_db() -> None:
    if _pool:
        await _pool.close()


async def get_db() -> AsyncGenerator[asyncpg.Connection, None]:
    assert _pool is not None, "DB pool not initialized"
    async with _pool.acquire() as conn:
        yield conn
