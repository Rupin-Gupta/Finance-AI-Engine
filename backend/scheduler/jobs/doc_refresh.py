import os
from backend.ingest.doc_pipeline import run_doc_ingest
from backend.db.connection import get_db_pool

DOC_URLS = [
    u.strip()
    for u in os.getenv("TRACKED_DOC_URLS", "").split(",")
    if u.strip()
]


async def run() -> None:
    if not DOC_URLS:
        return
    pool = get_db_pool()
    async with pool.acquire() as conn:
        for url in DOC_URLS:
            await run_doc_ingest(conn, url, doc_type="scheduled")
