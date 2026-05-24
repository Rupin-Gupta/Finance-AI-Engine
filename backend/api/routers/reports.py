from fastapi import APIRouter, Depends, Request

from backend.api.auth import require_api_key
from backend.api.limiter import limiter
from backend.dependencies import get_db

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("")
async def list_reports(limit: int = 20, offset: int = 0, conn=Depends(get_db)):
    rows = await conn.fetch(
        "SELECT id, user_id, query, response, created_at FROM chat_history ORDER BY created_at DESC LIMIT $1 OFFSET $2",
        limit,
        offset,
    )
    return [dict(r) for r in rows]


@router.get("/docs")
async def list_ingested_docs(conn=Depends(get_db)):
    rows = await conn.fetch(
        "SELECT source_url, doc_type, chunk_count, ingested_at FROM financial_reports ORDER BY ingested_at DESC"
    )
    return [dict(r) for r in rows]


@router.post("/generate")
@limiter.limit("5/minute")
async def generate_sector_reports(request: Request, conn=Depends(get_db)):
    """Run sector report generation immediately and return written chat IDs."""
    from backend.reporting.sector_report import run_sector_report
    chat_ids = await run_sector_report(conn)
    return {"generated": len(chat_ids), "chat_ids": chat_ids}
