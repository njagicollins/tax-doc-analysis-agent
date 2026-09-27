"""Mock ADP API: serves the synthetic documents over HTTP, like the real ADP would.

Run with: uv run uvicorn mock_sources.adp_api:app --reload
"""

import os
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse

load_dotenv()

DOCUMENTS_DIR = Path("data/sources/adp")
API_KEY = os.environ["MOCK_ADP_API_KEY"]

# A 4-digit year, optionally followed by a quarter, between underscores: _2026Q2 or _2026_
PERIOD_PATTERN = re.compile(r"_(\d{4}(?:Q[1-4])?)(?:_|$)")

app = FastAPI(title="Mock ADP API")


def check_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def available_documents() -> dict[str, Path]:
    return {path.name: path for path in sorted(DOCUMENTS_DIR.iterdir())}


def period_of(name: str) -> str:
    """form_941_2026Q2.pdf -> "2026Q2" (quarterly); w2_2026_E001.pdf -> "2026" (annual)."""
    match = PERIOD_PATTERN.search(Path(name).stem)
    if match is None:
        raise ValueError(f"No period in document name: {name!r}")
    return match.group(1)


@app.get("/documents", dependencies=[Depends(check_api_key)])
def list_documents(quarter: str | None = None) -> list[dict]:
    documents = [
        {"name": name, "period": period_of(name), "size_bytes": path.stat().st_size}
        for name, path in available_documents().items()
    ]
    if quarter:
        # A quarter needs its own documents plus that year's annual ones (W-2s)
        documents = [d for d in documents if d["period"] in (quarter, quarter[:4])]
    return documents


@app.get("/documents/{name}", dependencies=[Depends(check_api_key)])
def get_document(name: str) -> FileResponse:
    documents = available_documents()
    # Only serve names from the list, so "../.env" style requests can't escape
    if name not in documents:
        raise HTTPException(status_code=404, detail="Document not found")
    return FileResponse(documents[name])
