from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router


app = FastAPI(title="Office Agent")
app.include_router(api_router, prefix="/api")

_ROOT_DIR = Path(__file__).resolve().parents[2]
_FRONTEND_DIR = _ROOT_DIR / "frontend"
_STORAGE_DIR = _ROOT_DIR / "storage"

if _STORAGE_DIR.exists():
    app.mount("/storage", StaticFiles(directory=str(_STORAGE_DIR)), name="storage")

if _FRONTEND_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(_FRONTEND_DIR)), name="ui")


@app.get("/")
def index():
    index_file = _FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Frontend not found. Open /api docs or add frontend/index.html"}
