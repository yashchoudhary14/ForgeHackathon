"""Live myScheme public API plus a database cache of retrieved official details."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from ..db import SessionLocal
from ..models import Scheme
from ..schemas import ApplicationMode, SchemeDetail, SchemeSummary, SearchOut
from . import llm

BASE = "https://www.myscheme.gov.in/api/apisetu"
CASTES = {
    "general": "General", "obc": "Other Backward Class (OBC)",
    "sc": "Scheduled Caste (SC)", "st": "Scheduled Tribe (ST)",
    "pvtg": "Particularly Vulnerable Tribal Group (PVTG)",
    "dnt": "De-notified, Nomadic and Semi-Nomadic Tribes (DNT)",
}


def _filters(profile: dict) -> list[dict]:
    """Use the same identifiers and OR values as the official search client."""
    query = []
    fields = {"state": "beneficiaryState", "gender": "gender", "caste": "caste", "residence": "residence"}
    for field, identifier in fields.items():
        value = profile.get(field)
        if value is None:
            continue
        if field == "caste":
            value = CASTES.get(value, value)
        elif field != "state":
            value = str(value).title()
        query.append({"identifier": identifier, "value": value})
        # Also include schemes open to everyone, not just those targeting this group.
        common = "Both" if field == "residence" else "All"
        if value != common:
            query.append({"identifier": identifier, "value": common})
    for field, identifier in {
        "is_student": "isStudent", "is_bpl": "isBpl", "disability": "disability", "is_minority": "minority",
    }.items():
        if profile.get(field) is not None:
            query.append({"identifier": identifier, "value": "Yes" if profile[field] else "No"})
    if profile.get("age") is not None:
        caste = profile.get("caste")
        category = caste if caste in {"sc", "st", "obc", "pvtg"} else "general"
        query.append({"identifier": f"age-{category}", "min": profile["age"], "max": profile["age"]})
    return query


async def _get(client: httpx.AsyncClient, path: str, **params) -> dict | None:
    response = await client.get(f"{BASE}/{path}", params=params)
    response.raise_for_status()
    payload = response.json()
    if payload.get("statusCode", 200) != 200 or payload.get("error") not in (None, "null", "{}", {}):
        raise ValueError("myScheme could not complete that request")
    return payload.get("data")


def _summary(item: dict) -> SchemeSummary:
    fields = item["fields"]
    states = fields.get("beneficiaryState") or []
    return SchemeSummary(
        slug=fields["slug"], name=fields["schemeName"], ministry=fields.get("nodalMinistryName"),
        state=next((state for state in states if state != "All"), None),
        tags=fields.get("tags") or [], brief=fields.get("briefDescription"),
    )


async def search(keyword: str, filters: dict, offset: int, size: int) -> SearchOut:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        data = await _get(
            client, "search/schemes", lang="en", q=json.dumps(_filters(filters)),
            keyword=keyword, **{"from": max(0, offset), "size": max(1, min(size, 20))},
        )
    if data is None:
        raise ValueError("myScheme returned no search payload")
    seen = {}
    for item in data["hits"]["items"]:
        scheme = _summary(item)
        seen.setdefault(scheme.slug, scheme)
    return SearchOut(total=data["summary"]["total"], items=list(seen.values()))


def _text(value) -> str:
    """Read the official rich-text tree when a pre-rendered Markdown field is absent."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_text(item) for item in value).strip()
    if isinstance(value, dict):
        if "text" in value:
            return value["text"]
        children = value.get("children", [])
        if value.get("type") in {"paragraph", "list_item", "link", "block_quote"}:
            return "".join(_text(child) for child in children)
        return _text(children)
    return ""


def _section(data: dict, markdown: str, rich: str) -> str:
    return data.get(markdown) or _text(data.get(rich))


def _detail(data: dict, documents: dict | None, faqs: dict | None, lang: str) -> SchemeDetail:
    localized = data.get(lang)
    if not localized:
        raise LookupError("This scheme is not available in the requested language")
    basic = localized["basicDetails"]
    content = localized.get("schemeContent") or {}
    eligibility = localized.get("eligibilityCriteria") or {}
    docs = (documents or {}).get(lang) or {}
    faq = (faqs or {}).get(lang) or {}
    return SchemeDetail(
        id=data["_id"], slug=data["slug"], name=basic["schemeName"],
        ministry=(basic.get("nodalMinistryName") or {}).get("label"),
        state=(basic.get("state") or {}).get("label"), tags=basic.get("tags") or [],
        brief=content.get("briefDescription"),
        details_md=_section(content, "detailedDescription_md", "detailedDescription"),
        benefits_md=_section(content, "benefits_md", "benefits"),
        eligibility_md=_section(eligibility, "eligibilityDescription_md", "eligibilityDescription"),
        exclusions_md=_section(content, "exclusions_md", "exclusions"),
        documents_md=_section(docs, "documentsRequired_md", "documents_required"),
        application=[ApplicationMode(mode=item["mode"], steps_md=_section(item, "process_md", "process"))
                     for item in localized.get("applicationProcess", [])],
        references=content.get("references") or [], faqs=faq.get("faqs") or [],
        source_url=f"https://www.myscheme.gov.in/schemes/{data['slug']}",
    )


async def get_scheme(slug: str, lang: str = "en") -> SchemeDetail:
    async with SessionLocal() as db:
        cached = await db.get(Scheme, (slug, lang))
        if cached and cached.fetched_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc) - timedelta(hours=6):
            return SchemeDetail.model_validate(cached.data)
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        data = await _get(client, "schemes", slug=slug, lang=lang)
        if data is None:
            raise LookupError("Scheme not found on myScheme")
        documents, faqs = await asyncio.gather(
            _get(client, f"schemes/{data['_id']}/documents", lang=lang),
            _get(client, f"schemes/{data['_id']}/faqs", lang=lang),
        )
    result = _detail(data, documents, faqs, lang)
    async with SessionLocal() as db:
        cached = await db.get(Scheme, (slug, lang))
        if cached is None:
            cached = Scheme(slug=slug, lang=lang)
            db.add(cached)
        cached.name, cached.scheme_id = result.name, result.id
        cached.data, cached.fetched_at = result.model_dump(), datetime.now(timezone.utc)
        await db.commit()
    return result


async def semantic_search(query: str, k: int) -> list[SchemeSummary]:
    async with SessionLocal() as db:
        if not await db.scalar(select(Scheme.slug).where(Scheme.embedding.is_not(None)).limit(1)):
            return []
        vector = await llm.embed_query(query)
        rows = (await db.execute(
            select(Scheme).where(Scheme.embedding.is_not(None), Scheme.lang == "en")
            .order_by(Scheme.embedding.cosine_distance(vector)).limit(max(1, min(k, 20)))
        )).scalars()
        return [SchemeSummary.model_validate(row.data) for row in rows]
