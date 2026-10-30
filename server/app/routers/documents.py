from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["documents"])


@router.get("/documents/_ping")
async def ping():
    raise HTTPException(501, "not implemented yet")
