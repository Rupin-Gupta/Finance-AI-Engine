import asyncpg


async def upsert_document(conn: asyncpg.Connection, source_url: str,
                           doc_type: str, chunk_count: int) -> str:
    row = await conn.fetchrow(
        """
        INSERT INTO financial_reports (source_url, doc_type, chunk_count)
        VALUES ($1, $2, $3)
        ON CONFLICT (source_url) DO UPDATE SET chunk_count = EXCLUDED.chunk_count,
            ingested_at = now()
        RETURNING id
        """,
        source_url, doc_type, chunk_count,
    )
    return str(row["id"])


async def upsert_chunks(conn: asyncpg.Connection, doc_id: str, chunks: list[dict]) -> None:
    """chunks: [{chunk_index, text, embedding_vector}]"""
    stmt = """
        INSERT INTO embeddings (doc_id, chunk_index, text, embedding_vector, index_version)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (doc_id, chunk_index) DO UPDATE SET
            text = EXCLUDED.text, embedding_vector = EXCLUDED.embedding_vector,
            index_version = EXCLUDED.index_version
    """
    version = await _current_index_version(conn)
    data = [(doc_id, c["chunk_index"], c["text"], c["embedding_vector"], version)
            for c in chunks]
    await conn.executemany(stmt, data)


async def _current_index_version(conn: asyncpg.Connection) -> int:
    row = await conn.fetchrow("SELECT COALESCE(MAX(index_version), 0) AS v FROM embeddings")
    return row["v"]


async def get_db_index_version(conn: asyncpg.Connection) -> int:
    return await _current_index_version(conn)


async def get_chunk_texts(conn: asyncpg.Connection, doc_ids: list[str],
                           chunk_ids: list[int]) -> list[asyncpg.Record]:
    # Paired lookup — avoids cross-join between doc_ids × chunk_ids
    pairs = list(zip(doc_ids, chunk_ids))
    return await conn.fetch(
        """
        SELECT doc_id, chunk_index, text
        FROM embeddings
        WHERE (doc_id::text, chunk_index) IN (
            SELECT unnest($1::text[]), unnest($2::int[])
        )
        """,
        [str(d) for d in doc_ids], list(chunk_ids),
    )
