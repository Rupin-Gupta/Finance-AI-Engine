import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app


@pytest.mark.asyncio
async def test_no_api_key_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/alerts")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_wrong_api_key_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/alerts", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401
