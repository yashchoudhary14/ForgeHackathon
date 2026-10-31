# Adhikaar API

Python 3.12 FastAPI backend with headless Chromium. Deploy from the repository
root using `bash server/scripts/deploy_cloudrun.sh https://YOUR-APP.vercel.app`.
See the root `DEPLOYMENT.md` for Cloud Run, Neon, Secret Manager and Vercel setup.

The Dockerfile runs as UID 1000 with one uvicorn worker on `$PORT` (default 7860;
Cloud Run supplies 8080). `/api/health` makes no database or Gemini call. API docs
are at `/docs`; temporary audio and screenshots are served under `/files`.
