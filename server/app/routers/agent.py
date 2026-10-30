from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["agent"])


@router.get("/agent/_ping")
async def ping():
    raise HTTPException(501, "not implemented yet")
