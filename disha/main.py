"""
main.py — FastAPI Application
Phase 3 + Phase 4 REST API

Endpoints:
  POST /api/recommend          — Run pipeline (Phase 3 + 4) on component JSON
  GET  /api/cache              — List all cached queries
  DELETE /api/cache            — Clear all cache entries
  GET  /api/health             — Health check
  GET  /                       — Serve frontend HTML

Run with:
    uvicorn main:app --reload --port 8000
"""

import sys
import os

# Make sure backend/ is on the path when running from project root
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel
from typing import Any, Optional

from pipeline import run_pipeline
from phase4_cache import init_db, list_cached_queries, clear_cache

# Initialise DB
init_db()

app = FastAPI(
    title="Component Datasheet Parser — Phase 3 & 4 API",
    description="LLM-based alternate component recommendation system",
    version="1.0.0",
)

# Allow all origins during development (tighten in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend static files if the folder exists
FRONTEND_DIR = Path(__file__).parent/ "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic request/response models
# ─────────────────────────────────────────────────────────────────────────────

class RecommendRequest(BaseModel):
    component_json: dict[str, Any]
    use_llm_query: bool = True
    top_n: int = 5
    require_stock: bool = True


class RecommendResponse(BaseModel):
    results: list[dict[str, Any]]
    query_string: str
    cached: bool
    total_found: int
    after_filter: int
    created_at: str
    hit_count: int
    error: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "phase": "3+4"}


@app.post("/api/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest):
    """
    Main endpoint. Accepts a structured component JSON and returns
    scored alternative components from Mouser.

    On repeated requests for the same component JSON, the result is
    served from the SQLite cache (Phase 4) — instant response.
    """
    if not req.component_json:
        raise HTTPException(status_code=400, detail="component_json must not be empty")

    result = run_pipeline(
        component_json=req.component_json,
        use_llm_query=req.use_llm_query,
        top_n=req.top_n,
        require_stock=req.require_stock,
    )

    if result.get("error") and not result.get("results"):
        # Return 200 with error field so frontend can display the message gracefully
        return JSONResponse(status_code=200, content=result)

    return result


@app.get("/api/cache")
def get_cache():
    """Returns a list of all cached query entries (for debugging/admin)."""
    entries = list_cached_queries()
    return {"count": len(entries), "entries": entries}


@app.delete("/api/cache")
def delete_cache():
    """Clears all cached entries. Useful when Mouser data may be stale."""
    deleted = clear_cache()
    return {"deleted": deleted, "message": f"Cleared {deleted} cache entries."}


@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    """Serve the frontend HTML file."""
    html_path = FRONTEND_DIR / "index.html"
    if html_path.exists():

        return HTMLResponse(content=html_path.read_text(encoding="utf-8"), status_code=200)
        #return HTMLResponse(content=html_path.read_text(), status_code=200)
    return HTMLResponse(
        content="<h2>Frontend not found. Place index.html in the /frontend directory.</h2>",
        status_code=200,
    )
