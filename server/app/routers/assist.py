"""ai endpoints: conversational intake, eligibility matching, explainer"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents import explainer, intake, matcher
from ..db import get_db
from ..models import Profile
from ..schemas import (
    ExplainIn, ExplainOut, MatchIn, MatchResult, ProfileData, ProfileExtractIn, ProfileExtractOut,
    ProfileOut, SensitiveData,
)
from ..services import crypto

log = logging.getLogger(__name__)
router = APIRouter(tags=["assist"])


async def load_profile(db: AsyncSession, pid: str) -> Profile:
    p = await db.get(Profile, pid)
    if not p:
        raise HTTPException(404, "profile not found")
    return p


@router.post("/profile/extract", response_model=ProfileExtractOut)
async def extract_profile(body: ProfileExtractIn, db: AsyncSession = Depends(get_db)):
    if not body.text.strip():
        raise HTTPException(422, "say or type something about yourself first")
    if body.profile_id:
        row = await load_profile(db, body.profile_id)
        data, sens = ProfileData(**row.data), SensitiveData(**crypto.decrypt_json(row.sensitive))
    else:
        row, data, sens = Profile(), ProfileData(), SensitiveData()
        db.add(row)

    try:
        data, sens = await intake.extract(body.text, data, sens)
        question = await intake.follow_up(data, body.language)
    except Exception as e:
        log.exception("intake failed")
        raise HTTPException(502, f"AI service error, please retry ({type(e).__name__})")

    row.data = data.model_dump(exclude_none=True)
    row.sensitive = crypto.encrypt_json(sens.model_dump(exclude_none=True))
    row.language = body.language
    await db.commit()
    return ProfileExtractOut(
        profile=ProfileOut(id=row.id, data=data, sensitive=sens, language=body.language),
        missing_fields=intake.missing(data),
        follow_up_question=question,
    )


@router.post("/schemes/match", response_model=list[MatchResult])
async def match_schemes(body: MatchIn, db: AsyncSession = Depends(get_db)):
    row = await load_profile(db, body.profile_id)
    try:
        return await matcher.match(ProfileData(**row.data), body.keyword, body.limit)
    except Exception as e:
        log.exception("match failed")
        raise HTTPException(502, f"couldn't reach scheme data right now ({type(e).__name__})")


@router.post("/explain", response_model=ExplainOut)
async def explain(body: ExplainIn, db: AsyncSession = Depends(get_db)):
    src = body.source
    if (src.type == "scheme" and not src.slug) or (src.type == "url" and not src.url) or (
        src.type == "document" and not src.document_id
    ):
        raise HTTPException(422, f"source.{ {'scheme': 'slug', 'url': 'url', 'document': 'document_id'}[src.type] } is required")
    profile = None
    if body.profile_id:
        profile = ProfileData(**(await load_profile(db, body.profile_id)).data)
    try:
        return await explainer.explain(body, profile)
    except LookupError:
        raise HTTPException(404, "document not found")
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        log.exception("explain failed")
        raise HTTPException(502, f"AI service error, please retry ({type(e).__name__})")
