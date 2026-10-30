from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["schemes"])


@router.get("/schemes/_ping")
async def ping():
    raise HTTPException(501, "not implemented yet")
