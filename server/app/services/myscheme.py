"""Live myScheme API plus a 24-hour, language-specific Postgres cache."""
import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from .. import db, models
from ..schemas import ApplicationMode, SchemeDetail, SchemeSummary, SearchOut
from . import llm
from .markdown import field_markdown

BASE = "https://www.myscheme.gov.in"
_client: httpx.AsyncClient | None = None
_limit = asyncio.Semaphore(4)
CASTES = {
    "general": "General", "obc": "Other Backward Class (OBC)",
    "sc": "Scheduled Caste (SC)", "st": "Scheduled Tribe (ST)",
    "pvtg": "Particularly Vulnerable Tribal Group (PVTG)",
    "dnt": "De-Notified, Nomadic, and Semi-Nomadic (DNT) communities",
}


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=15, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0", "Referer": BASE + "/search"})
    return _client


async def _get(path: str, **params) -> dict:
    for attempt in range(3):
        try:
            async with _limit:
                response = await client().get(BASE + "/api/apisetu/" + path, params=params)
            response.raise_for_status()
            payload = response.json()
            if str(payload.get("statusCode", 200)) == "404":
                raise LookupError("Scheme not found")
            if payload.get("status") not in (None, "Success", "success"):
                raise ValueError("myScheme returned an unsuccessful response")
            return payload.get("data") or {}
        except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            if isinstance(exc, httpx.HTTPStatusError):
                if exc.response.status_code == 404:
                    raise LookupError("Scheme not found") from exc
                if exc.response.status_code < 500:
                    raise
            if attempt == 2:
                raise
            await asyncio.sleep(0.5 * 2 ** attempt)
    raise RuntimeError("unreachable")


def translate_filters(filters: dict) -> list[dict]:
    # Verified against /search facets and its public search client (2026-10-30).
    # q is [{identifier, value}, ...]; repeated identifiers are OR, different ones AND.
    # State/gender/caste include "All"; residence includes "Both". Booleans use
    # "Yes"/"No": isStudent, isBpl, disability, minority. Age uses min/max,
    # age-general/sc/st/obc/pvtg (DNT uses general), both set to the exact age.
    result = []
    for key, identifier in (("state", "beneficiaryState"), ("gender", "gender"),
                            ("caste", "caste"), ("residence", "residence")):
        value = filters.get(key)
        if value is None:
            continue
        if key == "caste":
            value = CASTES.get(str(value).lower())
        elif key in ("gender", "residence"):
            value = str(value).title()
            if value not in ("Male", "Female", "Transgender", "Urban", "Rural"):
                continue
        if value:
            result.extend([{"identifier": identifier, "value": value},
                           {"identifier": identifier, "value": "Both" if key == "residence" else "All"}])
    age = filters.get("age")
    if isinstance(age, int) and not isinstance(age, bool) and 0 <= age <= 120:
        caste = filters.get("caste", "general")
        category = caste if caste in ("sc", "st", "obc", "pvtg") else "general"
        result.append({"identifier": f"age-{category}", "min": age, "max": age})
    for key, identifier in (("is_student", "isStudent"), ("is_bpl", "isBpl"),
                            ("disability", "disability"), ("is_minority", "minority")):
        if isinstance(filters.get(key), bool):
            result.append({"identifier": identifier, "value": "Yes" if filters[key] else "No"})
    return result


def _label(value):
    if isinstance(value, dict):
        return value.get("label") or value.get("value")
    if isinstance(value, list):
        return ", ".join(str(_label(item)) for item in value)
    return value


def _summary(fields: dict) -> SchemeSummary:
    return SchemeSummary(slug=fields["slug"], name=fields["schemeName"],
        ministry=_label(fields.get("nodalMinistryName") or fields.get("nodalDepartmentName")),
        state=_label(fields.get("beneficiaryState")), tags=fields.get("tags") or [],
        brief=fields.get("briefDescription"))


async def search(keyword: str, filters: dict, offset: int, size: int) -> SearchOut:
    if offset < 0 or not 1 <= size <= 100:
        raise ValueError("offset must be nonnegative and size must be 1–100")
    data = await _get("search/schemes", lang="en", q=json.dumps(translate_filters(filters)),
                      keyword=keyword, sort="", **{"from": offset, "size": size})
    hits = data.get("hits", {})
    return SearchOut(total=hits.get("page", {}).get("total", 0),
                     items=[_summary(hit.get("fields", hit)) for hit in hits.get("items", [])])


def parse_detail(slug: str, lang: str, data: dict, documents: dict, faqs: dict) -> SchemeDetail:
    localized = data.get(lang)
    if not localized:
        raise LookupError(f"Scheme is unavailable in language {lang}")
    basic = localized.get("basicDetails", {})
    content = localized.get("schemeContent", {})
    eligibility = localized.get("eligibilityCriteria", {})
    summary = _summary({**basic, "slug": slug, "briefDescription": content.get("briefDescription")})
    faq_rows = faqs.get(lang, {}).get("faqs", [])
    return SchemeDetail(**summary.model_dump(), id=data["_id"],
        details_md=field_markdown(content, "detailedDescription"),
        benefits_md=field_markdown(content, "benefits"),
        eligibility_md=field_markdown(eligibility, "eligibilityDescription"),
        exclusions_md=field_markdown(content, "exclusions"),
        documents_md=field_markdown(documents.get(lang, {}), "documents_required"),
        application=[ApplicationMode(mode=row.get("mode", ""),
            steps_md=field_markdown(row, "process"), url=row.get("url") or None)
            for row in localized.get("applicationProcess", [])],
        faqs=[{"question": row.get("question", ""), "answer": field_markdown(row, "answer")}
              for row in faq_rows], references=content.get("references") or [],
        source_url=BASE + "/schemes/" + slug)


async def get_scheme(slug: str, lang: str = "en") -> SchemeDetail:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", slug) or lang not in ("en", "hi"):
        raise ValueError("Invalid slug or unsupported scheme language (use en or hi)")
    now = datetime.now(timezone.utc)
    async with db.SessionLocal() as session:
        cached = await session.get(models.Scheme, (slug, lang))
        if cached and cached.fetched_at.replace(tzinfo=timezone.utc) > now - timedelta(hours=24):
            return SchemeDetail.model_validate(cached.data["detail"])
    data = await _get("schemes", slug=slug, lang=lang)
    if not data.get("_id"):
        raise LookupError("Scheme not found")
    documents, faqs = await asyncio.gather(
        _get(f"schemes/{quote(data['_id'], safe='')}/documents", lang=lang),
        _get(f"schemes/{quote(data['_id'], safe='')}/faqs", lang=lang))
    detail = parse_detail(slug, lang, data, documents, faqs)
    embedding = (await llm.embed([f"{detail.name}\n{detail.brief or ''}\n{detail.eligibility_md}"]))[0]
    values = dict(slug=slug, lang=lang, scheme_id=detail.id, name=detail.name,
                  data={"raw": data, "documents": documents, "faqs": faqs,
                        "detail": detail.model_dump()}, embedding=embedding, fetched_at=now)
    async with db.SessionLocal() as session:
        await session.execute(insert(models.Scheme).values(**values).on_conflict_do_update(
            index_elements=[models.Scheme.slug, models.Scheme.lang], set_=values))
        await session.commit()
    return detail


async def semantic_search(query: str, k: int) -> list[SchemeSummary]:
    if not 1 <= k <= 100:
        raise ValueError("k must be 1–100")
    vector = await llm.embed_query(query)
    distance = models.Scheme.embedding.cosine_distance(vector)
    async with db.SessionLocal() as session:
        rows = (await session.scalars(select(models.Scheme).where(
            models.Scheme.embedding.is_not(None)).order_by(distance).limit(k * 2))).all()
    results, seen = [], set()
    for row in rows:
        if row.slug not in seen:
            results.append(SchemeSummary.model_validate(row.data["detail"]))
            seen.add(row.slug)
        if len(results) == k:
            break
    return results
