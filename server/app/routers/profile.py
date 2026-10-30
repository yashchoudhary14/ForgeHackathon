from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["profile"])


@router.get("/profile/_ping")
async def ping():
    raise HTTPException(501, "not implemented yet")
