"""Mock ADP API: serves the synthetic documents over HTTP, like the real ADP would.

Run with: uv run uvicorn mock_sources.adp_api:app --reload
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse

load_dotenv()

DOCUMENTS_DIR = Path("data/sources/adp")
API_KEY = os.environ["MOCK_ADP_API_KEY"]

app = FastAPI(title="Mock ADP API")


def check_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def available_documents() -> dict[str, Path]:
    return {path.name: path for path in sorted(DOCUMENTS_DIR.iterdir())}


@app.get("/documents", dependencies=[Depends(check_api_key)])
def list_documents() -> list[dict]:
    return [
        {"name": name, "size_bytes": path.stat().st_size}
        for name, path in available_documents().items()
    ]


@app.get("/documents/{name}", dependencies=[Depends(check_api_key)])
def get_document(name: str) -> FileResponse:
    documents = available_documents()
    # Only serve names from the list, so "../.env" style requests can't escape
    if name not in documents:
        raise HTTPException(status_code=404, detail="Document not found")
    return FileResponse(documents[name])
