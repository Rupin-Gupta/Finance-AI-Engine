import os
import httpx

API_BASE = os.getenv("API_BASE_URL", "http://api:8000").strip().strip('"').strip("'")
API_KEY = os.getenv("API_KEY", "changeme").strip().strip('"').strip("'")

_headers = {"X-API-Key": API_KEY}


def get(path: str, **params) -> dict | list:
    resp = httpx.get(f"{API_BASE}{path}", headers=_headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def post(path: str, body: dict) -> dict:
    resp = httpx.post(f"{API_BASE}{path}", headers=_headers, json=body, timeout=60)
    resp.raise_for_status()
    return resp.json()


def upload_file(path: str, file, doc_type: str) -> dict:
    resp = httpx.post(
        f"{API_BASE}{path}",
        headers=_headers,
        data={"doc_type": doc_type},
        files={"file": (file.name, file.getvalue(), file.type or "application/octet-stream")},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()
