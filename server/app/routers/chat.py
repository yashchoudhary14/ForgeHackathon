from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["chat"])


@router.get("/chat/_ping")
async def ping():
    raise HTTPException(501, "not implemented yet")
