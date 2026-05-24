from backend.db.connection import get_db_pool


async def get_db():
    pool = get_db_pool()
    async with pool.acquire() as conn:
        yield conn
