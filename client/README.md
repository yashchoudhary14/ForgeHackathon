# Adhikaar client

React + TypeScript + Vite, with Tailwind CSS, React Router, Lucide icons, and markdown rendering.

## Run

Use Node.js 22 or later. From `client/`:

```sh
npm install
cp .env.example .env
npm run dev
```

In PowerShell, use `Copy-Item .env.example .env`. The default API origin is `http://localhost:8000`. Set `VITE_API_URL` to the backend origin (without `/api`) when needed. The backend must allow the frontend origin in its CORS configuration. Voice recording needs HTTPS or localhost and microphone permission.

```sh
npm run build
npm test
npm run format
```

The seven routes cover intake, scheme matching/search, scheme details, document explanations, streamed chat, live application runs, and application tracking. All content comes from the real API. No scheme, feed, eligibility, chat, application, or receipt fixtures are supplied as fallbacks. Only the profile ID and selected language are stored in localStorage; profile fields are fetched from the backend.

English and Hindi interface translations live in `src/context.tsx` and `src/i18n.ts`. All eleven language choices are sent to extraction, transcription, explanation, and chat; other languages use English interface labels.

Chat uses POST fetch streaming and a chunk-safe SSE parser. Runs render JPEG frames on a proportional canvas, reconnect with backoff, recover the step snapshot, and send the human-action messages defined in `server/app/schemas.py`. The server must replay a pending human request on reconnection: `RunOut` has no field carrying that request. URLs supplied to document ingestion and agent execution must be validated on the backend, including redirects and private-network destinations.

## Integration verification

The backend in this checkout currently contains placeholder domain routers. Until the real endpoints run, the UI displays error/retry states; successful matching, transcription, explanations, chat, and browser-agent execution cannot be verified end to end.

When the backend is ready, check a real profile through follow-up extraction, editing and reload; scheme matching with citations; scheme and uploaded-document audio; chat token/tool/citation events; and all human gates on a run. Disconnect/reconnect a run, confirm coordinates on both phone and desktop, and check that the final receipt appears on `/runs`.

The SSE tests use protocol-only text to check arbitrary chunk boundaries, CRLF, Unicode, multiline data, final flushing, and error propagation. They do not feed static product content into the application.
