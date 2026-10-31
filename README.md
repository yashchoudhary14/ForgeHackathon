# Adhikaar

Know your rights, claim them. Forge Gen AI buildathon - Theme 1 (Civic Pulse).

Run the API from `server/` with `uvicorn app.main:app`. PostgreSQL must have pgvector;
startup creates the tables, including `llm_cache`.

Judge deployment: see [DEPLOYMENT.md](DEPLOYMENT.md) for Google Cloud Run
(Vertex AI and credits), Neon, Vercel, and live verification commands.

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

Live matcher regression (Bihar SC woman, 19, first-year B.Sc, rural student,
annual income ₹140,000): from `server/`, run
`python scripts/eval_match.py --fresh --model gemini-3.8-flash --rpm 600 --output storage/evals/bihar-sc-student.json`.
Uses the configured backend and paid quota; `--rpm` changes only this run's local
budget. Checks central and Bihar SC post-matric recall and positive verdicts in
the final eight results, plus direct KCC/Pragati rejection before judging.
Contrast checks retain a student who also farms and a technical-degree student.
The command exits nonzero on any failed check. `--fresh` bypasses matcher answer
caches; official source and embedding caches still apply. Matcher retrieval
interleaves category/state searches with relaxed-facet recall; evidence-backed
target-group triage precedes the existing 12 concurrent eligibility judges.
