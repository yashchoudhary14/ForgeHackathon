from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import engine, init_db
from .services import llm
from .routers import agent, assist, chat, documents, profile, schemes, voice

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google_genai").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.storage_dir).mkdir(parents=True, exist_ok=True)
    await init_db()
    if settings.gemini_api_key:
        await llm.initialize_pool()
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(title="Adhikaar API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.client_origin.split(",") if o.strip()],
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


@app.get("/api/health/llm")
async def llm_health():
    return await llm.health_status()
