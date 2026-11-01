"""profile -> candidate schemes (live myscheme) -> per-criterion eligibility with verified citations"""
import asyncio
from collections.abc import AsyncIterator
from contextlib import aclosing
import logging
from html import unescape
import re
from typing import Literal

from pydantic import BaseModel

from ..config import get_settings
from ..schemas import Citation, MatchResult, ProfileData, Reason, SchemeDetail, SchemeSummary
from ..services import llm
from .matching_rules import institutional_target, numeric_checks, profile_text

log = logging.getLogger(__name__)
MATCH_SECONDS = 55.0
TALK_MATCH_SECONDS = 18.0

JUDGE_SYSTEM = """You decide whether a citizen qualifies for an Indian government scheme.
The applicant is an individual citizen. Construction/organisation grants whose applicants
are institutions, states, UTs or NGOs are not citizen entitlements: mark not_eligible
with an exact quote establishing that target. Hostel construction is not hostel admission.
Read annual_income_display in Indian grouping and lakh; compare the actual numeric
income/age against the official limits, never add a zero or confuse lakh with million.
You get the scheme's OFFICIAL eligibility and exclusion text and the citizen's profile.
For every distinct criterion applicable to the citizen's eligibility route produce one reason:
- claim: the criterion in plain words
- met: true / false / null (null = profile doesn't say, we need to ask)
- quote: copy a SINGLE CONTIGUOUS span from the official text (verbatim, max 30 words).
  Never combine separate list items, insert connecting words, or rewrite an ampersand.
  For alternative applicant categories quote only the applicable item.
- section: "eligibility", "exclusions", or "details"
- For exclusions, also set exclusion_applies: true if the exclusion applies to this citizen,
  false if it clearly does not, null if unknown. met means the citizen PASSES the restriction,
  not whether the excluded condition is true. Never infer a completed prior degree or receipt
  of another scholarship from missing data or from being a first-year undergraduate.
Then give a verdict:
- eligible: every criterion met and no exclusion applies
- likely: nothing failed but some are unknown
- not_eligible: any criterion clearly failed or an exclusion clearly applies
- unknown: text too vague to judge
confidence 0..1. missing_info: short questions for unknown criteria. documents_needed: from the documents text.
Do not invent criteria that are not in the text.
Respect the official scheme jurisdiction, including state restrictions omitted from the eligibility prose.
Scope criteria to the applicable beneficiary/state/course branch. Alternative routes and lists of
qualifying groups are OR, not AND: satisfying one route is enough. Do not fail an applicant for an
inapplicable branch (for example high-performing-state rules for a low-performing-state resident).
Read exceptions with their rule; an exception can restore eligibility. Future renewal/payment
conditions are not proof of a present failure. Missing ordinary facts remain unknown.
For school-course restrictions, check whether the applicant passed a matriculation-equivalent
Class 10 before entering the current course. Class XI alone does not prove a continuous-course
exclusion applies. If board equivalence or the course transition is unknown, mark it null,
and quote the exception as well as the restriction. Do not turn uncertainty into a failure.
Special conditions (disability, widow, orphan, minority, BPL card, ex-serviceman, rank holder, single girl child...):
if the profile does not mention them, treat them as NOT applying (met=false), the citizen can correct us later.
Course level matters: a B.Sc/B.A/B.Com student is undergraduate, not postgraduate.
A general B.Sc/B.A/B.Com is not an AICTE technical degree. Check the target group in
the official name/description too, even if the eligibility section omits it.
Rural residence does not establish farming. A citizen whose occupation is student
is not a farmer unless farming/tenancy/animal husbandry/fishing is also stated.
Post-matric includes undergraduate study after class 10; do not confuse it with postgraduate.
Do not infer previous graduation, another scholarship, or an exclusion from missing information."""

TRIAGE_SYSTEM = """Screen an Indian government scheme's TARGET GROUP before detailed eligibility judging.
The applicant is an individual citizen, not an institution, state government or NGO.
Drop institution-only construction/organisation grants even if the citizen belongs to
the community ultimately served. Quote the institutional applicant/construction target.
Use annual_income_display (Indian grouping and lakh) for numeric comparisons.
Drop only a clear target-group mismatch supported by the supplied official text.
Check occupation, course/education level, caste/category, state, gender and special beneficiary groups.
A rural student is not a farmer just because she lives in a village. If occupation is student
and no farming/tenancy/livestock/fishing role is stated, drop farmer-only credit schemes.
Preserve students who explicitly also farm or have agricultural land; do not assume all students cannot farm.
A general B.Sc/B.A/B.Com is not an AICTE technical degree or diploma. An engineering student with
unknown institution approval is still a possible fit. B.Sc Nursing/agriculture are distinct from general B.Sc.
An undergraduate is not postgraduate; post-matric DOES include undergraduates.
SC students do not fit schemes restricted to OBC/EBC/ST alone, but fit combined SC/ST schemes.
Do not drop for ordinary unknowns such as documents, marks, institution approval or another scholarship.
Do not drop broad schemes merely because one example or optional beneficiary group differs.
Read exceptions and alternative routes together with restrictions. A quoted restriction is not
grounds to drop if its exception applies, or if an alternative route remains possible.
When unsure, keep. Return drop, reason and an exact short quote from the official text proving
the target restriction. If keeping, return empty reason and quote. Never invent requirements."""


class _Reason(BaseModel):
    claim: str
    met: bool | None
    quote: str
    section: str
    exclusion_applies: bool | None = None


class _Judgement(BaseModel):
    verdict: Literal["eligible", "likely", "not_eligible", "unknown"]
    confidence: float
    reasons: list[_Reason]
    missing_info: list[str]
    documents_needed: list[str]


class _Triage(BaseModel):
    drop: bool
    reason: str
    quote: str


def target_text(scheme: SchemeDetail) -> str:
    jurisdiction = f"Scheme jurisdiction: {scheme.state}\n" if scheme.state else ""
    return f"{scheme.name}\n{jurisdiction}{scheme.brief or ''}\n{scheme.details_md}"


def occupational_target_mismatch(p: ProfileData, scheme: SchemeDetail) -> bool:
    """An exhaustive farmer-only eligibility list needs a stated farming role.

    This is recommendation triage, not a formal finding of ineligibility. Do not
    mistake farmer-family scholarships or mixed student/farmer groups for own-role credit.
    """
    occupation = _norm(p.occupation or "")
    if not (p.is_student or occupation == "student" or re.search(r"street vendor|hawker", occupation)):
        return False
    if (p.land_acres or 0) > 0 or re.search(r"farm|agricultur|cultivat|fish|livestock|animal husbandry", occupation):
        return False
    text = _norm(scheme.eligibility_md)
    if re.search(r"\b(children|child|wards|sons|daughters|dependents|students|families|family)\b", text):
        return False
    lines = [_norm(line) for line in scheme.eligibility_md.splitlines() if _norm(line)]
    lines = [line for line in lines if line not in ("eligibility", "eligibility criteria")]
    return bool(lines) and all(re.search(r"\b(farmers?|cultivators?|tenant farmers?|share croppers?|sharecroppers?|oral lessees)\b", line) for line in lines)


def educational_target_mismatch(p: ProfileData, scheme: SchemeDetail) -> bool:
    """An explicitly technical degree/diploma title excludes a plain general degree.

    Specialised B.Sc courses and unspecified courses still go to source-based screening.
    """
    general = {"b sc", "bsc", "b a", "ba", "b com", "bcom",
               "bachelor of science", "bachelor of arts", "bachelor of commerce"}
    return _norm(p.course or "") in general and bool(re.search(
        r"\btechnical (degree|diploma)\b", _norm(scheme.name)))


def qualified_restriction(quote: str, official: str) -> bool:
    """A restriction with an exception needs the full judge, not a cheap hard drop."""
    q = _norm(quote)
    if not q:
        return False
    paragraphs = re.split(r"\n\s*\n|\n\s*(?:[-*]|\d+[.)])\s+", official)
    return any(q in _norm(paragraph) and re.search(
        r"\b(however|unless|except|exception|provided that)\b", _norm(paragraph)) for paragraph in paragraphs)


def explicit_target_mismatch(p: ProfileData, scheme: SchemeDetail) -> str | None:
    """Return official evidence for unambiguous jurisdiction or student mismatches."""
    if p.state and scheme.state:
        states = {_norm(state) for state in re.split(r",|;|\n", scheme.state)}
        if not states & {"all", "all india", "india", _norm(p.state)}:
            return f"Scheme jurisdiction: {scheme.state}"
    if p.is_student is False:
        # A worker's children being students does not require the worker to enroll.
        for line in scheme.eligibility_md.splitlines():
            if re.search(r"\bapplicant must be a (?:(?:girl|boy) )?student\b", _norm(line)):
                if not qualified_restriction(line, scheme.eligibility_md):
                    return line.strip()
    return None


async def triage(p: ProfileData, scheme: SchemeDetail) -> bool:
    """True means keep. Unsupported drops and unavailable triage fail open."""
    evidence = institutional_target(scheme) or explicit_target_mismatch(p, scheme)
    if evidence:
        log.info("triage dropped %s: official target restriction %r", scheme.slug, evidence)
        return False
    if occupational_target_mismatch(p, scheme):
        log.info("triage dropped %s: farmer-only target without a stated farming role", scheme.slug)
        return False
    if educational_target_mismatch(p, scheme):
        log.info("triage dropped %s: technical-course target excludes a general degree", scheme.slug)
        return False
    official = f"{target_text(scheme)}\n{scheme.eligibility_md}\n{scheme.exclusions_md}"
    try:
        async def screen():
            return await llm.generate_json(
                f"Official scheme text:\n{official}\n\nCitizen profile: {profile_text(p)}",
                _Triage, system=TRIAGE_SYSTEM, model="lite",  # quick screen, judge does the real work
            )

        result = _Triage.model_validate(await llm.cached("matcher.triage", [
            p.model_dump(exclude_none=True), scheme.model_dump(mode="json"), TRIAGE_SYSTEM,
        ], screen))
        # A drop needs a real source span, not a model's paraphrase.
        if (result.drop and result.reason and _norm(result.quote) and _norm(result.quote) in _norm(official)
                and not qualified_restriction(result.quote, official)
                and all(met is False for met in numeric_checks(p, result.reason, result.quote).values())):
            log.info("triage dropped %s: %s", scheme.slug, result.reason)
            return False
    except Exception as e:
        log.warning("triage unavailable for %s: %s", scheme.slug, e)
    return True


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9ऀ-෿]+", " ", unescape(s).lower()).strip()


def quote_found(quote: str, source: str) -> bool:
    """Require a contiguous source span after markup/punctuation normalization."""
    q, src = _norm(quote), _norm(source)
    return bool(q) and f" {q} " in f" {src} "


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


# scheme titles spell categories out, "sc" alone finds the wrong things
CASTE_NAMES = {"sc": "scheduled caste", "st": "scheduled tribe", "obc": "other backward class",
               "pvtg": "particularly vulnerable tribal group", "dnt": "denotified tribe"}


def keywords_for(p: ProfileData, extra: str | None) -> list[str]:
    kws = [extra] if extra else []
    if p.is_student:
        # Specific queries precede generic pages full of unrelated courses.
        caste = CASTE_NAMES.get(p.caste or "")
        if caste:
            kws.extend([f"post matric scholarship {caste}", f"scholarship {caste}"])
            # Official titles mix full category names and acronyms. Keep both,
            # always with the education intent rather than searching "SC" alone.
            kws.append(f"scholarship {p.caste}")
        if re.search(r"class\s*(11|12)\b", f"{p.course or ''} {p.education_level or ''}", re.I):
            kws.append("school education scholarship")
        if p.state:
            kws.extend([f"{p.state} post matric scholarship", f"{p.state} scholarship"])
        kws.append("scholarship")
    if p.occupation:
        kws.append(p.occupation)
    if p.land_acres:
        kws.append("farmer")
    occupation = _norm(p.occupation or "")
    if p.land_acres or re.search(r"farm|cultivat|agricultur", occupation):
        kws.extend(["kisan", "agriculture", "crop insurance"])
    if _norm(p.marital_status or "") in {"widow", "widowed"}:
        kws.extend(["widow pension", "single women pension"])
    if p.age is not None and p.age >= 60:
        kws.append("old age pension")
    if p.disability_percent:
        kws.extend(["disability", "skill development disabilities", "self employment disabled"])
    if re.search(r"unemploy|job seek", occupation):
        kws.extend(["employment", "skill development"])
    if p.is_pregnant or re.search(r"pregnan", occupation):
        kws.extend(["maternity", "pregnant women", "janani"])
    if re.search(r"street vendor|hawker", occupation):
        # Extra words broaden myScheme search and crowd out enterprise credit.
        kws.extend(["street vendor", "unorganised worker", "micro enterprise", "micro enterprise loan"])
    return list(dict.fromkeys(kws)) or [""]


def relevance(p: ProfileData, scheme: SchemeSummary) -> int:
    """Rank beneficiary fit before the bounded shortlist; never whitelist scheme slugs."""
    title = _norm(scheme.name)
    context = _norm(f"{scheme.brief or ''} {' '.join(scheme.tags)}")
    state = _norm(scheme.state or "")
    own_state = _norm(p.state or "")
    score = 0
    if own_state and state and state not in {"all", "all india"}:
        score += 12 if f" {own_state} " in f" {state} " else -60

    def topic(pattern, weight):
        nonlocal score
        if re.search(pattern, title):
            score += weight
        elif re.search(pattern, context):
            score += weight // 2

    category_patterns = {
        "sc": r"\bscheduled castes?\b|\bsc\b",
        "st": r"\bscheduled tribes?\b|\bst\b",
        "obc": r"\bother backward|\bobc\b|\bbackward class|\bpichda varg\b",
        "pvtg": r"particularly vulnerable tribal|\bpvtg\b",
        "dnt": r"denotified|de notified|\bdnt\b",
    }
    categories = {key for key, pattern in category_patterns.items() if re.search(pattern, title)}
    if p.caste and categories:
        score += 20 if p.caste in categories else -24
    if p.is_student:
        topic(r"scholarship|chhatravritti|chhaatravrtti", 16)
        education = _norm(f"{p.course or ''} {p.education_level or ''}")
        if re.search(r"\bug\b|undergrad|b sc|b a\b|b com|b tech|class 1[12]", education):
            topic(r"post matric|post metric|postmatric", 16)
            if re.search(r"pre matric|post graduate|post doctoral|fellowship", title):
                score -= 24
        if re.search(r"class 1[12]\b", education):
            topic(r"school education|higher secondary|senior secondary|class (xi|xii|11|12)\b", 16)
            if re.search(r"\bcollege|\bgraduate|doctoral|\bph d\b", title):
                score -= 20
    occupation = _norm(p.occupation or "")
    if p.land_acres or re.search(r"farm|cultivat|agricultur", occupation):
        topic(r"farmer|kisan|agricultur|crop", 24)
    if _norm(p.marital_status or "") in {"widow", "widowed"}:
        topic(r"widow|vidhva|ekal nari|single wom", 28)
    if p.age is not None and p.age >= 60:
        topic(r"old age|elderly|senior citizen|vrdhavastha|vridh", 24)
    if p.disability_percent:
        topic(r"disabil|disabled|divyang|differently abled", 28)
        if re.search(r"unemploy|job seek", occupation):
            topic(r"employment|skill|kaushal|vocational", 20)
    if p.is_pregnant or re.search(r"pregnan", occupation):
        topic(r"matern|pregnan|matru|janani|lactat", 32)
    if re.search(r"street vendor|hawker", occupation):
        topic(r"street vendor|hawker", 32)
        topic(r"unorgani[sz]ed|micro enterprise|self employment|business|entrepreneur", 16)
        topic(r"micro credit|micro enterprises?|\btrading\b", 24)
    if p.gender == "male" and re.search(r"\bwomen\b|\bgirl|\bmahila\b", title):
        score -= 24
    return score


async def candidates(p: ProfileData, keyword: str | None, limit: int) -> list[SchemeSummary]:
    from ..services import myscheme

    filters = profile_filters(p)
    seen: dict[str, SchemeSummary] = {}
    async def search(kw: str, search_filters: dict):
        try:
            return (await myscheme.search(kw, filters=search_filters, offset=0, size=max(24, limit))).items
        except Exception as e:
            log.warning("myscheme search failed for %r: %s", kw, e)
            return []

    # Official records sometimes omit age/student/category metadata. A relaxed
    # state-only pass recovers these; official eligibility is checked later.
    queries = [(kw, filters) for kw in keywords_for(p, keyword)]
    recall_filters = {"state": p.state} if p.state else {}
    queries.extend((kw, recall_filters) for kw in keywords_for(p, keyword) if kw)
    # central schemes (e.g. post matric for SC) carry no state tag, run the category queries unfiltered too
    caste = CASTE_NAMES.get(p.caste or "")
    if caste:
        queries.extend((kw, {}) for kw in keywords_for(p, keyword) if caste in kw)
    queries = list({(kw, tuple(sorted(f.items()))): (kw, f) for kw, f in queries}.values())
    pages = await asyncio.gather(*(search(kw, f) for kw, f in queries))
    # Interleave pages so one generic page cannot crowd out state/category hits.
    for i in range(max((len(page) for page in pages), default=0)):
        for page in pages:
            if i >= len(page):
                continue
            s = page[i]
            seen.setdefault(s.slug, s)
    # semantic pass over cached schemes catches ones keyword search misses
    try:
        query = " ".join(filter(None, [p.occupation, p.course, p.education_level,
                         CASTE_NAMES.get(p.caste or ""), p.state, *keywords_for(p, keyword)]))
        if query:
            semantic = await asyncio.wait_for(myscheme.semantic_search(query, k=max(16, limit * 2)), timeout=4)
            for s in semantic:
                if not p.state or not s.state or s.state == p.state or s.state == "All":
                    seen.setdefault(s.slug, s)
    except Exception as e:
        log.info("semantic search skipped: %s", e)
    return sorted(seen.values(), key=lambda s: -relevance(p, s))[: max(32, limit * 4)]


async def judge(p: ProfileData, scheme: SchemeDetail) -> MatchResult:
    evidence = institutional_target(scheme)
    if evidence:
        section, quote = evidence
        return MatchResult(
            scheme=SchemeSummary(**scheme.model_dump(include=set(SchemeSummary.model_fields))),
            verdict="not_eligible", confidence=1.0,
            reasons=[Reason(claim="This scheme funds institutions or construction, rather than individual applicants.",
                            met=False, citation=Citation(source_url=scheme.source_url, title=scheme.name,
                                                       quote=quote, section=section))],
        )
    result = await llm.cached("matcher.judge", [
        scheme.slug, p.model_dump(exclude_none=True), scheme.model_dump(mode="json"), JUDGE_SYSTEM,
        get_settings().gemini_judge_model,
    ], lambda: _judge(p, scheme))
    return MatchResult.model_validate(result)


async def _judge(p: ProfileData, scheme: SchemeDetail) -> MatchResult:
    sources = {"eligibility": scheme.eligibility_md, "exclusions": scheme.exclusions_md,
               "details": target_text(scheme)}
    official = "\n\n".join(f"{section.upper()}:\n{text}" for section, text in sources.items())
    prompt = (
        f"Scheme: {scheme.name} ({scheme.ministry or scheme.state or ''})\n\n{official}\n\n"
        f"DOCUMENTS:\n{scheme.documents_md[:1500]}\n\n"
        f"Citizen profile: {profile_text(p)}"
    )
    j = await llm.generate_json(prompt, _Judgement, system=JUDGE_SYSTEM,
                                model=get_settings().gemini_judge_model, thinking_level="LOW")
    if j.reasons and not any(quote_found(r.quote, sources.get(r.section, "")) for r in j.reasons):
        # One evidence correction, still under the caller's matching deadline.
        # Never relax verification to rescue a plausible but unsupported verdict.
        log.info("retrying judgement without any verified quotes for %s", scheme.slug)
        try:
            j = await llm.generate_json(
                prompt + "\nYour previous quotes failed exact-source verification. Regenerate the judgement. "
                "Copy each quote directly from ONE contiguous source passage, preferably a short applicable "
                "eligibility line. Do not join alternative list items or paraphrase their wording.",
                _Judgement, system=JUDGE_SYSTEM,
                model=get_settings().gemini_judge_model, thinking_level="LOW",
            )
        except Exception:
            log.warning("quote correction unavailable for %s", scheme.slug)

    reasons: list[Reason] = []
    dropped = 0
    for r in j.reasons:
        src = sources.get(r.section, "")
        if quote_found(r.quote, src):
            met = r.met
            if r.section == "exclusions":
                met = None if r.exclusion_applies is None else not r.exclusion_applies
            claim = r.claim
            if met is False:
                checks = numeric_checks(p, r.claim, r.quote)
                if checks:
                    # Exclusion text states the excluded condition, so invert it.
                    expected = True if r.section == "exclusions" else False
                    if not all(value is expected for value in checks.values()):
                        met = None
                        claim = "Confirm the quoted income/age requirement."
            reasons.append(Reason(
                claim=claim, met=met,
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


async def _load(s: SchemeSummary) -> SchemeDetail | None:
    from ..services import myscheme

    try:
        # judge on english text, explain later in user lang
        return await asyncio.wait_for(myscheme.get_scheme(s.slug, lang="en", index=False), timeout=20)
    except Exception as e:
        log.warning("loading %s failed: %s", s.slug, e)
        return None


async def _index(details: list[SchemeDetail]) -> None:
    from ..services import myscheme

    try:
        await myscheme.index_schemes(details)
    except Exception as e:
        # Text/citations remain authoritative if the optional index is unavailable.
        log.warning("candidate batch indexing skipped: %s", e)


async def _judge_one(p: ProfileData, detail: SchemeDetail, sem: asyncio.Semaphore) -> MatchResult | None:
    async with sem:
        try:
            if not detail.eligibility_md.strip():
                return None
            if not await triage(p, detail):
                return None
            return await judge(p, detail)
        except Exception as e:
            log.warning("judging %s failed: %s", detail.slug, e)
            return None


def _rank(p: ProfileData, cands: list[SchemeSummary], results: list[MatchResult]) -> list[MatchResult]:
    priority = {s.slug: relevance(p, s) for s in cands}
    positions = {s.slug: i for i, s in enumerate(cands)}
    return sorted(results, key=lambda r: (ORDER[r.verdict], -priority.get(r.scheme.slug, 0), -r.confidence,
                                          positions.get(r.scheme.slug, len(cands))))


async def _match_events(p: ProfileData, keyword: str | None, limit: int, *,
                        candidate_limit: int | None = None, max_seconds: float | None = None) -> AsyncIterator[dict]:
    """found -> result/checked -> done within the budget, preserving completed work."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + (MATCH_SECONDS if max_seconds is None else max_seconds)
    try:
        cands = await asyncio.wait_for(candidates(p, keyword, limit), timeout=max(0, deadline - loop.time()))
    except TimeoutError:
        log.warning("candidate discovery time budget reached")
        cands = []
    if candidate_limit is not None:
        cands = cands[:candidate_limit]
    total = len(cands)
    yield {"type": "found", "total": total}
    sem = asyncio.Semaphore(24)  # paid vertex quota, 4 was for the free tier
    loads = [asyncio.create_task(_load(s)) for s in cands]

    async def one(load):
        detail = await load
        return None if detail is None else await _judge_one(p, detail, sem)

    async def index():
        # one batched embedding call, off the critical path of judging
        await _index([d for d in await asyncio.gather(*loads) if d])

    indexing = asyncio.create_task(index())
    tasks = [asyncio.create_task(one(load)) for load in loads]
    results: list[MatchResult] = []
    try:
        checked = 0
        for future in asyncio.as_completed(tasks, timeout=max(0, deadline - loop.time())):
            try:
                result = await future
            except TimeoutError:
                log.warning("match time budget reached; returning %s completed judgements", len(results))
                break
            checked += 1
            if result is not None:
                results.append(result)
                yield {"type": "result", "result": result}
            yield {"type": "checked", "checked": checked, "total": total}
        yield {"type": "done", "results": _rank(p, cands, results)[:limit]}
    finally:
        for task in (*tasks, *loads, indexing):
            task.cancel()
        await asyncio.gather(*tasks, *loads, indexing, return_exceptions=True)


async def match(p: ProfileData, keyword: str | None = None, limit: int = 8, lang: str = "en") -> list[MatchResult]:
    async with aclosing(_match_events(p, keyword, limit)) as events:
        async for event in events:
            if event["type"] == "done":
                return event["results"]
    return []


async def first_matches(p: ProfileData, keyword: str | None = None, limit: int = 3) -> list[MatchResult]:
    """Talk's small first page; closing events cancels all unfinished matching work."""
    results = []
    async with aclosing(_match_events(p, keyword, limit, candidate_limit=12, max_seconds=TALK_MATCH_SECONDS)) as events:
        async for event in events:
            if event["type"] == "result" and event["result"].verdict in {"eligible", "likely"}:
                results.append(event["result"])
                if len(results) >= limit:
                    break
    return sorted(results, key=lambda r: (ORDER[r.verdict], -relevance(p, r.scheme), -r.confidence))


async def match_stream(p: ProfileData, keyword: str | None = None, limit: int = 8, lang: str = "en") -> AsyncIterator[dict]:
    """Yield progress, completion-order results, then the same ranked shortlist as match()."""
    async with aclosing(_match_events(p, keyword, limit)) as events:
        async for event in events:
            if event["type"] == "found":
                yield {"type": "progress", "message": f"found {event['total']} schemes", "checked": 0, "total": event["total"]}
            elif event["type"] == "checked":
                yield {"type": "progress", "message": f"checked {event['checked']}/{event['total']}",
                       "checked": event["checked"], "total": event["total"]}
            elif event["type"] == "result":
                yield {"type": "result", "result": event["result"].model_dump(mode="json")}
            else:
                yield {"type": "done", "results": [r.model_dump(mode="json") for r in event["results"]]}
