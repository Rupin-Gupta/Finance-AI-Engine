import asyncio
import asyncpg

from backend.config import settings

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


async def init_db_pool() -> None:
    global _pool
    async with _pool_lock:
        if _pool is not None:
            return
        _pool = await asyncpg.create_pool(
            settings.database_url,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )


def get_db_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized — call init_db_pool() first")
    return _pool


async def close_db_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
