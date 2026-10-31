# Judge deployment

## Hosting status (31 October 2026)

**A new deployment on this exact stack cannot currently be promised at $0.**
[Hugging Face's current documentation](https://huggingface.co/docs/hub/spaces-overview)
requires a paid plan to create a Docker Space, even though CPU Basic has no hourly
compute charge. Free hardware can also sleep when unused. The owner confirmed
there is no existing free Docker Space. Stop at the HF plan gate; do not buy an
upgrade for this deployment. The remaining steps are prepared for an eligible
account or a later hosting decision. Health pings are safe but do not provide an
uptime guarantee or override the provider's lifecycle policy.

The backend uses Neon WSS on port 443 by default because Spaces only documents
outbound ports 80, 443, and 8080. It keeps the existing SQLAlchemy/asyncpg sessions,
transactions, and pgvector queries; the external connection uses verified TLS.
`DATABASE_TRANSPORT=tcp` selects ordinary verified Postgres TLS on hosts that allow
port 5432. No database proxy service or paid storage is required.

## 1. Neon (free)

1. Open [Neon Console](https://console.neon.tech), sign in, click **New project**,
   name it `adhikaar`, choose the nearest available region, and create it on
   **Free**. Keep the default database `neondb` and owner role.
2. Click **Connect**. Select the production branch, `neondb`, and its owner role.
   Use the **direct** connection (connection pooling off) for this small demo.
   Copy the `postgresql://...` connection string, retaining
   `?sslmode=require&channel_binding=require`. Store it as the backend's
   `DATABASE_URL` secret, never in the Vercel client or a committed file.
3. No manual migration is required: startup runs
   `CREATE EXTENSION IF NOT EXISTS vector` before creating tables, including
   `llm_cache` for saved model probes.
4. To verify after backend startup, click **SQL Editor**, select the same branch
   and database, and run:

   ```sql
   SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
   SELECT tablename FROM pg_tables WHERE schemaname = 'public';
   ```

Leave scale-to-zero enabled and watch **Monitoring** / plan usage. The documented
Free plan includes 100 CU-hours per project per month; idle compute suspends
after five minutes. `/api/health` makes no DB query, so uptime monitoring does
not keep Neon compute awake. See [Neon limits](https://neon.com/docs/introduction/plans)
and [pgvector](https://neon.com/docs/extensions/pgvector).

## 2. Hugging Face (currently blocked for a new free account)

1. Open [Create Space](https://huggingface.co/new-space). Enter `adhikaar-api`,
   choose **Docker** → **Blank**, **Public**, and **CPU Basic** if available.
   If creating it requires upgrading the account, stop here. No paid plan is
   authorized. Public visibility allows judges and the Vercel browser to reach it.
2. If eligible, open **Settings** → **Variables and secrets**. Use **New secret**
   for each of:

   | Secret | Value |
   | --- | --- |
   | `DATABASE_URL` | Full Neon URL from step 1 |
   | `GEMINI_API_KEY` | Your Gemini key |
   | `PROFILE_SECRET` | A stable Fernet key; retain it across restarts |
   | `SARVAM_API_KEY` | Your Sarvam key if speech is needed |

   Generate the profile key locally with the existing Python environment:

   ```powershell
   .venv/Scripts/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

3. Use **New variable** for:

   | Variable | Value |
   | --- | --- |
   | `CLIENT_ORIGIN` | Exact Vercel origin, e.g. `https://adhikaar.vercel.app` |
   | `AGENT_HEADLESS` | `true` |
   | `STORAGE_DIR` | `/tmp/adhikaar` |
   | `DATABASE_TRANSPORT` | `auto` |
   | `GEMINI_MODEL_POOL` | `gemini-3.5-flash-lite` (tested); confirm availability/quota for your key |
   | `AGENT_MODEL` | `gemini-3.5-flash-lite` (tested) |
   | `GEMINI_RPM` | `12` or your lower actual per-model limit |

   For multiple frontends, `CLIENT_ORIGIN` can be
   `https://adhikaar.vercel.app,https://another-exact-origin.vercel.app`.
   Do not include URL paths, trailing slashes, or wildcard preview domains.
   Leave `PORT` at `7860`, matching `app_port` in `server/README.md`.

4. Open **Files** → **Add file** → **Upload files**. Upload these from the
   `deploy` branch's `server/` directory **at the Space repository root**:
   `Dockerfile`, `.dockerignore`, `README.md`, `requirements.txt`, and the `app/`
   and `scripts/` folders. Preserve subdirectories; do not upload a wrapping
   `server/` folder. Do not upload `.env`, tests, storage, caches, or `.venv`.
   Click **Commit changes**. GitHub pushes do not automatically sync an HF repo.
5. Open **App** and inspect **Logs** until the status is **Running**. Open the
   direct app URL shown by HF (`https://YOUR-SPACE-SUBDOMAIN.hf.space`) and visit
   `/api/health`: expect HTTP 200 with `ok: true`. `/docs` lists API endpoints.
   Try `/api/schemes/search?keyword=farmer&size=2`.

The image runs as UID 1000 with exactly one uvicorn worker. `/tmp/adhikaar` is
writable and is exposed at `/files`; audio URLs remain `/files/audio/*.wav`.
Files disappear on container replacement/restart. Profiles, scheme data, and
model/probe caches persist in Neon; file bytes do not. `/data` is supported via
`STORAGE_DIR` only if a writable volume is provided; persistent HF storage is
outside this free-only setup. See [Docker Spaces](https://huggingface.co/docs/hub/spaces-sdks-docker).

## 3. Vercel (Hobby)

1. Open [Vercel](https://vercel.com/new), sign in with GitHub, select the **Hobby**
   account, click **Add New** → **Project** if starting from the dashboard, then
   **Import** `yashchoudhary14/ForgeHackathon`.
2. Set **Framework Preset** to **Vite**. Click **Edit** beside **Root Directory**,
   select `client`, and confirm. Keep build command `npm run build` and output
   directory `dist`. `client/vercel.json` supplies the SPA rewrite.
3. Expand **Environment Variables**, add `VITE_API_URL` with the direct backend
   base such as `https://YOUR-SPACE-SUBDOMAIN.hf.space`, and apply it to Production
   and Preview. Omit `/api` and a trailing slash. This same base supplies HTTPS
   requests, WSS agent streams, audio, and screenshots. Do not put API keys here.
4. Deploy the **`deploy` branch**. If import defaults to `main`, first open the
   project **Settings** → **Environments** → **Production** → **Branch Tracking**
   and set it to `deploy`, then open **Deployments** → **Create Deployment**,
   choose `deploy`, and deploy. UI versions may call this setting **Production
   Branch** under **Settings** → **Git**. Verify the deployment's source branch
   and commit before sharing it.
5. Copy the assigned production origin back to HF's `CLIENT_ORIGIN` variable
   and let the backend restart. Add any exact preview origin judges will use.
6. Visit the Vercel app, open the Schemes page, then reload a deep URL such as
   `/schemes`: it should load the app instead of a Vercel 404. Start a read-only
   agent run and verify live frames and receipt images. Browser Network should
   show a `wss://...hf.space/api/agent/runs/.../ws` connection with status 101.

Changing `VITE_API_URL` requires a new build: **Deployments** → latest production
deployment → **…** → **Redeploy**. See [Vercel Vite setup](https://vercel.com/docs/frameworks/frontend/vite)
and [environment variables](https://vercel.com/docs/environment-variables).

## Quota and judging window

Use only `/api/health` for uptime checks. Both health endpoints report local
state without Gemini calls; liveness also avoids DB traffic. Model startup probes
are stored in Postgres, scoped to the API key and pool configuration, and reused
for **less than one hour**, including failed probes, cooldowns, and probe RPM
usage. Changing the key or pool triggers a fresh probe. With no key, startup
skips the probe and health/search remain usable.

Probe caching reduces restarts' quota cost; it does not increase the provider's
daily allowance. Every real agent step can make a generation call. With only
20 requests/day for a large model, a long form-filling run can exhaust that model.
Use an available lite model where appropriate, cache repeated demos, and check
`/api/health/llm` before judging. Keep one worker and one backend replica so the
in-memory limiter and live WebSockets share state. Existing runs cannot resume
after a backend restart. Free tiers and upstream government APIs provide no
multi-day availability guarantee.

## Repeat local checks

From the repository root, with Docker running and `server/.env` configured:

```powershell
docker compose up -d db
docker build -t adhikaar-api:deploy ./server
docker run -d --name adhikaar-judge-test -p 7860:7860 --env-file server/.env -e DATABASE_URL=postgresql+asyncpg://postgres:postgres@host.docker.internal:5432/adhikaar -e AGENT_HEADLESS=true -e STORAGE_DIR=/tmp/adhikaar adhikaar-api:deploy
docker logs -f adhikaar-judge-test
```

After startup, in another terminal:

```powershell
docker exec adhikaar-judge-test python scripts/smoke_deploy.py
# Uses real Gemini quota and saves a demo profile/run:
docker exec adhikaar-judge-test python scripts/smoke_deploy.py --agent
docker stop adhikaar-judge-test
docker rm adhikaar-judge-test
```

Set `-e GEMINI_API_KEY=` on the `docker run` command for health/search/audio
checks with no Gemini credentials or probes. Use a small explicit
`GEMINI_MODEL_POOL` to avoid probing unused models during validation.

## Validation recorded on this branch

- Docker build succeeded; Linux Python 3.12 image runs as UID 1000, headless,
  with one uvicorn worker. Default `7860` and an overridden `PORT=8080` passed.
- Backend: 74 tests passed on Windows and in the built Linux image; eight live
  service tests excluded. Frontend: 17 tests passed; production build succeeded.
- `/api/health`: five repeated pings added zero model requests, with and without
  a configured Gemini key. The keyless container also passed search and audio.
- `/api/schemes/search?keyword=farmer&size=2`: HTTP 200, 440 live results.
- A WAV written under `/tmp/adhikaar/audio` was served byte-for-byte at `/files`.
- Exact-origin CORS accepted the configured Vercel origin and rejected an
  unlisted origin. No `.env` was present in the image.
- Real headless myScheme run `429e2453262646a59af694aa219131b7`: **done**, one
  decision step, nine WebSocket frames, title `Find Scheme`, heading
  `Help us find the best schemes for you`, and a served receipt screenshot.
  Used `gemini-3.5-flash-lite`; the large Flash model returned a quota error.
- Both successful and failed probe results survived actual container restarts,
  logging `startup probe restored from database` with no repeated Gemini probe.
- Live hosted Neon and HF/Vercel deployment were not tested or provisioned.
  No Neon credentials are configured locally. The PostgreSQL/pgvector check used
  local Postgres. The binary bridge also passed real asyncpg authentication,
  a pgvector distance query, and transaction rollback through a local WebSocket
  proxy. URL/TLS, binary frames, cache expiry and restart behavior have regression
  coverage. New free HF Docker hosting remains blocked as above.
