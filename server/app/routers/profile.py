from fastapi import APIRouter, HTTPException
from cryptography.fernet import InvalidToken

from .. import db, models
from ..schemas import ProfileIn, ProfileOut
from ..services import crypto

router = APIRouter(tags=["profile"])


def _out(profile: models.Profile) -> ProfileOut:
    try:
        sensitive = crypto.decrypt_json(profile.sensitive)
    except InvalidToken as exc:
        raise HTTPException(503, "Profile could not be decrypted with the configured PROFILE_SECRET") from exc
    return ProfileOut(id=profile.id, data=profile.data, sensitive=sensitive, language=profile.language)


@router.post("/profile", response_model=ProfileOut, status_code=201)
async def create_profile(body: ProfileIn):
    async with db.SessionLocal() as session:
        profile = models.Profile(data=body.data.model_dump(exclude_none=True),
            sensitive=crypto.encrypt_json(body.sensitive.model_dump(exclude_none=True)),
            language=body.language)
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
async def update_profile(profile_id: str, body: ProfileIn):
    async with db.SessionLocal() as session:
        profile = await session.get(models.Profile, profile_id)
        if profile is None:
            raise HTTPException(404, "Profile not found")
        profile.data = body.data.model_dump(exclude_none=True)
        profile.sensitive = crypto.encrypt_json(body.sensitive.model_dump(exclude_none=True))
        profile.language = body.language
        await session.commit()
        return _out(profile)
