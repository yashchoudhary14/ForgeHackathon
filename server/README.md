---
title: Adhikaar API
emoji: 🇮🇳
colorFrom: orange
colorTo: green
sdk: docker
app_port: 7860
---

Adhikaar's FastAPI backend. Upload the **contents** of `server/` as the Space
repository root, excluding `.env`, storage, and local caches. Set secrets and
variables before starting; see `DEPLOYMENT.md` in the source repository.

`/api/health` is a liveness endpoint: no database or Gemini calls. API docs are
at `/docs`. A single uvicorn worker shares the model limiter and live agent runs.
