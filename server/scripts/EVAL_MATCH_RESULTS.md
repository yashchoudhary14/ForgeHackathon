# Live validation: 2026-10-31

Fresh matcher answers; source/embedding caches retained. Pool: `gemini-3.8-flash,gemini-3.1-flash-lite`, 600 RPM. Default result limit 8, candidate cap 32.

The combined run passed six profiles; Odisha passed a separate fresh rerun after clarifying alternative eligibility routes. The timings below are from those runs.

| Profile | Match seconds | Required returned schemes (eligible/likely) |
| --- | ---: | --- |
| bihar-sc-student | 33.27 | `pmsfss`, `pmssc`, `pmsscstb` |
| up-small-farmer | 30.82 | `pm-kisan`, `kcc`, `pmfby` |
| rajasthan-bpl-widow | 31.65 | `nsap-ignoaps`, `ignwps` |
| maharashtra-disabled-graduate | 31.84 | `sadppfaa`, `nap-sdp`, `fadse` |
| mp-obc-class11 | 7.79 | `pmsoeds` |
| odisha-pregnant | 30.94 | `mamata`, `jsy1`, `pmmvy`, `jssk` |
| delhi-street-vendor | 5.18 | `pm-svanidhi` |

Offline suite: **144 passed**. Full suite before the final prompt adjustment: **146 passed, 2 failed**; failures were live document retrieval and live voice/translation, including a closed event-loop error.

Full local reports: `server/storage/evals/varied-final.json` and `server/storage/evals/odisha-final.json` (ignored by git).
