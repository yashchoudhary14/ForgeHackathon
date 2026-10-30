from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import init_db
from .routers import agent, assist, chat, documents, profile, schemes, voice

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.storage_dir).mkdir(parents=True, exist_ok=True)
    await init_db()
    yield


app = FastAPI(title="Adhikaar API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.client_origin.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (assist, profile, schemes, documents, chat, voice, agent):
    app.include_router(r.router, prefix="/api")

Path(settings.storage_dir).mkdir(parents=True, exist_ok=True)
app.mount("/files", StaticFiles(directory=settings.storage_dir), name="files")


@app.get("/api/health")
async def health():
    return {"ok": True, "model": settings.gemini_model}
