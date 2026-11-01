from fastapi import APIRouter, HTTPException
from cryptography.fernet import InvalidToken

from .. import db, models
from ..schemas import ProfileIn, ProfileOut, ProfileUpdate
from ..services import crypto

router = APIRouter(tags=["profile"])


def _out(profile: models.Profile) -> ProfileOut:
    try:
        sensitive = crypto.decrypt_json(profile.sensitive)
    except InvalidToken as exc:
        raise HTTPException(503, "Profile could not be decrypted with the configured PROFILE_SECRET") from exc
    return ProfileOut(id=profile.id, data=profile.data, sensitive=sensitive, language=profile.language, mode=profile.mode)


@router.post("/profile", response_model=ProfileOut, status_code=201)
async def create_profile(body: ProfileIn):
    async with db.SessionLocal() as session:
        profile = models.Profile(data=body.data.model_dump(exclude_none=True),
            sensitive=crypto.encrypt_json(body.sensitive.model_dump(exclude_none=True)),
            language=body.language, mode=body.mode)
        session.add(profile)
        await session.commit()
        return _out(profile)


@router.get("/profile/{profile_id}", response_model=ProfileOut)
async def get_profile(profile_id: str):
    async with db.SessionLocal() as session:
        profile = await session.get(models.Profile, profile_id)
        if profile is None:
            raise HTTPException(404, "Profile not found")
        return _out(profile)


@router.put("/profile/{profile_id}", response_model=ProfileOut)
async def update_profile(profile_id: str, body: ProfileUpdate):
    async with db.SessionLocal() as session:
        profile = await session.get(models.Profile, profile_id)
        if profile is None:
            raise HTTPException(404, "Profile not found")
        if body.data is not None:
            profile.data = {**(profile.data or {}), **body.data.model_dump(exclude_none=True)}
        if body.sensitive is not None:
            profile.sensitive = crypto.encrypt_json({
                **crypto.decrypt_json(profile.sensitive), **body.sensitive.model_dump(exclude_none=True),
            })
        if body.language is not None:
            profile.language = body.language
            from ..agents.executor import manager
            manager.set_language(profile.id, body.language)
        if body.mode is not None:
            profile.mode = body.mode
        await session.commit()
        return _out(profile)
