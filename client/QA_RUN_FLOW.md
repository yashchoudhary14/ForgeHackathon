# Local Run UI verification — 2026-11-01

Backend: `http://localhost:8000`; frontend: `http://localhost:5173`.
Real government portals, configured Gemini planner, database and WebSocket stream.
Fictional profiles and live runs were created through the API as test setup;
all citizen answers, takeover controls and submit approvals were exercised from
the web Run page, not `try_agent.py` or a CLI WebSocket client.

## myScheme: passed

Run: `8611ca77d13242edaf1005dc560b5bf3`.

1. Opened `/runs/8611ca77d13242edaf1005dc560b5bf3` with a profile omitting caste.
2. Verified the live portal frame and step timeline.
3. Answered the social-category question with `Scheduled Caste (SC)` in **Your answer**,
   then clicked **Continue**. The agent selected SC and advanced the questionnaire.
4. Reviewed the **Ready to submit?** checkpoint and clicked **Approve final submission**.
5. Verified status **done**, receipt reference **30**, official results URL and a
   loaded receipt screenshot showing the results list/count. No scheme application
   was submitted; this was the find-scheme questionnaire only.

Local UI evidence: `server/storage/myscheme-ui-receipt.png`.
Portal receipt: `/files/runs/8611ca77d13242edaf1005dc560b5bf3/019.jpg`.

## Fixes found during the flow

- A planner action after a human answer omitted `element_id`, causing slow locator
  timeouts. Invalid targets now fail immediately with a useful correction; the
  planner explicitly receives instructions to identify the visible control after
  a human answer. The fresh myScheme run completed without this failure.
- A recovery prompt asked the citizen to finish a step in the live view, but
  missing-field prompts offered no takeover control. They now provide **Take over**
  and **I'm done, continue**, using the existing live-canvas input and resume path.
- Earlier sessions expired after their 15-minute human-response deadline during
  an interruption. Fresh sessions were used for the verification above.

## NSP: CAPTCHA ready; citizen completion pending

Run: `bb7c6fa17326463cb6ca4fc917d49a58`.

The captcha endpoint returned HTTP 200 on retry. The live agent completed the
institution/course flow and paused at **Complete the CAPTCHA**. Verified the image
renders in the Run page; clicked **Take over** and verified **I'm done, continue**
becomes enabled. The citizen was asked to enter the CAPTCHA in the live view and
continue. CAPTCHA text was not transcribed or entered by the agent.

Local handoff evidence: `server/storage/nsp-ui-captcha-handoff.png`.
Continuation and eligibility-submit approval still require verification after
the citizen completes the challenge. This is not an end-to-end NSP pass yet.

## Checks

- Backend offline suite: **159 passed** (`--ignore=tests/test_live_services.py`).
- Frontend: **23 tests passed**.
- TypeScript and production Vite build: passed.
- `git diff --check`: passed.

The pre-existing abort-at-approval fix was retained; it was not reimplemented.
