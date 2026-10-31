"""profile -> candidate schemes (live myscheme) -> per-criterion eligibility with verified citations"""
import asyncio
import logging
import re
from typing import Literal

from pydantic import BaseModel

from ..schemas import Citation, MatchResult, ProfileData, Reason, SchemeDetail, SchemeSummary
from ..services import llm

log = logging.getLogger(__name__)

JUDGE_SYSTEM = """You decide whether a citizen qualifies for an Indian government scheme.
You get the scheme's OFFICIAL eligibility and exclusion text and the citizen's profile.
For every distinct criterion in the official text produce one reason:
- claim: the criterion in plain words
- met: true / false / null (null = profile doesn't say, we need to ask)
- quote: copy the exact words from the official text that state this criterion (verbatim, max 30 words). No paraphrase.
- section: "eligibility" or "exclusions"
Then give a verdict:
- eligible: every criterion met and no exclusion applies
- likely: nothing failed but some are unknown
- not_eligible: any criterion clearly failed or an exclusion clearly applies
- unknown: text too vague to judge
confidence 0..1. missing_info: short questions for unknown criteria. documents_needed: from the documents text.
Do not invent criteria that are not in the text.
Special conditions (disability, widow, orphan, minority, BPL card, ex-serviceman, rank holder, single girl child...):
if the profile does not mention them, treat them as NOT applying (met=false), the citizen can correct us later.
Course level matters: a B.Sc/B.A/B.Com student is undergraduate, not postgraduate."""


class _Reason(BaseModel):
    claim: str
    met: bool | None
    quote: str
    section: str


class _Judgement(BaseModel):
    verdict: Literal["eligible", "likely", "not_eligible", "unknown"]
    confidence: float
    reasons: list[_Reason]
    missing_info: list[str]
    documents_needed: list[str]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9ऀ-෿]+", " ", s.lower()).strip()


def quote_found(quote: str, source: str) -> bool:
    """llms love to 'fix' quotes. accept exact match after normalising, or 85% of words in order-ish window"""
    q, src = _norm(quote), _norm(source)
    if not q:
        return False
    if q in src:
        return True
    words = q.split()
    if len(words) < 4:
        return False
    hits = sum(1 for w in words if w in src)
    return hits / len(words) >= 0.85


def profile_filters(p: ProfileData) -> dict:
    f = {
        "state": p.state,
        "gender": p.gender,
        "caste": p.caste,
        "residence": p.residence,
        "age": p.age,
        "is_student": p.is_student,
        "is_bpl": p.is_bpl,
        "disability": bool(p.disability_percent) if p.disability_percent is not None else None,
        "is_minority": p.is_minority,
    }
    return {k: v for k, v in f.items() if v is not None}


def keywords_for(p: ProfileData, extra: str | None) -> list[str]:
    kws = [extra] if extra else []
    if p.is_student:
        kws.append("scholarship")
    if p.occupation:
        kws.append(p.occupation)
    if p.land_acres:
        kws.append("farmer")
    return kws or [""]


async def candidates(p: ProfileData, keyword: str | None, limit: int) -> list[SchemeSummary]:
    from ..services import myscheme

    filters = profile_filters(p)
    seen: dict[str, SchemeSummary] = {}
    for kw in keywords_for(p, keyword):
        try:
            res = await myscheme.search(kw, filters=filters, offset=0, size=limit)
        except Exception as e:
            log.warning("myscheme search failed for %r: %s", kw, e)
            continue
        for s in res.items:
            seen.setdefault(s.slug, s)
    # semantic pass over cached schemes catches ones keyword search misses
    try:
        query = f"{p.occupation or ''} {p.education_level or ''} {p.state or ''} {keyword or ''}".strip()
        if query:
            for s in await myscheme.semantic_search(query, k=limit):
                if not p.state or not s.state or s.state == p.state:
                    seen.setdefault(s.slug, s)
    except Exception as e:
        log.info("semantic search skipped: %s", e)
    return list(seen.values())[: limit * 2]


async def judge(p: ProfileData, scheme: SchemeDetail) -> MatchResult:
    result = await llm.cached("matcher.judge", [
        scheme.slug, p.model_dump(exclude_none=True), scheme.model_dump(mode="json"), JUDGE_SYSTEM,
    ], lambda: _judge(p, scheme))
    return MatchResult.model_validate(result)


async def _judge(p: ProfileData, scheme: SchemeDetail) -> MatchResult:
    official = f"ELIGIBILITY:\n{scheme.eligibility_md}\n\nEXCLUSIONS:\n{scheme.exclusions_md or 'none listed'}"
    prompt = (
        f"Scheme: {scheme.name} ({scheme.ministry or scheme.state or ''})\n\n{official}\n\n"
        f"DOCUMENTS:\n{scheme.documents_md[:1500]}\n\n"
        f"Citizen profile: {p.model_dump_json(exclude_none=True)}"
    )
    j = await llm.generate_json(prompt, _Judgement, system=JUDGE_SYSTEM, model="strong")

    reasons: list[Reason] = []
    dropped = 0
    for r in j.reasons:
        src = scheme.exclusions_md if r.section == "exclusions" else scheme.eligibility_md
        if quote_found(r.quote, src) or quote_found(r.quote, official):
            reasons.append(Reason(
                claim=r.claim, met=r.met,
                citation=Citation(source_url=scheme.source_url, title=scheme.name, quote=r.quote, section=r.section),
            ))
        else:
            dropped += 1  # unsupported claim -> don't show it, don't let it decide anything
            log.info("dropped unverifiable reason for %s: %s", scheme.slug, r.claim)

    verdict, conf = j.verdict, max(0.0, min(1.0, j.confidence))
    # recompute verdict from verified reasons only, so the model can't contradict its own evidence
    if reasons:
        if any(r.met is False for r in reasons):
            verdict = "not_eligible"
        elif all(r.met is True for r in reasons):
            verdict = "eligible" if dropped == 0 else "likely"
        else:
            verdict = "likely"
    else:
        verdict, conf = "unknown", min(conf, 0.3)
    if dropped:
        conf *= 0.85
    missing_info = j.missing_info or [r.claim for r in reasons if r.met is None]

    summary = SchemeSummary(**scheme.model_dump(include=set(SchemeSummary.model_fields)))
    return MatchResult(
        scheme=summary, verdict=verdict, confidence=round(conf, 2), reasons=reasons,
        missing_info=missing_info, documents_needed=j.documents_needed,
    )


ORDER = {"eligible": 0, "likely": 1, "unknown": 2, "not_eligible": 3}


async def match(p: ProfileData, keyword: str | None = None, limit: int = 8, lang: str = "en") -> list[MatchResult]:
    from ..services import myscheme

    cands = await candidates(p, keyword, limit)
    sem = asyncio.Semaphore(12)  # paid vertex quota, 4 was for the free tier

    async def one(s: SchemeSummary) -> MatchResult | None:
        async with sem:
            try:
                detail = await myscheme.get_scheme(s.slug, lang="en")  # judge on english text, explain later in user lang
                if not detail.eligibility_md.strip():
                    return None
                return await judge(p, detail)
            except Exception as e:
                log.warning("judging %s failed: %s", s.slug, e)
                return None

    results = [r for r in await asyncio.gather(*(one(s) for s in cands)) if r]
    results.sort(key=lambda r: (ORDER[r.verdict], -r.confidence))
    return results[:limit]
