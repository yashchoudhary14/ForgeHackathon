# Live matcher regression profiles

Run from `server/` with a paid-quota model pool:

```powershell
.venv/Scripts/python.exe scripts/eval_match.py --fresh --model gemini-3.8-flash,gemini-3.1-flash-lite --rpm 600 --output storage/evals/varied.json
```

Each profile must retrieve and return these recommendations as eligible or likely
within 60 seconds. Likely means official conditions still require answers, not a
promise of an award. Profiles include explicit age/income assumptions in the script.

| Profile | Expected recommendations |
| --- | --- |
| Bihar SC undergraduate | SC post-matric scholarships: `pmsfss`, `pmsscstb`, `pmssc` |
| UP farmer, 2 acres | PM-KISAN, Kisan Credit Card, PM Fasal Bima Yojana |
| Rajasthan BPL widow, 68 | Indira Gandhi National Old Age Pension, Rajasthan widow pension |
| Maharashtra graduate job seeker, 24, 40% disability | Disabled self-employment assistance, ADIP aids/appliances, National Action Plan for Skill Development of Persons with Disabilities |
| MP OBC boy, class 11 | OBC post-matric scholarship (including PM-YASASVI) |
| Rural Odisha pregnant woman | MAMATA, Janani Suraksha Yojana, Janani Shishu Suraksha Karyakram, PM Matru Vandana Yojana |
| Delhi urban street vendor | PM SVANidhi |

Official catalogue examples: [SC post-matric](https://www.myscheme.gov.in/schemes/pmssc),
[ADIP](https://www.myscheme.gov.in/schemes/sadppfaa),
[OBC post-matric](https://www.myscheme.gov.in/schemes/pm-yasasvipmsobcebcdnts),
[MAMATA](https://www.myscheme.gov.in/schemes/mamata).

Search metadata can disagree with official detail: search labels `pmssc` Punjab,
while its official detail describes the national programme and has no state tag.
Keep specific category hits for official judging rather than treating search facets
as definitive eligibility. ADIP's acronym query returns no results; the title query
`aids appliances` needs a deeper search page. The final shortlist remains 32 at
the default limit. Specific beneficiary matches precede generic hits before both
the candidate cap and the final result cap.

The report separates recall, returned verdict, triage controls and elapsed match
time. `--fresh` bypasses matcher answers but retains source and embedding caches.
Reports are saved incrementally so interrupted runs remain inspectable. Cold-source
and provider latency can vary; unrelated embedding inputs now run concurrently,
while duplicate inputs still coalesce.
