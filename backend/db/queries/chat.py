import asyncpg
import json


async def append_chat_history(conn: asyncpg.Connection, query: str,
                               response: str, sources: list[dict],
                               user_id: str | None = None) -> str:
    row = await conn.fetchrow(
        """
        INSERT INTO chat_history (user_id, query, response, sources)
        VALUES ($1, $2, $3, $4) RETURNING id
        """,
        user_id, query, response, json.dumps(sources),
    )
    return str(row["id"])
