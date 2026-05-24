from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from backend.api.auth import require_api_key
from backend.api.limiter import limiter
from backend.dependencies import get_db
from backend.rag.chain import answer

router = APIRouter(dependencies=[Depends(require_api_key)])


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


@router.post("")
@limiter.limit("30/minute")
async def rag_query(request: Request, req: QueryRequest, conn=Depends(get_db)):
    return await answer(conn, req.query, top_k=req.top_k)
