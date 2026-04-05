from fastapi import APIRouter, Depends
from app.auth import get_current_user

# Routes are mounted with /api/v1 prefix in main.py
router = APIRouter(tags=["videos"])


@router.get("/videos")
async def list_videos(user_id: str = Depends(get_current_user)):
    return []
