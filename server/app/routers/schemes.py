from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Query

from ..schemas import SchemeDetail, SearchOut
from ..services import government, myscheme

router = APIRouter(tags=["schemes"])


@router.get("/schemes/search", response_model=SearchOut)
async def search_schemes(
    keyword: str = "", offset: int = Query(0, ge=0), size: int = Query(10, ge=1, le=100),
    state: str | None = None, gender: Literal["male", "female", "transgender"] | None = None,
    caste: Literal["general", "obc", "sc", "st", "pvtg", "dnt"] | None = None,
    residence: Literal["urban", "rural"] | None = None, age: int | None = Query(None, ge=0, le=120),
    is_student: bool | None = None, is_bpl: bool | None = None,
    disability: bool | None = None, is_minority: bool | None = None,
):
    filters = dict(state=state, gender=gender, caste=caste, residence=residence, age=age,
                   is_student=is_student, is_bpl=is_bpl, disability=disability, is_minority=is_minority)
    try:
        return await myscheme.search(keyword, filters, offset, size)
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "myScheme search is temporarily unavailable") from exc


# POST /schemes/match can be registered independently of this GET detail route.
@router.get("/schemes/{slug}/application-url")
async def scheme_application_url(slug: str):
    try:
        detail = await myscheme.get_scheme(slug, lang="en", index=False)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, "myScheme detail is temporarily unavailable") from exc
    return {"portal_url": government.scheme_application_url(detail)}


@router.get("/schemes/{slug}", response_model=SchemeDetail)
async def scheme_detail(slug: str, lang: Literal["en", "hi"] = "en"):
    try:
        return await myscheme.get_scheme(slug, lang)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, "myScheme detail is temporarily unavailable") from exc
    except RuntimeError as exc:
        raise HTTPException(503, "Scheme embeddings require a configured Gemini service") from exc
