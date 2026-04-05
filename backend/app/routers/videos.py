from fastapi import APIRouter, Depends
from app.auth import get_current_user

router = APIRouter(tags=["videos"])


@router.get("/videos")
async def list_videos(user_id: str = Depends(get_current_user)):
    return []
