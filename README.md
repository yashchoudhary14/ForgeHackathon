# Adhikaar

Know your rights, claim them. Forge Gen AI buildathon - Theme 1 (Civic Pulse).

Run the API from `server/` with `uvicorn app.main:app`. PostgreSQL must have pgvector;
startup creates the tables, including `llm_cache`.

Judge deployment: see [DEPLOYMENT.md](DEPLOYMENT.md) for the Docker image,
Neon/Vercel setup, verification commands, and the current HF free-hosting blocker.

### Gemini free-tier demo

Configure `GEMINI_API_KEY` and `GEMINI_MODEL_POOL` in `server/.env` (see
`server/.env.example`). Startup probes each pool model with a 10-second
deadline and only uses models that answer. Results (including failures) persist
in Postgres and are reused across restarts for less than one hour. Probes count against the same RPM
window as normal calls. The pool takes precedence over the legacy primary/fallback
settings; existing explicit `model=` names remain class hints. `model="lite"` and
`model="strong"` prefer that class, with fallback to available capacity.

`GEMINI_RPM=12` limits each model over a rolling minute. Run **one API worker** so
all demo requests share that limiter. `GEMINI_MODEL_RPM` optionally supplies JSON
overrides for individual models. Busy calls queue for up to
`GEMINI_QUEUE_TIMEOUT=45` seconds; SDK attempts have a
`GEMINI_CALL_TIMEOUT=25` second deadline (through the first chunk for streams).
SDK automatic retries are disabled so every retry uses the scheduler. Provider
`retryDelay` controls 429 cooldowns; daily exhaustion without a retry hint is
held for 24 hours. A stream is never replayed after emitting its first chunk.

Matcher judgements, explainer text, intake follow-ups, and embeddings persist in
Postgres for `LLM_CACHE_TTL_HOURS=24`. Profile, language, source content, prompt
versions, embedding model/task/dimensions are included in the relevant hashed
keys. Repeated concurrent requests for the same result share a cache fill.

Watch `GET /api/health/llm` for probe status, per-model usage, cooldowns, waiting
requests and cache counters. Call logs contain model, milliseconds, cached and
limited flags, without prompts or profile fields. Actual project quotas are shown
in [Google AI Studio](https://aistudio.google.com/usage?timeRange=last-28-days&tab=rate-limit);
this process cannot account for traffic from other apps sharing the project.

Tests: `python -m pytest tests -m "not live" -q` from `server/`.
