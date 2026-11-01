# Buddy client

React + TypeScript + Vite, with Tailwind CSS, React Router, Lucide icons, and markdown rendering.

## Run

Use Node.js 22.18 or later. From `client/`:

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

Routes cover Home, Profile, Talk, scheme matching/search, scheme details, document explanations, streamed chat, live application runs, documents, civic reports and activity. `/profile` edits saved details through the profile API, shows document counts and activity from the real APIs, and saves language and mode preferences. Home links to the saved profile with a short summary. No product fixtures are supplied as fallbacks. Profile fields are fetched from the backend; localStorage keeps the profile ID and interface preferences.

The brand, navigation, Home and Profile support English, Hindi, Bengali and Assamese through `src/ui-strings*.ts` and `src/profile-strings.ts`. Other language choices use English interface labels. The localized brand is Buddy / साथी / বন্ধু / বন্ধু. Localized manifests follow the active UI language. Code identifiers, storage keys and deployment URLs retain their original names.

The focused profile and branding tests run directly on Node without a browser or Vite: `node --test --test-isolation=none tests/profile.test.mjs`. They verify language-specific branding and manifests, complete profile translations, form patches, validation, completeness and avatar fallbacks.

Chat uses POST fetch streaming and a chunk-safe SSE parser. Runs render JPEG frames on a proportional canvas, reconnect with backoff, recover the step snapshot, and send the human-action messages defined in `server/app/schemas.py`. The server must replay a pending human request on reconnection: `RunOut` has no field carrying that request. URLs supplied to document ingestion and agent execution must be validated on the backend, including redirects and private-network destinations.

## Integration verification

The demo-polish verification record is in [QA.md](QA.md). Run the real API and database before checking the client; the interface never substitutes scheme, eligibility, explanation or run fixtures when a service fails.

Home introduces Understand, Act and Speak up, with a short personal summary linking to Profile. Language controls are available in the desktop header and Profile. Loading states explain the operation in progress without inventing counts, and failures show recovery guidance and retry controls.

For further integration checks, exercise microphone transcription, all human gates on a run, takeover coordinates on phone and desktop, and final submission only with explicit approval. A live session lost after an API restart displays recovery guidance while preserving saved steps.

The SSE tests use protocol-only text to check arbitrary chunk boundaries, CRLF, Unicode, multiline data, final flushing, and error propagation. They do not feed static product content into the application.
