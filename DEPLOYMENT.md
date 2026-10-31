# Judge deployment: Cloud Run + Neon + Vercel

The backend runs in project `forgehackathon`, region `asia-south1`, service
`adhikaar-api`. Cloud Run and Vertex AI use project credits. Neon and Vercel
remain on their free plans. Hugging Face is no longer the deployment target.

Live URLs:

- Frontend: https://adhikaar-jade.vercel.app
- API: https://adhikaar-api-813554369403.asia-south1.run.app
- API docs: https://adhikaar-api-813554369403.asia-south1.run.app/docs

Runtime identity: `forgehackathon-backend@forgehackathon.iam.gserviceaccount.com`.
All Google Cloud resources and secrets are in `forgehackathon`.

## Cloud prerequisites

Use a signed-in gcloud account with access to `forgehackathon`. The deploy script
needs permission to enable APIs, list service accounts, grant the two runtime
roles, read secret-version metadata, and deploy source builds. A project owner
can perform the initial API/IAM setup; routine source deployments require Cloud
Run source-deployment, Service Usage, and runtime service-account impersonation
permissions. The build service account also needs `roles/run.builder` if not
already configured by the project.

The script locates the **existing** service account by display name
`ForgeHackathon-backend`; it does not create a replacement. Set `SERVICE_ACCOUNT`
to the full email if display-name lookup is ambiguous. It ensures that account
has `roles/aiplatform.user` and `roles/secretmanager.secretAccessor`.

Required APIs: Cloud Run, Cloud Build, Artifact Registry, Secret Manager, Vertex
AI, and IAM. If Google reports `serviceusage.services.enable` or
`iam.serviceAccounts.list` denied, fix the active account's project permissions
before retrying. Logging into gcloud and selecting a project alone does not grant
those permissions.

## Neon and Secret Manager

1. In [Neon Console](https://console.neon.tech), use the existing project or create
   one on **Free**. Open **Connect**, choose the production branch, database and
   owner role, and copy its direct PostgreSQL URL with `sslmode=require` retained.
2. In [Secret Manager](https://console.cloud.google.com/security/secret-manager?project=forgehackathon),
   click **Create secret** for each of the following. Enter the value only in
   Secret Manager. Do not commit values or put them in frontend environment vars.

   | Secret name | Value |
   | --- | --- |
   | `adhikaar-database-url` | Hosted Neon SSL connection URL, never localhost |
   | `adhikaar-sarvam-api-key` | Existing Sarvam API key |
   | `adhikaar-profile-secret` | Stable Fernet key used to encrypt profiles |

3. Keep the profile key stable across revisions. If using an existing database,
   retain its existing profile key. Startup creates the vector extension and
   tables automatically; use a database role allowed to create the extension.
4. Existing secret names can be selected with `DATABASE_SECRET`, `SARVAM_SECRET`,
   and `PROFILE_SECRET_NAME` when running the deploy script. The script only reads
   metadata and attaches `latest` versions to Cloud Run; it never prints values.

## One-command backend deployment

With the exact Vercel origin as the argument, run from the repository root:

```bash
bash server/scripts/deploy_cloudrun.sh https://adhikaar-jade.vercel.app
```

On this Windows PC, Git Bash and gcloud are installed. From PowerShell:

```powershell
& 'C:/Program Files/Git/bin/bash.exe' server/scripts/deploy_cloudrun.sh https://adhikaar-jade.vercel.app
```

The script detects the Google SDK under `%LOCALAPPDATA%` if it is not on PATH.
`GCLOUD` can override the executable path. No install or service-account key file
is required. It builds the existing `server/Dockerfile` with `--source server`;
`.gcloudignore` excludes local `.env`, credentials, tests, storage and caches from
source upload. `.dockerignore` also excludes sensitive/local files.

The deployed configuration is:

- Vertex ADC: `GEMINI_BACKEND=vertex`, `GCP_PROJECT=forgehackathon`,
  `GCP_LOCATION=global`, `GEMINI_RPM=60`. No Gemini or Vertex API key is deployed.
- Model pool order comes from the application defaults. Vertex uses best-first
  scheduling; the agent prefers the first/highest model in that pool.
- `AGENT_HEADLESS=true`, `STORAGE_DIR=/tmp/adhikaar`, `DATABASE_TRANSPORT=tcp`,
  and `CLIENT_ORIGIN` set to the supplied frontend origin(s).
- 2 CPUs, 4 GiB RAM, minimum one and maximum one revision instance, service-level
  maximum one, continuously allocated CPU, 3,600-second timeout, session affinity,
  and one uvicorn worker on Cloud Run's injected `$PORT` (8080).
- Public API using `--no-invoker-iam-check`, without an `allUsers` IAM binding.
  The organization must allow disabling the invoker check.

`CLIENT_ORIGIN` may contain comma-separated exact origins. Deployments replace
this service's environment with the intended settings, so stale local/API-key
credentials do not override ADC. The region controls where the backend and
Chromium run; Vertex's model endpoint remains global as requested.

Cloud Run may replace an instance even with a minimum instance configured. Live
agent state and temporary audio/screenshots do not survive replacement. Neon
retains profiles, scheme data and LLM caches. Revisions can overlap during a
rollout; avoid redeploying while a judge is using a live agent run.

## Vercel frontend

1. Sign in at [Vercel](https://vercel.com/new), select the Hobby account, click
   **Add New** -> **Project**, and import `yashchoudhary14/ForgeHackathon`.
2. Select **Vite**, set **Root Directory** to `client`, keep build command
   `npm run build` and output `dist`, and select source branch `deploy`.
3. Add `VITE_API_URL` in **Environment Variables** for Production and Preview.
   Use the Cloud Run URL printed by the script, with no `/api` suffix or trailing
   slash. HTTP requests, WSS agent connections, audio and screenshots use it.
4. Deploy, then copy the production origin and redeploy the backend with that
   exact origin if it differed from the initial argument. Add only exact preview
   origins judges will use. `client/vercel.json` handles SPA deep-link rewrites.
5. For subsequent changes: **Settings** -> **Environment Variables** -> edit
   `VITE_API_URL`, then **Deployments** -> latest production -> **...** ->
   **Redeploy**. An environment change requires a new frontend build.
6. In project **Settings** -> **Environments** -> **Production** -> **Branch
   Tracking**, select `deploy` for Git-based updates (some UIs label this
   **Production Branch** under **Settings** -> **Git**).

## Live verification

From this checkout's Python environment, run with the real service and frontend
URLs (the script runs on the PC; it does not need server storage access):

```powershell
.venv/Scripts/python -X utf8 server/scripts/smoke_deploy.py --base-url https://adhikaar-api-813554369403.asia-south1.run.app --origin https://adhikaar-jade.vercel.app --agent --hindi-explain
```

It checks five no-quota health pings, live scheme search, the frontend CORS
preflight, a Hindi PM-KISAN explanation with verified source citations and a
served WAV, and a real headless agent run on
`https://www.myscheme.gov.in/find-scheme`. The agent's goal only reads the page;
it does not submit an application. Its WSS connection carries Cloud Run's session
affinity cookie and must receive live frames. The receipt screenshot must also
be publicly served. These checks consume real Vertex/Sarvam quota and create a
demo profile and run in Neon.

`/api/health` never queries Gemini or Postgres. `/api/health/llm` reports local
scheduler/cache state without a provider call. Startup probes and their failed
results are cached in Neon for less than one hour, scoped by backend, project,
location, credential fingerprint, and model/RPM configuration. A restart restores
the probe state; no API key is needed when Cloud Run uses its service identity.

For local checks, use the same Docker image and local pgvector container as
before. Inside a local API container, `smoke_deploy.py` also checks writable local
storage by creating and serving a short WAV file.

## Recorded live checks (31 October 2026)

- Source build `bf0ebb6f-23e9-4fec-8c7f-250aea3f946b` succeeded. Cloud Run
  revision `adhikaar-api-00002-xqt` serves 100% of traffic with the final CORS
  origin. Requested resource, scaling, timeout, identity, secret, session-affinity
  and public-invoker settings were read back and verified.
- Public health: HTTP 200; five pings consumed zero model calls. Scheme search
  from the Mumbai backend returned HTTP 200 and 440 farmer-related results.
- The CORS revision logged `startup probe restored from database`; all seven
  generation models were initialized at the configured 60 RPM.
- Hindi PM-KISAN explanation: native-script summary, three verified citations,
  and 1,203,328 bytes of served WAV audio.
- Headless myScheme run `5045bc251ae34443a12f53c63f697db0`: **done**, seven
  live frames received over WSS, title `Find Scheme`, heading `Help us find the
  best schemes for you`, and a served receipt screenshot.
- Local regressions: 78 backend tests pass on Windows and in the built Linux
  image; 17 client tests and the production client build pass.
- Vercel production deployment `5bmDrgMKtWX54An2m3Lh3tC4EqhD` is **Ready**
  from branch `deploy`, commit `a1530c7`, with root `client` and the correct
  Cloud Run URL. Production branch tracking is `deploy`.
- Anonymous `/schemes` returns HTTP 200 through the SPA rewrite. The deployed
  JavaScript contains the Cloud Run base and credentialed requests for affinity.
  A real browser search on the production frontend rendered 440 scheme results.

## References

- [Cloud Run source deployments](https://cloud.google.com/run/docs/deploying-source-code)
- [Cloud Run deploy flags](https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy)
- [Cloud Run public access without IAM checks](https://cloud.google.com/run/docs/authenticating/public)
- [Cloud Run WebSockets](https://cloud.google.com/run/docs/triggering/websockets)
- [Vercel Vite deployments](https://vercel.com/docs/frameworks/frontend/vite)
