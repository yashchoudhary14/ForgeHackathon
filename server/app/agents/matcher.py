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
    if not (p.is_student or occupation == "student"):
        return False
    if (p.land_acres or 0) > 0 or re.search(r"farm|agricultur|cultivat|fish|livestock|animal husbandry", occupation):
        return False
    text = _norm(scheme.eligibility_md)
    if re.search(r"\b(children|child|wards|sons|daughters|dependents|students|families|family)\b", text):
        return False
    lines = [_norm(line) for line in scheme.eligibility_md.splitlines() if _norm(line)]
    lines = [line for line in lines if line not in ("eligibility", "eligibility criteria")]
    return bool(lines) and all(re.search(r"\b(farmers?|cultivators?|tenant farmers?|share croppers?|sharecroppers?|oral lessees)\b", line) for line in lines)


async def triage(p: ProfileData, scheme: SchemeDetail) -> bool:
    """True means keep. Unsupported drops and unavailable triage fail open."""
    if occupational_target_mismatch(p, scheme):
        log.info("triage dropped %s: farmer-only target without a stated farming role", scheme.slug)
        return False
    official = f"{target_text(scheme)}\n{scheme.eligibility_md}\n{scheme.exclusions_md}"
    try:
        async def screen():
            return await llm.generate_json(
                f"Official scheme text:\n{official}\n\nCitizen profile: {p.model_dump_json(exclude_none=True)}",
                _Triage, system=TRIAGE_SYSTEM, model="lite",  # quick screen, judge does the real work
            )

        result = _Triage.model_validate(await llm.cached("matcher.triage", [
            p.model_dump(exclude_none=True), scheme.model_dump(mode="json"), TRIAGE_SYSTEM,
        ], screen))
        # A drop needs a real source span, not a model's paraphrase.
        if result.drop and result.reason and _norm(result.quote) and _norm(result.quote) in _norm(official):
            log.info("triage dropped %s: %s", scheme.slug, result.reason)
            return False
    except Exception as e:
        log.warning("triage unavailable for %s: %s", scheme.slug, e)
    return True


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
        kws.extend(["street vendor", "unorganised worker", "micro enterprise loan"])
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
        query = f"{p.occupation or ''} {p.education_level or ''} {p.state or ''} {keyword or ''}".strip()
        if query:
            for s in await myscheme.semantic_search(query, k=limit):
                if not p.state or not s.state or s.state == p.state or s.state == "All":
                    seen.setdefault(s.slug, s)
    except Exception as e:
        log.info("semantic search skipped: %s", e)
    return sorted(seen.values(), key=lambda s: -relevance(p, s))[: max(32, limit * 4)]


async def judge(p: ProfileData, scheme: SchemeDetail) -> MatchResult:
    result = await llm.cached("matcher.judge", [
        scheme.slug, p.model_dump(exclude_none=True), scheme.model_dump(mode="json"), JUDGE_SYSTEM,
    ], lambda: _judge(p, scheme))
    return MatchResult.model_validate(result)


async def _judge(p: ProfileData, scheme: SchemeDetail) -> MatchResult:
    sources = {"eligibility": scheme.eligibility_md, "exclusions": scheme.exclusions_md,
               "details": target_text(scheme)}
    official = "\n\n".join(f"{section.upper()}:\n{text}" for section, text in sources.items())
    prompt = (
        f"Scheme: {scheme.name} ({scheme.ministry or scheme.state or ''})\n\n{official}\n\n"
        f"DOCUMENTS:\n{scheme.documents_md[:1500]}\n\n"
        f"Citizen profile: {p.model_dump_json(exclude_none=True)}"
    )
    j = await llm.generate_json(prompt, _Judgement, system=JUDGE_SYSTEM, model="strong")

    reasons: list[Reason] = []
    dropped = 0
    for r in j.reasons:
        src = sources.get(r.section, "")
        if quote_found(r.quote, src):
            met = r.met
            if r.section == "exclusions":
                met = None if r.exclusion_applies is None else not r.exclusion_applies
            reasons.append(Reason(
                claim=r.claim, met=met,
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
    sem = asyncio.Semaphore(24)  # paid vertex quota, 4 was for the free tier

    async def one(s: SchemeSummary) -> MatchResult | None:
        async with sem:
            try:
                detail = await myscheme.get_scheme(s.slug, lang="en")  # judge on english text, explain later in user lang
                if not detail.eligibility_md.strip():
                    return None
                if not await triage(p, detail):
                    return None
                return await judge(p, detail)
            except Exception as e:
                log.warning("judging %s failed: %s", s.slug, e)
                return None

    results = [r for r in await asyncio.gather(*(one(s) for s in cands)) if r]
    priority = {s.slug: relevance(p, s) for s in cands}
    results.sort(key=lambda r: (ORDER[r.verdict], -priority.get(r.scheme.slug, 0), -r.confidence))
    return results[:limit]
