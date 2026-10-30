from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["voice"])


@router.get("/voice/_ping")
async def ping():
    raise HTTPException(501, "not implemented yet")
