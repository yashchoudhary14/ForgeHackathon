# Demo polish verification — 31 October 2026

Verification uses the actual local API and existing pgvector database. Preview: `http://localhost:5174`; API: `http://localhost:8001`. These temporary overrides were passed through process environment variables; no environment files or API contracts changed. The normal defaults remain 5173 and 8000.

## Browser checks

Chrome viewport: **375 × 812 CSS pixels**. The document content measured 360px with a 15px scrollbar, within the 375px viewport. Horizontal navigation and scheme tabs scroll within their own regions.

| Page | Real API checks | Result |
| --- | --- | --- |
| `/` | Profile extraction, profile reload and save | Passed; editable values returned by the API, English/हिंदी toggle and Start focus checked |
| `/schemes` | Matching and search against the saved profile | Passed; eight matches with official quotes; search returned 440 results and Next showed a different set using `offset=10` |
| `/schemes/nhmmih` | Scheme detail and explanation | All five tabs rendered; explanation endpoint returned 200 |
| `/explain` | Documents, live feed, explanation of an existing uploaded government notice | Passed; summary, citations and audio URL rendered |
| `/ask` | POST SSE chat | Passed; streamed answer, tool activity and three official citations; controls re-enabled after completion |
| `/runs` | Run list and existing receipts | Passed; receipt references, source links and screenshots rendered |
| `/runs/:id` | Created a read-only live browser preview, requested approval, reloaded the page, then aborted | Passed; actual 1280px portal frames, steps and pending approval replayed; no final approval or portal submission |

Additional checks: missing-run 404 rendered friendly guidance and a working retry button; all seven pages measured within the 375px viewport. Home English/हिंदी layout and Start focus were visually checked. Ended-session recovery was checked against a saved run with no live manager session.

## Automated checks

- `npm run build` — passed, TypeScript and production Vite build.
- `npm test` — **18 passed**, including SSE chunking, run event replay/snapshot handling, timeouts, receipts and friendly error regression checks.
- `git diff --check` — passed.

All product data came from the real API. The new run used a read-only goal to pause for approval on the live myScheme page; no application information was entered into that portal.

## Limits and backend observations

- CAPTCHA and OTP controls retain their existing WebSocket payloads. They were reviewed and covered by existing human-event state tests; real CAPTCHA/OTP challenges and takeover input were not exercised in this pass.
- The backend currently persists aborting at an approval node as `failed` with `Node 'approval' raised asyncio.CancelledError`. The client displays “This application was stopped” and keeps the actual API status. Backend behavior was left unchanged.
- The API has to replay a pending human request after reconnect; the current backend did this successfully. A session missing after a server restart cannot be resumed from `RunOut` alone and now gives clear recovery guidance.
- Microphone recording and final government-portal submission were not exercised.
