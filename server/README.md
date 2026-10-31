# Adhikaar API

Python 3.12 FastAPI backend with headless Chromium. Deploy from the repository
root using `bash server/scripts/deploy_cloudrun.sh https://YOUR-APP.vercel.app`.
See the root `DEPLOYMENT.md` for Cloud Run, Neon, Secret Manager and Vercel setup.

The Dockerfile runs as UID 1000 with one uvicorn worker on `$PORT` (default 7860;
Cloud Run supplies 8080). `/api/health` makes no database or Gemini call. API docs
are at `/docs`; temporary audio and screenshots are served under `/files`.

## Streaming scheme matches

`POST /api/schemes/match/stream` accepts the same JSON body as
`POST /api/schemes/match`: `profile_id`, optional `keyword`, and `limit` (default 8).
It returns `text/event-stream` with JSON in each SSE `data:` frame:

- `{"type":"progress","message":"found 32 schemes","checked":0,"total":32}`
- `{"type":"result","result":<MatchResult>}` as each judgement completes.
- `{"type":"progress","message":"checked 12/32","checked":12,"total":32}`
- `{"type":"done","results":[<MatchResult>, ...]}` with the sorted, limited shortlist.

Progress counts all checked candidates, including skipped or failed checks.
Intermediate results may exceed `limit`; the final shortlist has the same verdict,
confidence and tie ordering as the existing JSON endpoint. Comment keepalives are
sent every 10 seconds while waiting. A stream failure sends a safe `error` event;
client disconnects cancel pending matching work. Invalid or missing profiles are
rejected before streaming starts. The original JSON endpoint remains available.
