from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from pydantic import BaseModel, Field, field_validator

from backend.api.auth import require_api_key
from backend.api.limiter import limiter
from backend.api.validators import validate_ingest_url
from backend.dependencies import get_db
from backend.ingest.pipeline import run_market_ingest
from backend.ingest.doc_pipeline import run_doc_ingest, run_text_ingest

router = APIRouter(dependencies=[Depends(require_api_key)])

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


class MarketIngestRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)
    period: str = "5d"
    interval: str = "1d"

    @field_validator("symbols")
    @classmethod
    def symbols_must_not_be_blank(cls, symbols: list[str]) -> list[str]:
        if not any(symbol.strip() for symbol in symbols):
            raise ValueError("At least one market symbol is required")
        return symbols


class DocIngestRequest(BaseModel):
    source_url: str = Field(min_length=1)
    doc_type: str = "report"


@router.post("/market")
@limiter.limit("5/minute")
async def ingest_market(request: Request, req: MarketIngestRequest, conn=Depends(get_db)):
    job_id = await run_market_ingest(
        conn,
        req.symbols,
        period=req.period,
        interval=req.interval,
    )
    return {"job_id": job_id}


def _validated_doc_request(req: DocIngestRequest) -> DocIngestRequest:
    """Runs the SSRF guard before the DB dependency acquires a connection."""
    validate_ingest_url(req.source_url)
    return req


async def _checked_upload(file: UploadFile = File(...)) -> tuple[UploadFile, bytes]:
    """Reads the upload and enforces the size cap before the DB dependency."""
    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 10 MB limit")
    return file, raw


@router.post("/docs")
@limiter.limit("10/minute")
async def ingest_docs(request: Request, req: DocIngestRequest = Depends(_validated_doc_request), conn=Depends(get_db)):
    job_id = await run_doc_ingest(conn, req.source_url, req.doc_type)
    return {"job_id": job_id}


@router.post("/upload")
@limiter.limit("10/minute")
async def ingest_upload(
    request: Request,
    upload: tuple[UploadFile, bytes] = Depends(_checked_upload),
    doc_type: str = Form("report"),
    conn=Depends(get_db),
):
    file, raw = upload
    text = _extract_text(raw, file.filename or "", file.content_type or "")
    source_url = f"upload://{file.filename}"
    job_id = await run_text_ingest(conn, text, source_url, doc_type)
    return {"job_id": job_id, "filename": file.filename, "doc_type": doc_type}


def _extract_text(raw: bytes, filename: str, content_type: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        import io
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(raw))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if name.endswith(".csv"):
        import io
        import pandas as pd
        df = pd.read_csv(io.BytesIO(raw))
        return df.to_string(index=False)
    if name.endswith((".xlsx", ".xls")):
        import io
        import pandas as pd
        df = pd.read_excel(io.BytesIO(raw))
        return df.to_string(index=False)
    # plain text / html / markdown / json
    return raw.decode("utf-8", errors="ignore")
